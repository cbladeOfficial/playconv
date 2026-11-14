"""
YouTube Music Platform Adapter.
Supports reading public playlists, albums, and tracks via ytmusicapi and yt-dlp,
searching for exact song matches, and creating playlists on YouTube Music accounts.
"""

import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import yt_dlp
from ytmusicapi import YTMusic

from ..config import config
from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)


def parse_duration_str(dur_str: Any) -> int:
    """Parses 'MM:SS' or 'H:MM:SS' or int/float seconds into integer seconds."""
    if not dur_str:
        return 0
    if isinstance(dur_str, (int, float)):
        return int(dur_str)
    parts = str(dur_str).strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        elif len(parts) == 1 and parts[0].isdigit():
            return int(parts[0])
    except (ValueError, TypeError):
        pass
    return 0


class YTMusicPlatform(BasePlatform):
    """Platform implementation for YouTube Music."""

    platform_type = PlatformType.YTMUSIC

    def __init__(self):
        self._unauth_client = YTMusic()
        self._auth_client: Optional[YTMusic] = None
        self._init_auth_client()

    def _init_auth_client(self) -> None:
        """Attempts to initialize authenticated YTMusic client if credentials exist."""
        auth_file = config.ytmusic_auth_file
        if auth_file and os.path.exists(auth_file):
            try:
                self._auth_client = YTMusic(auth=auth_file)
                logger.info(f"Initialized authenticated YouTube Music client from {auth_file}")
            except Exception as e:
                logger.warning(f"Could not load YTMusic auth file {auth_file}: {e}")
                self._auth_client = None

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()
        if "music.youtube.com" not in raw_input and "youtube.com" not in raw_input and "youtu.be" not in raw_input:
            return False, ContentType.UNKNOWN, ""

        parsed = urllib.parse.urlparse(raw_input)
        query_params = urllib.parse.parse_qs(parsed.query)

        # Playlist or Album
        if "list" in query_params:
            list_id = query_params["list"][0]
            if list_id.startswith("OLAK5uy_"):
                return True, ContentType.ALBUM, list_id
            return True, ContentType.PLAYLIST, list_id

        # Video / Song
        if "v" in query_params:
            return True, ContentType.TRACK, query_params["v"][0]

        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/")
            if video_id:
                return True, ContentType.TRACK, video_id

        if "/channel/" in parsed.path or "/browse/" in parsed.path:
            browse_id = parsed.path.strip("/").split("/")[-1]
            if browse_id.startswith("MPREb_"):
                return True, ContentType.ALBUM, browse_id
            return True, ContentType.PLAYLIST, browse_id

        return True, ContentType.UNKNOWN, raw_input

    def _fetch_with_ytdlp(self, url: str) -> PlaylistMetadata:
        """Fallback extractor using yt-dlp flat playlist extraction."""
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        cookies_file = config.ytmusic_cookies_file
        if cookies_file and os.path.exists(cookies_file):
            ydl_opts["cookiefile"] = cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "YouTube Music Playlist"
        author = info.get("uploader") or info.get("channel") or ""
        entries = info.get("entries") or []

        tracks: List[Track] = []
        for i, entry in enumerate(entries, start=1):
            if not entry:
                continue
            t_title = entry.get("title") or ""
            t_artist = entry.get("artist") or entry.get("uploader") or ""
            t_artists = [t_artist] if t_artist else []
            t_dur = int(entry.get("duration") or 0)
            vid = entry.get("id") or ""
            t_url = f"https://music.youtube.com/watch?v={vid}" if vid else ""

            tracks.append(
                Track(
                    title=t_title,
                    artists=t_artists,
                    primary_artist=t_artist,
                    duration_sec=t_dur,
                    track_number=i,
                    source_platform=PlatformType.YTMUSIC,
                    source_id=vid,
                    source_url=t_url,
                )
            )

        return PlaylistMetadata(
            title=title,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.YTMUSIC,
            content_type=ContentType.PLAYLIST,
            source_url=url,
            tracks=tracks,
        )

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, list_id = self.can_handle_url(identifier_or_url)
        list_id = list_id or identifier_or_url.strip()

        # Try ytmusicapi first
        try:
            client = self._auth_client or self._unauth_client
            data = client.get_playlist(list_id)
            title = data.get("title") or "YouTube Music Playlist"
            author = data.get("author", {}).get("name") if isinstance(data.get("author"), dict) else data.get("author", "")
            description = data.get("description") or ""

            raw_tracks = data.get("tracks") or []
            tracks: List[Track] = []
            for i, t in enumerate(raw_tracks, start=1):
                vid = t.get("videoId")
                if not vid:
                    continue
                artists_list = [a.get("name") for a in t.get("artists", []) if a.get("name")]
                primary_artist = artists_list[0] if artists_list else ""
                album_name = t.get("album", {}).get("name") if isinstance(t.get("album"), dict) else ""
                dur_sec = parse_duration_str(t.get("duration") or t.get("duration_seconds"))
                thumbs = t.get("thumbnails", [])
                thumb_url = thumbs[-1].get("url") if thumbs else ""

                tracks.append(
                    Track(
                        title=t.get("title") or "",
                        artists=artists_list,
                        primary_artist=primary_artist,
                        album=album_name,
                        duration_sec=dur_sec,
                        track_number=i,
                        source_platform=PlatformType.YTMUSIC,
                        source_id=vid,
                        source_url=f"https://music.youtube.com/watch?v={vid}",
                        image_url=thumb_url,
                    )
                )

            return PlaylistMetadata(
                title=title,
                description=description,
                author=author,
                total_tracks=len(tracks),
                source_platform=PlatformType.YTMUSIC,
                content_type=ContentType.PLAYLIST,
                source_url=f"https://music.youtube.com/playlist?list={list_id}",
                tracks=tracks,
            )
        except Exception as e:
            logger.warning(f"ytmusicapi failed for playlist {list_id} ({e}); falling back to yt-dlp")
            clean_url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.youtube.com/playlist?list={list_id}"
            return self._fetch_with_ytdlp(clean_url)

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, browse_id = self.can_handle_url(identifier_or_url)
        browse_id = browse_id or identifier_or_url.strip()

        try:
            client = self._auth_client or self._unauth_client
            data = client.get_album(browse_id)
            title = data.get("title") or "YouTube Music Album"
            artists_list = [a.get("name") for a in data.get("artists", []) if a.get("name")]
            author = ", ".join(artists_list)
            year_val = None
            if "year" in data:
                try:
                    year_val = int(data["year"])
                except (ValueError, TypeError):
                    pass

            raw_tracks = data.get("tracks") or []
            tracks: List[Track] = []
            for i, t in enumerate(raw_tracks, start=1):
                vid = t.get("videoId")
                dur_sec = parse_duration_str(t.get("duration") or t.get("duration_seconds"))
                tracks.append(
                    Track(
                        title=t.get("title") or "",
                        artists=artists_list,
                        primary_artist=artists_list[0] if artists_list else "",
                        album=title,
                        duration_sec=dur_sec,
                        year=year_val,
                        track_number=i,
                        source_platform=PlatformType.YTMUSIC,
                        source_id=vid,
                        source_url=f"https://music.youtube.com/watch?v={vid}" if vid else "",
                    )
                )

            return PlaylistMetadata(
                title=title,
                author=author,
                total_tracks=len(tracks),
                source_platform=PlatformType.YTMUSIC,
                content_type=ContentType.ALBUM,
                source_url=identifier_or_url,
                tracks=tracks,
            )
        except Exception as e:
            logger.warning(f"ytmusicapi failed for album {browse_id} ({e}); falling back to yt-dlp")
            clean_url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.youtube.com/playlist?list={browse_id}"
            return self._fetch_with_ytdlp(clean_url)

    def fetch_track(self, identifier_or_url: str) -> Track:
        _, _, vid = self.can_handle_url(identifier_or_url)
        vid = vid or identifier_or_url.strip()

        try:
            client = self._auth_client or self._unauth_client
            data = client.get_song(vid)
            details = data.get("videoDetails", {})
            title = details.get("title", "")
            author = details.get("author", "")
            dur_sec = int(details.get("lengthSeconds") or 0)
            thumbs = details.get("thumbnail", {}).get("thumbnails", [])
            thumb_url = thumbs[-1].get("url") if thumbs else ""

            return Track(
                title=title,
                artists=[author] if author else [],
                primary_artist=author,
                duration_sec=dur_sec,
                source_platform=PlatformType.YTMUSIC,
                source_id=vid,
                source_url=f"https://music.youtube.com/watch?v={vid}",
                image_url=thumb_url,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch song {vid} via ytmusicapi: {e}")
            return Track(
                title=vid,
                source_platform=PlatformType.YTMUSIC,
                source_id=vid,
                source_url=f"https://music.youtube.com/watch?v={vid}",
            )

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        from ..matcher import clean_title
        cleaned = clean_title(track.title)
        primary = track.primary_artist or (track.artists[0] if track.artists else "")
        query = f"{cleaned} {primary}".strip()
        client = self._auth_client or self._unauth_client

        candidates: List[Track] = []
        try:
            raw_results = client.search(query, filter="songs")
            if not raw_results:
                raw_results = client.search(query, filter="videos")

            for r in raw_results[:limit]:
                vid = r.get("videoId")
                if not vid:
                    continue
                c_title = r.get("title") or ""
                artists_list = [a.get("name") for a in r.get("artists", []) if a.get("name")]
                primary_artist = artists_list[0] if artists_list else ""
                album_name = r.get("album", {}).get("name") if isinstance(r.get("album"), dict) else ""
                dur_sec = parse_duration_str(r.get("duration"))
                thumbs = r.get("thumbnails", [])
                thumb_url = thumbs[-1].get("url") if thumbs else ""

                candidates.append(
                    Track(
                        title=c_title,
                        artists=artists_list,
                        primary_artist=primary_artist,
                        album=album_name,
                        duration_sec=dur_sec,
                        source_platform=PlatformType.YTMUSIC,
                        source_id=vid,
                        source_url=f"https://music.youtube.com/watch?v={vid}",
                        image_url=thumb_url,
                    )
                )
        except Exception as e:
            logger.error(f"YouTube Music search failed for query '{query}': {e}")

        return candidates

    def search_album(self, title: str, artist: str, limit: int = 5) -> List[PlaylistMetadata]:
        from ..matcher import clean_title
        cleaned = clean_title(title)
        query = f"{cleaned} {artist}".strip()
        client = self._auth_client or self._unauth_client

        albums: List[PlaylistMetadata] = []
        try:
            results = client.search(query, filter="albums")
            for r in results[:limit]:
                browse_id = r.get("browseId")
                if browse_id:
                    try:
                        alb = self.fetch_album(browse_id)
                        albums.append(alb)
                    except Exception as e:
                        logger.debug(f"Failed to fetch YTMusic album {browse_id}: {e}")
        except Exception as e:
            logger.debug(f"YTMusic album search failed: {e}")

        return albums

    def is_authenticated_for_writing(self) -> bool:
        self._init_auth_client()
        return self._auth_client is not None

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        if not self.is_authenticated_for_writing():
            raise PermissionError(
                "YouTube Music playlist creation requires an authenticated session.\n"
                "Please configure authentication using: playconv auth ytmusic\n"
                "You can paste your browser request headers or authenticate via OAuth."
            )

        video_ids = [t.source_id for t in tracks if t.source_id]
        if not video_ids:
            raise ValueError("No valid YouTube Music video IDs found to create playlist.")

        desc = description or "Created with PlayConv"
        # Create playlist with the first batch (up to 50 tracks)
        initial_ids = video_ids[:50]
        try:
            res = self._auth_client.create_playlist(
                title=title,
                description=desc,
                privacy_status="PUBLIC",
                video_ids=initial_ids,
            )
        except Exception as e:
            raise PermissionError(f"YouTube Music playlist creation rejected by server: {e}")

        if not isinstance(res, str):
            err_msg = res.get("error", {}).get("message") if isinstance(res, dict) else str(res)
            raise ValueError(f"YouTube Music rejected playlist creation: {err_msg}")

        playlist_id = res

        # Append remaining tracks if more than 50
        remaining_ids = video_ids[50:]
        while remaining_ids:
            batch = remaining_ids[:50]
            try:
                self._auth_client.add_playlist_items(playlist_id, batch)
            except Exception as e:
                logger.warning(f"Error adding batch to YTMusic playlist: {e}")
            remaining_ids = remaining_ids[50:]

        playlist_url = f"https://music.youtube.com/playlist?list={playlist_id}"
        logger.info(f"Successfully created YouTube Music playlist: {title} ({playlist_id})")
        return playlist_id, playlist_url
