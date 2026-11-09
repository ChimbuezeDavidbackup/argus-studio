"""
Asynchronous multi-worker queue manager with multi-subscriber progress notifications.
"""

import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .engine import DownloaderEngine
from .models import DownloadTask


class QueueManager:
    """Manages asynchronous download jobs and dispatches progress updates to UI and Web clients."""

    def __init__(self, max_concurrent: int = 2):
        self.engine = DownloaderEngine()
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, DownloadTask] = {}
        self.task_order: List[str] = []

        self._active_workers = 0
        self._lock = threading.Lock()
        self._is_running = True

        # Multi-subscriber listeners for UI event dispatching
        self._listeners: List[Callable[[DownloadTask], None]] = []
        self._completion_listeners: List[Callable[[DownloadTask], None]] = []

        self._worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._worker_thread.start()

    def add_listener(self, callback: Callable[[DownloadTask], None]):
        """Subscribe a listener to task state changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[DownloadTask], None]):
        """Unsubscribe a listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def add_completion_listener(self, callback: Callable[[DownloadTask], None]):
        """Subscribe a listener to task completion events."""
        if callback not in self._completion_listeners:
            self._completion_listeners.append(callback)

    # Legacy callback compatibility
    @property
    def on_task_updated(self) -> Optional[Callable[[DownloadTask], None]]:
        return self._listeners[0] if self._listeners else None

    @on_task_updated.setter
    def on_task_updated(self, cb: Optional[Callable[[DownloadTask], None]]):
        if cb and cb not in self._listeners:
            self._listeners.append(cb)

    @property
    def on_task_completed(self) -> Optional[Callable[[DownloadTask], None]]:
        return self._completion_listeners[0] if self._completion_listeners else None

    @on_task_completed.setter
    def on_task_completed(self, cb: Optional[Callable[[DownloadTask], None]]):
        if cb and cb not in self._completion_listeners:
            self._completion_listeners.append(cb)

    def _notify_updated(self, task: DownloadTask):
        for listener in list(self._listeners):
            try:
                listener(task)
            except Exception:
                pass

    def _notify_completed(self, task: DownloadTask):
        for listener in list(self._completion_listeners):
            try:
                listener(task)
            except Exception:
                pass

    def add_task(self, task: DownloadTask) -> DownloadTask:
        with self._lock:
            self.tasks[task.id] = task
            self.task_order.append(task.id)

        self._notify_updated(task)
        return task

    def add_batch(
        self,
        urls: List[str],
        format_type: str = "video",
        quality: str = "best",
        audio_codec: str = "mp3",
        audio_quality: str = "320",
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        download_subtitles: bool = False,
        subtitles_lang: str = "en",
        output_dir: str = "",
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
    ) -> List[DownloadTask]:
        added = []
        for url in urls:
            u = url.strip()
            if u:
                task = DownloadTask(
                    url=u,
                    title="Analyzing URL...",
                    format_type=format_type,
                    quality=quality,
                    audio_codec=audio_codec,
                    audio_quality=audio_quality,
                    embed_thumbnail=embed_thumbnail,
                    add_metadata=add_metadata,
                    download_subtitles=download_subtitles,
                    subtitles_lang=subtitles_lang,
                    output_dir=output_dir,
                    browser_cookies=browser_cookies,
                    cookie_file=cookie_file,
                )
                self.add_task(task)
                added.append(task)
        return added

    def cancel_task(self, task_id: str):
        """Immediately abort active download or cancel pending queued task."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status in ("queued", "downloading"):
                task.status = "canceled"
                task.error_msg = "Download canceled by user."
                task.abort_event.set()
                task.speed = "--"
                task.eta = "--"
                self._notify_updated(task)

    def retry_task(self, task_id: str) -> Optional[DownloadTask]:
        """Reset failed or canceled task and re-insert into active queue rotation."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status in ("failed", "canceled"):
                task.reset_for_retry()
                # Bring to end of queue order or maintain position
                if task_id in self.task_order:
                    self.task_order.remove(task_id)
                self.task_order.append(task_id)
                self._notify_updated(task)
                return task
        return None

    def clear_completed(self):
        with self._lock:
            to_remove = [tid for tid, t in self.tasks.items() if t.status in ("completed", "failed", "canceled")]
            for tid in to_remove:
                del self.tasks[tid]
                if tid in self.task_order:
                    self.task_order.remove(tid)

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return [self.tasks[tid] for tid in self.task_order if tid in self.tasks]

    def _scheduler_loop(self):
        while self._is_running:
            task_to_run = None
            with self._lock:
                if self._active_workers < self.max_concurrent:
                    for tid in self.task_order:
                        t = self.tasks.get(tid)
                        if t and t.status == "queued":
                            t.status = "downloading"
                            task_to_run = t
                            self._active_workers += 1
                            break

            if task_to_run:
                threading.Thread(
                    target=self._execute_download,
                    args=(task_to_run,),
                    daemon=True
                ).start()
            else:
                time.sleep(0.3)

    def _execute_download(self, task: DownloadTask):
        self._notify_updated(task)

        if task.title in ("Media File", "Analyzing URL..."):
            try:
                meta = self.engine.extract_metadata(
                    url=task.url,
                    browser_cookies=task.browser_cookies,
                    cookie_file=task.cookie_file,
                )
                if meta and meta.get("title"):
                    task.title = meta.get("title", task.title)
                    task.thumbnail = meta.get("thumbnail")
                    self._notify_updated(task)
            except Exception:
                pass

        if task.status == "canceled":
            with self._lock:
                self._active_workers -= 1
            return

        def task_progress_hook(d: Dict[str, Any]):
            if task.status == "canceled":
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                ratio = (downloaded / total) if total > 0 else 0.0

                raw_speed = d.get("_speed_str", "0 B/s")
                raw_eta = d.get("_eta_str", "--:--")
                task.speed = re.sub(r"\x1b\[[0-9;]*m", "", raw_speed).strip()
                task.eta = re.sub(r"\x1b\[[0-9;]*m", "", raw_eta).strip()

                tot_mb = total / (1024 * 1024) if total > 0 else 0.0
                dl_mb = downloaded / (1024 * 1024) if downloaded > 0 else 0.0
                percent_str = f"{ratio * 100:.1f}%" if total > 0 else "..."
                task.size_info = f"{dl_mb:.1f} MB / {tot_mb:.1f} MB ({percent_str})"
                task.progress = ratio

                self._notify_updated(task)

            elif status == "finished":
                task.progress = 1.0
                task.speed = "Tagging..."
                task.eta = "Finalizing"
                self._notify_updated(task)

        try:
            saved_file = self.engine.download_media(
                url=task.url,
                output_dir=task.output_dir,
                format_type=task.format_type,
                quality=task.quality,
                audio_codec=task.audio_codec,
                audio_quality=task.audio_quality,
                embed_thumbnail=task.embed_thumbnail,
                add_metadata=task.add_metadata,
                download_subtitles=task.download_subtitles,
                subtitles_lang=task.subtitles_lang,
                embed_subtitles=task.embed_subtitles,
                start_time=task.start_time,
                end_time=task.end_time,
                rate_limit_bytes=task.rate_limit_bytes,
                browser_cookies=task.browser_cookies,
                cookie_file=task.cookie_file,
                abort_event=task.abort_event,
                progress_callback=task_progress_hook,
            )
            # Accurate completion verification (no false positives)
            if not saved_file or not os.path.exists(saved_file) or os.path.getsize(saved_file) == 0:
                raise RuntimeError("File muxing failed or output was empty.")

            task.saved_path = saved_file
            task.status = "completed"
            task.progress = 1.0
            task.eta = "Done"
            task.speed = "Complete"

            self._notify_updated(task)
            self._notify_completed(task)

        except Exception as e:
            if task.status != "canceled" and not task.abort_event.is_set():
                task.status = "failed"
                task.error_msg = str(e)
                self._notify_updated(task)
            elif task.abort_event.is_set() or task.status == "canceled":
                task.status = "canceled"
                task.error_msg = "Download canceled by user."
                self._notify_updated(task)
        finally:
            with self._lock:
                self._active_workers -= 1
