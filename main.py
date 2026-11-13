#!/usr/bin/env python3
"""
PlayConv - Main CLI Entry Point.
Universal Music Playlist Converter & CSV Exporter.
"""

import sys
from playconv.cli import main
from playconv.ui import display_exit_message

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, KeyboardInterrupt):
            display_exit_message(interrupted=True)
            sys.exit(0)
        sys.exit(e.code if hasattr(e, "code") else 0)
