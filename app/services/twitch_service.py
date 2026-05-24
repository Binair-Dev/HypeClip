"""
HypeClip Twitch Service — standalone Twitch GraphQL API client.

No Flask or Hypesync dependencies. Uses the public Twitch GQL endpoint
with the web-client ID.
"""

import json as _json
import logging
import uuid
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Client-Id": CLIENT_ID,
    "Content-Type": "application/json",
}

# SHA-256 hashes for persisted queries (from Twitch web client)
HASH_CLIPS_CARDS = "90c33f5e6465122fba8f9371e2a97076f9ed06c6fed3788d002ab9eba8f91d88"
HASH_VIDEO_ACCESS_TOKEN = "36b89d2507fce29e5ca551df756d27c1cfe079e2609642b4390aa4c35796eb11"

_DEFAULT_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gql_post(payload: dict, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    """Send a single GraphQL request and return the JSON response."""
    resp = requests.post(
        TWITCH_GQL_URL,
        json=payload,
        headers=HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_streamer(query: str) -> Optional[dict]:
    """Verify a Twitch streamer exists by login name.

    Uses the ``ClipsCards__User`` operation with limit=0 to check existence
    and fetch broadcaster info (displayName, profileImageURL).

    Returns a dict with keys: login, display_name, profile_image_url.
    Returns ``None`` when the channel is not found.
    """
    payload = {
        "operationName": "ClipsCards__User",
        "variables": {
            "login": query,
            "limit": 1,
            "criteria": {"sort": "VIEWS_DESC", "period": "LAST_DAY"},
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": HASH_CLIPS_CARDS,
            }
        },
    }

    try:
        data = _gql_post(payload)
    except requests.RequestException:
        log.exception("search_streamer: request failed for %r", query)
        return None

    user = (data.get("data") or {}).get("user")
    if not user:
        return None

    # Try to extract broadcaster info from first clip edge
    edges = (user.get("clips") or {}).get("edges") or []
    if edges:
        broadcaster = edges[0].get("node", {}).get("broadcaster") or {}
        return {
            "login": broadcaster.get("login", query),
            "display_name": broadcaster.get("displayName", query),
            "profile_image_url": broadcaster.get("profileImageURL", ""),
        }

    # User exists but no clips — return basic info
    return {
        "login": query,
        "display_name": query,
        "profile_image_url": "",
    }


def get_trending_clips(
    streamer_login: str,
    period: str = "LAST_DAY",
    sort: str = "VIEWS_DESC",
    limit: int = 20,
) -> list[dict]:
    """Fetch trending clips for a Twitch streamer.

    Parameters
    ----------
    streamer_login : str
        The lowercase login name of the broadcaster.
    period : str
        One of ``LAST_DAY``, ``LAST_WEEK``, ``LAST_MONTH``, ``ALL_TIME``.
    sort : str
        One of ``TRENDING``, ``VIEWS_DESC``.
    limit : int
        Number of clips to return.

    Returns
    -------
    list[dict]
        Each dict contains: slug, title, duration, view_count, game,
        thumbnail_url, clip_url, created_at, broadcaster_name.
    """
    payload = {
        "operationName": "ClipsCards__User",
        "variables": {
            "login": streamer_login,
            "limit": limit,
            "criteria": {
                "sort": sort,
                "period": period,
            },
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": HASH_CLIPS_CARDS,
            }
        },
    }

    try:
        data = _gql_post(payload)
    except requests.RequestException:
        log.exception("get_trending_clips: request failed for %r", streamer_login)
        return []

    user = (data.get("data") or {}).get("user")
    if not user:
        log.warning("get_trending_clips: no user returned for %r", streamer_login)
        return []

    clips_connection = user.get("clips") or {}
    edges = clips_connection.get("edges") or []

    results: list[dict] = []
    for edge in edges:
        node = edge.get("node") or {}

        slug = node.get("slug") or node.get("id", "")
        broadcaster = node.get("broadcaster") or {}
        game_node = node.get("game") or {}

        results.append(
            {
                "slug": slug,
                "title": node.get("title", ""),
                "duration": node.get("durationSeconds", 0),
                "view_count": node.get("viewCount", 0),
                "game": game_node.get("name", ""),
                "thumbnail_url": node.get("thumbnailURL", ""),
                "clip_url": node.get("url", f"https://www.twitch.tv/{streamer_login}/clip/{slug}"),
                "embed_url": node.get("embedURL", f"https://clips.twitch.tv/embed?clip={slug}"),
                "created_at": node.get("createdAt", ""),
                "broadcaster_name": broadcaster.get("displayName", streamer_login),
            }
        )

    return results


def get_clips_for_streamers_game(
    streamer_logins: list[str],
    game_name: str,
    count: int,
    period: str = "LAST_DAY",
    sort: str = "VIEWS_DESC",
    clips_per_streamer: int = 20,
) -> list[dict]:
    """Fetch random clips matching a game from a list of streamers in parallel."""
    import random
    from concurrent.futures import ThreadPoolExecutor, as_completed

    game_lower = game_name.strip().lower()

    def fetch_one(login: str) -> list[dict]:
        clips = get_trending_clips(login, period=period, sort=sort, limit=clips_per_streamer)
        return [c for c in clips if c.get('game', '').lower() == game_lower]

    all_clips: list[dict] = []
    max_workers = min(len(streamer_logins), 20)
    if max_workers == 0:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, login): login for login in streamer_logins}
        for future in as_completed(futures):
            try:
                all_clips.extend(future.result())
            except Exception as exc:
                log.warning("get_clips_for_streamers_game: error for %r: %s", futures[future], exc)

    if not all_clips:
        return []

    return random.sample(all_clips, min(count, len(all_clips)))


def get_clip_download_url(clip_slug: str) -> Optional[str]:
    """Return the signed (direct-download) URL for a Twitch clip.

    Parameters
    ----------
    clip_slug : str
        The clip slug (e.g. ``"VibrantBitterPenguinDatSheffy"``).

    Returns
    -------
    str or None
        The signed MP4 URL, or ``None`` on failure.
    """
    payload = {
        "operationName": "VideoAccessToken_Clip",
        "variables": {"slug": clip_slug},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": HASH_VIDEO_ACCESS_TOKEN,
            }
        },
    }

    try:
        data = _gql_post(payload)
    except requests.RequestException:
        log.exception("get_clip_download_url: request failed for %r", clip_slug)
        return None

    clip = (data.get("data") or {}).get("clip")
    if not clip:
        log.warning("get_clip_download_url: no clip data for %r", clip_slug)
        return None

    # The video qualities array contains the direct URLs
    video_qualities = clip.get("videoQualities") or []
    if not video_qualities:
        log.warning("get_clip_download_url: no videoQualities for %r", clip_slug)
        return None

    # Pick the highest quality (first entry, typically 1080p)
    best = video_qualities[0]
    source_url = best.get("sourceURL", "")
    if not source_url:
        return None

    # Append the signature + token for signed access
    # token_val is already a JSON string — pass it raw, do NOT json.dumps again
    token_data = clip.get("playbackAccessToken") or {}
    sig = token_data.get("signature", "")
    token_val = token_data.get("value", "")

    if sig and token_val:
        device_id = str(uuid.uuid4())
        source_url = f"{source_url}?sig={sig}&token={token_val}&device_id={device_id}"

    return source_url
