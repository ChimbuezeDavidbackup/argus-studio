"""
Cross-platform configuration and library storage.
"""

import json
import os
import platform
import shutil
import sys
from typing import Any, Dict, List


def get_data_dir() -> str:
    """Get platform-appropriate application data directory."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

    data_dir = os.path.join(base, "ArgusStudio")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_bin_dir() -> str:
    """Directory for portable binaries (ffmpeg, etc.)"""
    bin_dir = os.path.join(get_data_dir(), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


DATA_DIR = get_data_dir()
BIN_DIR = get_bin_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")
LOG_FILE = os.path.join(DATA_DIR, "argus_runtime.log")

# Legacy migration
_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.exists(os.path.join(_repo_dir, "library.json")) and not os.path.exists(LIBRARY_FILE):
    try:
        shutil.copy(os.path.join(_repo_dir, "library.json"), LIBRARY_FILE)
    except Exception:
        pass


def get_default_download_dir() -> str:
    """Resolve user Downloads folder across platforms."""
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.exists(downloads):
        try:
            os.makedirs(downloads, exist_ok=True)
        except Exception:
            pass
    return downloads


def load_config() -> Dict[str, Any]:
    default_cfg = {
        "download_dir": get_default_download_dir(),
        "default_format": "Video (MP4)",
        "default_quality": "best",
        "auth_mode": "None (Public Videos)",
        "max_concurrent": 2,
        "speed_limit": "Unlimited",
        "clipboard_monitor": True,
        "audio_codec": "mp3",
        "audio_quality": "320",
        "embed_thumbnail": True,
        "embed_metadata": True,
        "download_subtitles": False,
        "subtitle_lang": "en",
        "embed_subtitles": True,
        "web_port": 8000,
        "web_host": "0.0.0.0",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_cfg.update(cfg)
        except Exception:
            pass
    return default_cfg


def save_config(cfg: Dict[str, Any]):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def load_library() -> List[Dict[str, Any]]:
    if os.path.exists(LIBRARY_FILE):
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_library(items: List[Dict[str, Any]]):
    try:
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
