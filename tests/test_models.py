"""
Unit tests for PlayConv models.
"""

from playconv.models import ContentType, MatchResult, PlatformType, PlaylistMetadata, Track


def test_track_initialization():
    t = Track(
        title="Kesariya",
        artists=["Arijit Singh", "Pritam"],
        album="Brahmastra",
        duration_sec=268,
        year=2022,
        source_platform=PlatformType.JIOSAAVN,
    )
    assert t.title == "Kesariya"
    assert t.primary_artist == "Arijit Singh"
    assert t.artists_string == "Arijit Singh, Pritam"
    assert t.formatted_duration == "4:28"


def test_track_single_artist():
    t = Track(
        title="Never Gonna Give You Up",
        primary_artist="Rick Astley",
        duration_sec=213,
    )
    assert t.artists == ["Rick Astley"]
    assert t.primary_artist == "Rick Astley"
    assert t.formatted_duration == "3:33"


def test_platform_type_parsing():
    assert PlatformType.from_string("spotify") == PlatformType.SPOTIFY
    assert PlatformType.from_string("ytmusic") == PlatformType.YTMUSIC
    assert PlatformType.from_string("youtube") == PlatformType.YTMUSIC
    assert PlatformType.from_string("jiosaavn") == PlatformType.JIOSAAVN
    assert PlatformType.from_string("saavn") == PlatformType.JIOSAAVN
    assert PlatformType.from_string("csv") == PlatformType.CSV
    assert PlatformType.from_string("unknown_xyz") == PlatformType.UNKNOWN


def test_playlist_metadata():
    t1 = Track(title="Song 1", duration_sec=180)
    t2 = Track(title="Song 2", duration_sec=200)
    pl = PlaylistMetadata(
        title="My Playlist",
        tracks=[t1, t2],
        source_platform=PlatformType.SPOTIFY,
    )
    assert pl.total_tracks == 2
    assert len(pl.tracks) == 2


def test_match_result():
    s = Track(title="Song", primary_artist="Artist", duration_sec=180)
    m = Track(title="Song", primary_artist="Artist", duration_sec=182)
    res = MatchResult(
        source_track=s,
        matched_track=m,
        confidence_score=0.98,
        is_exact=True,
        duration_diff_sec=2,
    )
    assert res.is_successful is True
    assert res.is_exact is True
