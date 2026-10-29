"""
FastAPI REST & WebSocket Server for Argus Studio.
Enables cross-platform mobilization across Web, Mobile (PWA / Hybrid), and Desktop.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import (
    load_config,
    save_config,
    load_library,
    save_library,
    get_data_dir,
)
from core.engine import (
    DownloaderEngine,
    is_ffmpeg_available,
    get_ffmpeg_location,
    download_portable_ffmpeg,
)
from core.models import DownloadTask
from core.queue import QueueManager

app = FastAPI(
    title="Argus Studio API",
    version="2.2.0",
    description="Cross-platform media ingestion backend for Web, Mobile, and Desktop",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_config()
queue_mgr = QueueManager(max_concurrent=int(config.get("max_concurrent", 2)))
engine = DownloaderEngine()

# Active WebSocket connections
active_connections: List[WebSocket] = []


async def broadcast_ws(message: Dict[str, Any]):
    for ws in list(active_connections):
        try:
            await ws.send_json(message)
        except Exception:
            if ws in active_connections:
                active_connections.remove(ws)


def sync_on_task_updated(task: DownloadTask):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_ws({"type": "task_updated", "task": task.to_dict()}),
                loop,
            )
    except Exception:
        pass


def sync_on_task_completed(task: DownloadTask):
    try:
        lib = load_library()
        size_str = "Completed"
        if task.saved_path and os.path.exists(task.saved_path):
            sz = os.path.getsize(task.saved_path) / (1024 * 1024)
            size_str = f"{sz:.1f} MB"

        lib.insert(0, {
            "title": task.title,
            "format": task.format_type.upper(),
            "quality": task.quality,
            "size": size_str,
            "path": task.saved_path or "",
            "timestamp": task.created_at,
        })
        save_library(lib)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_ws({"type": "task_completed", "task": task.to_dict()}),
                loop,
            )
    except Exception:
        pass


queue_mgr.add_listener(sync_on_task_updated)
queue_mgr.add_completion_listener(sync_on_task_completed)


# Request schemas
class ExtractRequest(BaseModel):
    url: str
    browser_cookies: Optional[str] = None
    cookie_file: Optional[str] = None


class QueueRequest(BaseModel):
    url: str
    format_type: str = "video"
    quality: str = "best"
    audio_codec: str = "mp3"
    audio_quality: str = "320"
    embed_thumbnail: bool = True
    add_metadata: bool = True
    download_subtitles: bool = False
    subtitles_lang: str = "en"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    output_dir: Optional[str] = None
    browser_cookies: Optional[str] = None


class BatchQueueRequest(BaseModel):
    urls: List[str]
    format_type: str = "video"
    quality: str = "best"
    audio_codec: str = "mp3"
    audio_quality: str = "320"


# ================= REST API ROUTES ================= #

@app.get("/api/system")
def get_system_status():
    cfg = load_config()
    return {
        "status": "online",
        "ffmpeg_available": is_ffmpeg_available(),
        "ffmpeg_location": get_ffmpeg_location(),
        "max_concurrent": queue_mgr.max_concurrent,
        "download_dir": cfg.get("download_dir"),
        "data_dir": get_data_dir(),
        "version": "2.2.0",
    }


@app.post("/api/system/ffmpeg/install")
def trigger_ffmpeg_install():
    try:
        success = download_portable_ffmpeg()
        return {
            "success": success,
            "ffmpeg_location": get_ffmpeg_location()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract")
def extract_metadata(req: ExtractRequest):
    try:
        data = engine.extract_metadata(
            url=req.url,
            browser_cookies=req.browser_cookies,
            cookie_file=req.cookie_file,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/playlist")
def extract_playlist(req: ExtractRequest):
    try:
        entries = engine.extract_playlist_entries(
            url=req.url,
            browser_cookies=req.browser_cookies,
            cookie_file=req.cookie_file,
        )
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/queue")
def get_queue():
    tasks = queue_mgr.get_all_tasks()
    return {
        "tasks": [t.to_dict() for t in tasks],
        "active_count": sum(1 for t in tasks if t.status in ("queued", "downloading")),
        "completed_count": sum(1 for t in tasks if t.status == "completed"),
    }


@app.post("/api/queue")
def add_to_queue(req: QueueRequest):
    cfg = load_config()
    out_dir = req.output_dir or cfg.get("download_dir", "")
    task = DownloadTask(
        url=req.url,
        format_type=req.format_type,
        quality=req.quality,
        audio_codec=req.audio_codec,
        audio_quality=req.audio_quality,
        embed_thumbnail=req.embed_thumbnail,
        add_metadata=req.add_metadata,
        download_subtitles=req.download_subtitles,
        subtitles_lang=req.subtitles_lang,
        start_time=req.start_time,
        end_time=req.end_time,
        output_dir=out_dir,
        browser_cookies=req.browser_cookies,
    )
    queue_mgr.add_task(task)
    return {"status": "enqueued", "task": task.to_dict()}


@app.post("/api/queue/batch")
def add_batch_to_queue(req: BatchQueueRequest):
    cfg = load_config()
    tasks = queue_mgr.add_batch(
        urls=req.urls,
        format_type=req.format_type,
        quality=req.quality,
        audio_codec=req.audio_codec,
        audio_quality=req.audio_quality,
        output_dir=cfg.get("download_dir", ""),
    )
    return {"status": "enqueued", "count": len(tasks), "task_ids": [t.id for t in tasks]}


@app.post("/api/queue/{task_id}/cancel")
def cancel_task(task_id: str):
    queue_mgr.cancel_task(task_id)
    return {"status": "canceled", "task_id": task_id}


@app.post("/api/queue/clear")
def clear_completed_queue():
    queue_mgr.clear_completed()
    return {"status": "cleared"}


@app.get("/api/library")
def get_library():
    return {"items": load_library()}


@app.delete("/api/library/{idx}")
def delete_library_item(idx: int):
    lib = load_library()
    if 0 <= idx < len(lib):
        removed = lib.pop(idx)
        save_library(lib)
        return {"status": "removed", "item": removed}
    raise HTTPException(status_code=404, detail="Index out of bounds")


# ================= WEBSOCKET ROUTE ================= #

@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    try:
        tasks = [t.to_dict() for t in queue_mgr.get_all_tasks()]
        await ws.send_json({"type": "init", "tasks": tasks})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in active_connections:
            active_connections.remove(ws)
    except Exception:
        if ws in active_connections:
            active_connections.remove(ws)


# Serve Static Web & Mobile Client
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
