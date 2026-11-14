"""
Core Playlist Conversion Engine.
Orchestrates link resolution, track search, heuristic matching, CSV export, and playlist creation.
"""

import logging
import time
from typing import Any, List, Optional, Tuple

from .config import config
from .csv_handler import CSVHandler
from .matcher import TrackMatcher
from .models import ContentType, ConversionSummary, MatchResult, PlatformType, PlaylistMetadata, Track
from .platforms import get_platform, resolve_source_to_playlist
from .ui import (
    console,
    create_matching_progress,
    display_collection_header,
    display_tracks_table,
    show_final_summary,
    show_match_results_table,
)

logger = logging.getLogger(__name__)


class PlaylistConverter:
    """End-to-end converter across music platforms and CSV files."""

    def __init__(
        self,
        confidence_threshold: Optional[float] = None,
        exact_only: bool = False,
        duration_tolerance_sec: Optional[int] = None,
    ):
        self.exact_only = exact_only
        self.threshold = confidence_threshold or (config.exact_threshold if exact_only else config.confidence_threshold)
        self.duration_tol = duration_tolerance_sec or config.duration_tolerance_sec
        self.matcher = TrackMatcher(
            confidence_threshold=self.threshold,
            exact_threshold=config.exact_threshold,
            duration_tolerance_sec=self.duration_tol,
            strict_exact=exact_only,
        )

    def convert(
        self,
        source_input: str,
        destination_platform: PlatformType,
        playlist_name: Optional[str] = None,
        export_csv: bool = True,
        csv_output_path: Optional[str] = None,
        create_remote_playlist: bool = True,
        preview_only: bool = False,
    ) -> ConversionSummary:
        """Executes full conversion flow from source to destination platform."""
        start_time = time.time()
        console.print(f"  [bold #00f0ff]>[/] [bold bright_white]Resolving source:[/] [dim]{source_input}[/dim]")
        try:
            source_playlist = resolve_source_to_playlist(source_input)
        except Exception as e:
            console.print(f"    [bold red]Failed to resolve source:[/] {e}")
            raise

        display_collection_header(source_playlist)
        display_tracks_table(source_playlist.tracks)

        target_title = playlist_name or source_playlist.title
        summary = ConversionSummary(
            source_name=source_playlist.title,
            destination_platform=destination_platform,
            total_tracks=len(source_playlist.tracks),
        )

        # Case 1: Pure CSV export
        if destination_platform == PlatformType.CSV or preview_only:
            csv_path = CSVHandler.export_to_csv(source_playlist, csv_output_path)
            summary.exported_csv_path = csv_path
            summary.matched_count = len(source_playlist.tracks)
            show_final_summary(summary, elapsed_seconds=time.time() - start_time)
            return summary

        # Case 2: Matching onto a destination streaming platform
        dest_adapter = get_platform(destination_platform)

        # Check for exact album match conversion
        if source_playlist.content_type == ContentType.ALBUM and source_playlist.tracks:
            exact_album_res = self._attempt_exact_album_conversion(
                source_playlist=source_playlist,
                destination_platform=destination_platform,
                dest_adapter=dest_adapter,
            )
            if exact_album_res:
                exact_matched_album, album_results = exact_album_res
                summary.is_exact_album_conversion = True
                summary.matched_album_title = exact_matched_album.title
                summary.matched_album_artist = exact_matched_album.author
                summary.matched_album_url = exact_matched_album.source_url
                summary.created_playlist_url = exact_matched_album.source_url
                summary.created_playlist_id = exact_matched_album.source_url
                summary.results = album_results
                summary.matched_count = sum(1 for r in album_results if r.is_successful)
                summary.exact_match_count = sum(1 for r in album_results if r.is_exact)
                summary.unmatched_count = len(source_playlist.tracks) - summary.matched_count

                show_match_results_table(album_results)

                if export_csv:
                    csv_path = CSVHandler.export_to_csv(
                        source_playlist,
                        csv_output_path,
                        match_results=album_results,
                    )
                    summary.exported_csv_path = csv_path

                show_final_summary(summary, elapsed_seconds=time.time() - start_time)
                return summary

        results: List[MatchResult] = []
        matched_tracks_for_playlist: List[Track] = []

        mode_badge = "EXACT MATCH ONLY" if self.exact_only else f"CONFIDENCE >= {self.threshold * 100:.0f}%"
        console.print(
            f"  [bold #00f0ff]>[/] [bold bright_white]Target Platform:[/] [bold cyan]{destination_platform.value.upper()}[/]  "
            f"[bold white on #7c3aed]  {mode_badge}  [/]\n"
        )

        if create_remote_playlist and destination_platform not in (PlatformType.CSV, PlatformType.M3U):
            if not dest_adapter.is_authenticated_for_writing():
                auth_cmd_map = {
                    PlatformType.YTMUSIC: "playconv auth ytmusic",
                    PlatformType.SPOTIFY: "playconv auth spotify",
                    PlatformType.JIOSAAVN: "playconv auth jiosaavn",
                    PlatformType.AMAZON_MUSIC: "playconv auth amazonmusic",
                }
                cmd_hint = auth_cmd_map.get(destination_platform, f"playconv auth {destination_platform.value}")
                console.print(
                    f"  [bold #f59e0b]Notice:[/] [dim]Destination platform {destination_platform.value.upper()} is currently not authenticated for writing playlists.[/dim]\n"
                    f"  [dim]PlayConv will match all tracks and export the CSV record. To enable playlist creation, run:[/] [bold cyan]{cmd_hint}[/bold cyan]\n"
                )

        with create_matching_progress() as progress:
            task = progress.add_task("Matching songs...", total=len(source_playlist.tracks))

            for tr in source_playlist.tracks:
                try:
                    candidates = dest_adapter.search_track(tr, limit=6)
                    res = self.matcher.match(tr, candidates)
                except Exception as e:
                    logger.debug(f"Error matching track '{tr.title}': {e}")
                    res = MatchResult(
                        source_track=tr,
                        matched_track=None,
                        confidence_score=0.0,
                        reason=f"error: {e}",
                    )

                results.append(res)
                if res.is_successful and res.matched_track:
                    if not self.exact_only or res.is_exact:
                        matched_tracks_for_playlist.append(res.matched_track)

                progress.update(task, advance=1)

        # Calculate counts
        exact_count = sum(1 for r in results if r.is_exact)
        matched_count = len(matched_tracks_for_playlist)
        unmatched_count = len(source_playlist.tracks) - matched_count

        summary.results = results
        summary.exact_match_count = exact_count
        summary.matched_count = matched_count
        summary.unmatched_count = unmatched_count

        show_match_results_table(results)

        # Export CSV record
        if export_csv:
            csv_path = CSVHandler.export_to_csv(
                source_playlist,
                csv_output_path,
                match_results=results,
            )
            summary.exported_csv_path = csv_path

        # Create remote playlist on target platform
        if create_remote_playlist:
            if not matched_tracks_for_playlist:
                console.print("  [bold yellow]Notice:[/] [dim]No matching tracks met the required criteria to create a playlist.[/dim]\n")
            else:
                console.print(f"  [bold #00f0ff]>[/] [bold bright_white]Creating playlist[/] '[bold cyan]{target_title}[/]' [bold bright_white]on {destination_platform.value.upper()}...[/]")
                try:
                    pl_id, pl_url = dest_adapter.create_playlist(
                        title=target_title,
                        tracks=matched_tracks_for_playlist,
                        description=f"Converted from {source_playlist.source_platform.value.upper()} using PlayConv.",
                    )
                    summary.created_playlist_id = pl_id
                    summary.created_playlist_url = pl_url
                    console.print(f"    [bold green]Playlist provisioned successfully:[/] [link={pl_url}][bold underline cyan]{pl_url}[/bold underline cyan][/link]\n")
                except PermissionError as pe:
                    summary.playlist_error = f"Authentication required (run: playconv auth {destination_platform.value})"
                    console.print(f"\n  [bold white on #b91c1c]  AUTHENTICATION REQUIRED  [/]\n  [dim]{pe}[/dim]")
                    if summary.exported_csv_path:
                        console.print(f"  [dim]All matched track links and metadata have been preserved in: {summary.exported_csv_path}[/dim]\n")
                except NotImplementedError as nie:
                    summary.playlist_error = str(nie)
                    console.print(f"    [bold yellow]Playlist creation not supported on {destination_platform.value.upper()}:[/bold yellow] {nie}\n")
                except Exception as e:
                    summary.playlist_error = str(e)
                    console.print(f"    [bold red]Failed to create playlist on {destination_platform.value.upper()}:[/bold red] {e}\n")

        show_final_summary(summary, elapsed_seconds=time.time() - start_time)
        return summary

    def _attempt_exact_album_conversion(
        self,
        source_playlist: PlaylistMetadata,
        destination_platform: PlatformType,
        dest_adapter: Any,
    ) -> Optional[Tuple[PlaylistMetadata, List[MatchResult]]]:
        """
        Attempts to locate an exact matching album release on the destination streaming service.
        If an exact album is found, that album is considered as the direct conversion.
        """
        from rapidfuzz import fuzz
        from .matcher import clean_title

        console.print(
            f"  [bold #00f0ff]>[/] [bold bright_white]Album detected:[/] '[bold cyan]{source_playlist.title}[/]'  "
            f"[dim]Scanning {destination_platform.value.upper()} for exact album release...[/dim]"
        )

        artist_query = source_playlist.author or (source_playlist.tracks[0].primary_artist if source_playlist.tracks else "")
        try:
            candidates = dest_adapter.search_album(
                title=source_playlist.title,
                artist=artist_query,
                limit=5,
            )
        except Exception as e:
            logger.debug(f"Error querying candidate albums on {destination_platform.value}: {e}")
            candidates = []

        if not candidates:
            console.print(
                f"  [dim]No direct album release match found on {destination_platform.value.upper()}. "
                f"Falling back to track-by-track matching...[/dim]\n"
            )
            return None

        norm_src_title = clean_title(source_playlist.title).lower()
        norm_src_artist = artist_query.lower()

        for cand in candidates:
            if not cand.tracks:
                continue

            norm_cand_title = clean_title(cand.title).lower()
            norm_cand_artist = (cand.author or (cand.tracks[0].primary_artist if cand.tracks else "")).lower()

            title_sim = fuzz.ratio(norm_src_title, norm_cand_title) / 100.0
            artist_sim = fuzz.partial_ratio(norm_src_artist, norm_cand_artist) / 100.0 if norm_src_artist and norm_cand_artist else 1.0
            count_diff = abs(len(cand.tracks) - len(source_playlist.tracks))

            if title_sim >= 0.80 and artist_sim >= 0.70 and count_diff <= 2:
                matched_count = 0
                results: List[MatchResult] = []

                for s_idx, s_tr in enumerate(source_playlist.tracks):
                    best_match: Optional[Track] = None
                    best_score = 0.0

                    # 1. Position check
                    if s_idx < len(cand.tracks):
                        c_tr = cand.tracks[s_idx]
                        score = self.matcher.calculate_confidence(s_tr, c_tr)
                        if score >= 0.70:
                            best_match = c_tr
                            best_score = score

                    # 2. General search across candidate tracks
                    if not best_match or best_score < 0.80:
                        for c_tr in cand.tracks:
                            score = self.matcher.calculate_confidence(s_tr, c_tr)
                            if score > best_score and score >= 0.70:
                                best_score = score
                                best_match = c_tr

                    if best_match and best_score >= 0.70:
                        matched_count += 1
                        dur_diff = abs(s_tr.duration_sec - best_match.duration_sec) if s_tr.duration_sec and best_match.duration_sec else 0
                        results.append(
                            MatchResult(
                                source_track=s_tr,
                                matched_track=best_match,
                                confidence_score=max(best_score, 0.95),
                                is_exact=True,
                                duration_diff_sec=dur_diff,
                                reason="exact_album_track",
                            )
                        )
                    else:
                        results.append(
                            MatchResult(
                                source_track=s_tr,
                                matched_track=None,
                                confidence_score=0.0,
                                reason="album_track_mismatch",
                            )
                        )

                match_ratio = matched_count / max(len(source_playlist.tracks), 1)
                if match_ratio >= 0.80:
                    console.print(
                        f"  [bold white on #10b981]  EXACT ALBUM MATCH FOUND  [/]  "
                        f"[bold bright_white]{cand.title}[/] by [bold cyan]{cand.author or 'Artist'}[/]"
                    )
                    console.print(
                        f"  [bold #00f0ff]>[/] [bold bright_white]Destination Album URL:[/] "
                        f"[bold underline cyan]{cand.source_url or 'Target Album'}[/bold underline cyan]\n"
                    )
                    return cand, results

        console.print(
            f"  [dim]No candidate album met exact alignment criteria on {destination_platform.value.upper()}. "
            f"Falling back to track-by-track matching...[/dim]\n"
        )
        return None
