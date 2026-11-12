"""
Deezer Platform Adapter.
Provides public access to Deezer's catalog, playlists, albums, and tracks without API keys.
"""

import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)

DEEZER_API_BASE = "https://api.deezer.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


class DeezerPlatform(BasePlatform):
    """Platform implementation for Deezer."""

    platform_type = PlatformType.DEEZER

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()
        if "deezer.com" not in raw_input and "deezer.page.link" not in raw_input:
            return False, ContentType.UNKNOWN, ""

        # Follow redirects for shortlinks
        if "deezer.page.link" in raw_input:
            try:
                head = self.session.head(raw_input, allow_redirects=True, timeout=8)
                raw_input = head.url
            except Exception:
                pass

        parsed = urllib.parse.urlparse(raw_input)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not parts:
            return True, ContentType.UNKNOWN, ""

        # Look for playlist/album/track
        if "playlist" in parts:
            idx = parts.index("playlist")
            token = parts[idx + 1] if len(parts) > idx + 1 else parts[-1]
            return True, ContentType.PLAYLIST, token.split("?")[0]
        elif "album" in parts:
            idx = parts.index("album")
            token = parts[idx + 1] if len(parts) > idx + 1 else parts[-1]
            return True, ContentType.ALBUM, token.split("?")[0]
        elif "track" in parts:
            idx = parts.index("track")
            token = parts[idx + 1] if len(parts) > idx + 1 else parts[-1]
            return True, ContentType.TRACK, token.split("?")[0]

        return True, ContentType.UNKNOWN, parts[-1]

    def _parse_track_json(self, data: Dict[str, Any], index: int = 1) -> Track:
        artist_obj = data.get("artist", {})
        primary_artist = artist_obj.get("name") if isinstance(artist_obj, dict) else ""
        album_obj = data.get("album", {})
        album_name = album_obj.get("title") if isinstance(album_obj, dict) else ""
        album_art = album_obj.get("cover_xl") or album_obj.get("cover_big") if isinstance(album_obj, dict) else ""

        dur = int(data.get("duration") or 0)
        isrc = data.get("isrc")
        tid = str(data.get("id"))
        link = data.get("link") or f"https://www.deezer.com/track/{tid}"

        return Track(
            title=data.get("title") or "",
            artists=[primary_artist] if primary_artist else [],
            primary_artist=primary_artist,
            album=album_name,
            duration_sec=dur,
            isrc=isrc,
            track_number=index,
            source_platform=PlatformType.DEEZER,
            source_id=tid,
            source_url=link,
            image_url=album_art,
        )

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, pid = self.can_handle_url(identifier_or_url)
        pid = pid or identifier_or_url.strip()

        resp = self.session.get(f"{DEEZER_API_BASE}/playlist/{pid}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Deezer playlist error: {data['error'].get('message')}")

        title = data.get("title") or "Deezer Playlist"
        author = data.get("creator", {}).get("name") if isinstance(data.get("creator"), dict) else ""
        desc = data.get("description") or ""
        cover = data.get("picture_xl") or data.get("picture_big") or ""

        raw_tracks = data.get("tracks", {}).get("data", [])
        tracks = [self._parse_track_json(t, i) for i, t in enumerate(raw_tracks, start=1)]

        return PlaylistMetadata(
            title=title,
            description=desc,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.DEEZER,
            content_type=ContentType.PLAYLIST,
            source_url=data.get("link") or f"https://www.deezer.com/playlist/{pid}",
            image_url=cover,
            tracks=tracks,
        )

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, aid = self.can_handle_url(identifier_or_url)
        aid = aid or identifier_or_url.strip()

        resp = self.session.get(f"{DEEZER_API_BASE}/album/{aid}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Deezer album error: {data['error'].get('message')}")

        title = data.get("title") or "Deezer Album"
        author = data.get("artist", {}).get("name") if isinstance(data.get("artist"), dict) else ""
        cover = data.get("cover_xl") or data.get("cover_big") or ""

        raw_tracks = data.get("tracks", {}).get("data", [])
        tracks = [self._parse_track_json(t, i) for i, t in enumerate(raw_tracks, start=1)]

        return PlaylistMetadata(
            title=title,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.DEEZER,
            content_type=ContentType.ALBUM,
            source_url=data.get("link") or f"https://www.deezer.com/album/{aid}",
            image_url=cover,
            tracks=tracks,
        )

    def fetch_track(self, identifier_or_url: str) -> Track:
        _, _, tid = self.can_handle_url(identifier_or_url)
        tid = tid or identifier_or_url.strip()

        resp = self.session.get(f"{DEEZER_API_BASE}/track/{tid}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Deezer track error: {data['error'].get('message')}")

        return self._parse_track_json(data)

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        query = f"{track.title} {track.primary_artist}".strip()
        resp = self.session.get(f"{DEEZER_API_BASE}/search", params={"q": query, "limit": limit}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("data", [])
        return [self._parse_track_json(t, i) for i, t in enumerate(results, start=1)]

    def is_authenticated_for_writing(self) -> bool:
        return False

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        raise NotImplementedError("Creating user playlists on Deezer requires user token.")
