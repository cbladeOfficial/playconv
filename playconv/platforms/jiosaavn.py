"""
JioSaavn Platform Adapter.
Supports reading playlists, albums, and tracks via the public JioSaavn API without auth,
searching for matching tracks, and creating authenticated playlists via session cookies.
"""

import html
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..config import config
from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)

API_BASE = "https://www.jiosaavn.com/api.php"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_html(text: Optional[str]) -> str:
    """Unescapes HTML entities and strips unwanted whitespace."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    # Remove HTML tags if any
    clean = re.sub(r"<[^>]+>", "", unescaped)
    return re.sub(r"\s+", " ", clean).strip()


class JioSaavnPlatform(BasePlatform):
    """Platform implementation for JioSaavn."""

    platform_type = PlatformType.JIOSAAVN

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _call(self, params: Dict[str, Any], cookies: Optional[Dict[str, str]] = None) -> Any:
        default_params = {
            "_format": "json",
            "_marker": "0",
            "ctx": "web6dot0",
            "api_version": "4",
        }
        merged = {**default_params, **params}
        try:
            resp = self.session.get(API_BASE, params=merged, cookies=cookies, timeout=15)
            resp.raise_for_status()
            text = resp.text.strip()
            if text.startswith("/**/") or text.startswith("/*"):
                text = re.sub(r"^/\*\*?/?\s*", "", text)
            if not text:
                return {}
            return resp.json()
        except Exception as e:
            logger.error(f"JioSaavn API call failed: {e}")
            raise

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()

        # Follow redirects for shortlinks
        if re.match(r"^https?://(saa\.vn|jiosaavn\.com/s/|jiosaavn\.com/p/)", raw_input, re.IGNORECASE):
            try:
                head_resp = self.session.head(raw_input, allow_redirects=True, timeout=8)
                raw_input = head_resp.url
            except Exception:
                pass

        if "jiosaavn.com" not in raw_input and "saavn.com" not in raw_input:
            return False, ContentType.UNKNOWN, ""

        parsed = urllib.parse.urlparse(raw_input)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not parts:
            return True, ContentType.UNKNOWN, ""

        token = parts[-1]
        if "song" in parts:
            return True, ContentType.TRACK, token
        elif "album" in parts:
            return True, ContentType.ALBUM, token
        elif "featured" in parts or "playlist" in parts:
            return True, ContentType.PLAYLIST, token

        return True, ContentType.PLAYLIST, token

    def _parse_track_item(self, item: Dict[str, Any]) -> Track:
        more_info = item.get("more_info") if isinstance(item.get("more_info"), dict) else {}

        title = clean_html(item.get("song") or item.get("title") or "")
        
        # Extract artists comprehensively from JioSaavn response
        artists: List[str] = []
        # Check subtitle first (e.g. "Pritam, Arijit Singh, Amitabh Bhattacharya - Brahmastra")
        if item.get("subtitle") and " - " in item.get("subtitle", ""):
            sub_artists = item["subtitle"].split(" - ")[0]
            artists = [a.strip() for a in sub_artists.split(",") if a.strip()]

        # Check explicit primary_artists field
        primary_field = clean_html(item.get("primary_artists") or more_info.get("primary_artists") or "")
        if primary_field:
            for a in primary_field.split(","):
                a_clean = a.strip()
                if a_clean and a_clean not in artists:
                    artists.append(a_clean)

        # Check singers field
        singers_field = clean_html(item.get("singers") or more_info.get("singers") or "")
        if singers_field:
            for a in singers_field.split(","):
                a_clean = a.strip()
                if a_clean and a_clean not in artists:
                    artists.append(a_clean)

        # Check music / composer field
        music_field = clean_html(item.get("music") or more_info.get("music") or "")
        if music_field:
            for a in music_field.split(","):
                a_clean = a.strip()
                if a_clean and a_clean not in artists:
                    artists.append(a_clean)

        # Fallback to artistMap
        if not artists and "artistMap" in more_info and isinstance(more_info["artistMap"], dict):
            artists = list(more_info["artistMap"].keys())

        primary_artist = artists[0] if artists else ""

        album = clean_html(item.get("album") or more_info.get("album") or "")

        dur_str = item.get("duration") or more_info.get("duration") or "0"
        try:
            duration_sec = int(dur_str)
        except (ValueError, TypeError):
            duration_sec = 0

        year_str = item.get("year") or more_info.get("year")
        year_val = None
        if year_str:
            try:
                year_val = int(year_str)
            except ValueError:
                pass

        image_url = item.get("image") or ""
        if image_url:
            image_url = image_url.replace("150x150", "500x500").replace("50x50", "500x500")

        return Track(
            title=title,
            artists=artists,
            primary_artist=artists[0] if artists else "",
            album=album,
            duration_sec=duration_sec,
            year=year_val,
            release_date=item.get("release_date") or more_info.get("release_date"),
            source_platform=PlatformType.JIOSAAVN,
            source_id=item.get("id"),
            source_url=item.get("perma_url"),
            image_url=image_url,
            language=item.get("language") or more_info.get("language"),
            extra_metadata={
                "album_id": item.get("albumid") or more_info.get("album_id"),
                "encrypted_media_url": item.get("encrypted_media_url") or more_info.get("encrypted_media_url"),
            },
        )

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, token = self.can_handle_url(identifier_or_url)
        token = token or identifier_or_url.strip()

        # If token is pure digits, use listid, otherwise use token
        if token.isdigit():
            params = {"__call": "playlist.getDetails", "listid": token}
        else:
            params = {"__call": "webapi.get", "token": token, "type": "playlist"}

        data = self._call(params)
        title = clean_html(data.get("listname") or data.get("title") or "JioSaavn Playlist")
        description = clean_html(data.get("description") or "")
        author = clean_html(data.get("firstname") or data.get("username") or "")
        image_url = (data.get("image") or "").replace("150x150", "500x500")

        raw_list = data.get("songs") or data.get("list") or []
        tracks = [self._parse_track_item(s) for s in raw_list if isinstance(s, dict)]

        return PlaylistMetadata(
            title=title,
            description=description,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.JIOSAAVN,
            content_type=ContentType.PLAYLIST,
            source_url=data.get("perma_url") or identifier_or_url,
            image_url=image_url,
            tracks=tracks,
        )

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, token = self.can_handle_url(identifier_or_url)
        token = token or identifier_or_url.strip()

        if token.isdigit():
            params = {"__call": "content.getAlbumDetails", "albumid": token}
        else:
            params = {"__call": "webapi.get", "token": token, "type": "album"}

        data = self._call(params)
        title = clean_html(data.get("title") or data.get("name") or "JioSaavn Album")
        author = clean_html(data.get("primary_artists") or "")
        image_url = (data.get("image") or "").replace("150x150", "500x500")

        raw_list = data.get("songs") or data.get("list") or []
        tracks = [self._parse_track_item(s) for s in raw_list if isinstance(s, dict)]

        return PlaylistMetadata(
            title=title,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.JIOSAAVN,
            content_type=ContentType.ALBUM,
            source_url=data.get("perma_url") or identifier_or_url,
            image_url=image_url,
            tracks=tracks,
        )

    def fetch_track(self, identifier_or_url: str) -> Track:
        _, _, token = self.can_handle_url(identifier_or_url)
        token = token or identifier_or_url.strip()

        if token.isdigit():
            params = {"__call": "song.getDetails", "pids": token}
        else:
            params = {"__call": "webapi.get", "token": token, "type": "song"}

        data = self._call(params)
        if isinstance(data, dict):
            # Sometimes song.getDetails returns dict keyed by id
            if "songs" in data and isinstance(data["songs"], list) and data["songs"]:
                return self._parse_track_item(data["songs"][0])
            for k, v in data.items():
                if isinstance(v, dict) and "song" in v:
                    return self._parse_track_item(v)
            if "song" in data or "title" in data:
                return self._parse_track_item(data)

        raise ValueError(f"Could not resolve JioSaavn track from {identifier_or_url}")

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        from ..matcher import clean_title
        cleaned = clean_title(track.title)
        primary = track.primary_artist or (track.artists[0] if track.artists else "")
        query = f"{cleaned} {primary}".strip()

        params = {
            "__call": "search.getResults",
            "q": query,
            "n": limit,
        }
        data = self._call(params)
        results = data.get("results") or []
        candidates: List[Track] = []
        for r in results:
            if isinstance(r, dict):
                candidates.append(self._parse_track_item(r))
        return candidates

    def is_authenticated_for_writing(self) -> bool:
        return bool(config.jiosaavn_cookie)

    def _get_cookie_dict(self) -> Dict[str, str]:
        raw = config.jiosaavn_cookie.strip()
        cookie_dict = {}
        # Parse Cookie: a=1; b=2
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookie_dict[k.strip()] = v.strip()
        return cookie_dict

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        if not self.is_authenticated_for_writing():
            raise PermissionError(
                "JioSaavn playlist creation requires an authenticated session cookie.\n"
                "Please configure your JioSaavn cookie using: playconv auth jiosaavn"
            )

        cookies = self._get_cookie_dict()
        # Filter valid JioSaavn song IDs (pids)
        pids = []
        for t in tracks:
            sid = t.source_id or t.extra_metadata.get("id")
            if sid:
                lang = t.language or ""
                pids.append(f"~~{sid}~{lang}" if lang else f"~~{sid}")

        if not pids:
            raise ValueError("No valid JioSaavn track IDs found to create playlist.")

        # Format contents: ~~pid1~lang^~~pid2~lang
        contents_str = "^".join(pids)

        params = {
            "__call": "playlist.create",
            "listname": title,
            "contents": contents_str,
            "share": "true",
            "api_version": "4",
            "_format": "json",
            "_marker": "0",
            "ctx": "web6dot0",
        }

        resp = self._call(params, cookies=cookies)
        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            raise PermissionError(f"JioSaavn playlist creation rejected: {err.get('msg', err)}")

        playlist_id = resp.get("listid") or resp.get("id") or str(resp)
        playlist_url = resp.get("perma_url") or f"https://www.jiosaavn.com/featured/{playlist_id}"

        logger.info(f"Created JioSaavn playlist {title} ({playlist_id})")
        return str(playlist_id), playlist_url
