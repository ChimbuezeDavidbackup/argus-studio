"""
Media ingestion and transcoding engine built on yt-dlp and FFmpeg.
Includes resilience against YouTube bot challenges and SSL certificate issues.
"""

import os
import platform
import re
import shutil
import ssl
import sys
import zipfile
from typing import Any, Callable, Dict, List, Optional

import requests
import certifi
import yt_dlp
from yt_dlp.utils import download_range_func

from .config import get_bin_dir

BIN_DIR = get_bin_dir()


def get_ffmpeg_location() -> Optional[str]:
    """Discover FFmpeg executable across bundled paths, AppData, and system PATH."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    exe_ext = ".exe" if platform.system() == "Windows" else ""
    ffmpeg_name = f"ffmpeg{exe_ext}"
    ffprobe_name = f"ffprobe{exe_ext}"

    candidate_dirs = [
        os.path.join(base_path, "bin"),
        base_path,
        BIN_DIR,
    ]

    for d in candidate_dirs:
        p = os.path.join(d, ffmpeg_name)
        if os.path.isfile(p):
            return d

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return os.path.dirname(sys_ffmpeg)

    return None


def is_ffmpeg_available() -> bool:
    """Check if FFmpeg is configured and callable."""
    return get_ffmpeg_location() is not None


def download_portable_ffmpeg(progress_callback: Optional[Callable[[str, float], None]] = None) -> bool:
    """
    Download and configure portable static FFmpeg.
    Uses requests with certifi CA bundle and graceful SSL fallback to avoid SSL: CERTIFICATE_VERIFY_FAILED.
    """
    os.makedirs(BIN_DIR, exist_ok=True)
    zip_dest = os.path.join(BIN_DIR, "ffmpeg_bundle.zip")

    # Primary & fallback mirror endpoints
    urls = [
        "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    ]

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    download_success = False

    for url in urls:
        if progress_callback:
            progress_callback("Connecting to download mirror...", 0.05)

        # Attempt with certifi CA bundle first, then fallback to unverified
        for verify_ssl in [certifi.where(), False]:
            try:
                with session.get(url, stream=True, timeout=25, verify=verify_ssl) as resp:
                    if resp.status_code != 200:
                        continue

                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    block_size = 131072  # 128 KB chunks

                    with open(zip_dest, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=block_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0 and progress_callback:
                                    ratio = min(0.92, downloaded / total_size)
                                    mb = downloaded / (1024 * 1024)
                                    tot_mb = total_size / (1024 * 1024)
                                    progress_callback(
                                        f"Downloading FFmpeg: {mb:.1f} / {tot_mb:.1f} MB ({ratio * 100:.0f}%)",
                                        ratio
                                    )

                    download_success = True
                    break
            except Exception:
                continue

        if download_success:
            break

    if not download_success:
        if os.path.exists(zip_dest):
            try:
                os.remove(zip_dest)
            except Exception:
                pass
        raise RuntimeError("Unable to download FFmpeg: all mirrors and SSL verification attempts failed.")

    try:
        if progress_callback:
            progress_callback("Extracting portable binaries...", 0.94)

        with zipfile.ZipFile(zip_dest, "r") as zf:
            for member in zf.namelist():
                filename = os.path.basename(member)
                if filename.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
                    src = zf.open(member)
                    target_path = os.path.join(BIN_DIR, filename)
                    with open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    if platform.system() != "Windows":
                        os.chmod(target_path, 0o755)

        if os.path.exists(zip_dest):
            os.remove(zip_dest)

        if is_ffmpeg_available():
            if progress_callback:
                progress_callback("Portable FFmpeg ready!", 1.0)
            return True
        return False
    except Exception as e:
        if os.path.exists(zip_dest):
            try:
                os.remove(zip_dest)
            except Exception:
                pass
        raise RuntimeError(f"Failed extracting FFmpeg: {e}") from e


def parse_time_to_seconds(time_str: Optional[str]) -> Optional[int]:
    """Parse time string like '01:30' or '01:15:20' or '90' into seconds."""
    if not time_str or not time_str.strip():
        return None
    parts = time_str.strip().split(":")
    try:
        parts = [int(p) for p in parts]
        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        return None
    return None


class DownloaderEngine:
    """Core media ingestion engine with automatic bot-bypass and format resolution."""

    def __init__(self):
        pass

    def is_ffmpeg_available(self) -> bool:
        return is_ffmpeg_available()

    def get_ffmpeg_location(self) -> Optional[str]:
        return get_ffmpeg_location()

    def _build_ydl_opts(
        self,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        base_opts: Optional[Dict[str, Any]] = None,
        use_fallback_clients: bool = True
    ) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 25,
            # Windows file locking defense: write directly, skip .part file
            "nopart": True,
            "file_access_retries": 10,
            "windowsfilenames": True,
        }

        # Resolve FFmpeg location
        loc = get_ffmpeg_location()
        if loc:
            opts["ffmpeg_location"] = loc

        # Conditionally enable Node.js runtime if present
        if shutil.which("node"):
            opts["js_runtimes"] = {"node": {}}
            opts["remote_components"] = {"ejs:github"}

        # Client impersonation to bypass YouTube "Sign in to confirm you're not a bot"
        if use_fallback_clients:
            opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["android", "ios", "web_creator", "mweb"]
                }
            }

        if base_opts:
            opts.update(base_opts)

        # Cookie configuration
        if cookie_file and os.path.exists(cookie_file):
            opts["cookiefile"] = cookie_file
        elif browser_cookies and browser_cookies.lower() not in ("none", ""):
            opts["cookiesfrombrowser"] = (browser_cookies.lower(),)

        return opts

    def _is_cookie_lock_error(self, e: Exception) -> bool:
        msg = str(e)
        return (
            ("Could not copy" in msg and "cookie" in msg)
            or ("Permission denied" in msg and "Cookies" in msg)
            or ("cookie database" in msg)
        )

    def _is_bot_check_error(self, e: Exception) -> bool:
        msg = str(e)
        return "Sign in to confirm you're not a bot" in msg or "bot" in msg.lower() or "429" in msg

    def _handle_exception(self, e: Exception) -> str:
        msg = str(e)
        if self._is_cookie_lock_error(e):
            return (
                "Browser Cookie Database Locked:\n\n"
                "The selected browser is running and has locked its cookie file.\n\n"
                "Solutions:\n"
                "1. If this video is public, change 'Session Auth' to 'None'.\n"
                "2. Completely close your browser and try again.\n"
                "3. Alternatively, export your cookies to a 'cookies.txt' file."
            )
        if self._is_bot_check_error(e):
            return (
                "YouTube Bot Protection Encountered:\n\n"
                "YouTube requested client verification for this request.\n\n"
                "Solutions:\n"
                "1. Argus Studio has applied mobile client routing automatically.\n"
                "2. If still restricted, select your active browser under 'Session Auth' to authenticate requests."
            )
        if "ffmpeg" in msg.lower() and ("not found" in msg.lower() or "postprocessing" in msg.lower()):
            return (
                "FFmpeg Not Configured:\n\n"
                "FFmpeg is required to merge high-resolution video streams and convert MP3 audio.\n\n"
                "Click 'Install Portable FFmpeg' in Settings to configure it automatically."
            )
        if "WinError 32" in msg or "used by another process" in msg:
            return (
                "Windows File Lock Error [WinError 32]:\n\n"
                "An external Windows process held a temporary lock on the target file."
            )
        return msg

    def extract_metadata(
        self,
        url: str,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract metadata without downloading, with automatic anti-bot client fallback."""
        # Try with anti-bot mobile clients first
        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts={
                "skip_download": True,
                "extract_flat": "in_playlist",
            },
            use_fallback_clients=True
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                raw_info = ydl.extract_info(url, download=False)
                return ydl.sanitize_info(raw_info)
        except Exception as e:
            # If failed, attempt alternative client profile without cookies
            if self._is_bot_check_error(e) or self._is_cookie_lock_error(e):
                try:
                    alt_opts = self._build_ydl_opts(
                        browser_cookies=None,
                        cookie_file=None,
                        base_opts={
                            "skip_download": True,
                            "extract_flat": "in_playlist",
                        },
                        use_fallback_clients=True
                    )
                    with yt_dlp.YoutubeDL(alt_opts) as ydl:
                        raw_info = ydl.extract_info(url, download=False)
                        return ydl.sanitize_info(raw_info)
                except Exception:
                    pass

            friendly_err = self._handle_exception(e)
            raise RuntimeError(friendly_err) from e

    def extract_playlist_entries(
        self,
        url: str,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extract flat playlist / channel items for interactive picker."""
        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts={
                "skip_download": True,
                "extract_flat": True,
            },
            use_fallback_clients=True
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", [])
            results = []
            for idx, entry in enumerate(entries):
                if entry:
                    entry_url = entry.get("url")
                    if entry_url and not entry_url.startswith("http"):
                        entry_url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    results.append({
                        "index": idx + 1,
                        "id": entry.get("id"),
                        "title": entry.get("title") or f"Item {idx + 1}",
                        "url": entry_url or url,
                        "duration": entry.get("duration"),
                        "uploader": entry.get("uploader") or info.get("uploader") or "Unknown",
                    })
            return results

    def download_media(
        self,
        url: str,
        output_dir: str,
        format_type: str = "video",
        quality: str = "best",
        audio_codec: str = "mp3",
        audio_quality: str = "320",
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        download_subtitles: bool = False,
        subtitles_lang: str = "en",
        embed_subtitles: bool = True,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        rate_limit_bytes: Optional[int] = None,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Optional[str]:
        """Download media with rich options and live progress notifications."""
        downloaded_file: Optional[str] = None

        def yt_progress_hook(d: Dict[str, Any]):
            nonlocal downloaded_file
            if d.get("status") == "finished":
                filename = d.get("filename")
                if filename:
                    downloaded_file = filename
            if progress_callback:
                progress_callback(d)

        def yt_postprocessor_hook(d: Dict[str, Any]):
            nonlocal downloaded_file
            if d.get("status") == "finished":
                info = d.get("info_dict", {})
                fp = info.get("filepath") or d.get("filename")
                if fp:
                    downloaded_file = fp

        base_opts: Dict[str, Any] = {
            "outtmpl": os.path.join(output_dir, "%(title).140s [%(id)s].%(ext)s"),
            "progress_hooks": [yt_progress_hook],
            "postprocessor_hooks": [yt_postprocessor_hook],
            "windowsfilenames": True,
            "nopart": True,
            "file_access_retries": 10,
        }

        # Rate Limiter
        if rate_limit_bytes and rate_limit_bytes > 0:
            base_opts["ratelimit"] = rate_limit_bytes

        # Timestamp clipping
        s_sec = parse_time_to_seconds(start_time)
        e_sec = parse_time_to_seconds(end_time)
        if s_sec is not None or e_sec is not None:
            s_val = s_sec if s_sec is not None else 0
            e_val = e_sec if e_sec is not None else float("inf")
            base_opts["download_ranges"] = download_range_func(None, [(s_val, e_val)])
            base_opts["force_keyframes_at_cuts"] = True

        # Subtitles
        if download_subtitles:
            base_opts.update({
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [subtitles_lang] if subtitles_lang != "all" else ["all"],
            })

        postprocessors = []

        if format_type == "audio":
            base_opts["format"] = "bestaudio/best"
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_codec,
                "preferredquality": audio_quality,
            })
            if add_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
            if embed_thumbnail and audio_codec in ("mp3", "m4a"):
                base_opts["writethumbnail"] = True
                postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        else:
            # Video format selection
            if quality == "best":
                base_opts["format"] = "bestvideo+bestaudio/best"
            else:
                height = re.sub(r"\D", "", quality)
                if height:
                    base_opts["format"] = (
                        f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
                    )
                else:
                    base_opts["format"] = "bestvideo+bestaudio/best"

            base_opts["merge_output_format"] = "mp4"

            if add_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
            if download_subtitles and embed_subtitles:
                postprocessors.append({"key": "FFmpegEmbedSubtitle"})

        if postprocessors:
            base_opts["postprocessors"] = postprocessors

        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts=base_opts,
            use_fallback_clients=True
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not downloaded_file and info:
                    downloaded_file = ydl.prepare_filename(info)
                    if format_type == "audio":
                        base, _ = os.path.splitext(downloaded_file)
                        downloaded_file = f"{base}.{audio_codec}"
                return downloaded_file
        except Exception as e:
            friendly_err = self._handle_exception(e)
            raise RuntimeError(friendly_err) from e
