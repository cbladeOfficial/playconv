"""
Unit tests for the TrackMatcher and heuristic scoring algorithms.
"""

from playconv.matcher import TrackMatcher, clean_title, normalize_string
from playconv.models import PlatformType, Track


def test_clean_title():
    assert clean_title('Kesariya (From "Brahmastra")') == "Kesariya"
    assert clean_title("Song Name (feat. Artist)") == "Song Name"
    assert clean_title("Blinding Lights [Official Music Video]") == "Blinding Lights"
    assert clean_title("Hotel California (Remastered 2013)") == "Hotel California"
    assert clean_title("Levitating (feat. DaBaby)") == "Levitating"


def test_normalize_string():
    assert normalize_string("Beyoncé") == "beyonce"
    assert normalize_string("Rock & Roll") == "rock and roll"
    assert normalize_string("Track   Name - (Official)") == "track name official"


def test_isrc_exact_match():
    matcher = TrackMatcher()
    s = Track(title="Song A", primary_artist="Artist 1", duration_sec=200, isrc="USUM71234567")
    c1 = Track(title="Random Title", primary_artist="Other", duration_sec=200, isrc="USUM71234567")
    c2 = Track(title="Song A", primary_artist="Artist 1", duration_sec=200, isrc="GBAYE0000001")

    res = matcher.match(s, [c1, c2])
    assert res.is_exact is True
    assert res.isrc_match is True
    assert res.confidence_score == 1.0
    assert res.matched_track == c1


def test_exact_match_heuristics():
    matcher = TrackMatcher(exact_threshold=0.85, duration_tolerance_sec=10)
    s = Track(
        title='Kesariya (From "Brahmastra")',
        primary_artist="Arijit Singh",
        album="Brahmastra",
        duration_sec=268,
    )

    # Candidate 1: Exact match with clean title and close duration
    c1 = Track(
        title="Kesariya",
        primary_artist="Arijit Singh, Pritam",
        album="Brahmastra (Original Motion Picture Soundtrack)",
        duration_sec=269,
        source_platform=PlatformType.YTMUSIC,
    )

    # Candidate 2: Different remix version
    c2 = Track(
        title="Kesariya (Dance Mix)",
        primary_artist="Arijit Singh, Shashwat Singh",
        duration_sec=195,
        source_platform=PlatformType.YTMUSIC,
    )

    res = matcher.match(s, [c2, c1])
    assert res.is_successful is True
    assert res.matched_track == c1
    assert res.is_exact is True
    assert res.confidence_score >= 0.85
    assert res.duration_diff_sec == 1


def test_duration_penalty_mismatch():
    matcher = TrackMatcher(strict_exact=True, duration_tolerance_sec=15)
    s = Track(title="Short Song", primary_artist="Band", duration_sec=180)
    # Candidate is a 10-minute live extended cut
    c_live = Track(title="Short Song", primary_artist="Band", duration_sec=600)

    res = matcher.match(s, [c_live])
    assert res.is_exact is False
    assert res.is_successful is False  # Rejected because strict_exact and duration diff is 420s
