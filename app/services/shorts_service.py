"""
HypeClip Shorts Service — manages the clip-to-short generation pipeline.

Each generation session gets a unique UUID, an output directory, and a
progress.json file for real-time status tracking. All processing runs in
background threads so the API returns immediately.

No DB, no Hypesync imports.
"""

import json
import logging
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Optional

import requests

from app.services.twitch_service import get_clip_download_url
from pipeline.fast_pipeline import detect_webcam_region_only

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # HypeClip/
OUTPUT_BASE = _PROJECT_ROOT / "output"
_CACHE_DIR = OUTPUT_BASE / "_cache"

# Font shipped with the project (fallback to a system font)
_HEAVITAS_FONT = _PROJECT_ROOT / "pipeline" / "fonts" / "Heavitas.ttf"
_FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font_path() -> str:
    if _HEAVITAS_FONT.exists():
        return str(_HEAVITAS_FONT)
    if os.path.exists(_FALLBACK_FONT):
        return _FALLBACK_FONT
    # Last resort — let FFmpeg try its built-in default
    return "DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------------------
# FFmpeg command builder
# ---------------------------------------------------------------------------

def _build_ffmpeg_command(
    input_path: str,
    output_path: str,
    webcam_region: Optional[tuple] = None,
    webcam_position: Optional[dict] = None,
    streamer_name: Optional[str] = None,
) -> list:
    """Build an FFmpeg command that produces a 1080×1920 short.

    * Always crops / scales to 9:16 (1080×1920).
    * If *webcam_region* is provided the webcam strip is overlaid.
    * If *streamer_name* is provided a drawtext filter is appended.
    * Uses CPU encoding (libx264).
    """
    cmd = ["ffmpeg", "-y", "-i", input_path]

    filters: list[str] = []

    # 1. Scale to 1920 height, then centre-crop to 1080 width
    main_filter = "[0:v]scale=-2:1920,crop=1080:1920:(in_w-1080)/2:0[main]"
    filters.append(main_filter)

    video_label = "main"

    # 2. Webcam overlay (if region was detected)
    if webcam_region:
        x, y, w, h = webcam_region
        filters.append(f"[0:v]crop={w}:{h}:{x}:{y}[webcam_raw]")
        filters.append("[webcam_raw]scale=-2:480[webcam]")

        # Position: use user-provided or default center-top
        if webcam_position:
            overlay_x = f"({webcam_position['x_pct']}*W/100)"
            overlay_y = f"({webcam_position['y_pct']}*H/100)"
        else:
            overlay_x = "(W-w)/2"
            overlay_y = "0"

        filters.append(f"[main][webcam]overlay={overlay_x}:{overlay_y}[video_with_webcam]")
        video_label = "video_with_webcam"

    # 3. Streamer name text overlay
    if streamer_name:
        font = _font_path()
        # Escape single quotes in the name
        safe_name = streamer_name.upper().replace("'", "'\\''")
        text_filter = (
            f"[{video_label}]drawtext="
            f"text='{safe_name}':"
            f"fontfile={font}:"
            f"fontsize=60:"
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"x=(w-text_w)/2:"
            f"y=h-100"
            f"[final]"
        )
        filters.append(text_filter)
        video_label = "final"

    filter_complex = ";".join(filters)
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", f"[{video_label}]", "-map", "0:a?"])

    # CPU encoding with libx264
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
    ])

    cmd.append(output_path)
    return cmd


# ---------------------------------------------------------------------------
# ShortsService
# ---------------------------------------------------------------------------

class ShortsService:
    """Manages clip-to-short generation sessions."""

    def __init__(self):
        self._lock = threading.Lock()
        # Ensure the top-level output directory exists
        OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_shorts(self, clips: list[dict], options: dict) -> str:
        """Start a background processing job and return the session_id.

        Parameters
        ----------
        clips : list[dict]
            Each dict must contain: slug, title, broadcaster_name, thumbnail_url.
        options : dict
            ``webcam`` (bool) – detect & overlay webcam region.
            ``streamer_name`` (bool) – add streamer name text overlay.
        """
        session_id = uuid.uuid4().hex
        session_dir = OUTPUT_BASE / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Normalise options
        opts = {
            "webcam": bool(options.get("webcam", False)),
            "streamer_name": bool(options.get("streamer_name", False)),
        }

        # Initialise progress
        progress_data = {
            "status": "processing",
            "clips": [
                {"slug": c["slug"], "status": "pending", "progress": 0}
                for c in clips
            ],
            "total": len(clips),
            "completed": 0,
        }
        self._write_progress(session_id, progress_data)

        # Fire off background thread
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(session_id, clips, opts),
            daemon=True,
        )
        thread.start()

        return session_id

    def get_progress(self, session_id: str) -> dict:
        """Read and return progress.json for *session_id*."""
        progress_file = OUTPUT_BASE / session_id / "progress.json"
        if not progress_file.exists():
            return {
                "status": "unknown",
                "clips": [],
                "total": 0,
                "completed": 0,
            }
        return self._read_progress(session_id)

    def get_results(self, session_id: str) -> list[dict]:
        """Return a list of generated shorts with download URLs."""
        session_dir = OUTPUT_BASE / session_id
        if not session_dir.exists():
            return []

        # Collect title mapping from progress.json
        progress = self._read_progress(session_id)
        slug_to_title: dict[str, str] = {}
        # We don't store titles in progress clips; we'll fall back to slug.
        # But let's read the original clip metadata if available.
        meta_file = session_dir / "clips_meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r") as f:
                    clips_meta = json.load(f)
                slug_to_title = {c["slug"]: c["title"] for c in clips_meta}
            except (json.JSONDecodeError, KeyError):
                pass

        results: list[dict] = []
        for fname in sorted(session_dir.iterdir()):
            if fname.is_file() and fname.name.endswith("_short.mp4"):
                slug = fname.name.replace("_short.mp4", "")
                results.append({
                    "filename": fname.name,
                    "title": slug_to_title.get(slug, slug),
                    "download_url": f"/download/{session_id}/{fname.name}",
                })

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_pipeline(self, session_id: str, clips: list[dict], options: dict):
        """Process all clips sequentially in the background thread."""
        session_dir = OUTPUT_BASE / session_id

        # Persist clip metadata so get_results can map slug → title
        meta_file = session_dir / "clips_meta.json"
        with open(meta_file, "w") as f:
            json.dump(clips, f)

        progress = self._read_progress(session_id)

        for idx, clip in enumerate(clips):
            slug = clip["slug"]

            # Mark as processing
            self._update_clip_status(session_id, slug, "processing", 10)

            try:
                self._process_single_clip(session_id, clip, options)
                self._update_clip_status(session_id, slug, "done", 100)
            except Exception:
                log.exception("Failed to process clip %s", slug)
                self._update_clip_status(session_id, slug, "failed", 0)

        # Final status
        progress = self._read_progress(session_id)
        all_done = all(c["status"] in ("done", "failed") for c in progress["clips"])
        any_failed = any(c["status"] == "failed" for c in progress["clips"])

        if all_done:
            progress["status"] = "completed" if not any_failed else "failed"
            progress["completed"] = sum(
                1 for c in progress["clips"] if c["status"] == "done"
            )
            self._write_progress(session_id, progress)

    def _process_single_clip(self, session_id: str, clip: dict, options: dict):
        """Download → process → save a single clip.

        Steps:
        1. Obtain download URL via TwitchService
        2. Download the clip (reuse cache if available)
        3. (Optional) Detect webcam region or use user-provided region
        4. Build & run FFmpeg command
        """
        session_dir = OUTPUT_BASE / session_id
        slug = clip["slug"]

        # --- 1. Get download URL ------------------------------------------
        self._update_clip_status(session_id, slug, "processing", 15)
        download_url = get_clip_download_url(slug)
        if not download_url:
            raise RuntimeError(f"Could not obtain download URL for clip {slug}")

        # --- 2. Download clip (reuse cache if available) -------------------
        self._update_clip_status(session_id, slug, "processing", 25)

        # Ensure cache directory exists
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        cached_clip = _CACHE_DIR / f"{slug}.mp4"
        if cached_clip.exists():
            log.info("Reusing cached clip for %s", slug)
            clip_path = session_dir / f"{slug}.mp4"
            import shutil
            shutil.copy2(str(cached_clip), str(clip_path))
        else:
            clip_path = session_dir / f"{slug}.mp4"
            self._download_file(download_url, clip_path)
            # Also copy to cache for future reuse
            try:
                import shutil
                shutil.copy2(str(clip_path), str(cached_clip))
            except OSError:
                log.warning("Could not cache clip %s", slug)

        # --- 3. Webcam detection (optional) --------------------------------
        webcam_region = None
        webcam_position = None
        if options.get("webcam"):
            self._update_clip_status(session_id, slug, "processing", 40)
            # If user provided a webcam_region in the clip data, use it directly
            user_region = clip.get("webcam_region")
            if user_region and isinstance(user_region, dict):
                x = int(user_region.get("x", 0))
                y = int(user_region.get("y", 0))
                w = int(user_region.get("w", 0))
                h = int(user_region.get("h", 0))
                if w > 0 and h > 0:
                    webcam_region = (x, y, w, h)
                    log.info("Using user-provided webcam region for %s: %s", slug, webcam_region)
                else:
                    webcam_region = detect_webcam_region_only(str(clip_path), user_id=session_id)
            else:
                webcam_region = detect_webcam_region_only(str(clip_path), user_id=session_id)

            # Extract user-provided webcam position (percentage-based)
            webcam_position = clip.get("webcam_position")

        # --- 4. Build and run FFmpeg ---------------------------------------
        self._update_clip_status(session_id, slug, "processing", 55)

        streamer_name = clip.get("broadcaster_name") if options.get("streamer_name") else None

        output_path = session_dir / f"{slug}_short.mp4"
        cmd = _build_ffmpeg_command(
            input_path=str(clip_path),
            output_path=str(output_path),
            webcam_region=webcam_region,
            webcam_position=webcam_position,
            streamer_name=streamer_name,
        )

        self._update_clip_status(session_id, slug, "processing", 65)
        log.info("FFmpeg command for %s: %s", slug, " ".join(cmd[:8]))

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            log.error("FFmpeg failed for %s:\n%s", slug, result.stderr)
            raise RuntimeError(f"FFmpeg failed for clip {slug}")

        if not output_path.exists():
            raise RuntimeError(f"Output file not created for clip {slug}")

        self._update_clip_status(session_id, slug, "processing", 95)

        # Clean up raw clip to save space
        try:
            clip_path.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Progress helpers (thread-safe)
    # ------------------------------------------------------------------

    def _progress_path(self, session_id: str) -> Path:
        return OUTPUT_BASE / session_id / "progress.json"

    def _read_progress(self, session_id: str) -> dict:
        path = self._progress_path(session_id)
        with self._lock:
            with open(path, "r") as f:
                return json.load(f)

    def _write_progress(self, session_id: str, data: dict):
        path = self._progress_path(session_id)
        with self._lock:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    def _update_clip_status(self, session_id: str, slug: str, status: str, progress_pct: int):
        """Update a single clip's status inside progress.json."""
        data = self._read_progress(session_id)
        for clip in data["clips"]:
            if clip["slug"] == slug:
                clip["status"] = status
                clip["progress"] = progress_pct
                break
        # Refresh completed count
        data["completed"] = sum(1 for c in data["clips"] if c["status"] == "done")
        self._write_progress(session_id, data)

    # ------------------------------------------------------------------
    # Download helper
    # ------------------------------------------------------------------

    @staticmethod
    def _download_file(url: str, dest: Path, chunk_size: int = 8192):
        """Stream-download *url* to *dest*."""
        log.info("Downloading %s → %s", url[:80], dest.name)
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        tmp = dest.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                f.write(chunk)
        tmp.rename(dest)
        log.info("Downloaded %s (%d bytes)", dest.name, dest.stat().st_size)
