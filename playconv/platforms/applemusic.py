"""
Apple Music Platform Adapter.
Extracts public album, playlist, and track metadata from music.apple.com using schema.org JSON-LD.
"""

import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_iso8601_duration(dur_str: str) -> int:
    """Parses ISO 8601 duration strings like 'PT3M45S' into integer seconds."""
    if not dur_str or not dur_str.startswith("PT"):
        return 0
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur_str)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


class AppleMusicPlatform(BasePlatform):
    """Platform implementation for Apple Music (Public Metadata Scraper)."""

    platform_type = PlatformType.APPLE_MUSIC

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()
        if "music.apple.com" not in raw_input:
            return False, ContentType.UNKNOWN, ""

        parsed = urllib.parse.urlparse(raw_input)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        qs = urllib.parse.parse_qs(parsed.query)

        # Song in an album link: ?i=1559523359
        if "i" in qs:
            return True, ContentType.TRACK, qs["i"][0]

        if "playlist" in parts:
            return True, ContentType.PLAYLIST, parts[-1]
        elif "album" in parts:
            return True, ContentType.ALBUM, parts[-1]
        elif "song" in parts:
            return True, ContentType.TRACK, parts[-1]

        return True, ContentType.PLAYLIST, parts[-1] if parts else raw_input

    def _extract_jsonld(self, url: str) -> Dict[str, Any]:
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL)
        for m in matches:
            try:
                data = json.loads(m.strip())
                if isinstance(data, dict) and data.get("@type") in ("MusicAlbum", "MusicPlaylist", "MusicRecording"):
                    return data
            except Exception:
                continue
        raise ValueError(f"Could not find valid JSON-LD schema on Apple Music page: {url}")

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.apple.com/playlist/{identifier_or_url}"
        data = self._extract_jsonld(url)

        title = data.get("name") or "Apple Music Playlist"
        desc = data.get("description") or ""
        author = data.get("author", {}).get("name") if isinstance(data.get("author"), dict) else ""
        raw_tracks = data.get("track", [])

        tracks: List[Track] = []
        for i, tr in enumerate(raw_tracks, start=1):
            t_title = tr.get("name") or ""
            artist_obj = tr.get("byArtist", {})
            t_artist = artist_obj.get("name") if isinstance(artist_obj, dict) else ""
            dur_sec = parse_iso8601_duration(tr.get("duration", ""))
            t_url = tr.get("url") or ""

            tracks.append(
                Track(
                    title=t_title,
                    artists=[t_artist] if t_artist else [],
                    primary_artist=t_artist,
                    duration_sec=dur_sec,
                    track_number=i,
                    source_platform=PlatformType.APPLE_MUSIC,
                    source_url=t_url,
                )
            )

        return PlaylistMetadata(
            title=title,
            description=desc,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.APPLE_MUSIC,
            content_type=ContentType.PLAYLIST,
            source_url=url,
            tracks=tracks,
        )

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.apple.com/album/{identifier_or_url}"
        data = self._extract_jsonld(url)

        title = data.get("name") or "Apple Music Album"
        artist_obj = data.get("byArtist", {})
        author = artist_obj.get("name") if isinstance(artist_obj, dict) else ""
        raw_tracks = data.get("track", [])

        tracks: List[Track] = []
        for i, tr in enumerate(raw_tracks, start=1):
            t_title = tr.get("name") or ""
            dur_sec = parse_iso8601_duration(tr.get("duration", ""))
            t_url = tr.get("url") or ""

            tracks.append(
                Track(
                    title=t_title,
                    artists=[author] if author else [],
                    primary_artist=author,
                    album=title,
                    duration_sec=dur_sec,
                    track_number=i,
                    source_platform=PlatformType.APPLE_MUSIC,
                    source_url=t_url,
                )
            )

        return PlaylistMetadata(
            title=title,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.APPLE_MUSIC,
            content_type=ContentType.ALBUM,
            source_url=url,
            tracks=tracks,
        )

    def fetch_track(self, identifier_or_url: str) -> Track:
        url = identifier_or_url
        data = self._extract_jsonld(url)

        title = data.get("name") or ""
        artist_obj = data.get("byArtist", {})
        author = artist_obj.get("name") if isinstance(artist_obj, dict) else ""
        dur_sec = parse_iso8601_duration(data.get("duration", ""))
        album_obj = data.get("inAlbum", {})
        album_name = album_obj.get("name") if isinstance(album_obj, dict) else ""

        return Track(
            title=title,
            artists=[author] if author else [],
            primary_artist=author,
            album=album_name,
            duration_sec=dur_sec,
            source_platform=PlatformType.APPLE_MUSIC,
            source_url=url,
        )

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        from ..matcher import clean_title
        cleaned = clean_title(track.title)
        primary = track.primary_artist or (track.artists[0] if track.artists else "")
        query = f"{cleaned} {primary}".strip()
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=song&limit={limit}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                candidates: List[Track] = []
                for item in data.get("results", []):
                    t_title = item.get("trackName") or ""
                    artist = item.get("artistName") or ""
                    album = item.get("collectionName") or ""
                    dur_ms = item.get("trackTimeMillis") or 0
                    track_url = item.get("trackViewUrl") or ""
                    candidates.append(
                        Track(
                            title=t_title,
                            artists=[artist] if artist else [],
                            primary_artist=artist,
                            album=album,
                            duration_sec=int(dur_ms // 1000),
                            source_platform=PlatformType.APPLE_MUSIC,
                            source_url=track_url,
                        )
                    )
                return candidates
        except Exception as e:
            logger.debug(f"iTunes track search error: {e}")
        return []

    def search_album(self, title: str, artist: str, limit: int = 5) -> List[PlaylistMetadata]:
        from ..matcher import clean_title
        cleaned = clean_title(title)
        query = f"{cleaned} {artist}".strip()
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=album&limit={limit}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                albums: List[PlaylistMetadata] = []
                for item in data.get("results", []):
                    view_url = item.get("collectionViewUrl")
                    if view_url:
                        try:
                            alb = self.fetch_album(view_url)
                            albums.append(alb)
                        except Exception as e:
                            logger.debug(f"Failed to fetch Apple Music album {view_url}: {e}")
                return albums
        except Exception as e:
            logger.debug(f"iTunes album search error: {e}")
        return []

    def is_authenticated_for_writing(self) -> bool:
        return False

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        raise NotImplementedError("Creating Apple Music playlists via web API is not supported.")
