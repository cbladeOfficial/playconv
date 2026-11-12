"""
Spotify Platform Adapter.
Supports reading public playlists, albums, and tracks (via official Spotipy or zero-config Embed scraper),
searching tracks by title, artist, or ISRC, and creating playlists via Spotify OAuth.
"""

import json
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

from ..config import config
from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)

SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private user-library-read"
EMBED_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


class SpotifyPlatform(BasePlatform):
    """Platform implementation for Spotify."""

    platform_type = PlatformType.SPOTIFY

    def __init__(self):
        self._sp_client: Optional[spotipy.Spotify] = None
        self._sp_oauth_client: Optional[spotipy.Spotify] = None
        self._init_clients()

    def _init_clients(self) -> None:
        client_id = config.spotify_client_id
        client_secret = config.spotify_client_secret

        if client_id and client_secret:
            try:
                # Client credentials for read/search
                cred_mgr = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
                self._sp_client = spotipy.Spotify(client_credentials_manager=cred_mgr)
            except Exception as e:
                logger.warning(f"Could not init Spotify client credentials: {e}")

            try:
                # OAuth client for user playlist creation
                oauth_mgr = SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=config.spotify_redirect_uri,
                    scope=SPOTIFY_SCOPES,
                    cache_path=config.spotify_token_cache,
                    open_browser=False,
                )
                # Check if token exists in cache
                token_info = oauth_mgr.get_cached_token()
                if token_info:
                    self._sp_oauth_client = spotipy.Spotify(auth_manager=oauth_mgr)
            except Exception as e:
                logger.debug(f"Spotify OAuth cached token not ready: {e}")

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()

        # Handle URI: spotify:track:..., spotify:album:..., spotify:playlist:...
        if raw_input.startswith("spotify:"):
            parts = raw_input.split(":")
            if len(parts) >= 3:
                ctype_str = parts[1].lower()
                token = parts[2]
                if ctype_str == "playlist":
                    return True, ContentType.PLAYLIST, token
                elif ctype_str == "album":
                    return True, ContentType.ALBUM, token
                elif ctype_str == "track":
                    return True, ContentType.TRACK, token
            return True, ContentType.UNKNOWN, raw_input

        if "spotify.com" not in raw_input:
            return False, ContentType.UNKNOWN, ""

        parsed = urllib.parse.urlparse(raw_input)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not parts:
            return True, ContentType.UNKNOWN, ""

        # Check for embed/track/... or track/...
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

    def _fetch_embed_data(self, content_type_str: str, spotify_id: str) -> Dict[str, Any]:
        """Fetches and parses public __NEXT_DATA__ JSON from Spotify Embed."""
        url = f"https://open.spotify.com/embed/{content_type_str}/{spotify_id}"
        resp = requests.get(url, headers=EMBED_HEADERS, timeout=15)
        resp.raise_for_status()
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text)
        if not match:
            raise ValueError(f"Could not extract embed metadata from Spotify {url}")
        data = json.loads(match.group(1))
        return data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, playlist_id = self.can_handle_url(identifier_or_url)
        playlist_id = playlist_id or identifier_or_url.strip()

        # If Spotify API client is available, use it (supports pagination > 100 tracks)
        client = self._sp_oauth_client or self._sp_client
        if client:
            try:
                pl_data = client.playlist(playlist_id, fields="name,description,owner,images,tracks.total")
                title = pl_data.get("name") or "Spotify Playlist"
                desc = pl_data.get("description") or ""
                owner = pl_data.get("owner", {}).get("display_name") or ""
                imgs = pl_data.get("images", [])
                img_url = imgs[0].get("url") if imgs else ""

                tracks: List[Track] = []
                results = client.playlist_items(playlist_id, additional_types=("track",))
                while results:
                    for i, item in enumerate(results.get("items", []), start=len(tracks) + 1):
                        tr = item.get("track")
                        if not tr or not tr.get("id"):
                            continue
                        artists_list = [a.get("name") for a in tr.get("artists", []) if a.get("name")]
                        album_name = tr.get("album", {}).get("name") or ""
                        album_art = tr.get("album", {}).get("images", [{}])[0].get("url", "")
                        dur_sec = int(tr.get("duration_ms", 0) // 1000)
                        isrc = tr.get("external_ids", {}).get("isrc")
                        release_date = tr.get("album", {}).get("release_date")
                        year_val = int(release_date[:4]) if (release_date and len(release_date) >= 4 and release_date[:4].isdigit()) else None

                        tracks.append(
                            Track(
                                title=tr.get("name") or "",
                                artists=artists_list,
                                primary_artist=artists_list[0] if artists_list else "",
                                album=album_name,
                                duration_sec=dur_sec,
                                year=year_val,
                                release_date=release_date,
                                isrc=isrc,
                                track_number=i,
                                source_platform=PlatformType.SPOTIFY,
                                source_id=tr.get("id"),
                                source_url=f"https://open.spotify.com/track/{tr.get('id')}",
                                image_url=album_art,
                            )
                        )
                    if results.get("next"):
                        results = client.next(results)
                    else:
                        break

                return PlaylistMetadata(
                    title=title,
                    description=desc,
                    author=owner,
                    total_tracks=len(tracks),
                    source_platform=PlatformType.SPOTIFY,
                    content_type=ContentType.PLAYLIST,
                    source_url=f"https://open.spotify.com/playlist/{playlist_id}",
                    image_url=img_url,
                    tracks=tracks,
                )
            except Exception as e:
                logger.warning(f"Spotify API client error: {e}; falling back to Embed scraper")

        # Fallback to Embed Scraper
        entity = self._fetch_embed_data("playlist", playlist_id)
        title = entity.get("title") or entity.get("name") or "Spotify Playlist"
        desc = entity.get("subtitle") or ""
        imgs = entity.get("visualIdentity", {}).get("image", [])
        img_url = imgs[0].get("url") if imgs else ""
        raw_list = entity.get("trackList", [])

        tracks = []
        for i, tr in enumerate(raw_list, start=1):
            t_title = tr.get("title") or ""
            artist_str = tr.get("subtitle") or ""
            artists_list = [a.strip() for a in artist_str.split(",") if a.strip()]
            dur_ms = tr.get("duration") or 0
            dur_sec = int(dur_ms // 1000)
            uri = tr.get("uri", "")
            tid = uri.split(":")[-1] if ":" in uri else ""

            tracks.append(
                Track(
                    title=t_title,
                    artists=artists_list,
                    primary_artist=artists_list[0] if artists_list else "",
                    duration_sec=dur_sec,
                    track_number=i,
                    source_platform=PlatformType.SPOTIFY,
                    source_id=tid,
                    source_url=f"https://open.spotify.com/track/{tid}" if tid else "",
                )
            )

        return PlaylistMetadata(
            title=title,
            description=desc,
            total_tracks=len(tracks),
            source_platform=PlatformType.SPOTIFY,
            content_type=ContentType.PLAYLIST,
            source_url=f"https://open.spotify.com/playlist/{playlist_id}",
            image_url=img_url,
            tracks=tracks,
        )

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, album_id = self.can_handle_url(identifier_or_url)
        album_id = album_id or identifier_or_url.strip()

        client = self._sp_oauth_client or self._sp_client
        if client:
            try:
                alb = client.album(album_id)
                title = alb.get("name") or "Spotify Album"
                artists_list = [a.get("name") for a in alb.get("artists", []) if a.get("name")]
                author = ", ".join(artists_list)
                release_date = alb.get("release_date")
                year_val = int(release_date[:4]) if (release_date and len(release_date) >= 4 and release_date[:4].isdigit()) else None
                imgs = alb.get("images", [])
                img_url = imgs[0].get("url") if imgs else ""

                tracks: List[Track] = []
                results = alb.get("tracks", {})
                while results:
                    for i, tr in enumerate(results.get("items", []), start=len(tracks) + 1):
                        t_artists = [a.get("name") for a in tr.get("artists", []) if a.get("name")]
                        dur_sec = int(tr.get("duration_ms", 0) // 1000)
                        tracks.append(
                            Track(
                                title=tr.get("name") or "",
                                artists=t_artists,
                                primary_artist=t_artists[0] if t_artists else "",
                                album=title,
                                duration_sec=dur_sec,
                                year=year_val,
                                release_date=release_date,
                                track_number=i,
                                source_platform=PlatformType.SPOTIFY,
                                source_id=tr.get("id"),
                                source_url=f"https://open.spotify.com/track/{tr.get('id')}",
                                image_url=img_url,
                            )
                        )
                    if results.get("next"):
                        results = client.next(results)
                    else:
                        break

                return PlaylistMetadata(
                    title=title,
                    author=author,
                    total_tracks=len(tracks),
                    source_platform=PlatformType.SPOTIFY,
                    content_type=ContentType.ALBUM,
                    source_url=f"https://open.spotify.com/album/{album_id}",
                    image_url=img_url,
                    tracks=tracks,
                )
            except Exception as e:
                logger.warning(f"Spotify album API call failed: {e}; falling back to Embed")

        entity = self._fetch_embed_data("album", album_id)
        title = entity.get("title") or entity.get("name") or "Spotify Album"
        raw_list = entity.get("trackList", [])
        tracks = []
        for i, tr in enumerate(raw_list, start=1):
            t_title = tr.get("title") or ""
            artist_str = tr.get("subtitle") or ""
            artists_list = [a.strip() for a in artist_str.split(",") if a.strip()]
            dur_ms = tr.get("duration") or 0
            dur_sec = int(dur_ms // 1000)
            uri = tr.get("uri", "")
            tid = uri.split(":")[-1] if ":" in uri else ""

            tracks.append(
                Track(
                    title=t_title,
                    artists=artists_list,
                    primary_artist=artists_list[0] if artists_list else "",
                    album=title,
                    duration_sec=dur_sec,
                    track_number=i,
                    source_platform=PlatformType.SPOTIFY,
                    source_id=tid,
                    source_url=f"https://open.spotify.com/track/{tid}" if tid else "",
                )
            )

        return PlaylistMetadata(
            title=title,
            total_tracks=len(tracks),
            source_platform=PlatformType.SPOTIFY,
            content_type=ContentType.ALBUM,
            source_url=f"https://open.spotify.com/album/{album_id}",
            tracks=tracks,
        )

    def fetch_track(self, identifier_or_url: str) -> Track:
        _, _, track_id = self.can_handle_url(identifier_or_url)
        track_id = track_id or identifier_or_url.strip()

        client = self._sp_oauth_client or self._sp_client
        if client:
            try:
                tr = client.track(track_id)
                artists_list = [a.get("name") for a in tr.get("artists", []) if a.get("name")]
                album_name = tr.get("album", {}).get("name") or ""
                album_art = tr.get("album", {}).get("images", [{}])[0].get("url", "")
                dur_sec = int(tr.get("duration_ms", 0) // 1000)
                isrc = tr.get("external_ids", {}).get("isrc")
                release_date = tr.get("album", {}).get("release_date")
                year_val = int(release_date[:4]) if (release_date and len(release_date) >= 4 and release_date[:4].isdigit()) else None

                return Track(
                    title=tr.get("name") or "",
                    artists=artists_list,
                    primary_artist=artists_list[0] if artists_list else "",
                    album=album_name,
                    duration_sec=dur_sec,
                    year=year_val,
                    release_date=release_date,
                    isrc=isrc,
                    source_platform=PlatformType.SPOTIFY,
                    source_id=tr.get("id"),
                    source_url=f"https://open.spotify.com/track/{tr.get('id')}",
                    image_url=album_art,
                )
            except Exception as e:
                logger.warning(f"Spotify track API error: {e}; falling back to embed")

        entity = self._fetch_embed_data("track", track_id)
        title = entity.get("title") or entity.get("name") or ""
        raw_artists = entity.get("artists", [])
        artists_list = [a.get("name") for a in raw_artists if a.get("name")]
        dur_ms = entity.get("duration") or 0
        dur_sec = int(dur_ms // 1000)

        return Track(
            title=title,
            artists=artists_list,
            primary_artist=artists_list[0] if artists_list else "",
            duration_sec=dur_sec,
            source_platform=PlatformType.SPOTIFY,
            source_id=track_id,
            source_url=f"https://open.spotify.com/track/{track_id}",
        )

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        client = self._sp_oauth_client or self._sp_client
        if not client:
            logger.warning("Spotify client credentials needed for Spotify search. Configure via: playconv auth spotify")
            return []

        candidates: List[Track] = []

        # 1. Search by ISRC if available
        if track.isrc:
            try:
                res = client.search(q=f"isrc:{track.isrc.strip()}", type="track", limit=2)
                for tr in res.get("tracks", {}).get("items", []):
                    artists_list = [a.get("name") for a in tr.get("artists", []) if a.get("name")]
                    candidates.append(
                        Track(
                            title=tr.get("name") or "",
                            artists=artists_list,
                            primary_artist=artists_list[0] if artists_list else "",
                            album=tr.get("album", {}).get("name") or "",
                            duration_sec=int(tr.get("duration_ms", 0) // 1000),
                            isrc=tr.get("external_ids", {}).get("isrc"),
                            source_platform=PlatformType.SPOTIFY,
                            source_id=tr.get("id"),
                            source_url=f"https://open.spotify.com/track/{tr.get('id')}",
                        )
                    )
            except Exception as e:
                logger.debug(f"ISRC search failed on Spotify: {e}")

        # 2. Search by title + artist
        from ..matcher import clean_title
        cleaned = clean_title(track.title)
        primary = track.primary_artist or (track.artists[0] if track.artists else "")
        query = f"track:{cleaned} artist:{primary}" if primary else cleaned
        try:
            res = client.search(q=query, type="track", limit=limit)
            items = res.get("tracks", {}).get("items", [])
            if not items:
                # Broader search without field filters
                res = client.search(q=f"{cleaned} {primary}".strip(), type="track", limit=limit)
                items = res.get("tracks", {}).get("items", [])

            for tr in items:
                artists_list = [a.get("name") for a in tr.get("artists", []) if a.get("name")]
                candidates.append(
                    Track(
                        title=tr.get("name") or "",
                        artists=artists_list,
                        primary_artist=artists_list[0] if artists_list else "",
                        album=tr.get("album", {}).get("name") or "",
                        duration_sec=int(tr.get("duration_ms", 0) // 1000),
                        isrc=tr.get("external_ids", {}).get("isrc"),
                        source_platform=PlatformType.SPOTIFY,
                        source_id=tr.get("id"),
                        source_url=f"https://open.spotify.com/track/{tr.get('id')}",
                    )
                )
        except Exception as e:
            logger.error(f"Spotify search failed for '{query}': {e}")

        return candidates

    def is_authenticated_for_writing(self) -> bool:
        self._init_clients()
        if not self._sp_oauth_client:
            return False
        try:
            self._sp_oauth_client.me()
            return True
        except Exception:
            return False

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        if not self.is_authenticated_for_writing():
            raise PermissionError(
                "Spotify playlist creation requires user OAuth authentication.\n"
                "Please configure Spotify credentials using: playconv auth spotify"
            )

        user_info = self._sp_oauth_client.me()
        user_id = user_info["id"]
        desc = description or "Created with PlayConv"

        # Create playlist
        new_pl = self._sp_oauth_client.user_playlist_create(
            user=user_id,
            name=title,
            public=True,
            description=desc,
        )
        playlist_id = new_pl["id"]
        playlist_url = new_pl.get("external_urls", {}).get("spotify") or f"https://open.spotify.com/playlist/{playlist_id}"

        # Collect track URIs
        track_uris = []
        for t in tracks:
            if t.source_id:
                track_uris.append(f"spotify:track:{t.source_id}")

        if not track_uris:
            raise ValueError("No valid Spotify track IDs found to add to playlist.")

        # Batch add items in chunks of 100 (Spotify API limit)
        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i : i + 100]
            self._sp_oauth_client.playlist_add_items(playlist_id, chunk)

        logger.info(f"Successfully created Spotify playlist: {title} ({playlist_id})")
        return playlist_id, playlist_url
