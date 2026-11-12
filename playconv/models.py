"""
Data models for PlayConv.
Defines unified representations of Tracks, Playlists, Match Results, and Platform Types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PlatformType(str, Enum):
    SPOTIFY = "spotify"
    YTMUSIC = "ytmusic"
    JIOSAAVN = "jiosaavn"
    APPLE_MUSIC = "applemusic"
    DEEZER = "deezer"
    CSV = "csv"
    M3U = "m3u"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, name: str) -> "PlatformType":
        clean = name.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        if clean in ("spotify", "sp"):
            return cls.SPOTIFY
        elif clean in ("ytmusic", "youtube", "youtubemusic", "ytm", "yt"):
            return cls.YTMUSIC
        elif clean in ("jiosaavn", "saavn", "jio", "js"):
            return cls.JIOSAAVN
        elif clean in ("applemusic", "apple", "itunes"):
            return cls.APPLE_MUSIC
        elif clean in ("deezer", "dz"):
            return cls.DEEZER
        elif clean in ("csv", "excel"):
            return cls.CSV
        elif clean in ("m3u", "m3u8"):
            return cls.M3U
        return cls.UNKNOWN


class ContentType(str, Enum):
    TRACK = "track"
    ALBUM = "album"
    PLAYLIST = "playlist"
    SEARCH = "search"
    CSV_FILE = "csv_file"
    M3U_FILE = "m3u_file"
    UNKNOWN = "unknown"


@dataclass
class Track:
    """Unified cross-platform Track entity."""
    title: str
    artists: List[str] = field(default_factory=list)
    primary_artist: str = ""
    album: str = ""
    album_artist: str = ""
    duration_sec: int = 0
    year: Optional[int] = None
    release_date: Optional[str] = None
    isrc: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    source_platform: PlatformType = PlatformType.UNKNOWN
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    explicit: Optional[bool] = None
    language: Optional[str] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Auto-populate primary_artist if missing
        if not self.primary_artist and self.artists:
            self.primary_artist = self.artists[0].strip()
        elif self.primary_artist and not self.artists:
            self.artists = [a.strip() for a in self.primary_artist.split(",") if a.strip()]

        if not self.album_artist and self.primary_artist:
            self.album_artist = self.primary_artist

    @property
    def artists_string(self) -> str:
        return ", ".join(self.artists) if self.artists else self.primary_artist

    @property
    def formatted_duration(self) -> str:
        if not self.duration_sec or self.duration_sec <= 0:
            return "0:00"
        m = self.duration_sec // 60
        s = self.duration_sec % 60
        if m >= 60:
            h = m // 60
            m = m % 60
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


@dataclass
class MatchResult:
    """Outcome of attempting to match a source track onto a destination platform."""
    source_track: Track
    matched_track: Optional[Track] = None
    confidence_score: float = 0.0
    is_exact: bool = False
    isrc_match: bool = False
    duration_diff_sec: Optional[int] = None
    reason: str = "unmatched"

    @property
    def is_successful(self) -> bool:
        return self.matched_track is not None and self.confidence_score > 0.0


@dataclass
class PlaylistMetadata:
    """Metadata and track list for a collection of songs (playlist, album, or batch)."""
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    total_tracks: int = 0
    source_platform: PlatformType = PlatformType.UNKNOWN
    content_type: ContentType = ContentType.PLAYLIST
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    tracks: List[Track] = field(default_factory=list)

    def __post_init__(self):
        if not self.total_tracks:
            self.total_tracks = len(self.tracks)


@dataclass
class ConversionSummary:
    """Aggregated summary of a playlist conversion run."""
    source_name: str
    destination_platform: PlatformType
    total_tracks: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    exact_match_count: int = 0
    created_playlist_id: Optional[str] = None
    created_playlist_url: Optional[str] = None
    exported_csv_path: Optional[str] = None
    results: List[MatchResult] = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        if self.total_tracks == 0:
            return 0.0
        return (self.matched_count / self.total_tracks) * 100.0
