"""
Root wrapper for backward compatibility. Delegates to core.queue.
"""

from core.queue import QueueManager
from core.models import DownloadTask

__all__ = ["QueueManager", "DownloadTask"]
