"""
Core data models for Argus Studio.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FormatOption:
    label: str
    quality: str
    format_type: str  # "video" or "audio"


@dataclass
class MediaMetadata:
    id: str
    title: str
    uploader: str
    duration: int
    duration_string: str
    view_count: int
    view_count_string: str
    thumbnail: Optional[str]
    formats: List[Dict[str, Any]] = field(default_factory=list)
    webpage_url: str = ""


class DownloadTask:
    def __init__(
        self,
        url: str,
        title: str = "Media File",
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
        output_dir: str = "",
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        thumbnail: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        self.id = task_id or str(uuid.uuid4())[:8]
        self.url = url
        self.title = title
        self.format_type = format_type
        self.quality = quality
        self.audio_codec = audio_codec
        self.audio_quality = audio_quality
        self.embed_thumbnail = embed_thumbnail
        self.add_metadata = add_metadata
        self.download_subtitles = download_subtitles
        self.subtitles_lang = subtitles_lang
        self.embed_subtitles = embed_subtitles
        self.start_time = start_time
        self.end_time = end_time
        self.rate_limit_bytes = rate_limit_bytes
        self.output_dir = output_dir
        self.browser_cookies = browser_cookies
        self.cookie_file = cookie_file
        self.thumbnail = thumbnail

        self.status = "queued"  # queued, downloading, completed, failed, canceled
        self.progress = 0.0
        self.speed = "--"
        self.eta = "--:--"
        self.size_info = "0 MB / 0 MB"
        self.error_msg: Optional[str] = None
        self.saved_path: Optional[str] = None
        self.created_at = time.time()
        self.abort_event = threading.Event()

    def reset_for_retry(self):
        """Reset task state to re-queue after a failure or cancellation."""
        self.status = "queued"
        self.progress = 0.0
        self.speed = "--"
        self.eta = "--:--"
        self.size_info = "0 MB / 0 MB"
        self.error_msg = None
        self.saved_path = None
        self.abort_event.clear()

    def get_badge_text(self) -> str:
        if self.format_type == "audio":
            return f"[{self.audio_codec.upper()} {self.audio_quality}k]"
        clip = " [Clip]" if (self.start_time or self.end_time) else ""
        return f"[MP4 {self.quality}{clip}]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "format_type": self.format_type,
            "quality": self.quality,
            "badge": self.get_badge_text(),
            "status": self.status,
            "progress": round(self.progress, 4),
            "speed": self.speed,
            "eta": self.eta,
            "size_info": self.size_info,
            "error_msg": self.error_msg,
            "saved_path": self.saved_path,
            "thumbnail": self.thumbnail,
            "created_at": self.created_at,
        }
