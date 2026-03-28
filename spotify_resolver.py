"""
spotify_resolver.py
~~~~~~~~~~~~~~~~~~~
Resolves Spotify track / album / playlist URLs to YouTube search queries
using the Spotify Web API (client-credentials flow), then hands them off
to yt-dlp for the actual download.

Requirements: requests (already in requirements.txt)
No extra packages needed — we call the Spotify REST API directly.
"""

import re
import requests
from typing import Optional


# ── Spotify API helpers ───────────────────────────────────────────────────────

class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE  = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id     = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None

    def _get_token(self) -> str:
        """Fetch a client-credentials access token."""
        resp = requests.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self._get_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.API_BASE}/{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code == 401:
            # Token expired — refresh once
            self._get_token()
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Public helpers ────────────────────────────────────

    def get_track_info(self, track_id: str) -> dict:
        """Return {"title", "artist", "album", "duration_ms"} for a track."""
        data = self._get(f"tracks/{track_id}")
        return {
            "title":       data["name"],
            "artist":      ", ".join(a["name"] for a in data["artists"]),
            "album":       data["album"]["name"],
            "duration_ms": data["duration_ms"],
        }

    def get_album_tracks(self, album_id: str) -> list[dict]:
        """Return a list of track info dicts for every track in an album."""
        album = self._get(f"albums/{album_id}")
        album_name = album["name"]
        tracks = []
        items = album["tracks"]["items"]
        # Handle pagination
        next_url = album["tracks"].get("next")
        while next_url:
            page = requests.get(next_url, headers=self._headers(), timeout=15).json()
            items.extend(page["items"])
            next_url = page.get("next")
        for item in items:
            tracks.append({
                "title":  item["name"],
                "artist": ", ".join(a["name"] for a in item["artists"]),
                "album":  album_name,
            })
        return tracks

    def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """Return a list of track info dicts for every track in a playlist."""
        tracks = []
        path = f"playlists/{playlist_id}/tracks"
        params = {"fields": "items(track(name,artists,album(name))),next", "limit": 100}
        while path:
            data = self._get(path, params)
            for item in data["items"]:
                t = item.get("track")
                if not t:
                    continue
                tracks.append({
                    "title":  t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "album":  t["album"]["name"] if t.get("album") else "",
                })
            path = None
            params = None
            next_url = data.get("next")
            if next_url:
                # Switch to full URL mode for subsequent pages
                resp = requests.get(next_url, headers=self._headers(), timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for item in data["items"]:
                    t = item.get("track")
                    if not t:
                        continue
                    tracks.append({
                        "title":  t["name"],
                        "artist": ", ".join(a["name"] for a in t["artists"]),
                        "album":  t["album"]["name"] if t.get("album") else "",
                    })
                if not data.get("next"):
                    break
                next_url = data["next"]
        return tracks


# ── URL parsing ───────────────────────────────────────────────────────────────

_SPOTIFY_RE = re.compile(
    r'open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist)/([A-Za-z0-9]+)',
    re.IGNORECASE
)

def parse_spotify_url(url: str) -> Optional[tuple[str, str]]:
    """
    Returns (kind, spotify_id) where kind is 'track', 'album', or 'playlist',
    or None if the URL is not a recognised Spotify URL.
    """
    m = _SPOTIFY_RE.search(url)
    if m:
        return m.group(1).lower(), m.group(2)
    return None


# ── YouTube search query builder ──────────────────────────────────────────────

def build_ytdlp_search_url(track: dict) -> str:
    """
    Build a yt-dlp ytsearch: URL from a Spotify track info dict.
    yt-dlp accepts  ytsearch1:QUERY  to download the single best match.
    """
    query = f"{track['artist']} - {track['title']} official audio"
    # ytsearch1: tells yt-dlp to search YouTube and pick the first result
    return f"ytsearch1:{query}"


# ── High-level resolver ───────────────────────────────────────────────────────

def resolve_spotify_url(url: str, client_id: str, client_secret: str,
                        progress_cb=None) -> list[str]:
    """
    Given a Spotify URL and API credentials, return a list of yt-dlp-compatible
    search URLs (one per track).

    progress_cb: optional callable(str) for status messages.
    Raises ValueError / requests.HTTPError on bad credentials or unknown URL.
    """
    def emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    parsed = parse_spotify_url(url)
    if not parsed:
        raise ValueError(f"Not a recognised Spotify URL: {url}")

    kind, spot_id = parsed
    client = SpotifyClient(client_id, client_secret)

    if kind == "track":
        emit("🎵 Fetching track info from Spotify…")
        info = client.get_track_info(spot_id)
        emit(f"  → {info['artist']} – {info['title']}")
        return [build_ytdlp_search_url(info)]

    elif kind == "album":
        emit("💿 Fetching album tracks from Spotify…")
        tracks = client.get_album_tracks(spot_id)
        emit(f"  → {len(tracks)} tracks found")
        return [build_ytdlp_search_url(t) for t in tracks]

    elif kind == "playlist":
        emit("📋 Fetching playlist tracks from Spotify…")
        tracks = client.get_playlist_tracks(spot_id)
        emit(f"  → {len(tracks)} tracks found")
        return [build_ytdlp_search_url(t) for t in tracks]

    raise ValueError(f"Unsupported Spotify URL type: {kind}")
