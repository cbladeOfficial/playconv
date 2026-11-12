"""
Unit tests for platform identification and link resolution.
"""

from playconv.models import ContentType, PlatformType
from playconv.platforms import identify_source


def test_spotify_url_identification():
    p, c, t = identify_source("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    assert p == PlatformType.SPOTIFY
    assert c == ContentType.PLAYLIST
    assert t == "37i9dQZF1DXcBWIGoYBM5M"

    p, c, t = identify_source("https://open.spotify.com/album/4cOdK2wGLETKBW3PvgPWqT")
    assert p == PlatformType.SPOTIFY
    assert c == ContentType.ALBUM
    assert t == "4cOdK2wGLETKBW3PvgPWqT"

    p, c, t = identify_source("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc")
    assert p == PlatformType.SPOTIFY
    assert c == ContentType.TRACK
    assert t == "4cOdK2wGLETKBW3PvgPWqT"

    p, c, t = identify_source("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
    assert p == PlatformType.SPOTIFY
    assert c == ContentType.TRACK
    assert t == "4cOdK2wGLETKBW3PvgPWqT"


def test_ytmusic_url_identification():
    p, c, t = identify_source("https://music.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj")
    assert p == PlatformType.YTMUSIC
    assert c == ContentType.PLAYLIST
    assert t == "PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"

    p, c, t = identify_source("https://music.youtube.com/watch?v=NJAv_7lHUIU")
    assert p == PlatformType.YTMUSIC
    assert c == ContentType.TRACK
    assert t == "NJAv_7lHUIU"


def test_jiosaavn_url_identification():
    p, c, t = identify_source("https://www.jiosaavn.com/song/kesariya/AgIAQyBeWlI")
    assert p == PlatformType.JIOSAAVN
    assert c == ContentType.TRACK
    assert t == "AgIAQyBeWlI"

    p, c, t = identify_source("https://www.jiosaavn.com/album/brahmastra/xq4v9ZFC9iA_")
    assert p == PlatformType.JIOSAAVN
    assert c == ContentType.ALBUM
    assert t == "xq4v9ZFC9iA_"

    p, c, t = identify_source("https://www.jiosaavn.com/featured/todays-top-hits/Iz0pi7nkjUHfemJ68FuXsA__")
    assert p == PlatformType.JIOSAAVN
    assert c == ContentType.PLAYLIST


def test_deezer_url_identification():
    p, c, t = identify_source("https://www.deezer.com/track/3135556")
    assert p == PlatformType.DEEZER
    assert c == ContentType.TRACK
    assert t == "3135556"

    p, c, t = identify_source("https://www.deezer.com/playlist/908622995")
    assert p == PlatformType.DEEZER
    assert c == ContentType.PLAYLIST


def test_csv_identification():
    p, c, t = identify_source("my_playlist.csv")
    assert p == PlatformType.CSV
    assert c == ContentType.CSV_FILE
