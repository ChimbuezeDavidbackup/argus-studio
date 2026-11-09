<div align="center">

<img src="app_icon.png" alt="Argus Studio Logo" width="96" height="96" />

# Argus Studio

**A cross-platform desktop media downloader and format converter built with CustomTkinter, yt-dlp, and FFmpeg.**

[![Platform: Windows | Linux | macOS](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-0078D6.svg)](https://github.com/ChimbuezeDavidbackup/argus-studio)
[![Release: v2.2.0](https://img.shields.io/badge/Release-v2.2.0-blue.svg)](https://github.com/ChimbuezeDavidbackup/argus-studio/releases)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![UI: CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Engine: yt-dlp](https://img.shields.io/badge/Engine-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Overview](#overview) • [Why Desktop Application](#why-desktop-application) • [Engineering Decisions](#engineering-decisions) • [Features](#features) • [Installation](#installation) • [Releases & Updates](#releases--updates) • [Building from Source](#building-from-source)

</div>

---

## Overview

**Argus Studio** is a desktop application for downloading and transcoding online media across Windows, Linux, and macOS. It provides a clean, responsive interface for single links, playlists, and batch URLs, backed by concurrent worker queues and high-efficiency media tools.

### Architecture
- **Desktop UI (`desktop/`)**: Built with CustomTkinter, supporting system, dark, and light themes, responsive queue telemetry (speed, ETA, progress), and diagnostics.
- **Engine Layer (`core/`)**: Integrates `yt-dlp`, `curl_cffi`, and `FFmpeg` to handle media extraction, stream multiplexing, timestamp trimming, and metadata tagging.
- **Updater (`core/updater.py`)**: Checks GitHub Releases for new versions and applies in-place updates.

---

## Why Desktop Application

Earlier prototypes evaluated cloud backend services, but desktop execution proved fundamentally superior for media extraction:

- **Datacenter IP Restrictions**: Major streaming platforms block requests originating from cloud host IP ranges (AWS, DigitalOcean, Render, etc.) with automated bot challenges. Running directly on a local desktop uses residential network connections where requests pass normally.
- **Zero Bandwidth Costs**: Downloading and transcoding high-resolution video streams in the cloud consumes substantial bandwidth, quickly hitting hosting caps or requiring costly proxy infrastructure. A local desktop app incurs zero hosting expense.
- **Direct Local File Storage**: Media saves directly into the user's `Downloads\ArgusStudio` directory.
- **Hardware Utilization**: Audio conversion, video stream merging, and section clipping leverage the user's multi-core CPU and disk directly without container resource caps.

---

## Engineering Decisions

| Challenge | Cause | Resolution in Argus Studio |
| :--- | :--- | :--- |
| **Datacenter Bot Blocks** | Streaming platforms reject requests originating from cloud host IP ranges. | **Residential Desktop Execution**: Direct client execution paired with anti-bot client profile rotation (`['android', 'ios', 'web_creator', 'mweb']`). |
| **TLS Fingerprinting on Alternative Sites** | Non-YouTube sites (e.g. Dailymotion, Vimeo) reject default Python HTTP clients. | **`curl_cffi` Impersonation**: Uses browser-mimicking TLS fingerprints so requests succeed across different media extractors. |
| **Bundled FFmpeg Path Discovery (Windows)** | In PyInstaller single-file builds, `sys._MEIPASS` points to a temporary directory, missing the FFmpeg binaries installed into `{app}\bin`. | **Application-Relative Discovery**: `get_ffmpeg_location()` in `core/engine.py` inspects `os.path.join(os.path.dirname(sys.executable), "bin")` first, ensuring bundled binaries work out of the box on Windows. |
| **Cross-Platform Storage Isolation** | Operating systems store user preferences in different locations. | **Platform-Native Paths**: Automatically resolves `%APPDATA%\ArgusStudio` (Windows), `~/.local/share/ArgusStudio` (Linux), and `~/Library/Application Support/ArgusStudio` (macOS). |
| **Update Check 404 Handling** | When no GitHub releases exist yet, the GitHub API returns HTTP 404, which previously triggered a generic connection error. | **Status Fallback**: `core/updater.py` handles 404 by returning `"Running latest build"` rather than raising an error dialog. |
| **DASH Stream Multiplexing** | High-definition formats (1080p, 1440p, 4K) serve video and audio as separate tracks. | **Integrated FFmpeg Engine**: Bundled static binaries on Windows, and seamless discovery of system FFmpeg on Linux and macOS. |
| **Windows File Locking (`WinError 32`)** | Antivirus scanners and Windows Search Indexer can lock `.part` temporary files during finalization. | **Direct-to-Target File I/O**: Downloads stream directly to destination containers (`nopart: True`) with exponential retry backoff. |
| **Crash Visibility in Windowed Builds** | Packaged GUI executables (`--noconsole`) silently discard standard output and error streams. | **Diagnostic Logging**: Unhandled exceptions are captured via `sys.excepthook` and written to the platform runtime log. |

---

## Features

- **Video Downloads**: Single videos, playlists, and channel URLs with resolution options from 360p up to 4K (2160p), merged into MP4 or MKV containers.
- **Audio Extraction**: Conversion to MP3 (up to 320 kbps), M4A, FLAC, or WAV, with automatic cover art embedding and ID3 tag writing via Mutagen.
- **Timestamp Trimming**: Download specific segments (`Start: HH:MM:SS` to `End: HH:MM:SS`) using stream slicing without fetching entire files.
- **Subtitles**: Closed-caption extraction with sidecar `.srt` or direct container embedding.
- **Queue Management**: Multi-worker background queue with live telemetry (speed, ETA, file size) updating continuously.
- **Multi-Theme Support**: Clean System, Dark, and Light appearance modes with vector icons.

---

## Installation

Precompiled packages for all platforms are available on the [Releases](https://github.com/ChimbuezeDavidbackup/argus-studio/releases) page:

### 🪟 Windows
1. Download **`ArgusStudio-Setup-v2.2.0.exe`**.
2. Run the setup installer (installs to `%LOCALAPPDATA%\Programs\Argus Studio` without administrator rights).
3. Launch from the desktop shortcut or Start Menu. Static FFmpeg and FFprobe binaries are bundled.

---

### 🐧 Ubuntu / Debian Linux
1. Ensure system prerequisites are present:
   ```bash
   sudo apt update && sudo apt install -y python3-tk ffmpeg
   ```
2. Download and extract **`ArgusStudio-Linux-x86_64.tar.gz`**:
   ```bash
   tar -xzvf ArgusStudio-Linux-x86_64.tar.gz
   chmod +x ArgusStudio
   ./ArgusStudio
   ```

---

### 🍏 macOS (Intel & Apple Silicon)
1. Ensure FFmpeg is installed via Homebrew:
   ```bash
   brew install ffmpeg
   ```
2. Download **`ArgusStudio-macOS.zip`**, extract the archive, and move **`Argus Studio.app`** to your `/Applications` folder.

---

## Releases & Updates

Argus Studio utilizes a multi-platform GitHub Actions CI/CD pipeline that automatically builds and attaches native binaries for Windows, Linux, and macOS upon every version tag release.

The desktop client includes an in-app updater that checks for newer version tags:
1. On launch (or via **Settings > Check for Updates**), the app queries the GitHub Releases API.
2. If a newer version is available, a prompt appears showing the release notes.
3. On Windows, clicking **Update Now** downloads the installer and upgrades the app silently in place.

---

## Building from Source

### Requirements
- Python 3.10 or higher
- Git
- FFmpeg (system package on Linux/macOS; bundled in `bin/` on Windows)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (Windows only, required to compile the setup installer)

### Build Commands
```bash
# Windows (PyInstaller + Inno Setup)
python -m PyInstaller ArgusStudio.spec --noconfirm
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss

# Linux (Standalone Binary)
pyinstaller --name ArgusStudio --onedir --windowed --noconfirm app.py

# macOS (Application Bundle)
pyinstaller --name ArgusStudio --windowed --noconfirm app.py
```

---

## Diagnostics

- **Log File Locations**:
  - **Windows**: `%APPDATA%\ArgusStudio\argus_runtime.log`
  - **Linux**: `~/.local/share/ArgusStudio/argus_runtime.log`
  - **macOS**: `~/Library/Application Support/ArgusStudio/argus_runtime.log`
- **FFmpeg Status**: Check status in the app under **Settings > Diagnostics**.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
