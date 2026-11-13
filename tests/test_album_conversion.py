"""
Unit tests for album exact match conversion optimization.
Verifies that when an album link is provided, if an exact matching album release
exists on the target platform, that album is directly adopted as the conversion.
"""

from unittest.mock import MagicMock, patch

from playconv.converter import PlaylistConverter
from playconv.models import ContentType, PlatformType, PlaylistMetadata, Track


def _create_sample_album(title: str, artist: str, platform: PlatformType, url: str) -> PlaylistMetadata:
    tracks = [
        Track(
            title="I Forgot That You Existed",
            primary_artist=artist,
            album=title,
            duration_sec=171,
            track_number=1,
            source_platform=platform,
            source_id="t1",
            source_url=f"{url}/track/1",
        ),
        Track(
            title="Cruel Summer",
            primary_artist=artist,
            album=title,
            duration_sec=178,
            track_number=2,
            source_platform=platform,
            source_id="t2",
            source_url=f"{url}/track/2",
        ),
        Track(
            title="Lover",
            primary_artist=artist,
            album=title,
            duration_sec=221,
            track_number=3,
            source_platform=platform,
            source_id="t3",
            source_url=f"{url}/track/3",
        ),
    ]
    return PlaylistMetadata(
        title=title,
        author=artist,
        total_tracks=len(tracks),
        source_platform=platform,
        content_type=ContentType.ALBUM,
        source_url=url,
        tracks=tracks,
    )


def test_exact_album_match_resolution():
    source_album = _create_sample_album(
        title="Lover",
        artist="Taylor Swift",
        platform=PlatformType.SPOTIFY,
        url="https://open.spotify.com/album/1NAmidJlEaVgA3MpcZTqui",
    )

    dest_album = _create_sample_album(
        title="Lover",
        artist="Taylor Swift",
        platform=PlatformType.YTMUSIC,
        url="https://music.youtube.com/playlist?list=OLAK5uy_lover",
    )

    mock_dest_adapter = MagicMock()
    mock_dest_adapter.search_album.return_value = [dest_album]

    converter = PlaylistConverter()
    res = converter._attempt_exact_album_conversion(
        source_playlist=source_album,
        destination_platform=PlatformType.YTMUSIC,
        dest_adapter=mock_dest_adapter,
    )

    assert res is not None
    matched_album, match_results = res
    assert matched_album.title == "Lover"
    assert matched_album.source_url == "https://music.youtube.com/playlist?list=OLAK5uy_lover"
    assert len(match_results) == 3
    assert all(r.is_exact for r in match_results)
    assert all(r.reason == "exact_album_track" for r in match_results)


def test_exact_album_conversion_pipeline():
    source_album = _create_sample_album(
        title="Lover",
        artist="Taylor Swift",
        platform=PlatformType.SPOTIFY,
        url="https://open.spotify.com/album/1NAmidJlEaVgA3MpcZTqui",
    )

    dest_album = _create_sample_album(
        title="Lover",
        artist="Taylor Swift",
        platform=PlatformType.AMAZON_MUSIC,
        url="https://music.amazon.com/albums/B07SYHQPPD",
    )

    mock_dest_adapter = MagicMock()
    mock_dest_adapter.search_album.return_value = [dest_album]

    converter = PlaylistConverter()
    with patch("playconv.converter.resolve_source_to_playlist", return_value=source_album):
        with patch("playconv.converter.get_platform", return_value=mock_dest_adapter):
            summary = converter.convert(
                source_input="https://open.spotify.com/album/1NAmidJlEaVgA3MpcZTqui",
                destination_platform=PlatformType.AMAZON_MUSIC,
                export_csv=False,
                create_remote_playlist=False,
            )

    assert summary.is_exact_album_conversion is True
    assert summary.matched_album_title == "Lover"
    assert summary.matched_album_url == "https://music.amazon.com/albums/B07SYHQPPD"
    assert summary.created_playlist_url == "https://music.amazon.com/albums/B07SYHQPPD"
    assert summary.matched_count == 3
    assert summary.exact_match_count == 3
    assert summary.unmatched_count == 0


def test_non_matching_album_fallback():
    source_album = _create_sample_album(
        title="Lover",
        artist="Taylor Swift",
        platform=PlatformType.SPOTIFY,
        url="https://open.spotify.com/album/1NAmidJlEaVgA3MpcZTqui",
    )

    # Completely different album
    unrelated_album = _create_sample_album(
        title="1989",
        artist="Taylor Swift",
        platform=PlatformType.YTMUSIC,
        url="https://music.youtube.com/playlist?list=OLAK5uy_1989",
    )

    mock_dest_adapter = MagicMock()
    mock_dest_adapter.search_album.return_value = [unrelated_album]

    converter = PlaylistConverter()
    res = converter._attempt_exact_album_conversion(
        source_playlist=source_album,
        destination_platform=PlatformType.YTMUSIC,
        dest_adapter=mock_dest_adapter,
    )

    # Should not match and return None to allow track-by-track fallback
    assert res is None
