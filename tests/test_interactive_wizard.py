from unittest.mock import patch
from playconv.cli import run_interactive_wizard
from playconv.models import PlatformType, PlaylistMetadata, Track


def test_run_interactive_wizard_convert_flow():
    # Simulate user choosing option 1 (Convert Collection), entering a CSV path, choosing destination 5 (CSV), and confirming
    track = Track(title="Song 1", artists=["Artist 1"], duration_sec=180)
    dummy_playlist = PlaylistMetadata(title="Test", tracks=[track], source_platform=PlatformType.CSV)

    prompts = [
        "1",                    # Main menu: Convert Collection
        "test_playlist.csv",    # Step 1: Source URL/file
        "5",                    # Step 2: Destination Platform: 5 (CSV File)
        "Converted Title",      # Step 3: Playlist Title
    ]

    with patch("rich.prompt.Prompt.ask", side_effect=prompts), \
         patch("rich.prompt.Confirm.ask", return_value=True), \
         patch("playconv.cli.resolve_source_to_playlist", return_value=dummy_playlist), \
         patch("playconv.cli.PlaylistConverter.convert") as mock_convert:
        run_interactive_wizard()
        assert mock_convert.called


def test_run_interactive_wizard_inspect_info_flow():
    track = Track(title="Song 1", artists=["Artist 1"], duration_sec=180)
    dummy_playlist = PlaylistMetadata(title="Test", tracks=[track], source_platform=PlatformType.CSV)

    prompts = [
        "4",                    # Main menu: Inspect URL Info
        "test_playlist.csv",    # Source to inspect
    ]

    with patch("rich.prompt.Prompt.ask", side_effect=prompts), \
         patch("playconv.cli.resolve_source_to_playlist", return_value=dummy_playlist):
        run_interactive_wizard()
