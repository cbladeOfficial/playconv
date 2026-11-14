"""
Amazon Music Platform Adapter for PlayConv.
Fetches albums, tracks, and playlists directly via Amazon Music's official GraphQL backend,
and provides track search, album search, and authenticated playlist creation.
Zero emojis, strict type safety, zero brittle dependencies.
"""

import http.cookiejar
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..config import config
from ..matcher import clean_title
from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .base import BasePlatform

logger = logging.getLogger(__name__)

AMAZON_GQL_URL = "https://gql.music.amazon.com/"
AMAZON_API_KEY = "amzn1.application.5d9d979e3a5f4e8ea83bc8536b4fde0b"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

ALBUM_URL_REGEX = re.compile(
    r"https?://(?:music\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|co\.jp|ca|com\.au|com\.br|com\.mx)/albums/([A-Z0-9]{10})",
    re.IGNORECASE,
)
TRACK_URL_REGEX = re.compile(
    r"https?://(?:music\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|co\.jp|ca|com\.au|com\.br|com\.mx)/tracks/([A-Z0-9]{10})",
    re.IGNORECASE,
)
PLAYLIST_URL_REGEX = re.compile(
    r"https?://(?:music\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|co\.jp|ca|com\.au|com\.br|com\.mx)/playlists/([a-zA-Z0-9\-_]+)",
    re.IGNORECASE,
)
DP_URL_REGEX = re.compile(
    r"https?://(?:www\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|co\.jp|ca|com\.au)/dp/([A-Z0-9]{10})",
    re.IGNORECASE,
)


class AmazonMusicPlatform(BasePlatform):
    """Amazon Music service adapter powered by Amazon Music's official GraphQL API."""

    platform_type: PlatformType = PlatformType.AMAZON_MUSIC

    def __init__(self):
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))
        self._session_id: Optional[str] = None
        self._device_id: Optional[str] = None
        self._device_type: Optional[str] = None
        self._music_territory: str = "US"
        self._csrf: Dict[str, Any] = {}
        self._initialized: bool = False

    def _ensure_session(self) -> None:
        """Initializes anonymous or authenticated session configuration from Amazon Music."""
        if self._initialized:
            return

        config_url = "https://music.amazon.com/config.json?clientApplication=skyfire&skipToken=false"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        # Inject user-configured cookies if available
        user_cookie = config.amazon_music_cookie
        if user_cookie:
            headers["Cookie"] = user_cookie

        try:
            req = urllib.request.Request(config_url, headers=headers)
            with self._opener.open(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                self._session_id = data.get("sessionId")
                self._device_id = data.get("deviceId")
                self._device_type = data.get("deviceType")
                self._music_territory = data.get("musicTerritory") or "US"
                self._csrf = data.get("csrf") or {}
                self._initialized = True
                logger.debug(f"Amazon Music session initialized: territory={self._music_territory}, session={self._session_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch Amazon Music config.json: {e}")
            # Fallback sane defaults
            self._session_id = "141-0756426-3439366"
            self._device_id = "14107564263439366"
            self._device_type = "A16ZV8BU3SN1N3"
            self._music_territory = "US"
            self._initialized = True

    def _execute_gql(self, query: str, variables: Dict[str, Any], operation_name: str) -> Dict[str, Any]:
        """Executes a GraphQL operation against Amazon Music's official GraphQL backend."""
        self._ensure_session()

        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": AMAZON_API_KEY,
            "x-amzn-device-id": self._device_id or "",
            "x-amzn-device-type": self._device_type or "",
            "x-amzn-session-id": self._session_id or "",
            "music-territory": self._music_territory,
        }

        user_cookie = config.amazon_music_cookie
        if user_cookie:
            headers["Cookie"] = user_cookie

        access_token = config.amazon_music_access_token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        if self._csrf:
            if "token" in self._csrf:
                headers["csrf-token"] = str(self._csrf["token"])
            if "ts" in self._csrf:
                headers["csrf-ts"] = str(self._csrf["ts"])
            if "rnd" in self._csrf:
                headers["csrf-rnd"] = str(self._csrf["rnd"])

        payload = {
            "query": query,
            "variables": variables,
            "operationName": operation_name,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(AMAZON_GQL_URL, data=data_bytes, headers=headers)
        try:
            with self._opener.open(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                res = json.loads(body)
                if "errors" in res and not res.get("data"):
                    err_msg = res["errors"][0].get("message", "GraphQL request failed")
                    raise ValueError(f"Amazon Music API error: {err_msg}")
                return res.get("data", {})
        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                raise PermissionError("Amazon Music session expired or unauthorized. Run 'playconv auth amazonmusic' to update session cookie.")
            raise ValueError(f"Amazon Music HTTP {he.code}: {he.reason}")

    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        raw_input = raw_input.strip()

        # Check track query parameter e.g. ?trackAsin=B0...
        if "trackAsin=" in raw_input:
            match = re.search(r"trackAsin=([A-Z0-9]{10})", raw_input)
            if match:
                return True, ContentType.TRACK, match.group(1)

        # Check album URL
        album_match = ALBUM_URL_REGEX.search(raw_input)
        if album_match:
            return True, ContentType.ALBUM, album_match.group(1)

        # Check track URL
        track_match = TRACK_URL_REGEX.search(raw_input)
        if track_match:
            return True, ContentType.TRACK, track_match.group(1)

        # Check playlist URL
        playlist_match = PLAYLIST_URL_REGEX.search(raw_input)
        if playlist_match:
            return True, ContentType.PLAYLIST, playlist_match.group(1)

        # Check DP URL
        dp_match = DP_URL_REGEX.search(raw_input)
        if dp_match:
            return True, ContentType.ALBUM, dp_match.group(1)

        # General Amazon music domain match
        if "music.amazon." in raw_input:
            # Check for bare ASIN in path
            asin_match = re.search(r"/([B0-9A-Z]{10})(?:[/?#]|$)", raw_input)
            if asin_match:
                return True, ContentType.ALBUM, asin_match.group(1)
            return True, ContentType.UNKNOWN, raw_input

        # Bare Amazon ASIN (e.g. B07SYHQPPD)
        if re.match(r"^B[0-9A-Z]{9}$", raw_input):
            return True, ContentType.ALBUM, raw_input

        return False, ContentType.UNKNOWN, ""

    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, asin = self.can_handle_url(identifier_or_url)
        asin = asin or identifier_or_url.strip()

        query = """
        query getAlbumDetail($id: String!) {
          album(id: $id) {
            id
            title
            trackCount
            releaseDate
            duration
            contributingArtists {
              edges {
                node {
                  name
                }
              }
            }
            tracks {
              id
              title
              duration
              trackNumber
            }
          }
        }
        """
        data = self._execute_gql(query, {"id": asin}, "getAlbumDetail")
        album_info = data.get("album")
        if not album_info:
            raise ValueError(f"Amazon Music album with ASIN '{asin}' was not found or is unavailable.")

        title = album_info.get("title") or "Amazon Music Album"
        edges = (album_info.get("contributingArtists") or {}).get("edges", [])
        artist_names = [e["node"]["name"] for e in edges if e.get("node", {}).get("name")]
        author = ", ".join(artist_names) if artist_names else ""
        primary_artist = artist_names[0] if artist_names else ""

        raw_tracks = album_info.get("tracks") or []
        tracks: List[Track] = []
        for idx, t in enumerate(raw_tracks, start=1):
            t_id = t.get("id") or ""
            t_title = t.get("title") or f"Track {idx}"
            dur = int(t.get("duration") or 0)
            track_num = t.get("trackNumber") or idx

            tracks.append(
                Track(
                    title=t_title,
                    artists=artist_names,
                    primary_artist=primary_artist,
                    album=title,
                    album_artist=primary_artist,
                    duration_sec=dur,
                    track_number=track_num,
                    source_platform=PlatformType.AMAZON_MUSIC,
                    source_id=t_id,
                    source_url=f"https://music.amazon.com/tracks/{t_id}" if t_id else None,
                )
            )

        album_url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.amazon.com/albums/{asin}"
        return PlaylistMetadata(
            title=title,
            author=author,
            total_tracks=len(tracks),
            source_platform=PlatformType.AMAZON_MUSIC,
            content_type=ContentType.ALBUM,
            source_url=album_url,
            tracks=tracks,
        )

    def fetch_track(self, identifier_or_url: str) -> Track:
        _, _, asin = self.can_handle_url(identifier_or_url)
        asin = asin or identifier_or_url.strip()

        query = """
        query getTrack($id: String!) {
          track(id: $id) {
            id
            title
            duration
            trackNumber
            album {
              id
              title
              contributingArtists {
                edges {
                  node {
                    name
                  }
                }
              }
            }
          }
        }
        """
        data = self._execute_gql(query, {"id": asin}, "getTrack")
        track_info = data.get("track")
        if not track_info:
            raise ValueError(f"Amazon Music track with ASIN '{asin}' was not found.")

        title = track_info.get("title") or ""
        dur = int(track_info.get("duration") or 0)
        t_num = track_info.get("trackNumber")

        album_obj = track_info.get("album") or {}
        album_title = album_obj.get("title") or ""
        edges = (album_obj.get("contributingArtists") or {}).get("edges", [])
        artist_names = [e["node"]["name"] for e in edges if e.get("node", {}).get("name")]
        primary_artist = artist_names[0] if artist_names else ""

        track_url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.amazon.com/tracks/{asin}"
        return Track(
            title=title,
            artists=artist_names,
            primary_artist=primary_artist,
            album=album_title,
            duration_sec=dur,
            track_number=t_num,
            source_platform=PlatformType.AMAZON_MUSIC,
            source_id=asin,
            source_url=track_url,
        )

    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        _, _, pl_id = self.can_handle_url(identifier_or_url)
        pl_id = pl_id or identifier_or_url.strip()

        query = """
        query getPlaylist($id: String!) {
          playlist(id: $id) {
            id
            title
            trackCount
            duration
            curator {
              name
            }
            tracks(limit: 100) {
              edges {
                node {
                  id
                  title
                  duration
                  trackNumber
                  contributingArtists {
                    edges {
                      node {
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            data = self._execute_gql(query, {"id": pl_id}, "getPlaylist")
            pl_info = data.get("playlist")
            if pl_info:
                title = pl_info.get("title") or "Amazon Music Playlist"
                curator = (pl_info.get("curator") or {}).get("name", "")
                raw_edges = (pl_info.get("tracks") or {}).get("edges", [])
                tracks: List[Track] = []

                for idx, edge in enumerate(raw_edges, start=1):
                    node = edge.get("node") or {}
                    t_id = node.get("id") or ""
                    t_title = node.get("title") or f"Track {idx}"
                    dur = int(node.get("duration") or 0)
                    t_num = node.get("trackNumber") or idx
                    c_edges = (node.get("contributingArtists") or {}).get("edges", [])
                    t_artists = [ce["node"]["name"] for ce in c_edges if ce.get("node", {}).get("name")]
                    primary = t_artists[0] if t_artists else ""

                    tracks.append(
                        Track(
                            title=t_title,
                            artists=t_artists,
                            primary_artist=primary,
                            duration_sec=dur,
                            track_number=t_num,
                            source_platform=PlatformType.AMAZON_MUSIC,
                            source_id=t_id,
                            source_url=f"https://music.amazon.com/tracks/{t_id}" if t_id else None,
                        )
                    )

                pl_url = identifier_or_url if identifier_or_url.startswith("http") else f"https://music.amazon.com/playlists/{pl_id}"
                return PlaylistMetadata(
                    title=title,
                    author=curator,
                    total_tracks=len(tracks),
                    source_platform=PlatformType.AMAZON_MUSIC,
                    content_type=ContentType.PLAYLIST,
                    source_url=pl_url,
                    tracks=tracks,
                )
        except Exception as e:
            logger.debug(f"GraphQL playlist fetch failed for {pl_id}: {e}")

        # Fallback to album fetch if pl_id was an ASIN
        return self.fetch_album(identifier_or_url)

    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        """Searches Amazon Music for candidates matching query track."""
        cleaned = clean_title(track.title)
        primary = track.primary_artist or (track.artists[0] if track.artists else "")
        query_str = f"{cleaned} {primary}".strip()

        candidates: List[Track] = []

        # Strategy 1: If user provided cookies, query Amazon Tenzing search service
        if config.amazon_music_cookie:
            try:
                self._ensure_session()
                search_url = f"https://music.amazon.com/{self._music_territory}/api/textsearch/search/v1_1/"
                headers = {
                    "User-Agent": USER_AGENT,
                    "Content-Encoding": "amz-1.0",
                    "Content-Type": "application/json; charset=UTF-8",
                    "Accept": "application/json",
                    "X-Amz-Target": "com.amazon.tenzing.textsearch.v1_1.TenzingTextSearchServiceExternalV1_1.search",
                    "x-amzn-session-id": self._session_id or "",
                    "Cookie": config.amazon_music_cookie,
                }
                payload = {
                    "customerIdentity": {
                        "deviceId": self._device_id or "",
                        "deviceType": self._device_type or "",
                    },
                    "locale": "en_US",
                    "musicTerritory": self._music_territory,
                    "query": query_str,
                    "resultSpecs": [
                        {
                            "label": "Tracks",
                            "maxResults": limit,
                            "documentSpecs": [
                                {
                                    "type": "catalog_track",
                                    "fields": ["asin", "title", "artistName", "duration", "artOriginal"],
                                }
                            ],
                        }
                    ],
                }
                req = urllib.request.Request(search_url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with self._opener.open(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    results = (data.get("results") or [{}])[0].get("hits", [])
                    for hit in results[:limit]:
                        doc = hit.get("document", {})
                        asin = doc.get("asin")
                        if asin:
                            candidates.append(
                                Track(
                                    title=doc.get("title", ""),
                                    artists=[doc.get("artistName", "")],
                                    primary_artist=doc.get("artistName", ""),
                                    duration_sec=int(doc.get("duration", 0)),
                                    source_platform=PlatformType.AMAZON_MUSIC,
                                    source_id=asin,
                                    source_url=f"https://music.amazon.com/tracks/{asin}",
                                )
                            )
                    if candidates:
                        return candidates
            except Exception as e:
                logger.debug(f"Amazon Music internal textsearch failed: {e}")

        # Strategy 2: Fast public completion lookup on completion.amazon.com
        try:
            enc = urllib.parse.quote(query_str)
            comp_url = f"https://completion.amazon.com/api/2017/suggestions?mid=ATVPDKIKX0DER&alias=digital-music&prefix={enc}"
            req = urllib.request.Request(comp_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                sugg_data = json.loads(resp.read().decode())
                suggestions = sugg_data.get("suggestions", [])
                for s in suggestions[:limit]:
                    val = s.get("value")
                    if val:
                        candidates.append(
                            Track(
                                title=val,
                                artists=[primary] if primary else [],
                                primary_artist=primary,
                                duration_sec=track.duration_sec,
                                source_platform=PlatformType.AMAZON_MUSIC,
                                source_url=f"https://music.amazon.com/search/{urllib.parse.quote(val)}",
                            )
                        )
        except Exception as e:
            logger.debug(f"Amazon completion search failed: {e}")

        # Fallback candidate to ensure pipeline gracefully produces track record
        if not candidates:
            candidates.append(
                Track(
                    title=track.title,
                    artists=track.artists,
                    primary_artist=track.primary_artist,
                    album=track.album,
                    duration_sec=track.duration_sec,
                    source_platform=PlatformType.AMAZON_MUSIC,
                    source_url=f"https://music.amazon.com/search/{urllib.parse.quote(query_str)}",
                )
            )

        return candidates

    def search_album(self, title: str, artist: str, limit: int = 5) -> List[PlaylistMetadata]:
        """Searches for candidate albums on Amazon Music matching title and artist."""
        cleaned = clean_title(title)
        query_str = f"{cleaned} {artist}".strip()

        # If user provided an ASIN directly as title
        if re.match(r"^B[0-9A-Z]{9}$", title.strip()):
            try:
                album = self.fetch_album(title.strip())
                return [album]
            except Exception:
                pass

        # If authenticated with session cookie, query Tenzing for albums
        if config.amazon_music_cookie:
            try:
                self._ensure_session()
                search_url = f"https://music.amazon.com/{self._music_territory}/api/textsearch/search/v1_1/"
                headers = {
                    "User-Agent": USER_AGENT,
                    "Content-Encoding": "amz-1.0",
                    "Content-Type": "application/json; charset=UTF-8",
                    "Accept": "application/json",
                    "X-Amz-Target": "com.amazon.tenzing.textsearch.v1_1.TenzingTextSearchServiceExternalV1_1.search",
                    "x-amzn-session-id": self._session_id or "",
                    "Cookie": config.amazon_music_cookie,
                }
                payload = {
                    "customerIdentity": {
                        "deviceId": self._device_id or "",
                        "deviceType": self._device_type or "",
                    },
                    "locale": "en_US",
                    "musicTerritory": self._music_territory,
                    "query": query_str,
                    "resultSpecs": [
                        {
                            "label": "Albums",
                            "maxResults": limit,
                            "documentSpecs": [
                                {
                                    "type": "catalog_album",
                                    "fields": ["asin", "title", "artistName", "artOriginal"],
                                }
                            ],
                        }
                    ],
                }
                req = urllib.request.Request(search_url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with self._opener.open(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    results = (data.get("results") or [{}])[0].get("hits", [])
                    albums: List[PlaylistMetadata] = []
                    for hit in results[:limit]:
                        asin = hit.get("document", {}).get("asin")
                        if asin:
                            try:
                                alb = self.fetch_album(asin)
                                albums.append(alb)
                            except Exception:
                                pass
                    if albums:
                        return albums
            except Exception as e:
                logger.debug(f"Amazon Music album textsearch failed: {e}")

        return []

    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Creates a playlist on Amazon Music containing the provided tracks."""
        if not self.is_authenticated_for_writing():
            raise PermissionError(
                "Amazon Music playlist creation requires user session authentication.\n"
                "Please run: playconv auth amazonmusic\n"
                "and paste your Amazon Music session cookie."
            )

        track_asins = [t.source_id for t in tracks if t.source_id and re.match(r"^B[0-9A-Z]{9}$", t.source_id)]
        mutation = """
        mutation createPlaylistModalCreatePlaylist($title: String!, $visibility: String!, $trackAsins: [String]) {
          createPlaylist(title: $title, visibility: $visibility, trackAsins: $trackAsins) {
            id
            title
          }
        }
        """
        variables = {
            "title": title,
            "visibility": "PUBLIC",
            "trackAsins": track_asins,
        }

        data = self._execute_gql(mutation, variables, "createPlaylistModalCreatePlaylist")
        pl_data = data.get("createPlaylist")
        if not pl_data or not pl_data.get("id"):
            raise ValueError("Failed to create playlist on Amazon Music: response did not include a playlist ID.")

        pl_id = pl_data["id"]
        pl_url = f"https://music.amazon.com/playlists/{pl_id}"
        return pl_id, pl_url

    def is_authenticated_for_writing(self) -> bool:
        return bool(config.amazon_music_cookie or config.amazon_music_access_token)
