"""
Platform Registry and Universal Link Resolver.
Directs incoming queries, URLs, and file paths to appropriate streaming service adapters.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

from ..csv_handler import CSVHandler
from ..models import ContentType, PlatformType, PlaylistMetadata, Track
from .applemusic import AppleMusicPlatform
from .base import BasePlatform
from .deezer import DeezerPlatform
from .jiosaavn import JioSaavnPlatform
from .spotify import SpotifyPlatform
from .ytmusic import YTMusicPlatform

logger = logging.getLogger(__name__)

PLATFORM_REGISTRY: Dict[PlatformType, BasePlatform] = {
    PlatformType.SPOTIFY: SpotifyPlatform(),
    PlatformType.YTMUSIC: YTMusicPlatform(),
    PlatformType.JIOSAAVN: JioSaavnPlatform(),
    PlatformType.DEEZER: DeezerPlatform(),
    PlatformType.APPLE_MUSIC: AppleMusicPlatform(),
}


def get_platform(ptype: PlatformType) -> BasePlatform:
    """Retrieves adapter instance for the specified platform type."""
    if ptype not in PLATFORM_REGISTRY:
        raise ValueError(f"Unsupported destination platform: {ptype.value}")
    return PLATFORM_REGISTRY[ptype]


def identify_source(raw_input: str) -> Tuple[PlatformType, ContentType, str]:
    """
    Identifies the platform, content type, and identifier for an input URL or path.
    Returns: (platform_type, content_type, token_or_path)
    """
    raw_input = raw_input.strip()

    # Check for CSV file
    if raw_input.endswith(".csv") or ".csv?" in raw_input or raw_input.endswith(".csv/"):
        return PlatformType.CSV, ContentType.CSV_FILE, raw_input
    if os.path.exists(raw_input) and raw_input.lower().endswith(".csv"):
        return PlatformType.CSV, ContentType.CSV_FILE, raw_input

    # Check for M3U file
    if raw_input.endswith(".m3u") or raw_input.endswith(".m3u8"):
        return PlatformType.M3U, ContentType.M3U_FILE, raw_input

    # Check each streaming service adapter
    for ptype, adapter in PLATFORM_REGISTRY.items():
        can_handle, content_type, token = adapter.can_handle_url(raw_input)
        if can_handle:
            return ptype, content_type, token

    return PlatformType.UNKNOWN, ContentType.UNKNOWN, raw_input


def resolve_source_to_playlist(raw_input: str) -> PlaylistMetadata:
    """
    Resolves any input (URL, local CSV/M3U path, or query) into a unified PlaylistMetadata object.
    Supports playlists, albums, single tracks, and CSV files.
    """
    ptype, ctype, token = identify_source(raw_input)

    # 1. Handle CSV
    if ptype == PlatformType.CSV:
        return CSVHandler.import_from_csv(raw_input)

    # 2. Handle Unknown / Search Query
    if ptype == PlatformType.UNKNOWN:
        raise ValueError(
            f"Could not recognize source music platform or file format for:\n{raw_input}\n"
            "Supported platforms: Spotify, YouTube Music, JioSaavn, Deezer, Apple Music, or CSV files."
        )

    adapter = get_platform(ptype)

    # 3. Handle Single Track -> Wrap in a 1-song Playlist
    if ctype == ContentType.TRACK:
        track = adapter.fetch_track(raw_input)
        return PlaylistMetadata(
            title=f"{track.title} - Single",
            author=track.primary_artist,
            total_tracks=1,
            source_platform=ptype,
            content_type=ContentType.TRACK,
            source_url=track.source_url or raw_input,
            image_url=track.image_url,
            tracks=[track],
        )

    # 4. Handle Album
    elif ctype == ContentType.ALBUM:
        return adapter.fetch_album(raw_input)

    # 5. Handle Playlist
    elif ctype == ContentType.PLAYLIST:
        return adapter.fetch_playlist(raw_input)

    # Fallback to playlist
    try:
        return adapter.fetch_playlist(raw_input)
    except Exception:
        return adapter.fetch_album(raw_input)
