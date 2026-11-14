"""
Command Line Interface for PlayConv.
Provides subcommands for convert, export, import, info, auth, and sleek interactive wizard.
Zero emojis, high-color Rich terminal styling, and solid box badges.
"""

import os
import signal
import sys
from typing import Optional

import click
from rich import box
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .config import config
from .converter import PlaylistConverter
from .csv_handler import CSVHandler
from .models import PlatformType
from .platforms import PLATFORM_REGISTRY, get_platform, resolve_source_to_playlist
from .ui import (
    console,
    display_collection_header,
    display_exit_message,
    display_tracks_table,
    render_step_header,
    show_banner,
)

_exit_handled = False


def handle_sigint(signum=None, frame=None):
    """Graceful signal handler for SIGINT (Ctrl+C)."""
    global _exit_handled
    if _exit_handled:
        sys.exit(0)
    _exit_handled = True
    display_exit_message(interrupted=True)
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, handle_sigint)
except (ValueError, AttributeError):
    pass


def _custom_excepthook(exc_type, exc_value, exc_traceback):
    """Fallback exception hook to catch unhandled KeyboardInterrupts and click.Abort."""
    global _exit_handled
    if issubclass(exc_type, (KeyboardInterrupt, click.Abort)):
        if not _exit_handled:
            _exit_handled = True
            display_exit_message(interrupted=True)
        sys.exit(0)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _custom_excepthook


class GracefulGroup(click.Group):
    """Click command group that gracefully traps KeyboardInterrupt, click.Abort, and SIGINT."""

    def main(self, *args, **kwargs):
        try:
            rv = super().main(*args, standalone_mode=False, **kwargs)
            if isinstance(rv, int):
                sys.exit(rv)
            return rv
        except (KeyboardInterrupt, click.Abort):
            global _exit_handled
            if not _exit_handled:
                _exit_handled = True
                display_exit_message(interrupted=True)
            sys.exit(0)
        except click.ClickException as e:
            e.show()
            sys.exit(e.exit_code)


@click.group(cls=GracefulGroup, invoke_without_command=True)
@click.pass_context
@click.version_option("1.0.0", prog_name="PlayConv")
def main(ctx: click.Context):
    """Universal Music Playlist Converter & CSV Exporter."""
    if ctx.invoked_subcommand is None:
        run_interactive_wizard()


def run_interactive_wizard():
    """Interactive wizard when run without command-line switches."""
    show_banner()

    wizard_panel = Panel(
        Text.from_markup(
            "[bold bright_white]INTERACTIVE PLAYLIST CONVERTER WIZARD[/bold bright_white]\n"
            "[dim #94a3b8]Convert playlists, albums, and tracks across services or export to CSV. Zero cloud servers, 100% on-device.[/dim #94a3b8]"
        ),
        box=box.ROUNDED,
        border_style="bold #38bdf8",
        padding=(1, 3),
    )
    console.print(wizard_panel)

    console.print()
    console.print("    [bold white on #0284c7]  1  [/]  [bold bright_white]Convert Collection[/]     [dim]Convert Playlist / Album / Track across platforms[/]     [bold white on #16a34a]  RECOMMENDED  [/]")
    console.print("    [bold white on #475569]  2  [/]  [bold bright_white]Export to CSV[/]          [dim]Export full metadata from any music URL to CSV file[/]")
    console.print("    [bold white on #475569]  3  [/]  [bold bright_white]Import CSV to Service[/]  [dim]Create a playlist on a platform from an existing CSV file[/]")
    console.print("    [bold white on #475569]  4  [/]  [bold bright_white]Inspect URL Info[/]       [dim]Preview collection tracks and metadata without converting[/]")
    console.print("    [bold white on #475569]  5  [/]  [bold bright_white]Platform Accounts[/]      [dim]Configure YouTube Music, Spotify, JioSaavn, or Amazon Music credentials[/]")
    console.print("    [bold white on #475569]  6  [/]  [bold bright_white]Exit[/]")
    console.print()

    choice = Prompt.ask(
        "  [bold #00f0ff]>[/] [bold white]Choose an action [1-6][/bold white]",
        choices=["1", "2", "3", "4", "5", "6"],
        default="1",
    )

    if choice == "1":
        # Step 1: Source
        render_step_header(
            step_num="1",
            title="Source Music Link or CSV Path",
            subtitle="Paste any Spotify, YouTube Music, JioSaavn, Amazon Music, Deezer, or Apple Music URL (or local CSV)",
        )
        source = ""
        while not source.strip():
            source = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Source URL or File Path[/bold white]").strip().strip("'\"")
            if not source:
                console.print("    [bold red]Input cannot be empty. Please enter a valid URL or path.[/bold red]\n")

        # Step 2: Destination Platform
        render_step_header(
            step_num="2",
            title="Destination Streaming Platform",
            subtitle="Select the service where matched tracks will be transferred",
        )
        yt_ready = get_platform(PlatformType.YTMUSIC).is_authenticated_for_writing()
        sp_ready = get_platform(PlatformType.SPOTIFY).is_authenticated_for_writing()
        js_ready = get_platform(PlatformType.JIOSAAVN).is_authenticated_for_writing()
        amz_ready = get_platform(PlatformType.AMAZON_MUSIC).is_authenticated_for_writing()

        yt_badge = " [bold white on #16a34a]  READY  [/]" if yt_ready else " [dim](auth required to write)[/dim]"
        sp_badge = " [bold white on #16a34a]  READY  [/]" if sp_ready else " [dim](requires Spotify Premium to write)[/dim]"
        js_badge = " [bold white on #16a34a]  READY  [/]" if js_ready else " [dim](cookie needed to write)[/dim]"
        amz_badge = " [bold white on #16a34a]  READY  [/]" if amz_ready else " [dim](cookie needed to write)[/dim]"

        console.print(f"    [bold white on #b91c1c]  1  [/]  [bold bright_white]YouTube Music[/]   [dim]music.youtube.com[/]{yt_badge}")
        console.print(f"    [bold white on #15803d]  2  [/]  [bold bright_white]Spotify[/]         [dim]open.spotify.com[/]{sp_badge}")
        console.print(f"    [bold white on #0284c7]  3  [/]  [bold bright_white]JioSaavn[/]        [dim]jiosaavn.com[/]{js_badge}")
        console.print(f"    [bold white on #ea580c]  4  [/]  [bold bright_white]Amazon Music[/]    [dim]music.amazon.com[/]{amz_badge}")
        console.print("    [bold white on #7c3aed]  5  [/]  [bold bright_white]CSV File[/]        [dim]Export structured metadata spreadsheet only[/] [bold white on #16a34a]  NO AUTH NEEDED  [/]")
        console.print()

        dest_choice = Prompt.ask(
            "  [bold #00f0ff]>[/] [bold white]Select Destination [1-5][/bold white]",
            choices=["1", "2", "3", "4", "5", "ytmusic", "spotify", "jiosaavn", "amazonmusic", "amazon", "csv"],
            default="1",
        )
        dest_map = {"1": "ytmusic", "2": "spotify", "3": "jiosaavn", "4": "amazonmusic", "5": "csv"}
        dest_str = dest_map.get(dest_choice, dest_choice)
        dest_platform = PlatformType.from_string(dest_str)

        # Step 3: Options
        render_step_header(
            step_num="3",
            title="Conversion Parameters",
            subtitle="Configure exact matching heuristics and title",
        )
        custom_name = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Playlist Title[/bold white] [dim](press Enter to keep original)[/dim]", default="").strip()
        exact_only = Confirm.ask(
            "  [bold #00f0ff]>[/] [bold white]Exact matches only?[/bold white] [dim](requires 85%+ score & matching duration)[/dim]",
            default=False,
        )
        export_csv = Confirm.ask(
            "  [bold #00f0ff]>[/] [bold white]Export backup CSV record?[/bold white]",
            default=True,
        )

        converter = PlaylistConverter(exact_only=exact_only)
        converter.convert(
            source_input=source,
            destination_platform=dest_platform,
            playlist_name=custom_name or None,
            export_csv=export_csv,
        )

    elif choice == "2":
        render_step_header(
            step_num="1",
            title="Export Source URL",
            subtitle="Spotify, YouTube Music, JioSaavn, Deezer, or Apple Music link to export",
        )
        source = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Source URL[/bold white]").strip().strip("'\"")
        if not source:
            return
        out_csv = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Output CSV path[/bold white] [dim](press Enter for auto-name)[/dim]", default="").strip()

        converter = PlaylistConverter()
        converter.convert(
            source_input=source,
            destination_platform=PlatformType.CSV,
            csv_output_path=out_csv or None,
            create_remote_playlist=False,
        )

    elif choice == "3":
        render_step_header(
            step_num="1",
            title="Import Existing CSV File",
            subtitle="Path to CSV spreadsheet exported from PlayConv, JSD-CSV, SpotDL, or SoundShift",
        )
        csv_path = Prompt.ask("  [bold #00f0ff]>[/] [bold white]CSV File Path[/bold white]").strip().strip("'\"")

        render_step_header(
            step_num="2",
            title="Destination Platform",
            subtitle="Target platform to create playlist on",
        )
        console.print("    [bold white on #b91c1c]  1  [/]  [bold bright_white]YouTube Music[/]")
        console.print("    [bold white on #15803d]  2  [/]  [bold bright_white]Spotify[/]  [dim](requires Spotify Premium)[/dim]")
        console.print("    [bold white on #0284c7]  3  [/]  [bold bright_white]JioSaavn[/]")
        console.print()
        dest_choice = Prompt.ask(
            "  [bold #00f0ff]>[/] [bold white]Select Target [1-3][/bold white]",
            choices=["1", "2", "3", "ytmusic", "spotify", "jiosaavn"],
            default="1",
        )
        dest_map = {"1": "ytmusic", "2": "spotify", "3": "jiosaavn"}
        dest_str = dest_map.get(dest_choice, dest_choice)
        dest_platform = PlatformType.from_string(dest_str)

        custom_name = Prompt.ask("  [bold #00f0ff]>[/] [bold white]New Playlist Title[/bold white] [dim](press Enter for CSV name)[/dim]", default="").strip()
        exact_only = Confirm.ask("  [bold #00f0ff]>[/] [bold white]Strict exact matches only?[/bold white]", default=False)

        converter = PlaylistConverter(exact_only=exact_only)
        converter.convert(
            source_input=csv_path,
            destination_platform=dest_platform,
            playlist_name=custom_name or None,
        )

    elif choice == "4":
        source = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Enter Playlist, Album, or Track URL[/bold white]").strip().strip("'\"")
        try:
            pl = resolve_source_to_playlist(source)
            display_collection_header(pl)
            display_tracks_table(pl.tracks, max_rows=30)
        except Exception as e:
            console.print(f"    [bold red]Error:[/] {e}\n")

    elif choice == "5":
        plat = Prompt.ask(
            "  [bold #00f0ff]>[/] [bold white]Select Platform to Configure[/bold white]",
            choices=["ytmusic", "spotify", "jiosaavn", "all"],
            default="all",
        )
        run_auth_wizard(plat)

    elif choice == "6":
        display_exit_message(interrupted=False)
        sys.exit(0)


# =====================================================================
# CLI SUBCOMMANDS
# =====================================================================


@main.command("convert")
@click.argument("source")
@click.option("--to", "-t", "destination", required=True, help="Destination platform: ytmusic, spotify, jiosaavn, csv")
@click.option("--name", "-n", "playlist_name", default=None, help="Name for the newly created playlist")
@click.option("--exact", is_flag=True, default=False, help="Strict exact match only (85%+ score, close duration)")
@click.option("--threshold", type=float, default=None, help="Custom confidence threshold (0.0 to 1.0)")
@click.option("--csv/--no-csv", default=True, help="Export matched tracklist to CSV (default: enabled)")
@click.option("--out", "-o", "csv_out", default=None, help="Custom CSV output file path")
def convert_cmd(source: str, destination: str, playlist_name: Optional[str], exact: bool, threshold: Optional[float], csv: bool, csv_out: Optional[str]):
    """Convert a playlist, album, track, or CSV across streaming platforms."""
    show_banner()
    dest_platform = PlatformType.from_string(destination)
    if dest_platform == PlatformType.UNKNOWN:
        console.print(f"  [bold red]Error:[/bold red] Unknown destination platform '{destination}'. Choose from: ytmusic, spotify, jiosaavn, csv\n")
        sys.exit(1)

    converter = PlaylistConverter(confidence_threshold=threshold, exact_only=exact)
    try:
        converter.convert(
            source_input=source,
            destination_platform=dest_platform,
            playlist_name=playlist_name,
            export_csv=csv,
            csv_output_path=csv_out,
        )
    except Exception as e:
        console.print(f"\n  [bold red]Conversion failed:[/bold red] {e}\n")
        sys.exit(1)


@main.command("export")
@click.argument("source")
@click.option("--out", "-o", "output_path", default=None, help="Output CSV path")
@click.option("--m3u", is_flag=True, default=False, help="Also export as M3U8 playlist")
def export_cmd(source: str, output_path: Optional[str], m3u: bool):
    """Export tracklist of any playlist, album, or track to CSV."""
    show_banner()
    try:
        pl = resolve_source_to_playlist(source)
        display_collection_header(pl)
        display_tracks_table(pl.tracks)
        csv_file = CSVHandler.export_to_csv(pl, output_path)
        console.print(f"  [bold green]Exported to CSV:[/] [bold cyan]{csv_file}[/bold cyan]\n")

        if m3u:
            m3u_file = CSVHandler.export_to_m3u(pl)
            console.print(f"  [bold green]Exported to M3U8:[/] [bold cyan]{m3u_file}[/bold cyan]\n")
    except Exception as e:
        console.print(f"  [bold red]Export failed:[/bold red] {e}\n")
        sys.exit(1)


@main.command("import")
@click.argument("csv_file")
@click.option("--to", "-t", "destination", required=True, help="Destination platform: ytmusic, spotify, jiosaavn")
@click.option("--name", "-n", "playlist_name", default=None, help="Playlist name")
@click.option("--exact", is_flag=True, default=False, help="Exact match only")
def import_cmd(csv_file: str, destination: str, playlist_name: Optional[str], exact: bool):
    """Create a playlist on a platform from an existing CSV file."""
    show_banner()
    dest_platform = PlatformType.from_string(destination)
    converter = PlaylistConverter(exact_only=exact)
    try:
        converter.convert(
            source_input=csv_file,
            destination_platform=dest_platform,
            playlist_name=playlist_name,
        )
    except Exception as e:
        console.print(f"  [bold red]Import failed:[/bold red] {e}\n")
        sys.exit(1)


@main.command("info")
@click.argument("source")
def info_cmd(source: str):
    """Preview metadata and tracks of any music URL or CSV."""
    show_banner()
    try:
        pl = resolve_source_to_playlist(source)
        display_collection_header(pl)
        display_tracks_table(pl.tracks, max_rows=30)
    except Exception as e:
        console.print(f"  [bold red]Failed to inspect collection:[/bold red] {e}\n")
        sys.exit(1)


@main.command("auth")
@click.argument("platform", default="all", required=False)
def auth_cmd(platform: str):
    """Configure accounts and credentials for YouTube Music, Spotify, or JioSaavn."""
    show_banner()
    run_auth_wizard(platform)


def run_auth_wizard(platform_str: str):
    """Guided authentication setup for platforms with zero emojis."""
    plat = platform_str.lower().strip()

    # YouTube Music
    if plat in ("all", "ytmusic", "youtube"):
        render_step_header(
            step_num="AUTH",
            title="YouTube Music Authentication",
            subtitle="Paste browser request headers or point to cookies.txt",
            badge="YTMUSIC",
            badge_color="#b91c1c",
        )
        method = Prompt.ask(
            "  [bold #00f0ff]>[/] [bold white]Select auth method[/bold white]",
            choices=["headers", "cookies", "skip"],
            default="cookies" if os.path.exists("cookies_yt.txt") else "headers",
        )

        if method == "headers":
            console.print("  [dim]Paste your raw request headers below, then press Enter twice:[/dim]")
            lines = []
            while True:
                try:
                    line = input()
                    if not line.strip() and lines:
                        break
                    lines.append(line)
                except EOFError:
                    break
            raw_headers = "\n".join(lines).strip()
            if raw_headers:
                try:
                    from ytmusicapi import setup
                    auth_path = str(config.config_dir / "browser.json")
                    setup(filepath=auth_path, headers_raw=raw_headers)
                    config.set("ytmusic", "auth_file", auth_path)
                    console.print(f"    [bold green]Saved YTMusic auth to:[/] [bold cyan]{auth_path}[/bold cyan]\n")
                except Exception as e:
                    console.print(f"    [bold red]Failed to setup YTMusic headers:[/bold red] {e}\n")

        elif method == "cookies":
            default_cookie = "cookies_yt.txt" if os.path.exists("cookies_yt.txt") else ""
            c_file = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Path to cookies.txt[/bold white]", default=default_cookie)
            if c_file and os.path.exists(c_file):
                config.set("ytmusic", "cookies_file", os.path.abspath(c_file))
                console.print(f"    [bold green]Saved YTMusic cookies file:[/] [bold cyan]{c_file}[/bold cyan]\n")
            else:
                console.print("    [dim]Cookies file not found. Skipped.[/dim]\n")

    # Spotify
    if plat in ("all", "spotify"):
        render_step_header(
            step_num="AUTH",
            title="Spotify Authentication",
            subtitle="Choose Zero-Config Free Mode or configure Spotify Developer credentials",
            badge="SPOTIFY",
            badge_color="#15803d",
        )
        console.print(
            "    [bold #38bdf8]NOTE:[/] Spotify Web API requires an active Spotify Premium subscription for Developer Apps.\n"
            "    [dim]You DO NOT need Spotify Premium or any API keys to read, export, or convert FROM Spotify.\n"
            "    PlayConv extracts tracks and metadata from public Spotify URLs automatically with zero credentials.[/dim]\n"
        )
        console.print("    [bold white on #16a34a]  1  [/]  [bold bright_white]Use Zero-Config Free Mode[/] [dim](Recommended - no Spotify Premium or API keys needed)[/]")
        console.print("    [bold white on #475569]  2  [/]  [bold bright_white]Configure Developer App[/]   [dim](Requires Spotify Premium account)[/]")
        console.print("    [bold white on #475569]  3  [/]  [bold bright_white]Clear Saved Credentials[/]  [dim](Reset to zero-config mode)[/]")
        console.print()
        sp_choice = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Choose Spotify mode [1-3][/bold white]", choices=["1", "2", "3"], default="1")

        if sp_choice in ("1", "3"):
            config.set("spotify", "client_id", "")
            config.set("spotify", "client_secret", "")
            if os.path.exists(config.spotify_token_cache):
                try:
                    os.remove(config.spotify_token_cache)
                except Exception:
                    pass
            if sp_choice == "1":
                console.print("    [bold green]Zero-Config mode active. No Spotify Premium required to read/export Spotify playlists.[/bold green]\n")
            else:
                console.print("    [bold green]Cleared Spotify credentials and token cache.[/bold green]\n")

        elif sp_choice == "2":
            cur_id = config.spotify_client_id
            cur_sec = config.spotify_client_secret
            cid = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Spotify Client ID[/bold white]", default=cur_id).strip()
            csec = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Spotify Client Secret[/bold white]", default=cur_sec).strip()

            if cid:
                config.set("spotify", "client_id", cid)
            if csec:
                config.set("spotify", "client_secret", csec)

            if cid and csec:
                if Confirm.ask("  [bold #00f0ff]>[/] [bold white]Authenticate with Spotify now in browser?[/bold white]", default=True):
                    try:
                        import spotipy
                        from spotipy.oauth2 import SpotifyOAuth
                        from .platforms.spotify import SPOTIFY_SCOPES
                        sp_oauth = SpotifyOAuth(
                            client_id=cid,
                            client_secret=csec,
                            redirect_uri=config.spotify_redirect_uri,
                            scope=SPOTIFY_SCOPES,
                            cache_path=config.spotify_token_cache,
                            open_browser=True,
                        )
                        sp = spotipy.Spotify(auth_manager=sp_oauth)
                        user = sp.me()
                        console.print(f"    [bold green]Successfully authenticated as Spotify user:[/] [bold cyan]{user.get('display_name')}[/bold cyan]\n")
                    except Exception as e:
                        err_str = str(e)
                        if "Active premium subscription required" in err_str or "403" in err_str:
                            console.print(
                                "\n    [bold #d97706]SPOTIFY PREMIUM RESTRICTION DETECTED[/bold #d97706]\n"
                                "    [dim]Spotify's developer policy mandates paid Spotify Premium for Developer Apps.\n"
                                "    Since your account does not have Premium, PlayConv has automatically cleared\n"
                                "    these credentials and reverted to 100% free zero-config mode.[/dim]\n"
                            )
                            config.set("spotify", "client_id", "")
                            config.set("spotify", "client_secret", "")
                            if os.path.exists(config.spotify_token_cache):
                                try:
                                    os.remove(config.spotify_token_cache)
                                except Exception:
                                    pass
                        else:
                            console.print(f"    [bold red]Spotify auth failed:[/bold red] {e}\n")

    # JioSaavn
    if plat in ("all", "jiosaavn"):
        render_step_header(
            step_num="AUTH",
            title="JioSaavn Authentication",
            subtitle="Paste your session cookie string or path to cookies.txt (from jiosaavn.com)",
            badge="JIOSAAVN",
            badge_color="#0284c7",
        )
        cookie = Prompt.ask("  [bold #00f0ff]>[/] [bold white]JioSaavn Cookie string or cookies.txt path[/bold white] [dim](press Enter to skip)[/dim]", default=config.jiosaavn_cookie)
        if cookie:
            val = cookie.strip()
            if os.path.isfile(val):
                config.set("jiosaavn", "cookies_file", os.path.abspath(val))
                console.print(f"    [bold green]Saved JioSaavn cookies file:[/] [bold cyan]{val}[/bold cyan]\n")
            else:
                config.set("jiosaavn", "cookie", val)
                console.print("    [bold green]Saved JioSaavn session cookie.[/bold green]\n")

    # Amazon Music
    if plat in ("all", "amazonmusic", "amazon", "amz"):
        render_step_header(
            step_num="AUTH",
            title="Amazon Music Authentication",
            subtitle="Paste your session cookie string or path to cookies.txt (from music.amazon.com)",
            badge="AMAZON",
            badge_color="#ea580c",
        )
        cookie = Prompt.ask("  [bold #00f0ff]>[/] [bold white]Amazon Music Cookie string or cookies.txt path[/bold white] [dim](press Enter to skip)[/dim]", default=config.amazon_music_cookie)
        if cookie:
            val = cookie.strip()
            if os.path.isfile(val):
                config.set("amazonmusic", "cookies_file", os.path.abspath(val))
                console.print(f"    [bold green]Saved Amazon Music cookies file:[/] [bold cyan]{val}[/bold cyan]\n")
            else:
                config.set("amazonmusic", "cookie", val)
                console.print("    [bold green]Saved Amazon Music session cookie.[/bold green]\n")


@main.command("config")
@click.option("--show", is_flag=True, default=True, help="Show current configuration")
def config_cmd(show: bool):
    """View saved configurations and file locations."""
    show_banner()
    import json
    console.print(f"  [bold #00f0ff]>[/] [bold bright_white]Configuration file:[/] [bold cyan]{config.config_file}[/bold cyan]\n")
    data = dict(config._data)
    if "spotify" in data and "client_secret" in data["spotify"] and data["spotify"]["client_secret"]:
        data["spotify"]["client_secret"] = "********"
    if "jiosaavn" in data and "cookie" in data["jiosaavn"] and data["jiosaavn"]["cookie"]:
        data["jiosaavn"]["cookie"] = data["jiosaavn"]["cookie"][:15] + "..."
    if "amazonmusic" in data and "cookie" in data["amazonmusic"] and data["amazonmusic"]["cookie"]:
        data["amazonmusic"]["cookie"] = data["amazonmusic"]["cookie"][:15] + "..."
    console.print_json(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
