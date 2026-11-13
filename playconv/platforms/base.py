"""
Base Platform Adapter abstract class.
Every music streaming service adapter implements this interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..models import ContentType, PlatformType, PlaylistMetadata, Track


class BasePlatform(ABC):
    """Abstract base class for all music service providers."""

    platform_type: PlatformType = PlatformType.UNKNOWN

    @abstractmethod
    def can_handle_url(self, raw_input: str) -> Tuple[bool, ContentType, str]:
        """
        Determines if this platform can handle the given URL or identifier.
        Returns: (can_handle: bool, content_type: ContentType, identifier: str)
        """
        pass

    @abstractmethod
    def fetch_playlist(self, identifier_or_url: str) -> PlaylistMetadata:
        """Fetches metadata and all tracks for a playlist."""
        pass

    @abstractmethod
    def fetch_album(self, identifier_or_url: str) -> PlaylistMetadata:
        """Fetches metadata and all tracks for an album."""
        pass

    @abstractmethod
    def fetch_track(self, identifier_or_url: str) -> Track:
        """Fetches metadata for a single track."""
        pass

    @abstractmethod
    def search_track(self, track: Track, limit: int = 5) -> List[Track]:
        """Searches for candidate tracks on this platform matching the query track."""
        pass

    def search_album(self, title: str, artist: str, limit: int = 5) -> List[PlaylistMetadata]:
        """
        Searches for candidate albums on this platform matching the given title and artist.
        Returns a list of candidate albums with their track lists populated.
        """
        return []

    @abstractmethod
    def create_playlist(
        self,
        title: str,
        tracks: List[Track],
        description: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Creates a new playlist on the platform containing the given tracks.
        Returns: (created_playlist_id: str, created_playlist_url: str)
        """
        pass

    @abstractmethod
    def is_authenticated_for_writing(self) -> bool:
        """Checks if current credentials allow writing/creating playlists on this platform."""
        pass
