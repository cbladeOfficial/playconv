"""
Core Playlist Conversion Engine.
Orchestrates link resolution, track search, heuristic matching, CSV export, and playlist creation.
"""

import logging
import time
from typing import List, Optional

from .config import config
from .csv_handler import CSVHandler
from .matcher import TrackMatcher
from .models import ConversionSummary, MatchResult, PlatformType, PlaylistMetadata, Track
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
        results: List[MatchResult] = []
        matched_tracks_for_playlist: List[Track] = []

        mode_badge = "EXACT MATCH ONLY" if self.exact_only else f"CONFIDENCE >= {self.threshold * 100:.0f}%"
        console.print(
            f"  [bold #00f0ff]>[/] [bold bright_white]Target Platform:[/] [bold cyan]{destination_platform.value.upper()}[/]  "
            f"[bold white on #7c3aed]  {mode_badge}  [/]\n"
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
                    console.print(f"    [bold green]Playlist provisioned successfully:[/] [bold underline cyan]{pl_url}[/bold underline cyan]\n")
                except PermissionError as pe:
                    console.print(f"\n  [bold white on #b91c1c]  AUTHENTICATION REQUIRED  [/]\n  [dim]{pe}[/dim]")
                    console.print(f"  [dim]All matched track links and metadata have been preserved in: {summary.exported_csv_path}[/dim]\n")
                except Exception as e:
                    console.print(f"    [bold red]Failed to create playlist on {destination_platform.value.upper()}:[/bold red] {e}\n")

        show_final_summary(summary, elapsed_seconds=time.time() - start_time)
        return summary
