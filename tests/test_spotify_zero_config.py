"""
Unit tests for Spotify Zero-Config Mode and Spotify Premium restriction handling.
Verifies that Spotify playlists, albums, and tracks can be fetched without Spotify Premium,
and that 403 / Premium-required API errors are handled gracefully without crashing.
"""

from unittest.mock import MagicMock, PropertyMock, patch
import pytest

from playconv.config import Config, config
from playconv.models import ContentType, PlatformType, Track
from playconv.platforms.spotify import SpotifyPlatform


def test_spotify_zero_config_initialization():
    """Verify SpotifyPlatform initializes cleanly with empty credentials."""
    with patch.object(Config, "spotify_client_id", new_callable=PropertyMock, return_value=""), \
         patch.object(Config, "spotify_client_secret", new_callable=PropertyMock, return_value=""):
        sp = SpotifyPlatform()
        assert sp._sp_client is None
        assert sp._sp_oauth_client is None
        assert not sp._credentials_disabled


def test_spotify_handle_api_error_disables_premium_gated_credentials():
    """Verify that a 403 or Active premium subscription required error disables clients cleanly."""
    sp = SpotifyPlatform()
    sp._sp_client = MagicMock()
    sp._sp_oauth_client = MagicMock()

    err = Exception("HTTP 403: Active premium subscription required for the owner of the app. When the subscription status changes...")
    sp._handle_api_error(err)

    assert sp._credentials_disabled is True
    assert sp._sp_client is None
    assert sp._sp_oauth_client is None


def test_spotify_create_playlist_permission_error_without_premium():
    """Verify that attempting to create a playlist on Spotify without premium raises a clear PermissionError."""
    sp = SpotifyPlatform()
    sp._credentials_disabled = True

    dummy_track = Track(title="Test Song", artists=["Test Artist"], source_id="12345")
    with pytest.raises(PermissionError) as exc_info:
        sp.create_playlist("Test Playlist", [dummy_track])

    assert "Spotify Premium" in str(exc_info.value)
    assert "YouTube Music, JioSaavn, Amazon Music, or CSV" in str(exc_info.value)


def test_spotify_url_parsing():
    """Verify URL detection for playlist, album, and track URLs."""
    sp = SpotifyPlatform()

    ok, ctype, token = sp.can_handle_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123xyz")
    assert ok is True
    assert ctype == ContentType.PLAYLIST
    assert token == "37i9dQZF1DXcBWIGoYBM5M"

    ok, ctype, token = sp.can_handle_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3")
    assert ok is True
    assert ctype == ContentType.ALBUM
    assert token == "1DFixLWuPkv3KT3TnV35m3"

    ok, ctype, token = sp.can_handle_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert ok is True
    assert ctype == ContentType.TRACK
    assert token == "4cOdK2wGLETKBW3PvgPWqT"
