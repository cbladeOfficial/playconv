"""
Unit tests for CSV import, export, and M3U conversion.
"""

import os
from pathlib import Path
from playconv.csv_handler import CSVHandler, parse_duration_to_seconds
from playconv.models import MatchResult, PlatformType, PlaylistMetadata, Track


def test_parse_duration():
    assert parse_duration_to_seconds(180) == 180
    assert parse_duration_to_seconds("3:45") == 225
    assert parse_duration_to_seconds("1:02:15") == 3735
    assert parse_duration_to_seconds("213000") == 213  # ms to s
    assert parse_duration_to_seconds("") == 0


def test_csv_export_and_import(tmp_path: Path):
    t1 = Track(
        title="Shape of You",
        artists=["Ed Sheeran"],
        primary_artist="Ed Sheeran",
        album="÷ (Divide)",
        duration_sec=233,
        year=2017,
        isrc="GBAHS1600463",
        source_platform=PlatformType.SPOTIFY,
        source_id="7qiZfU4dY1lWllzX7mPBI3",
        source_url="https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3",
    )
    t2 = Track(
        title="Believer",
        artists=["Imagine Dragons"],
        primary_artist="Imagine Dragons",
        album="Evolve",
        duration_sec=204,
        year=2017,
        source_platform=PlatformType.SPOTIFY,
        source_id="0pqnGHJpmpxLKLy7a2wbxo",
    )

    pl = PlaylistMetadata(
        title="Test Hits",
        tracks=[t1, t2],
        source_platform=PlatformType.SPOTIFY,
    )

    csv_path = tmp_path / "test_export.csv"
    exported_file = CSVHandler.export_to_csv(pl, str(csv_path))
    assert os.path.exists(exported_file)

    # Re-import from CSV
    imported_pl = CSVHandler.import_from_csv(exported_file)
    assert len(imported_pl.tracks) == 2
    assert imported_pl.tracks[0].title == "Shape of You"
    assert imported_pl.tracks[0].primary_artist == "Ed Sheeran"
    assert imported_pl.tracks[0].duration_sec == 233
    assert imported_pl.tracks[0].isrc == "GBAHS1600463"
    assert imported_pl.tracks[1].title == "Believer"


def test_m3u_export(tmp_path: Path):
    t1 = Track(title="Song 1", primary_artist="Artist 1", duration_sec=120, source_url="https://music.example.com/1")
    pl = PlaylistMetadata(title="M3U Test", tracks=[t1], source_platform=PlatformType.SPOTIFY)

    m3u_path = tmp_path / "test.m3u8"
    out_file = CSVHandler.export_to_m3u(pl, str(m3u_path))
    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "#EXTM3U" in content
    assert "Artist 1 - Song 1" in content
    assert "https://music.example.com/1" in content
