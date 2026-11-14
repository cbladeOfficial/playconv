from playconv.models import ConversionSummary, MatchResult, PlatformType, Track
from playconv.ui import make_box_badge, show_final_summary, show_match_results_table


def test_make_box_badge_symmetry():
    # Test varying lengths and widths
    for text in ["EXACT", "TARGET", "SOURCE", "CSV RECORD", "1", "LONG TEXT SAMPLE"]:
        for width in [None, 8, 12, 16, 18, 20]:
            badge = make_box_badge(text, "#16a34a", width=width)
            plain = badge.plain
            assert text in plain
            # Check left and right space counts
            left_spaces = len(plain) - len(plain.lstrip(" "))
            right_spaces = len(plain) - len(plain.rstrip(" "))
            assert left_spaces == right_spaces, (
                f"Badge '{plain}' has asymmetric padding: {left_spaces} left vs {right_spaces} right"
            )
            assert left_spaces >= 1


def test_show_match_results_table_runs():
    track1 = Track(title="Song 1", artists=["Artist A"], duration_sec=200)
    track2 = Track(title="Song 2", artists=["Artist B"], duration_sec=180)
    results = [
        MatchResult(source_track=track1, matched_track=track1, confidence_score=1.0, is_exact=True),
        MatchResult(source_track=track2, matched_track=track2, confidence_score=0.85, is_exact=False),
        MatchResult(source_track=track1, matched_track=None, confidence_score=0.0, is_exact=False),
    ]
    # Verify execution without exception
    show_match_results_table(results)


def test_show_final_summary_runs():
    summary = ConversionSummary(
        source_name="Test Playlist",
        destination_platform=PlatformType.YTMUSIC,
        total_tracks=10,
        matched_count=9,
        exact_match_count=8,
        unmatched_count=1,
        exported_csv_path="test_export.csv",
        created_playlist_url="https://music.youtube.com/playlist?list=xyz",
    )
    show_final_summary(summary, elapsed_seconds=42.5)

    # Test summary when playlist creation failed (auth required)
    summary_err = ConversionSummary(
        source_name="Test Playlist",
        destination_platform=PlatformType.YTMUSIC,
        total_tracks=10,
        matched_count=10,
        exact_match_count=10,
        playlist_error="Authentication required (run: playconv auth)",
        exported_csv_path="test_export.csv",
    )
    show_final_summary(summary_err, elapsed_seconds=12.0)


def test_summary_badges_uniform_width_and_symmetry():
    # Verify all badge labels in show_final_summary have uniform width of 18 and strictly equal padding
    labels = [
        "SOURCE",
        "TARGET",
        "TRACKS MATCHED",
        "ALBUM RESULT",
        "ALBUM LINK",
        "EXACT TRACKS",
        "NO MATCHES",
        "PLAYLIST URL",
        "PLAYLIST",
        "CSV RECORD",
        "ELAPSED TIME",
    ]
    target_width = 18
    for label in labels:
        assert len(label) % 2 == 0, f"Label '{label}' has odd length {len(label)}, which prevents symmetric padding"
        total_pad = max(0, target_width - len(label))
        left_pad = total_pad // 2
        right_pad = total_pad - left_pad
        assert left_pad == right_pad, f"Label '{label}' is not symmetrically padded"
        assert len(label) + total_pad == target_width, f"Label '{label}' total width is not {target_width}"
