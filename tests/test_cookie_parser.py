import tempfile
import os
from playconv.config import parse_cookie_input, cookies_to_header_str
from playconv.models import PlatformType, PlaylistMetadata, Track
from playconv.platforms import PLATFORM_REGISTRY
from playconv.converter import PlaylistConverter


def test_parse_cookie_input_header():
    raw = "Cookie: CT=12345; B=abcdef; DL=english"
    parsed = parse_cookie_input(raw)
    assert parsed.get("CT") == "12345"
    assert parsed.get("B") == "abcdef"
    assert parsed.get("DL") == "english"


def test_parse_cookie_input_netscape():
    netscape_content = (
        "# Netscape HTTP Cookie File\n"
        ".jiosaavn.com\tTRUE\t/\tTRUE\t1800000000\tCT\tnetscape_val_1\n"
        ".jiosaavn.com\tTRUE\t/\tTRUE\t1800000000\tB\tnetscape_val_2\n"
    )
    parsed = parse_cookie_input(netscape_content)
    assert parsed.get("CT") == "netscape_val_1"
    assert parsed.get("B") == "netscape_val_2"


def test_parse_cookie_input_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t1800000000\tsession_id\txyz987\n")
        temp_path = f.name

    try:
        parsed = parse_cookie_input(temp_path)
        assert parsed.get("session_id") == "xyz987"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_cookies_to_header_str():
    d = {"key1": "val1", "key2": "val2"}
    h = cookies_to_header_str(d)
    assert "key1=val1" in h
    assert "key2=val2" in h


def test_unauthenticated_conversion_sets_playlist_error(tmp_path, monkeypatch):
    csv_file = tmp_path / "test_source.csv"
    csv_file.write_text("title,artist,duration_sec\nSong Test,Artist Test,180\n", encoding="utf-8")

    converter = PlaylistConverter()
    # Mock search_track to return a matched track so create_playlist is invoked
    dummy_target = Track(title="Song Test", artists=["Artist Test"], duration_sec=180, source_platform=PlatformType.APPLE_MUSIC)
    from playconv.platforms.applemusic import AppleMusicPlatform
    monkeypatch.setattr(AppleMusicPlatform, "search_track", lambda self, tr, limit=6: [dummy_target])

    summary = converter.convert(
        source_input=str(csv_file),
        destination_platform=PlatformType.APPLE_MUSIC,
        create_remote_playlist=True,
        export_csv=False,
    )
    assert summary.playlist_error is not None
    assert "not supported" in summary.playlist_error.lower()
