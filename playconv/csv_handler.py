"""
Universal CSV and M3U Exporter and Importer.
Exports rich playlist and track metadata into Excel/Google Sheets-compatible CSV (utf-8-sig)
and imports playlists from CSV or M3U files (supporting SpotDL, JSD-CSV, and custom formats).
"""

import csv
import io
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .models import ContentType, MatchResult, PlatformType, PlaylistMetadata, Track

logger = logging.getLogger(__name__)

STANDARD_CSV_HEADERS = [
    "Track Number",
    "Title",
    "Artists",
    "Primary Artist",
    "Album",
    "Album Artist",
    "Duration (Formatted)",
    "Duration (Seconds)",
    "Year",
    "Release Date",
    "ISRC",
    "Source Platform",
    "Source ID",
    "Source URL",
    "Destination Platform",
    "Destination ID",
    "Destination URL",
    "Match Score (%)",
    "Match Status",
    "Album Art URL",
]


def parse_duration_to_seconds(dur_val: Any) -> int:
    """Parses various duration representations (seconds, 'MM:SS', 'H:MM:SS', ms) into integer seconds."""
    if dur_val is None or dur_val == "":
        return 0
    if isinstance(dur_val, (int, float)):
        # If over 10,000, likely milliseconds
        if dur_val > 10000:
            return int(dur_val // 1000)
        return int(dur_val)

    s = str(dur_val).strip()
    if not s:
        return 0

    # If simple digits
    if s.isdigit():
        val = int(s)
        if val > 10000:
            return val // 1000
        return val

    # Colon separated format MM:SS or H:MM:SS
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
    except (ValueError, TypeError):
        pass

    return 0


class CSVHandler:
    """Handles bidirectional CSV and M3U conversion for playlists."""

    @staticmethod
    def export_to_csv(
        playlist: PlaylistMetadata,
        output_path: Optional[str] = None,
        match_results: Optional[List[MatchResult]] = None,
    ) -> str:
        """
        Exports a playlist to a standardized utf-8-sig CSV file.
        Returns the absolute path to the written file.
        """
        if not output_path:
            clean_name = re.sub(r'[\\/*?:"<>|]', "", playlist.title).strip() or "playlist"
            output_path = f"{clean_name}.csv"

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Map match results by source track if provided
        result_map: Dict[int, MatchResult] = {}
        if match_results:
            for idx, res in enumerate(match_results):
                result_map[idx] = res

        rows: List[List[Any]] = []
        for idx, track in enumerate(playlist.tracks, start=1):
            res = result_map.get(idx - 1)
            matched = res.matched_track if res else None

            dest_platform = matched.source_platform.value if matched else ""
            dest_id = matched.source_id or "" if matched else ""
            dest_url = matched.source_url or "" if matched else ""
            score_str = f"{res.confidence_score * 100:.1f}" if res else ""
            status_str = res.reason if res else "original"

            row = [
                track.track_number or idx,
                track.title,
                track.artists_string,
                track.primary_artist,
                track.album,
                track.album_artist or track.primary_artist,
                track.formatted_duration,
                track.duration_sec,
                track.year or "",
                track.release_date or "",
                track.isrc or "",
                track.source_platform.value,
                track.source_id or "",
                track.source_url or "",
                dest_platform,
                dest_id,
                dest_url,
                score_str,
                status_str,
                track.image_url or "",
            ]
            rows.append(row)

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(STANDARD_CSV_HEADERS)
            writer.writerows(rows)

        logger.info(f"Successfully exported {len(rows)} tracks to CSV: {out_path}")
        return str(out_path)

    @staticmethod
    def import_from_csv(csv_path_or_url: str) -> PlaylistMetadata:
        """
        Imports tracks from a local CSV file or HTTP/HTTPS CSV URL.
        Features intelligent header detection compatible with SpotDL, JSD-CSV, and custom CSVs.
        """
        raw_text = ""
        csv_path_or_url = csv_path_or_url.strip()

        if csv_path_or_url.startswith("http://") or csv_path_or_url.startswith("https://"):
            resp = requests.get(csv_path_or_url, timeout=20)
            resp.raise_for_status()
            raw_text = resp.text
            title = Path(csv_path_or_url.split("?")[0]).stem or "Imported Web Playlist"
        else:
            file_path = Path(csv_path_or_url).resolve()
            if not file_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path_or_url}")
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                raw_text = f.read()
            title = file_path.stem

        reader = csv.reader(io.StringIO(raw_text))
        rows = list(reader)
        if not rows:
            return PlaylistMetadata(title=title, tracks=[], source_platform=PlatformType.CSV)

        # Detect headers
        header_row = [h.strip().lower() for h in rows[0]]

        def find_idx(*aliases: str) -> Optional[int]:
            for alias in aliases:
                a_clean = alias.strip().lower()
                for i, h in enumerate(header_row):
                    if h == a_clean or a_clean in h:
                        return i
            return None

        idx_title = find_idx("title", "track name", "song title", "song", "name")
        idx_artists = find_idx("artists", "artist", "singers", "primary artist")
        idx_album = find_idx("album", "album name")
        idx_duration = find_idx("duration (seconds)", "duration_sec", "duration", "length", "time")
        idx_year = find_idx("year", "release year", "release date")
        idx_isrc = find_idx("isrc", "isrc code")
        idx_url = find_idx("source url", "url", "jiosaavn url", "spotify url", "yt music url", "link")
        idx_art = find_idx("album art url", "image url", "cover art", "artwork")

        if idx_title is None and len(rows[0]) >= 1:
            # Fallback: assume first column is title, second is artist
            idx_title = 0
            idx_artists = 1 if len(rows[0]) > 1 else None

        tracks: List[Track] = []
        for i, row in enumerate(rows[1:], start=1):
            if not row or not any(field.strip() for field in row):
                continue

            track_title = row[idx_title].strip() if (idx_title is not None and idx_title < len(row)) else ""
            if not track_title:
                continue

            artists_str = row[idx_artists].strip() if (idx_artists is not None and idx_artists < len(row)) else ""
            artists_list = [a.strip() for a in re.split(r"[,;/&]", artists_str) if a.strip()] if artists_str else []

            album_str = row[idx_album].strip() if (idx_album is not None and idx_album < len(row)) else ""

            dur_raw = row[idx_duration].strip() if (idx_duration is not None and idx_duration < len(row)) else ""
            dur_sec = parse_duration_to_seconds(dur_raw)

            year_val = None
            if idx_year is not None and idx_year < len(row):
                y_str = row[idx_year].strip()
                match = re.search(r"\b(19\d\d|20\d\d)\b", y_str)
                if match:
                    year_val = int(match.group(1))

            isrc_val = row[idx_isrc].strip() if (idx_isrc is not None and idx_isrc < len(row)) else None
            source_url_val = row[idx_url].strip() if (idx_url is not None and idx_url < len(row)) else None
            art_val = row[idx_art].strip() if (idx_art is not None and idx_art < len(row)) else None

            track = Track(
                title=track_title,
                artists=artists_list,
                primary_artist=artists_list[0] if artists_list else "",
                album=album_str,
                duration_sec=dur_sec,
                year=year_val,
                isrc=isrc_val,
                track_number=i,
                source_platform=PlatformType.CSV,
                source_url=source_url_val,
                image_url=art_val,
            )
            tracks.append(track)

        return PlaylistMetadata(
            title=title,
            tracks=tracks,
            total_tracks=len(tracks),
            source_platform=PlatformType.CSV,
            content_type=ContentType.CSV_FILE,
        )

    @staticmethod
    def export_to_m3u(
        playlist: PlaylistMetadata,
        output_path: Optional[str] = None,
        match_results: Optional[List[MatchResult]] = None,
    ) -> str:
        """Exports playlist to standard extended M3U8 format."""
        if not output_path:
            clean_name = re.sub(r'[\\/*?:"<>|]', "", playlist.title).strip() or "playlist"
            output_path = f"{clean_name}.m3u8"

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        result_map: Dict[int, MatchResult] = {}
        if match_results:
            for idx, res in enumerate(match_results):
                result_map[idx] = res

        lines = ["#EXTM3U", f"#PLAYLIST:{playlist.title}"]
        for idx, track in enumerate(playlist.tracks):
            res = result_map.get(idx)
            target = res.matched_track if res and res.matched_track else track
            dur = target.duration_sec or -1
            artist_title = f"{target.primary_artist} - {target.title}" if target.primary_artist else target.title
            lines.append(f"#EXTINF:{dur},{artist_title}")
            lines.append(target.source_url or "")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return str(out_path)
