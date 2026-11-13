"""
Sleek, High-Color Rich Terminal User Interface for PlayConv.
Provides stylized two-tone gradient banners, solid box badges, elegant interactive wizard,
structured tracks preview tables, live matching status, and completion dashboard with zero emojis.
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .models import ConversionSummary, MatchResult, PlatformType, PlaylistMetadata, Track

# Force UTF-8 stdout encoding on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(legacy_windows=False)


def make_box_badge(text: str, bg_color: str, fg_color: str = "white", width: Optional[int] = None) -> Text:
    """Builds a complete solid colored box with centered text (no brackets)."""
    if width and width > len(text):
        total_pad = width - len(text)
        left_pad = total_pad // 2
        right_pad = total_pad - left_pad
        label = f"{' ' * left_pad}{text}{' ' * right_pad}"
    else:
        label = f"  {text}  "
    return Text(label, style=f"bold {fg_color} on {bg_color}")


def render_gradient_banner() -> Panel:
    """Builds a crisp, left-aligned, two-tone gradient ASCII banner with solid box badges."""
    banner_lines = [
        r"██████╗ ██╗      █████╗ ██╗   ██╗ ██████╗ ██████╗ ███╗   ██╗██╗   ██╗",
        r"██╔══██╗██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔═══██╗████╗  ██║██║   ██║",
        r"██████╔╝██║     ███████║ ╚████╔╝ ██║     ██║   ██║██╔██╗ ██║██║   ██║",
        r"██╔═══╝ ██║     ██╔══██║  ╚██╔╝  ██║     ██║   ██║██║╚██╗██║╚██╗ ██╔╝",
        r"██║     ███████╗██║  ██║   ██║   ╚██████╗╚██████╔╝██║ ╚████║ ╚████╔╝ ",
        r"╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝  ╚═══╝  ",
    ]

    ascii_text = Text()
    for line in banner_lines:
        ascii_text.append(line[:32], style="bold #00f0ff")
        ascii_text.append(line[32:38], style="bold bright_white")
        ascii_text.append(line[38:], style="bold #d946ef")
        ascii_text.append("\n")

    sub_text = Text()
    sub_text.append("Universal Music Playlist Converter & Exact Track Matcher", style="bold bright_white")
    sub_text.append("  |  ", style="bold #facc15")
    sub_text.append("v1.0.0", style="bold bright_cyan")

    badges_text = Text()
    if console.width >= 95:
        items = [
            ("  SPOTIFY  ", "bold white on #15803d"),
            ("  YT MUSIC  ", "bold white on #b91c1c"),
            ("  JIOSAAVN  ", "bold white on #0284c7"),
            ("  AMAZON  ", "bold white on #ea580c"),
            ("  CSV / M3U  ", "bold white on #7c3aed"),
            ("  EXACT MATCH  ", "bold white on #d97706"),
            ("  ISRC ENGINE  ", "bold white on #059669"),
        ]
        sep = "   "
    else:
        items = [
            (" SPOTIFY ", "bold white on #15803d"),
            (" YT MUSIC ", "bold white on #b91c1c"),
            (" JIOSAAVN ", "bold white on #0284c7"),
            (" AMAZON ", "bold white on #ea580c"),
            (" CSV / M3U ", "bold white on #7c3aed"),
            (" EXACT ", "bold white on #d97706"),
        ]
        sep = "  "

    for idx, (label, style) in enumerate(items):
        if idx > 0:
            badges_text.append(sep, style="default")
        badges_text.append(label, style=style)

    banner_group = Group(
        ascii_text,
        sub_text,
        Text(""),
        badges_text,
    )

    return Panel(
        banner_group,
        box=box.ROUNDED,
        border_style="bright_blue",
        padding=(1, 3 if console.width >= 95 else 2),
    )


def show_banner() -> None:
    """Renders the sleek PlayConv banner in full color with decent spacing."""
    console.print()
    console.print(render_gradient_banner())
    console.print()


def render_step_header(
    step_num: str,
    title: str,
    subtitle: str = "",
    badge: Optional[str] = None,
    badge_color: str = "#10b981",
) -> None:
    """Renders an elegant, spacious step card header with solid box step badge."""
    console.print()
    step_box = Text(f"  STEP {step_num}  ", style="bold white on #6366f1")
    header = Text()
    header.append_text(step_box)
    header.append("  ")
    header.append(title, style="bold bright_white")
    if badge:
        header.append("  ")
        header.append(f"  {badge}  ", style=f"bold white on {badge_color}")
    console.print(header)
    if subtitle:
        console.print(f"            [dim #94a3b8]{subtitle}[/dim #94a3b8]")
    console.print()


def display_collection_header(playlist: PlaylistMetadata) -> None:
    """Displays collection header details before track listing with solid box badges and generous padding."""
    raw_type = playlist.content_type.value.lower()
    title = playlist.title or "Unknown Collection"
    author = playlist.author or ""
    count = len(playlist.tracks)
    source_platform = playlist.source_platform.value.upper()

    header_text = Text()

    # Complete solid boxes for collection types (no brackets)
    type_badge_map = {
        "csv_file": ("  CSV BATCH  ", "bold white on #059669"),
        "m3u_file": ("  M3U PLAYLIST  ", "bold white on #059669"),
        "album": ("  ALBUM  ", "bold white on #2563eb"),
        "playlist": ("  PLAYLIST  ", "bold white on #7c3aed"),
        "track": ("  SINGLE TRACK  ", "bold white on #db2777"),
    }
    badge_label, badge_style = type_badge_map.get(raw_type, ("  COLLECTION  ", "bold white on #4b5563"))
    header_text.append(badge_label, style=badge_style)
    header_text.append("   ")
    header_text.append(title, style="bold bright_white")

    if author and raw_type not in ("csv_file", "m3u_file"):
        header_text.append("   |   ", style="dim yellow")
        header_text.append("Creator / Artist: ", style="bold cyan")
        header_text.append(author, style="bright_white")

    header_text.append("   |   ", style="dim yellow")
    header_text.append("Source: ", style="bold cyan")
    header_text.append(source_platform, style="bold #38bdf8")

    header_text.append("   |   ", style="dim yellow")
    header_text.append(f"  {count} TRACKS  ", style="bold black on #4ade80")

    console.print()
    console.print(Panel(header_text, box=box.ROUNDED, border_style="bright_blue", padding=(1, 3)))
    console.print()


def show_source_summary(playlist: PlaylistMetadata) -> None:
    """Legacy alias that routes to sleek collection header."""
    display_collection_header(playlist)


def display_tracks_table(tracks: List[Track], max_rows: int = 25) -> None:
    """Displays a neat, responsive table of tracks about to be converted with solid styling."""
    has_year = console.width >= 105
    has_isrc = console.width >= 120

    table = Table(
        title="[bold #38bdf8]=== Found Tracks Preview ===[/bold #38bdf8]",
        title_justify="left",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold #c084fc",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim cyan", width=3, justify="right", no_wrap=True)
    table.add_column("Title", style="bold bright_white", ratio=3, no_wrap=True, overflow="ellipsis")
    table.add_column("Artist(s)", style="bold #38bdf8", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("Album", style="bold #facc15", ratio=2, no_wrap=True, overflow="ellipsis")
    if has_year:
        table.add_column("Year", style="bold #fbbf24", width=6, justify="center", no_wrap=True)
    table.add_column("Duration", style="bold #4ade80", width=8, justify="center", no_wrap=True)
    if has_isrc:
        table.add_column("ISRC", style="dim #94a3b8", width=14, justify="center", no_wrap=True)

    display_list = tracks[:max_rows]
    for idx, t in enumerate(display_list):
        row = [
            f"{t.track_number or idx + 1:02d}",
            t.title or "Unknown",
            t.artists_string or "Unknown",
            t.album or "--",
        ]
        if has_year:
            row.append(str(t.year or "--"))
        row.append(t.formatted_duration)
        if has_isrc:
            row.append(t.isrc or "--")
        table.add_row(*row)

    console.print(table)
    if len(tracks) > max_rows:
        console.print(f"  [dim cyan]... and {len(tracks) - max_rows} more tracks[/dim cyan]\n")
    else:
        console.print()


def show_track_preview(tracks: List[Track], max_display: int = 15) -> None:
    """Legacy alias that routes to display_tracks_table."""
    display_tracks_table(tracks, max_rows=max_display)


def create_matching_progress() -> Progress:
    """Returns a rich progress bar configured for track matching operations with zero emojis."""
    return Progress(
        SpinnerColumn(style="bold cyan"),
        TextColumn("[bold #38bdf8]{task.description}[/bold #38bdf8]"),
        BarColumn(bar_width=40, complete_style="#10b981", finished_style="bold #10b981"),
        TextColumn("[bold bright_white]{task.completed}/{task.total}[/bold bright_white]"),
        TimeElapsedColumn(),
        console=console,
    )


def show_match_results_table(results: List[MatchResult], max_rows: int = 25) -> None:
    """Displays matched tracks alongside their confidence scores and match reasons with solid box badges."""
    table = Table(
        title="[bold #38bdf8]=== Matching Results Summary ===[/bold #38bdf8]",
        title_justify="left",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold #c084fc",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim cyan", width=3, justify="right", no_wrap=True)
    table.add_column("Match Status", justify="center", width=12, no_wrap=True)
    table.add_column("Source Track", style="bright_white", ratio=3, no_wrap=True, overflow="ellipsis")
    table.add_column("Matched Target Track", style="bold bright_white", ratio=3, no_wrap=True, overflow="ellipsis")
    table.add_column("Score", justify="right", width=8, no_wrap=True)
    table.add_column("Diff", justify="center", width=7, no_wrap=True)

    for idx, res in enumerate(results[:max_rows], start=1):
        src = res.source_track
        src_label = f"{src.title} - {src.primary_artist}"

        if res.is_successful and res.matched_track:
            target = res.matched_track
            target_label = f"{target.title} - {target.primary_artist}"
            score_pct = f"{res.confidence_score * 100:.0f}%"
            diff_str = f"+/-{res.duration_diff_sec}s" if res.duration_diff_sec is not None else "--"

            if res.is_exact:
                badge = Text("  EXACT  ", style="bold white on #16a34a")
                score_str = f"[bold #4ade80]{score_pct}[/]"
            else:
                badge = Text("  CLOSE  ", style="bold white on #ca8a04")
                score_str = f"[bold #facc15]{score_pct}[/]"

            table.add_row(
                f"{idx:02d}",
                badge,
                src_label,
                target_label,
                score_str,
                f"[dim]{diff_str}[/dim]",
            )
        else:
            badge = Text("  MISS  ", style="bold white on #dc2626")
            table.add_row(
                f"{idx:02d}",
                badge,
                src_label,
                "[dim red]No candidate met threshold[/dim red]",
                "[dim]--[/dim]",
                "[dim]--[/dim]",
            )

    console.print(table)
    if len(results) > max_rows:
        console.print(f"  [dim cyan]... and {len(results) - max_rows} additional tracks (all saved to CSV)[/dim cyan]\n")
    else:
        console.print()


def show_final_summary(summary: ConversionSummary, elapsed_seconds: float = 0.0) -> None:
    """Renders a sleek, colorful dashboard summary card with consistent-width solid boxes and generous spacing."""
    def make_badge(text: str, bg: str, width: int = 16) -> str:
        total_pad = max(0, width - len(text))
        left_pad = total_pad // 2
        right_pad = total_pad - left_pad
        label = f"{' ' * left_pad}{text}{' ' * right_pad}"
        return f"[bold white on {bg}]{label}[/]"

    summary_table = Table.grid(padding=(0, 4))
    summary_table.add_column(justify="left")
    summary_table.add_column(style="bright_white")

    summary_table.add_row(
        make_badge("SOURCE", "#2563eb", 16),
        f"[bold bright_white]{summary.source_name}[/bold bright_white]",
    )
    summary_table.add_row(
        make_badge("TARGET PLATFORM", "#7c3aed", 16),
        f"[bold #c084fc]{summary.destination_platform.value.upper()}[/bold #c084fc]",
    )
    summary_table.add_row(
        make_badge("COMPLETE", "#16a34a", 16),
        f"[bold bright_green]{summary.matched_count}[/] / [bold bright_white]{summary.total_tracks}[/] tracks matched ([bold #4ade80]{summary.match_rate:.1f}%[/])",
    )
    if summary.is_exact_album_conversion:
        summary_table.add_row(
            make_badge("ALBUM CONVERT", "#059669", 16),
            f"[bold #34d399]Direct Exact Album Match:[/] [bold bright_white]{summary.matched_album_title or summary.source_name}[/] "
            + (f"by [dim]{summary.matched_album_artist}[/dim]" if summary.matched_album_artist else ""),
        )
        if summary.matched_album_url:
            summary_table.add_row(
                make_badge("ALBUM URL", "#0284c7", 16),
                f"[bold underline #38bdf8]{summary.matched_album_url}[/bold underline #38bdf8]",
            )
    if summary.exact_match_count > 0 and not summary.is_exact_album_conversion:
        summary_table.add_row(
            make_badge("EXACT MATCHES", "#059669", 16),
            f"[bold #34d399]{summary.exact_match_count}[/] tracks with 100% exact metadata & duration alignment",
        )
    if summary.unmatched_count > 0:
        summary_table.add_row(
            make_badge("UNMATCHED", "#dc2626", 16),
            f"[bold red]{summary.unmatched_count}[/] tracks below confidence threshold",
        )
    if summary.created_playlist_url and not summary.is_exact_album_conversion:
        summary_table.add_row(
            make_badge("PLAYLIST URL", "#0284c7", 16),
            f"[bold underline #38bdf8]{summary.created_playlist_url}[/bold underline #38bdf8]",
        )
    if summary.exported_csv_path:
        summary_table.add_row(
            make_badge("CSV RECORD", "#9333ea", 16),
            f"[bold bright_magenta]{os.path.abspath(summary.exported_csv_path)}[/bold bright_magenta]",
        )
    if elapsed_seconds > 0:
        mins, secs = divmod(int(elapsed_seconds), 60)
        summary_table.add_row(
            make_badge("ELAPSED TIME", "#d97706", 16),
            f"[bold #facc15]{mins}m {secs:02d}s[/bold #facc15]",
        )

    panel = Panel(
        summary_table,
        title="[bold bright_white]PlayConv Conversion Pipeline Complete[/bold bright_white]",
        box=box.ROUNDED,
        border_style="bright_green",
        padding=(1, 3),
    )
    console.print()
    console.print(panel)
    console.print()
