# PlayConv

```
██████╗ ██╗      █████╗ ██╗   ██╗ ██████╗ ██████╗ ███╗   ██╗██╗   ██╗
██╔══██╗██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔═══██╗████╗  ██║██║   ██║
██████╔╝██║     ███████║ ╚████╔╝ ██║     ██║   ██║██╔██╗ ██║██║   ██║
██╔═══╝ ██║     ██╔══██║  ╚██╔╝  ██║     ██║   ██║██║╚██╗██║╚██╗ ██╔╝
██║     ███████╗██║  ██║   ██║   ╚██████╗╚██████╔╝██║ ╚████║ ╚████╔╝ 
╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝  ╚═══╝  
```

> **Universal Music Playlist Converter, CSV Archiver & Exact Track Matcher CLI.**  
> Effortlessly convert playlists, albums, and tracks between **Spotify**, **YouTube Music**, **JioSaavn**, **Deezer**, and **Apple Music** with intelligent exact-matching heuristics and rich CSV exports.

---

## Key Features

- **Multi-Platform Cross-Conversion**:
  - **Spotify** <-> **YouTube Music**
  - **Spotify** <-> **JioSaavn**
  - **JioSaavn** <-> **YouTube Music**
  - **Apple Music / Deezer** -> **YouTube Music / JioSaavn / Spotify / CSV**
- **Full Entity Support (Playlists, Albums & Tracks)**:
  - Supports Playlist URLs, Album URLs, Single Track URLs, and CSV spreadsheets.
- **Intelligent Exact Match Engine**:
  - **ISRC (International Standard Recording Code)** matching for 100% verified matches.
  - **Smart Title Normalization**: Automatically strips promo subtitles, feature tags `(feat. ...)`, movie tags `(From "Movie")`, remasters `(Remastered 2011)`, video tags `[Official Video]`, and live tags.
  - **Multi-Artist & Collaborator Alignment**: Compares primary artists and collaborating singers/producers.
  - **Duration Tolerance Filters**: Strict duration comparison (e.g. within 10-15 seconds) preventing matching 10-minute live videos or short ringtones.
  - **Confidence Scoring (0-100%)**: Configurable match thresholds with strict `--exact` mode.
- **Rich CSV & M3U8 Export**:
  - Automatically exports structured metadata (Excel/Google Sheets-friendly `utf-8-sig` with UTF-8 BOM): Track Title, Artists, Album, Year, Duration, ISRC, Source URL, Destination URL, Match Score, Match Status, and Cover Art.
  - Export extended `#EXTM3U8` playlists compatible with VLC, Apple Music, and local media players.
- **Direct Remote Playlist Creation**:
  - Automatically provisions the newly converted playlist with matched songs on your destination platform account.
- **Two Flexible Usage Modes**:
  1. **Interactive Wizard**: Step-by-step guided prompt when launched without parameters.
  2. **Headless CLI Flags**: Rich command-line switches for scripts, cron jobs, and terminal power-users.
- **100% Privacy-First & Local**:
  - Runs entirely on your local machine. No third-party cloud servers or monthly transfer subscriptions.

---

## Installation

### Prerequisites
- **Python 3.9+** installed on your system.

### Install from Source

Clone or navigate to the repository directory:

```bash
cd PlayConv
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Install in editable mode to register the `playconv` command globally in your terminal:

```bash
pip install -e .
```

---

## Quick Start & Usage

### 1. Interactive Mode (Wizard)
Simply run `playconv` with no arguments to launch the interactive terminal wizard:

```bash
playconv
```
*(Or `python main.py`)*

```
=== INTERACTIVE PLAYLIST CONVERTER WIZARD ===

  [1] Convert Collection     Convert Playlist / Album / Track across platforms    RECOMMENDED
  [2] Export to CSV          Export full metadata from any music URL to CSV file
  [3] Import CSV to Service  Create a playlist on a platform from an existing CSV file
  [4] Inspect URL Info       Preview collection tracks and metadata without converting
  [5] Platform Accounts      Configure YouTube Music, Spotify, or JioSaavn credentials
  [6] Exit
```

---

### 2. Command-Line (CLI) Modes

#### A. Convert Across Platforms (Direct URL)
Convert any Spotify, JioSaavn, YouTube Music, or Deezer playlist/album/track directly to another service:

```bash
# JioSaavn to YouTube Music (Exact matches only)
playconv convert "https://www.jiosaavn.com/featured/todays-top-hits/Iz0pi7nkjUHfemJ68FuXsA__" --to ytmusic --exact

# Spotify to YouTube Music with custom playlist title
playconv convert "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" --to ytmusic --name "Top Hits 2026"

# Spotify to JioSaavn
playconv convert "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT" --to jiosaavn --exact

# Convert an Album URL
playconv convert "https://www.jiosaavn.com/album/brahmastra/xq4v9ZFC9iA_" --to ytmusic
```

#### B. Export Tracklist to CSV
Export metadata for any playlist, album, or track without converting:

```bash
# Export to CSV
playconv export "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" -o top_hits.csv

# Export to both CSV and M3U8
playconv export "https://www.jiosaavn.com/album/brahmastra/xq4v9ZFC9iA_" -o brahmastra.csv --m3u
```

#### C. Import CSV & Create Playlist on Platform
Take an existing CSV file (exported by PlayConv, JSD-CSV, SpotDL, SoundShift, or a custom spreadsheet) and convert it onto a platform:

```bash
playconv import top_hits.csv --to ytmusic --name "Imported Hits" --exact
```

#### D. Preview Collection Metadata & Tracks
Inspect any music URL or CSV file in the terminal before converting:

```bash
playconv info "https://www.jiosaavn.com/album/brahmastra/xq4v9ZFC9iA_"
```

#### E. Manage Authentication & Credentials
```bash
playconv auth
# Or for a specific service:
playconv auth ytmusic
playconv auth spotify
playconv auth jiosaavn
```

#### F. Inspect Configuration
```bash
playconv config
```

---

## Platform Authentication Guide

| Platform | Reading / Exporting | Creating Playlists | Auth Setup Command |
| :--- | :---: | :---: | :--- |
| **YouTube Music** | Zero Auth Required | Session Headers / Cookies / OAuth | `playconv auth ytmusic` |
| **JioSaavn** | Zero Auth Required | Session Cookie | `playconv auth jiosaavn` |
| **Spotify** | Zero Auth (Embed fallback) | Free Spotify Developer App OAuth | `playconv auth spotify` |
| **Deezer** | Zero Auth (Public API) | Not Supported | Built-in |
| **Apple Music** | Zero Auth (Schema scraper) | Not Supported | Built-in |

### Setting Up YouTube Music Writing
1. Open [music.youtube.com](https://music.youtube.com) in your browser while logged in.
2. Press `F12` to open Developer Tools, head to the **Network** tab, and reload the page.
3. Click on any network request, right click and choose **Copy** -> **Copy request headers**.
4. Run `playconv auth ytmusic`, select `headers`, and paste the text.
*(Alternatively, place a `cookies_yt.txt` or `cookies.txt` file in your working directory).*

### Setting Up Spotify Writing
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create a free application.
2. Set the **Redirect URI** to: `http://127.0.0.1:8888/callback`
3. Run `playconv auth spotify` and enter your **Client ID** and **Client Secret**.
4. Accept the browser prompt to link your account.

### Setting Up JioSaavn Writing
1. Log in to [jiosaavn.com](https://www.jiosaavn.com) in your browser.
2. Open DevTools (`F12`) -> **Network** tab, inspect any request to `jiosaavn.com`, and copy the `Cookie` header string.
3. Run `playconv auth jiosaavn` and paste the cookie string.

---

## Testing

Run the test suite with `pytest`:

```bash
pytest -v
```

---

## License

MIT License. Built with privacy in mind.
