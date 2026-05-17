from flask import Blueprint, render_template, request, jsonify, send_file
from app.services.shorts_service import ShortsService
from app.services.twitch_service import get_clip_download_url
import os
import subprocess
import tempfile
from pathlib import Path

shorts_bp = Blueprint('shorts', __name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "output" / "_cache"


@shorts_bp.route('/generate', methods=['GET'])
def generate_page():
    """Serve the generate.html page. Clip data is loaded from sessionStorage via JS."""
    return render_template('generate.html')


@shorts_bp.route('/api/frame/<slug>')
def get_frame(slug):
    """Extract a single frame from a clip and return it as JPEG.

    Downloads the clip (cached in output/_cache/), extracts one frame at the
    1-second mark via FFmpeg, and returns it as a JPEG image.
    """
    import logging
    log = logging.getLogger(__name__)

    # Ensure cache dir exists
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    clip_path = _CACHE_DIR / f"{slug}.mp4"
    frame_path = _CACHE_DIR / f"{slug}_frame.jpg"

    # If frame already cached, return it directly
    if frame_path.exists():
        return send_file(str(frame_path), mimetype='image/jpeg')

    # Download clip if not cached
    if not clip_path.exists():
        download_url = get_clip_download_url(slug)
        if not download_url:
            return jsonify({'error': f'Could not obtain download URL for clip {slug}'}), 404

        # Stream-download to cache
        import requests
        log.info("Downloading clip %s for frame extraction", slug)
        resp = requests.get(download_url, stream=True, timeout=60)
        resp.raise_for_status()
        tmp = clip_path.with_suffix('.tmp')
        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        tmp.rename(clip_path)
        log.info("Cached clip %s", slug)

    # Extract a single frame at 1 second using FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-ss", "1",
        "-i", str(clip_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(frame_path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        log.error("FFmpeg frame extraction failed for %s: %s", slug, result.stderr)
        return jsonify({'error': 'Frame extraction failed'}), 500

    if not frame_path.exists():
        return jsonify({'error': 'Frame not generated'}), 500

    return send_file(str(frame_path), mimetype='image/jpeg')


@shorts_bp.route('/api/generate', methods=['POST'])
def generate():
    """Create a shorts generation job. Returns {session_id}."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    clips = data.get('clips', [])
    options = data.get('options', {})

    if not clips:
        return jsonify({'error': 'No clips provided'}), 400

    service = ShortsService()
    session_id = service.generate_shorts(clips, options)
    return jsonify({'session_id': session_id})


@shorts_bp.route('/api/progress/<session_id>')
def progress(session_id):
    """Return progress JSON for a generation session."""
    service = ShortsService()
    status = service.get_progress(session_id)
    return jsonify(status)


@shorts_bp.route('/result/<session_id>')
def result(session_id):
    """Serve the result page for a generation session."""
    return render_template('result.html', shorts=[], session_id=session_id)


@shorts_bp.route('/api/results/<session_id>')
def api_results(session_id):
    """Return generated shorts as JSON."""
    service = ShortsService()
    shorts = service.get_results(session_id)
    return jsonify(shorts)


@shorts_bp.route('/download/<session_id>/<filename>')
def download(session_id, filename):
    """Download a generated file."""
    from pathlib import Path
    # Use the same absolute path as ShortsService
    project_root = Path(__file__).resolve().parent.parent.parent  # HypeClip/
    filepath = project_root / "output" / session_id / filename
    if filepath.exists():
        return send_file(str(filepath), as_attachment=True)
    return jsonify({'error': 'File not found'}), 404
