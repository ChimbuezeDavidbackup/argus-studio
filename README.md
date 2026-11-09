<div align="center">

<img src="app_icon.png" alt="Argus Studio Logo" width="96" height="96" />

# Argus Studio

**A desktop media downloader and format converter built with CustomTkinter, yt-dlp, and FFmpeg.**

[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://github.com/ChimbuezeDavidbackup/argus-studio)
[![Release: v2.2.0](https://img.shields.io/badge/Release-v2.2.0-blue.svg)](https://github.com/ChimbuezeDavidbackup/argus-studio/releases)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![UI: CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Engine: yt-dlp](https://img.shields.io/badge/Engine-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Overview](#overview) • [Why Desktop-First](#why-desktop-first) • [Engineering Decisions](#engineering-decisions) • [Features](#features) • [Installation](#installation) • [Releases & Updates](#releases--updates) • [Building from Source](#building-from-source)

</div>

---

## Overview

**Argus Studio** is a Windows desktop application for downloading and transcoding online media. It provides a clean, single-window interface for single links, playlists, and batch URLs, with background queue processing and bundled media tools.

### Core Architecture
- **Desktop UI (`desktop/`)**: Built with CustomTkinter, offering light, dark, and system themes, responsive telemetry (transfer speed, ETA, progress), and a dedicated download queue.
- **Engine Layer (`core/`)**: Wraps `yt-dlp`, `curl_cffi`, and `FFmpeg` to handle media extraction, stream multiplexing, timestamp trimming, and metadata tagging.
- **Updater (`core/updater.py`)**: Checks GitHub Releases for new versions and applies silent in-place updates.
- **Embedded API (`server/`)**: Optional local FastAPI service (`app.py --server`) for LAN browser access.

---

## Why Desktop-First

Earlier versions experimented with deploying backend extraction services on cloud platforms (e.g. Render, AWS, VPS). In practice, desktop execution proved significantly more practical:

- **Datacenter IP Restrictions**: Major streaming platforms block traffic from cloud hosting providers (AWS, DigitalOcean, Render, etc.) with automated bot challenges. Running directly on a local desktop uses residential network connections where requests pass normally.
- **Bandwidth and Infrastructure Costs**: Downloading and transcoding high-resolution video streams in the cloud consumes substantial bandwidth, quickly hitting hosting limits or requiring expensive rotating residential proxies. A local desktop app has zero infrastructure cost.
- **Direct Local File Storage**: Media saves directly into the user's `Downloads\ArgusStudio` directory without needing a second download pass from a remote server.
- **Hardware Utilization**: Audio conversion, video muxing, and section clipping leverage the user's local multi-core CPU and storage without cloud container resource caps.

---

## Engineering Decisions

| Challenge | Cause | Resolution in Argus Studio |
| :--- | :--- | :--- |
| **Datacenter Bot Blocks** | Streaming platforms reject requests originating from cloud host IP ranges. | **Residential Execution**: Desktop-first design paired with mobile client profile rotation (`['android', 'ios', 'web_creator', 'mweb']`). |
| **TLS Fingerprinting on Alternative Sites** | Non-YouTube sites (e.g. Dailymotion, Vimeo) reject default Python HTTP clients. | **`curl_cffi` Impersonation**: Uses browser-mimicking TLS fingerprints so requests succeed across different media extractors. |
| **Bundled FFmpeg Path Discovery** | In PyInstaller single-file builds, `sys._MEIPASS` points to a temporary directory, missing the FFmpeg binaries installed into `{app}\bin`. | **Application-Relative Discovery**: `get_ffmpeg_location()` in `core/engine.py` inspects `os.path.join(os.path.dirname(sys.executable), "bin")` first, ensuring bundled binaries work out of the box. |
| **Update Check 404 Handling** | When no GitHub releases exist yet, the GitHub API returns HTTP 404, which previously triggered a generic connection error. | **Status Fallback**: `core/updater.py` handles 404 by returning `"Running latest build"` rather than raising an error dialog. |
| **DASH Stream Multiplexing** | High-definition formats (1080p, 1440p, 4K) serve video and audio as separate tracks. | **Bundled Binaries**: Static Windows builds of `ffmpeg.exe` and `ffprobe.exe` are packaged directly inside the Inno Setup installer. |
| **Windows File Locking (`WinError 32`)** | Antivirus scanners and Windows Search Indexer can lock `.part` temporary files during finalization. | **Direct-to-Target File I/O**: Downloads stream directly to destination containers (`nopart: True`) with exponential retry backoff. |
| **Crash Visibility in Windowed Builds** | Packaged GUI executables (`--noconsole`) silently discard standard output and error streams. | **Diagnostic Logging**: Unhandled exceptions are captured via `sys.excepthook` and written to `%APPDATA%\ArgusStudio\argus_runtime.log`. |

---

## Features

- **Video Downloads**: Single videos, playlists, and channel URLs with resolution options from 360p up to 4K (2160p), merged into MP4 or MKV.
- **Audio Extraction**: Conversion to MP3 (up to 320 kbps), M4A, FLAC, or WAV, with automatic cover art embedding and ID3 tag writing via Mutagen.
- **Timestamp Trimming**: Download specific segments (`Start: HH:MM:SS` to `End: HH:MM:SS`) using server-side stream slicing without fetching entire files.
- **Subtitles**: Closed-caption extraction with sidecar `.srt` or direct container embedding.
- **Queue Management**: Multi-worker background queue with live telemetry (speed, ETA, file size) updating continuously.
- **Self-Contained Installer**: Windows setup installer with bundled FFmpeg, desktop shortcuts, and an uninstaller.

---

## Installation

### Windows Installer (Recommended)
1. Download `ArgusStudio-Setup-v2.2.0.exe` from the [Releases](https://github.com/ChimbuezeDavidbackup/argus-studio/releases) page.
2. Run the installer. It installs to `%LOCALAPPDATA%\Programs\Argus Studio` without requiring administrator privileges.
3. Launch **Argus Studio** from the desktop shortcut or Start Menu. All required tools (FFmpeg and FFprobe) are included.

---

## Releases & Updates

Argus Studio includes an in-app updater that checks for newer version tags on GitHub Releases:

1. On launch (or via **Settings > Check for Updates**), the app checks the GitHub API.
2. If a newer version is available, a prompt appears showing the release notes.
3. Clicking **Update Now** downloads the installer in the background and runs it silently (`/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`) to upgrade the app in place.

### Publishing Releases (Maintainers)
1. Set the version number in `core/config.py` (`APP_VERSION`) and `installer.iss` (`MyAppVersion`).
2. Build the executable and installer:
   ```powershell
   python -m PyInstaller ArgusStudio.spec --noconfirm
   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
   ```
3. Create a GitHub Release with the tag (e.g. `v2.3.0`) and attach `dist/ArgusStudio-Setup-vX.X.X.exe`.

---

## Building from Source

### Requirements
- Python 3.10 or higher
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (only needed to compile the setup installer)
- Git

### Setup & Run
```powershell
# Clone the repository
git clone https://github.com/ChimbuezeDavidbackup/argus-studio.git
cd argus-studio

# Install dependencies
pip install -r requirements.txt

# Run desktop client
python app.py

# Optional: Run local web/LAN server
python app.py --server
```

---

## Diagnostics

- **Log File**: Detailed runtime logs are saved to:
  ```
  %APPDATA%\ArgusStudio\argus_runtime.log
  ```
- **FFmpeg Status**: Check status in the app under **Settings > Diagnostics**.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
