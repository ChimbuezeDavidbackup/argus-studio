"""
Root wrapper for backward compatibility. Delegates to core.engine.
"""

from core.engine import (
    DownloaderEngine,
    parse_time_to_seconds,
    is_ffmpeg_available,
    get_ffmpeg_location,
    download_portable_ffmpeg,
)

__all__ = [
    "DownloaderEngine",
    "parse_time_to_seconds",
    "is_ffmpeg_available",
    "get_ffmpeg_location",
    "download_portable_ffmpeg",
]
