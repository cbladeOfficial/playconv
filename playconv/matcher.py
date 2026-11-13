"""
Intelligent Track Matcher with exact match heuristics and confidence scoring.
Matches tracks across different streaming platforms using title normalization,
artist comparison, ISRC matching, album similarity, and duration tolerances.
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz
    def _token_set_ratio(s1: str, s2: str) -> float:
        return fuzz.token_set_ratio(s1, s2) / 100.0

    def _ratio(s1: str, s2: str) -> float:
        return fuzz.ratio(s1, s2) / 100.0
except ImportError:
    import difflib
    def _token_set_ratio(s1: str, s2: str) -> float:
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _ratio(s1: str, s2: str) -> float:
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

from .models import MatchResult, Track

logger = logging.getLogger(__name__)

# Patterns to strip from titles to extract clean core name
CLEANUP_PATTERNS = [
    r"\((from\s+[\"'].*?[\"']|from\s+.*?)\)",            # (From "Movie")
    r"\[(from\s+[\"'].*?[\"']|from\s+.*?)\]",            # [From "Movie"]
    r"\((feat\.|ft\.|with|featuring)\s+.*?\)",           # (feat. Artist)
    r"\[(feat\.|ft\.|with|featuring)\s+.*?\]",           # [feat. Artist]
    r"\b(feat\.|ft\.|featuring)\s+.*$",                  # feat. Artist at end
    r"\((official\s+(audio|video|music\s+video|lyric\s+video)|visualizer|lyrics?)\)", # (Official Video)
    r"\[(official\s+(audio|video|music\s+video|lyric\s+video)|visualizer|lyrics?)\]", # [Official Video]
    r"\((remaster(?:ed)?(?:\s+\d+)?|deluxe|expanded|bonus\s+track|anniversary|radio\s+edit)\)", # (Remastered 2013)
    r"\[(remaster(?:ed)?(?:\s+\d+)?|deluxe|expanded|bonus\s+track|anniversary|radio\s+edit)\]",
    r"-\s*(remaster(?:ed)?(?:\s+\d+)?|radio\s+edit|bonus\s+track|original\s+motion\s+picture\s+soundtrack).*?$",
    r"\((slowed\s*\+?\s*reverb|sped\s*up|lofi\s*flip|acoustic|live)\)", # (Lofi Flip)
]


def normalize_string(text: str) -> str:
    """Normalizes string for comparison: NFKD unicode normalization, lowercase, trimmed."""
    if not text:
        return ""
    # Unicode normalize
    norm = unicodedata.normalize("NFKD", text)
    # Remove accents/diacritics
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.lower()
    # Replace standard separators
    norm = norm.replace("&", " and ")
    norm = norm.replace("/", " ")
    norm = norm.replace("-", " ")
    norm = re.sub(r"[^\w\s]", "", norm)
    return re.sub(r"\s+", " ", norm).strip()


def clean_title(title: str) -> str:
    """Strips meta tags and extraneous information from song titles."""
    if not title:
        return ""
    cleaned = title
    for pat in CLEANUP_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    # Also strip any generic trailing parenthesis/brackets if it leaves a valid name (>= 2 chars)
    trailing_cleaned = re.sub(r"\s*[\(\[][^()\[\]]*[\)\]]\s*$", "", cleaned).strip()
    if len(trailing_cleaned) >= 2:
        cleaned = trailing_cleaned
    # Clean whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title


def calculate_duration_score(dur_a: int, dur_b: int) -> Tuple[float, int]:
    """
    Compares two durations in seconds.
    Returns (duration_score [0.0 - 1.0], difference_in_seconds).
    """
    if dur_a <= 0 or dur_b <= 0:
        # Duration unknown on one platform, return neutral 0.8 score
        return 0.8, 0

    diff = abs(dur_a - dur_b)

    if diff <= 3:
        return 1.0, diff
    elif diff <= 8:
        return 0.95, diff
    elif diff <= 15:
        return 0.85, diff
    elif diff <= 25:
        return 0.65, diff
    elif diff <= 45:
        return 0.35, diff
    else:
        return 0.05, diff


class TrackMatcher:
    """Matching engine for finding exact and best-matching tracks across platforms."""

    def __init__(
        self,
        confidence_threshold: float = 0.75,
        exact_threshold: float = 0.85,
        duration_tolerance_sec: int = 15,
        strict_exact: bool = False,
    ):
        self.confidence_threshold = confidence_threshold
        self.exact_threshold = exact_threshold
        self.duration_tolerance_sec = duration_tolerance_sec
        self.strict_exact = strict_exact

    def match(
        self,
        source: Track,
        candidates: List[Track],
    ) -> MatchResult:
        """
        Evaluates a list of candidates from a target platform against the source track.
        Returns the top MatchResult with confidence score and match reason.
        """
        if not candidates:
            return MatchResult(
                source_track=source,
                matched_track=None,
                confidence_score=0.0,
                is_exact=False,
                reason="no_candidates_found",
            )

        # 1. First priority: ISRC exact match
        if source.isrc:
            source_isrc_clean = source.isrc.strip().upper()
            for cand in candidates:
                if cand.isrc and cand.isrc.strip().upper() == source_isrc_clean:
                    diff = abs(source.duration_sec - cand.duration_sec) if (source.duration_sec and cand.duration_sec) else 0
                    return MatchResult(
                        source_track=source,
                        matched_track=cand,
                        confidence_score=1.0,
                        is_exact=True,
                        isrc_match=True,
                        duration_diff_sec=diff,
                        reason="isrc_exact_match",
                    )

        # 2. Score each candidate
        best_cand: Optional[Track] = None
        best_score = 0.0
        best_diff = 0
        best_is_exact = False

        source_clean_title = normalize_string(clean_title(source.title))
        source_clean_artist = normalize_string(source.primary_artist)
        source_all_artists = [normalize_string(a) for a in source.artists if a]
        source_clean_album = normalize_string(source.album)

        for cand in candidates:
            cand_clean_title = normalize_string(clean_title(cand.title))
            cand_clean_artist = normalize_string(cand.primary_artist)
            cand_all_artists = [normalize_string(a) for a in cand.artists if a]
            cand_clean_album = normalize_string(cand.album)

            # Title similarity
            title_token_score = _token_set_ratio(source_clean_title, cand_clean_title)
            title_exact_score = _ratio(source_clean_title, cand_clean_title)
            title_score = max(title_token_score, title_exact_score)

            # Artist similarity
            artist_scores = []
            if source_clean_artist and cand_clean_artist:
                artist_scores.append(_token_set_ratio(source_clean_artist, cand_clean_artist))
                # Check if one artist is substring of the other
                if source_clean_artist in cand_clean_artist or cand_clean_artist in source_clean_artist:
                    artist_scores.append(0.95)

            # Cross-check collaborating artists
            for s_art in source_all_artists:
                for c_art in cand_all_artists:
                    if s_art and c_art:
                        if s_art == c_art:
                            artist_scores.append(1.0)
                        elif s_art in c_art or c_art in s_art:
                            artist_scores.append(0.9)

            artist_score = max(artist_scores) if artist_scores else 0.5

            # Album similarity
            album_score = 0.5
            if source_clean_album and cand_clean_album:
                album_score = _token_set_ratio(source_clean_album, cand_clean_album)

            # Duration similarity
            dur_score, dur_diff = calculate_duration_score(source.duration_sec, cand.duration_sec)

            # Weighted composite score
            # Title: 45%, Artist: 35%, Album: 10%, Duration: 10%
            total_score = (
                (title_score * 0.45)
                + (artist_score * 0.35)
                + (album_score * 0.10)
                + (dur_score * 0.10)
            )

            # Check exact match criteria
            is_exact = (
                total_score >= self.exact_threshold
                and title_score >= 0.85
                and artist_score >= 0.80
                and dur_diff <= self.duration_tolerance_sec
            )

            # Heavy duration mismatch penalty (e.g. 10m video vs 3m track)
            if source.duration_sec > 0 and cand.duration_sec > 0 and dur_diff > 45:
                total_score *= 0.4
                is_exact = False

            if total_score > best_score:
                best_score = total_score
                best_cand = cand
                best_diff = dur_diff
                best_is_exact = is_exact

        # Evaluate against thresholds
        required_threshold = self.exact_threshold if self.strict_exact else self.confidence_threshold

        if best_cand and best_score >= required_threshold:
            # If strict exact is requested, duration difference must also be within tolerance
            if self.strict_exact and best_diff > self.duration_tolerance_sec and source.duration_sec > 0:
                return MatchResult(
                    source_track=source,
                    matched_track=None,
                    confidence_score=best_score,
                    is_exact=False,
                    duration_diff_sec=best_diff,
                    reason=f"duration_tolerance_exceeded ({best_diff}s > {self.duration_tolerance_sec}s)",
                )

            reason = "exact_match" if best_is_exact else "high_confidence_match"
            return MatchResult(
                source_track=source,
                matched_track=best_cand,
                confidence_score=best_score,
                is_exact=best_is_exact,
                isrc_match=False,
                duration_diff_sec=best_diff,
                reason=reason,
            )

        return MatchResult(
            source_track=source,
            matched_track=None,
            confidence_score=best_score,
            is_exact=False,
            duration_diff_sec=best_diff,
            reason=f"below_threshold ({best_score:.2f} < {required_threshold:.2f})" if best_cand else "no_match",
        )

    def calculate_confidence(self, source: Track, candidate: Track) -> float:
        """Calculates candidate matching confidence score against source track."""
        res = self.match(source, [candidate])
        return res.confidence_score
