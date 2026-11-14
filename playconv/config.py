"""
Configuration and credentials management for PlayConv.
Persists settings and credentials locally in ~/.playconv/config.json.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".playconv"
CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


def parse_cookie_input(raw: str) -> Dict[str, str]:
    """
    Parses cookies from:
    1. Netscape/Mozilla cookies.txt format (tab-separated)
    2. Raw HTTP 'Cookie: a=1; b=2' or 'a=1; b=2' string
    3. File path containing either format
    """
    if not raw:
        return {}
    raw = raw.strip()
    if os.path.isfile(raw):
        try:
            with open(raw, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read().strip()
        except Exception:
            return {}

    cookies: Dict[str, str] = {}
    if "\t" in raw or raw.startswith("#"):
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5].strip()
                val = parts[6].strip()
                if name:
                    cookies[name] = val
    else:
        if raw.lower().startswith("cookie:"):
            raw = raw[7:].strip()
        for item in raw.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                k_clean = k.strip()
                v_clean = v.strip()
                if k_clean:
                    cookies[k_clean] = v_clean
    return cookies


def cookies_to_header_str(cookies: Dict[str, str]) -> str:
    """Converts cookie dictionary to a clean standard HTTP Cookie header string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


class Config:
    """Manages persistent application settings and credentials."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_dir = config_path.parent if config_path else DEFAULT_CONFIG_DIR
        self.config_file = config_path or CONFIG_FILE
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads configuration from JSON file or returns default structure."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read config file {self.config_file}: {e}")
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "spotify": {
                "client_id": os.environ.get("SPOTIPY_CLIENT_ID", ""),
                "client_secret": os.environ.get("SPOTIPY_CLIENT_SECRET", ""),
                "redirect_uri": os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
                "token_cache": str(self.config_dir / ".spotify_cache"),
            },
            "ytmusic": {
                "auth_file": str(self.config_dir / "ytmusic_auth.json"),
                "cookies_file": "",
            },
            "jiosaavn": {
                "cookie": "",
                "cookies_file": "",
            },
            "amazonmusic": {
                "cookie": "",
                "cookies_file": "",
                "access_token": "",
            },
            "matching": {
                "confidence_threshold": 0.75,
                "exact_threshold": 0.85,
                "duration_tolerance_sec": 15,
                "strict_duration": False,
            },
            "output": {
                "export_csv": True,
                "output_dir": ".",
            },
        }

    def save(self) -> None:
        """Saves current configuration to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config to {self.config_file}: {e}")

    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        sec = self._data.get(section, {})
        if key is None:
            return sec
        return sec.get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self.save()

    # Spotify Helpers
    @property
    def spotify_client_id(self) -> str:
        return self.get("spotify", "client_id") or os.environ.get("SPOTIPY_CLIENT_ID", "")

    @property
    def spotify_client_secret(self) -> str:
        return self.get("spotify", "client_secret") or os.environ.get("SPOTIPY_CLIENT_SECRET", "")

    @property
    def spotify_redirect_uri(self) -> str:
        return self.get("spotify", "redirect_uri") or os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    @property
    def spotify_token_cache(self) -> str:
        return self.get("spotify", "token_cache", str(self.config_dir / ".spotify_cache"))

    # YouTube Music Helpers
    @property
    def ytmusic_auth_file(self) -> str:
        auth_file = self.get("ytmusic", "auth_file")
        if auth_file and os.path.exists(auth_file):
            return auth_file
        # Check if local headers_auth.json or browser.json exists in cwd or config_dir
        search_dirs = [Path("."), self.config_dir]
        for sdir in search_dirs:
            for candidate in ["browser.json", "oauth.json", "headers_auth.json", "ytmusic_auth.json"]:
                p = sdir / candidate
                if p.exists():
                    return str(p.resolve())
        return auth_file

    @property
    def ytmusic_cookies_file(self) -> Optional[str]:
        cookie_path = self.get("ytmusic", "cookies_file")
        if cookie_path and os.path.exists(cookie_path):
            return cookie_path
        # Also check default local names in current working directory and config_dir
        for sdir in [Path("."), self.config_dir]:
            for cand in ["cookies_yt.txt", "cookies.txt"]:
                p = sdir / cand
                if p.exists():
                    return str(p.resolve())
        return None

    # JioSaavn Helpers
    @property
    def jiosaavn_cookie(self) -> str:
        raw = self.get("jiosaavn", "cookie")
        cookie_file = self.get("jiosaavn", "cookies_file")
        source = raw or cookie_file or ""
        cookies = parse_cookie_input(source)
        return cookies_to_header_str(cookies)

    def jiosaavn_cookie_dict(self) -> Dict[str, str]:
        raw = self.get("jiosaavn", "cookie")
        cookie_file = self.get("jiosaavn", "cookies_file")
        source = raw or cookie_file or ""
        return parse_cookie_input(source)

    # Amazon Music Helpers
    @property
    def amazon_music_cookie(self) -> str:
        raw = self.get("amazonmusic", "cookie")
        cookie_file = self.get("amazonmusic", "cookies_file")
        source = raw or cookie_file or ""
        cookies = parse_cookie_input(source)
        return cookies_to_header_str(cookies)

    def amazon_music_cookie_dict(self) -> Dict[str, str]:
        raw = self.get("amazonmusic", "cookie")
        cookie_file = self.get("amazonmusic", "cookies_file")
        source = raw or cookie_file or ""
        return parse_cookie_input(source)

    @property
    def amazon_music_access_token(self) -> str:
        return self.get("amazonmusic", "access_token") or os.environ.get("AMAZON_MUSIC_ACCESS_TOKEN", "")

    # Matching settings
    @property
    def confidence_threshold(self) -> float:
        return float(self.get("matching", "confidence_threshold", 0.75))

    @property
    def exact_threshold(self) -> float:
        return float(self.get("matching", "exact_threshold", 0.85))

    @property
    def duration_tolerance_sec(self) -> int:
        return int(self.get("matching", "duration_tolerance_sec", 15))


# Global singleton instance
config = Config()
