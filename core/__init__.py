"""
Argus Studio - Core Domain Package
Platform-agnostic ingestion engine, queue management, and data models.
"""

from .models import DownloadTask, MediaMetadata, FormatOption
from .config import load_config, save_config, load_library, save_library, get_data_dir, get_bin_dir
from .engine import DownloaderEngine, is_ffmpeg_available, get_ffmpeg_location, download_portable_ffmpeg
from .queue import QueueManager

__all__ = [
    "DownloadTask",
    "MediaMetadata",
    "FormatOption",
    "load_config",
    "save_config",
    "load_library",
    "save_library",
    "get_data_dir",
    "get_bin_dir",
    "DownloaderEngine",
    "is_ffmpeg_available",
    "get_ffmpeg_location",
    "download_portable_ffmpeg",
    "QueueManager",
]
