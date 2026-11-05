"""
Argus Studio - Native Windows Desktop Application (CustomTkinter).
Modern, clean, balanced interface inspired by the Argus Studio web application.
Supports Dark, Light, and System themes, dynamic stream merging, and collapsible power tools.
"""

import io
import logging
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from PIL import Image
import requests

from core.config import (
    load_config,
    save_config,
    load_library,
    save_library,
    get_data_dir,
    LOG_FILE,
    APP_VERSION,
)
from core.engine import (
    DownloaderEngine,
    parse_time_to_seconds,
    is_ffmpeg_available,
    get_ffmpeg_location,
    download_portable_ffmpeg,
)
from core.models import DownloadTask
from core.queue import QueueManager
from core.updater import UpdateManager

# ================= PERSISTENCE & CRASH LOGGING ================= #

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

class _SafeStreamWriter:
    def write(self, s):
        if s and s.strip():
            logging.info(s.strip())
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = _SafeStreamWriter()
if sys.stderr is None:
    sys.stderr = _SafeStreamWriter()

def _global_exception_handler(exc_type, exc_value, exc_tb):
    err_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("Fatal Unhandled Exception:\n%s", err_text)
    try:
        messagebox.showerror(
            "Argus Studio - Runtime Error",
            f"An unexpected error occurred:\n\n{exc_value}\n\nDiagnostics have been logged to:\n{LOG_FILE}"
        )
    except Exception:
        pass

sys.excepthook = _global_exception_handler


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# ================= THEME PALETTE SYSTEM (Light, Dark) ================= #

PALETTE = {
    # Backgrounds
    "bg_main": ("#f8fafc", "#090a0f"),
    "bg_sidebar": ("#f1f5f9", "#12151d"),
    "bg_sidebar_footer": ("#e2e8f0", "#0c0e14"),
    "bg_header": ("#ffffff", "#0f1118"),
    "bg_card": ("#ffffff", "#131722"),
    "bg_card_subtle": ("#f1f5f9", "#0c0e14"),
    "bg_hover": ("#e2e8f0", "#1e2433"),
    "border": ("#cbd5e1", "#1e293b"),
    
    # Text
    "text_primary": ("#0f172a", "#f8fafc"),
    "text_secondary": ("#475569", "#94a3b8"),
    "text_muted": ("#94a3b8", "#64748b"),
    
    # Buttons
    "btn_primary": ("#2563eb", "#2563eb"),
    "btn_primary_hover": ("#1d4ed8", "#1d4ed8"),
    "btn_secondary": ("#e2e8f0", "#1f2937"),
    "btn_secondary_hover": ("#cbd5e1", "#374151"),
    "btn_secondary_text": ("#1e293b", "#e2e8f0"),
    "btn_success": ("#10b981", "#10b981"),
    "btn_success_hover": ("#059669", "#059669"),
    "btn_accent": ("#4f46e5", "#4f46e5"),
    "btn_accent_hover": ("#4338ca", "#4338ca"),
    "btn_danger": ("#ef4444", "#dc2626"),
    "btn_danger_hover": ("#dc2626", "#b91c1c"),
    
    # Inputs
    "entry_bg": ("#ffffff", "#0c0e14"),
    "entry_border": ("#cbd5e1", "#1e293b"),
    "entry_text": ("#0f172a", "#f8fafc"),
    
    # Pills
    "pill_inactive": ("#e2e8f0", "#1f2937"),
    "pill_inactive_hover": ("#cbd5e1", "#374151"),
    "pill_text_inactive": ("#334155", "#94a3b8"),
    "pill_active": ("#2563eb", "#2563eb"),
    "pill_text_active": ("#ffffff", "#ffffff"),
}


class ArgusStudioApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Config & Engine
        self.config_data = load_config()
        self.library_items = load_library()
        self.engine = DownloaderEngine()

        # Apply saved theme mode
        theme_setting = self.config_data.get("theme", "System")
        ctk.set_appearance_mode(theme_setting)
        ctk.set_default_color_theme("blue")

        # Window Config
        self.title("Argus Studio")
        self.geometry("1140x840")
        self.minsize(1020, 720)
        self.configure(fg_color=PALETTE["bg_main"])

        # App Icon
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        max_workers = int(self.config_data.get("max_concurrent", 2))
        self.queue_mgr = QueueManager(max_concurrent=max_workers)
        self.queue_mgr.add_listener(self._on_queue_task_updated)
        self.queue_mgr.add_completion_listener(self._on_queue_task_completed)

        # Downloader State
        self.current_metadata: Optional[Dict[str, Any]] = None
        self.selected_quality = "best"
        self.selected_format_type = "video"
        self.custom_cookie_path: Optional[str] = None
        self.last_clipboard_text = ""
        self.adv_expanded = False

        # UI Maps
        self.queue_widgets: Dict[str, Dict[str, Any]] = {}

        self._build_layout()
        self._show_tab("downloader")

        # Thread-safe Mainloop Clipboard Polling
        if self.config_data.get("clipboard_monitor", True):
            self.after(1500, self._check_clipboard_poll)

        # Silent background update check
        if self.config_data.get("auto_check_updates", True):
            self.after(3500, lambda: self._check_updates_async(show_popup_if_none=False))

    # ================= LAYOUT BUILDER ================= #

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Left Sidebar (Web-inspired modern navigation)
        self.sidebar = ctk.CTkFrame(
            self,
            width=230,
            corner_radius=0,
            fg_color=PALETTE["bg_sidebar"]
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Brand Header
        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.pack(fill="x", padx=18, pady=(22, 20))

        self.brand_icon = ctk.CTkLabel(
            self.brand_frame,
            text="▶",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#2563eb"
        )
        self.brand_icon.pack(side="left", padx=(0, 10))

        self.brand_title = ctk.CTkLabel(
            self.brand_frame,
            text="Argus Studio",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.brand_title.pack(side="left")

        # Nav Buttons
        self.nav_btns = {}
        nav_items = [
            ("downloader", "Downloader"),
            ("queue", "Queue (0)"),
            ("library", "Library"),
            ("settings", "Settings")
        ]

        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=42,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="transparent",
                text_color=PALETTE["text_secondary"],
                hover_color=PALETTE["bg_hover"],
                command=lambda k=key: self._show_tab(k)
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_btns[key] = btn

        # Sidebar Footer: Engine status & Quick Theme Switcher
        self.sidebar_footer = ctk.CTkFrame(
            self.sidebar,
            fg_color=PALETTE["bg_sidebar_footer"],
            corner_radius=10
        )
        self.sidebar_footer.pack(side="bottom", fill="x", padx=12, pady=16)

        self.engine_dot = ctk.CTkLabel(
            self.sidebar_footer,
            text=f"● Engine Active ({self.config_data.get('max_concurrent', 2)} slots)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981"
        )
        self.engine_dot.pack(padx=10, pady=(10, 6))

        # Sidebar Theme Switcher
        theme_lbl = ctk.CTkLabel(
            self.sidebar_footer,
            text="Appearance Mode:",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"]
        )
        theme_lbl.pack(anchor="w", padx=12, pady=(2, 2))

        self.sidebar_theme_seg = ctk.CTkSegmentedButton(
            self.sidebar_footer,
            values=["System", "Dark", "Light"],
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._set_theme
        )
        cur_theme = self.config_data.get("theme", "System")
        self.sidebar_theme_seg.set(cur_theme.capitalize())
        self.sidebar_theme_seg.pack(fill="x", padx=10, pady=(0, 10))

        # 2. Main Workspace
        self.main_container = ctk.CTkFrame(
            self,
            fg_color=PALETTE["bg_main"],
            corner_radius=0
        )
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(3, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Top Header Bar
        self.header_frame = ctk.CTkFrame(
            self.main_container,
            height=54,
            fg_color=PALETTE["bg_header"],
            corner_radius=0
        )
        self.header_frame.grid(row=0, column=0, sticky="ew")

        self.header_title = ctk.CTkLabel(
            self.header_frame,
            text="Media Downloader",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.header_title.pack(side="left", padx=24, pady=14)

        self.header_subtitle = ctk.CTkLabel(
            self.header_frame,
            text="Universal Media Suite",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        )
        self.header_subtitle.pack(side="right", padx=24, pady=14)

        # FFmpeg Alert Banner
        self.ffmpeg_banner = ctk.CTkFrame(self.main_container, fg_color="#7c2d12", corner_radius=8)
        self.ffmpeg_banner_lbl = ctk.CTkLabel(
            self.ffmpeg_banner,
            text="Notice: FFmpeg not detected. Required for 1080p+ merging and MP3 conversion.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fdba74"
        )
        self.ffmpeg_banner_lbl.pack(side="left", padx=14, pady=6)

        self.ffmpeg_banner_btn = ctk.CTkButton(
            self.ffmpeg_banner,
            text="Install Portable FFmpeg",
            width=150,
            height=26,
            corner_radius=6,
            fg_color="#ea580c",
            hover_color="#c2410c",
            command=self._start_ffmpeg_install
        )
        self.ffmpeg_banner_btn.pack(side="right", padx=10, pady=6)

        if not self.engine.is_ffmpeg_available():
            self.ffmpeg_banner.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 0))

        # In-App Update Alert Banner
        self.update_banner = ctk.CTkFrame(self.main_container, fg_color="#14532d", corner_radius=8)
        self.update_banner_lbl = ctk.CTkLabel(
            self.update_banner,
            text="Update Available: Argus Studio update is ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#86efac"
        )
        self.update_banner_lbl.pack(side="left", padx=14, pady=6)

        self.update_banner_btn = ctk.CTkButton(
            self.update_banner,
            text="Update Now",
            width=110,
            height=26,
            corner_radius=6,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._start_inapp_update
        )
        self.update_banner_btn.pack(side="right", padx=10, pady=6)
        self.cached_update_info: Optional[Dict[str, Any]] = None

        # Clipboard Auto-Detect Toast Banner
        self.clip_banner = ctk.CTkFrame(self.main_container, fg_color="#1e3a8a", corner_radius=8)
        self.clip_banner_label = ctk.CTkLabel(
            self.clip_banner,
            text="Media link detected in clipboard. Click to load",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#93c5fd"
        )
        self.clip_banner_label.pack(side="left", padx=14, pady=6)

        self.clip_load_btn = ctk.CTkButton(
            self.clip_banner,
            text="Load Link",
            width=80,
            height=26,
            corner_radius=6,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._load_detected_clipboard
        )
        self.clip_load_btn.pack(side="right", padx=10, pady=6)

        # View Panels
        self.view_downloader = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.view_queue = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.view_library = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.view_settings = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")

        self._build_downloader_view()
        self._build_queue_view()
        self._build_library_view()
        self._build_settings_view()

    def _show_tab(self, tab_key: str):
        self.view_downloader.grid_forget()
        self.view_queue.grid_forget()
        self.view_library.grid_forget()
        self.view_settings.grid_forget()

        for k, btn in self.nav_btns.items():
            if k == tab_key:
                btn.configure(
                    fg_color=PALETTE["btn_primary"],
                    text_color="#ffffff",
                    hover_color=PALETTE["btn_primary_hover"]
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=PALETTE["text_secondary"],
                    hover_color=PALETTE["bg_hover"]
                )

        if tab_key == "downloader":
            self.header_title.configure(text="Media Downloader")
            self.header_subtitle.configure(text="Universal Media Suite")
            self.view_downloader.grid(row=3, column=0, sticky="nsew", padx=20, pady=12)
        elif tab_key == "queue":
            self.header_title.configure(text="Download Queue")
            self.header_subtitle.configure(text="Active & Completed Ingestion")
            self.view_queue.grid(row=3, column=0, sticky="nsew", padx=20, pady=12)
            self._render_queue_list()
        elif tab_key == "library":
            self.header_title.configure(text="Media Library")
            self.header_subtitle.configure(text="Local Download History")
            self.view_library.grid(row=3, column=0, sticky="nsew", padx=20, pady=12)
            self._refresh_library_ui()
        elif tab_key == "settings":
            self.header_title.configure(text="Settings")
            self.header_subtitle.configure(text="Preferences & Performance")
            self.view_settings.grid(row=3, column=0, sticky="nsew", padx=20, pady=12)
            self._refresh_ffmpeg_status_ui()

    def _set_theme(self, mode: str):
        mode_capitalized = mode.capitalize()
        ctk.set_appearance_mode(mode_capitalized)
        self.config_data["theme"] = mode_capitalized
        save_config(self.config_data)

        if hasattr(self, "sidebar_theme_seg"):
            self.sidebar_theme_seg.set(mode_capitalized)
        if hasattr(self, "setting_theme_seg"):
            self.setting_theme_seg.set(mode_capitalized)

    # ================= 1. DOWNLOADER VIEW (CLEAN & BALANCED) ================= #

    def _build_downloader_view(self):
        # 1. Primary Ingestion Input Card (Clean, web-aligned)
        input_card = ctk.CTkFrame(
            self.view_downloader,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        input_card.pack(fill="x", pady=(0, 12))

        url_row = ctk.CTkFrame(input_card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=16)

        self.url_entry = ctk.CTkEntry(
            url_row,
            placeholder_text="Enter YouTube, Vimeo, Playlist, or media URL...",
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=PALETTE["entry_bg"],
            border_color=PALETTE["entry_border"],
            text_color=PALETTE["entry_text"]
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            url_row,
            text="Paste",
            width=65,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._paste_url
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            url_row,
            text="Batch URLs",
            width=95,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._open_batch_modal
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            url_row,
            text="Playlist",
            width=85,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["btn_accent"],
            hover_color=PALETTE["btn_accent_hover"],
            command=self._open_playlist_inspector
        ).pack(side="left", padx=(0, 8))

        self.fetch_btn = ctk.CTkButton(
            url_row,
            text="Fetch Media",
            width=115,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["btn_primary"],
            hover_color=PALETTE["btn_primary_hover"],
            command=self._start_fetch_metadata
        )
        self.fetch_btn.pack(side="right")

        # 2. Media Preview Card (Clean, centered, web-app layout)
        self.preview_card = ctk.CTkFrame(
            self.view_downloader,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        self.preview_card.pack(fill="x", pady=6)

        preview_grid = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        preview_grid.pack(fill="x", padx=18, pady=18)
        preview_grid.grid_columnconfigure(1, weight=1)

        # 16:9 Thumbnail Frame
        self.thumb_container = ctk.CTkFrame(
            preview_grid,
            width=220,
            height=124,
            fg_color=PALETTE["bg_card_subtle"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=8
        )
        self.thumb_container.grid(row=0, column=0, rowspan=4, padx=(0, 18), sticky="nw")
        self.thumb_container.pack_propagate(False)

        self.thumb_label = ctk.CTkLabel(
            self.thumb_container,
            text="[ Media Preview ]",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        )
        self.thumb_label.pack(expand=True)

        # Meta Details
        self.meta_title = ctk.CTkLabel(
            preview_grid,
            text="Paste a media URL above and click 'Fetch Media'",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"],
            wraplength=540,
            justify="left",
            anchor="w"
        )
        self.meta_title.grid(row=0, column=1, sticky="w", pady=(0, 4))

        self.meta_channel = ctk.CTkLabel(
            preview_grid,
            text="Author / Channel: -",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_secondary"],
            anchor="w"
        )
        self.meta_channel.grid(row=1, column=1, sticky="w", pady=2)

        self.meta_stats = ctk.CTkLabel(
            preview_grid,
            text="Duration: -  •  Views: -",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"],
            anchor="w"
        )
        self.meta_stats.grid(row=2, column=1, sticky="w", pady=2)

        # Format / Quality Selector Pills
        self.pills_container = ctk.CTkFrame(preview_grid, fg_color="transparent")
        self.pills_container.grid(row=3, column=1, sticky="w", pady=(10, 0))

        ctk.CTkLabel(
            self.pills_container,
            text="Select Format & Quality:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_secondary"]
        ).pack(side="left", padx=(0, 10))

        self.pill_buttons: List[ctk.CTkButton] = []
        self._populate_default_pills()

        # 3. Collapsible Advanced Options Accordion (Clean, zero cognitive overload)
        self.adv_card = ctk.CTkFrame(
            self.view_downloader,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        self.adv_card.pack(fill="x", pady=6)

        # Accordion Header Button
        self.adv_toggle_btn = ctk.CTkButton(
            self.adv_card,
            text="▼ Advanced Options (Audio, Subtitles, Clipper, Auth)",
            anchor="w",
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            text_color=PALETTE["text_secondary"],
            hover_color=PALETTE["bg_hover"],
            command=self._toggle_advanced_options
        )
        self.adv_toggle_btn.pack(fill="x", padx=12, pady=6)

        # Hidden-by-default expandable inner container
        self.adv_inner = ctk.CTkFrame(self.adv_card, fg_color="transparent")

        # Row A: Audio Format & ID3 Metadata
        row_a = ctk.CTkFrame(self.adv_inner, fg_color="transparent")
        row_a.pack(fill="x", pady=4)

        ctk.CTkLabel(
            row_a,
            text="Audio Options:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left", padx=(0, 10))

        self.audio_codec_combo = ctk.CTkComboBox(
            row_a,
            values=["MP3 (320 kbps)", "MP3 (192 kbps)", "M4A (AAC)", "FLAC (Lossless)", "WAV"],
            width=150,
            height=28
        )
        self.audio_codec_combo.set("MP3 (320 kbps)")
        self.audio_codec_combo.pack(side="left", padx=(0, 16))

        self.tag_id3_switch = ctk.CTkCheckBox(
            row_a,
            text="Embed Album Art & ID3 Metadata",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_primary"]
        )
        self.tag_id3_switch.select()
        self.tag_id3_switch.pack(side="left")

        # Row B: Subtitles (CC)
        row_b = ctk.CTkFrame(self.adv_inner, fg_color="transparent")
        row_b.pack(fill="x", pady=6)

        ctk.CTkLabel(
            row_b,
            text="Subtitles (CC):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left", padx=(0, 10))

        self.sub_switch = ctk.CTkCheckBox(
            row_b,
            text="Download Subtitles",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_primary"]
        )
        self.sub_switch.pack(side="left", padx=(0, 12))

        self.sub_lang_combo = ctk.CTkComboBox(
            row_b,
            values=["en (English)", "es (Spanish)", "fr (French)", "de (German)", "all (All Available)"],
            width=140,
            height=28
        )
        self.sub_lang_combo.set("en (English)")
        self.sub_lang_combo.pack(side="left", padx=(0, 12))

        self.sub_embed_switch = ctk.CTkCheckBox(
            row_b,
            text="Embed into MP4",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_primary"]
        )
        self.sub_embed_switch.select()
        self.sub_embed_switch.pack(side="left")

        # Row C: Section Clipper (Timestamps)
        row_c = ctk.CTkFrame(self.adv_inner, fg_color="transparent")
        row_c.pack(fill="x", pady=6)

        self.clip_switch = ctk.CTkCheckBox(
            row_c,
            text="Clip Section (Timestamps)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.clip_switch.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row_c, text="Start:", font=ctk.CTkFont(size=11), text_color=PALETTE["text_muted"]).pack(side="left", padx=(4, 4))
        self.clip_start_entry = ctk.CTkEntry(row_c, width=70, height=26, placeholder_text="00:01:30")
        self.clip_start_entry.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row_c, text="End:", font=ctk.CTkFont(size=11), text_color=PALETTE["text_muted"]).pack(side="left", padx=(4, 4))
        self.clip_end_entry = ctk.CTkEntry(row_c, width=70, height=26, placeholder_text="00:03:45")
        self.clip_end_entry.pack(side="left")

        # Row D: Session Auth & Speed Limit (Advanced access)
        row_d = ctk.CTkFrame(self.adv_inner, fg_color="transparent")
        row_d.pack(fill="x", pady=6)

        ctk.CTkLabel(
            row_d,
            text="Session Auth:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left", padx=(0, 8))

        self.cookie_selector = ctk.CTkComboBox(
            row_d,
            values=["None (Public Videos)", "Browser: Chrome", "Browser: Edge", "Browser: Brave", "Browser: Firefox", "Custom cookies.txt File"],
            height=28,
            width=180,
            command=self._on_auth_selection_changed
        )
        self.cookie_selector.set(self.config_data.get("auth_mode", "None (Public Videos)"))
        self.cookie_selector.pack(side="left")

        self.cookie_file_frame = ctk.CTkFrame(row_d, fg_color="transparent")
        self.cookie_file_entry = ctk.CTkEntry(self.cookie_file_frame, height=28, width=160)
        self.cookie_file_entry.pack(side="left", padx=(6, 4))
        ctk.CTkButton(self.cookie_file_frame, text="Browse", width=60, height=28, command=self._browse_cookie_file).pack(side="left")

        ctk.CTkLabel(row_d, text="Speed Limit:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_primary"]).pack(side="left", padx=(18, 8))
        self.speed_combo = ctk.CTkComboBox(
            row_d,
            values=["Unlimited", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s"],
            height=28,
            width=110
        )
        self.speed_combo.set(self.config_data.get("speed_limit", "Unlimited"))
        self.speed_combo.pack(side="left")

        # 4. Action Bar (Matches web application: Add to Queue & Download Now)
        action_card = ctk.CTkFrame(
            self.view_downloader,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        action_card.pack(fill="x", pady=10)

        action_box = ctk.CTkFrame(action_card, fg_color="transparent")
        action_box.pack(fill="x", padx=18, pady=16)

        self.status_line = ctk.CTkLabel(
            action_box,
            text="Ready. Paste a media link above or manage active downloads.",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        )
        self.status_line.pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(action_box, fg_color="transparent")
        btn_row.pack(fill="x")

        self.add_queue_btn = ctk.CTkButton(
            btn_row,
            text="+ Add to Queue",
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._queue_current_media
        )
        self.add_queue_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.quick_download_btn = ctk.CTkButton(
            btn_row,
            text="▶ Download Now & Open Queue",
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["btn_success"],
            hover_color=PALETTE["btn_success_hover"],
            command=lambda: self._queue_current_media(jump_to_queue=True)
        )
        self.quick_download_btn.pack(side="left", fill="x", expand=True)

    def _toggle_advanced_options(self):
        self.adv_expanded = not self.adv_expanded
        if self.adv_expanded:
            self.adv_toggle_btn.configure(text="▲ Hide Advanced Options")
            self.adv_inner.pack(fill="x", padx=18, pady=(0, 14))
        else:
            self.adv_toggle_btn.configure(text="▼ Advanced Options (Audio, Subtitles, Clipper, Auth)")
            self.adv_inner.pack_forget()

    # Resolution Pills
    def _populate_default_pills(self):
        for btn in self.pill_buttons:
            btn.destroy()
        self.pill_buttons.clear()

        defaults = [
            ("Best (Video)", "best", "video"),
            ("1080p", "1080", "video"),
            ("720p", "720", "video"),
            ("Audio MP3", "best", "audio")
        ]
        for label, q_val, f_type in defaults:
            is_active = (q_val == self.selected_quality and f_type == self.selected_format_type)
            btn = ctk.CTkButton(
                self.pills_container,
                text=label,
                width=80,
                height=30,
                corner_radius=15,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=PALETTE["pill_active"] if is_active else PALETTE["pill_inactive"],
                text_color=PALETTE["pill_text_active"] if is_active else PALETTE["pill_text_inactive"],
                hover_color=PALETTE["pill_active"] if is_active else PALETTE["pill_inactive_hover"],
                command=lambda q=q_val, f=f_type, l=label: self._select_pill(q, f, l)
            )
            btn.pack(side="left", padx=4)
            self.pill_buttons.append(btn)

    def _populate_dynamic_pills(self, formats: List[Dict[str, Any]]):
        for btn in self.pill_buttons:
            btn.destroy()
        self.pill_buttons.clear()

        heights = sorted(list({f.get("height") for f in formats if f.get("height")}), reverse=True)
        pill_items = [("Auto (Best)", "best", "video")]

        for h in heights[:4]:
            label = f"{h}p"
            if h == 2160:
                label = "4K (2160p)"
            elif h == 1440:
                label = "2K (1440p)"
            pill_items.append((label, str(h), "video"))

        pill_items.append(("Audio MP3", "best", "audio"))

        for label, q_val, f_type in pill_items:
            is_active = (q_val == self.selected_quality and f_type == self.selected_format_type)
            btn = ctk.CTkButton(
                self.pills_container,
                text=label,
                height=30,
                corner_radius=15,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=PALETTE["pill_active"] if is_active else PALETTE["pill_inactive"],
                text_color=PALETTE["pill_text_active"] if is_active else PALETTE["pill_text_inactive"],
                hover_color=PALETTE["pill_active"] if is_active else PALETTE["pill_inactive_hover"],
                command=lambda q=q_val, f=f_type, l=label: self._select_pill(q, f, l)
            )
            btn.pack(side="left", padx=4)
            self.pill_buttons.append(btn)

    def _select_pill(self, quality: str, format_type: str, label: str):
        self.selected_quality = quality
        self.selected_format_type = format_type
        for btn in self.pill_buttons:
            if btn.cget("text") == label:
                btn.configure(
                    fg_color=PALETTE["pill_active"],
                    text_color=PALETTE["pill_text_active"]
                )
            else:
                btn.configure(
                    fg_color=PALETTE["pill_inactive"],
                    text_color=PALETTE["pill_text_inactive"]
                )
        self.status_line.configure(text=f"Selected format: {label}")

    def _paste_url(self):
        try:
            val = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, val.strip())
        except Exception:
            pass

    def _on_auth_selection_changed(self, choice: str):
        if "cookies.txt" in choice:
            self.cookie_file_frame.pack(side="left", padx=(8, 0))
        else:
            self.cookie_file_frame.pack_forget()

    def _browse_cookie_file(self):
        fp = filedialog.askopenfilename(title="Select Netscape cookies.txt file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if fp:
            self.custom_cookie_path = fp
            self.cookie_file_entry.delete(0, "end")
            self.cookie_file_entry.insert(0, fp)

    def _get_auth_params(self):
        choice = self.cookie_selector.get()
        browser_val = None
        cookie_file = None
        if "None" in choice:
            pass
        elif "cookies.txt" in choice:
            cookie_file = self.cookie_file_entry.get().strip() or self.custom_cookie_path
        elif "Chrome" in choice:
            browser_val = "chrome"
        elif "Edge" in choice:
            browser_val = "edge"
        elif "Brave" in choice:
            browser_val = "brave"
        elif "Firefox" in choice:
            browser_val = "firefox"
        return browser_val, cookie_file

    def _get_rate_limit(self) -> Optional[int]:
        val = self.speed_combo.get()
        if "1 MB" in val:
            return 1 * 1024 * 1024
        elif "2 MB" in val:
            return 2 * 1024 * 1024
        elif "5 MB" in val:
            return 5 * 1024 * 1024
        elif "10 MB" in val:
            return 10 * 1024 * 1024
        return None

    def _get_audio_settings(self):
        raw = self.audio_codec_combo.get().lower()
        if "320" in raw:
            return "mp3", "320"
        elif "192" in raw:
            return "mp3", "192"
        elif "m4a" in raw:
            return "m4a", "192"
        elif "flac" in raw:
            return "flac", "0"
        elif "wav" in raw:
            return "wav", "0"
        return "mp3", "320"

    def _start_fetch_metadata(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please paste a video or media URL first.")
            return

        browser_val, cookie_file = self._get_auth_params()
        self.fetch_btn.configure(state="disabled", text="Analyzing...")
        self.status_line.configure(text="Extracting metadata & available formats...")

        threading.Thread(
            target=self._worker_fetch_metadata,
            args=(url, browser_val, cookie_file),
            daemon=True
        ).start()

    def _worker_fetch_metadata(self, url: str, browser: Optional[str], cookie_file: Optional[str]):
        try:
            metadata = self.engine.extract_metadata(url=url, browser_cookies=browser, cookie_file=cookie_file)
            self.after(0, self._on_metadata_success, metadata)
        except Exception as e:
            self.after(0, self._on_metadata_error, str(e))

    def _on_metadata_success(self, metadata: Dict[str, Any]):
        self.current_metadata = metadata
        self.fetch_btn.configure(state="normal", text="Fetch Media")

        title = metadata.get("title", "Untitled Media")
        uploader = metadata.get("uploader") or metadata.get("channel", "Unknown Creator")
        duration = metadata.get("duration")
        m, s = divmod(duration or 0, 60)
        h, m = divmod(m, 60)
        dur_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

        views = metadata.get("view_count")
        view_str = f"{views:,} views" if isinstance(views, int) else "N/A"

        self.meta_title.configure(text=title)
        self.meta_channel.configure(text=f"Author: {uploader}")
        self.meta_stats.configure(text=f"Duration: {dur_str}  •  {view_str}")

        formats = metadata.get("formats", [])
        self._populate_dynamic_pills(formats)
        self.status_line.configure(text="Metadata retrieved! Click 'Add to Queue' or 'Download Now'.")

        thumb_url = metadata.get("thumbnail")
        if thumb_url:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()

    def _load_thumbnail(self, url: str):
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code == 200:
                img_data = resp.content
                image = Image.open(io.BytesIO(img_data))
                ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(220, 124))
                self.after(0, lambda: self.thumb_label.configure(image=ctk_img, text=""))
        except Exception:
            pass

    def _on_metadata_error(self, err_msg: str):
        self.fetch_btn.configure(state="normal", text="Fetch Media")
        self.status_line.configure(text="Failed to retrieve metadata.")
        messagebox.showerror("Metadata Error", err_msg)

    def _queue_current_media(self, jump_to_queue: bool = False):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please enter a valid media URL.")
            return

        title = self.current_metadata.get("title", "Media Download") if self.current_metadata else "Media Download"
        thumb = self.current_metadata.get("thumbnail") if self.current_metadata else None
        output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        browser_val, cookie_file = self._get_auth_params()

        # Advanced options
        codec, a_qual = self._get_audio_settings()
        tag_meta = bool(self.tag_id3_switch.get())
        sub_enabled = bool(self.sub_switch.get())
        sub_lang = self.sub_lang_combo.get().split()[0]
        sub_embed = bool(self.sub_embed_switch.get())
        rate_lim = self._get_rate_limit()

        clip_start = self.clip_start_entry.get().strip() if self.clip_switch.get() else None
        clip_end = self.clip_end_entry.get().strip() if self.clip_switch.get() else None

        task = DownloadTask(
            url=url,
            title=title,
            format_type=self.selected_format_type,
            quality=self.selected_quality,
            audio_codec=codec,
            audio_quality=a_qual,
            embed_thumbnail=tag_meta,
            add_metadata=tag_meta,
            download_subtitles=sub_enabled,
            subtitles_lang=sub_lang,
            embed_subtitles=sub_embed,
            start_time=clip_start,
            end_time=clip_end,
            rate_limit_bytes=rate_lim,
            output_dir=output_dir,
            browser_cookies=browser_val,
            cookie_file=cookie_file,
            thumbnail=thumb
        )
        self.queue_mgr.add_task(task)

        self.status_line.configure(text=f"Added to queue: {title}")
        self._update_queue_badge()

        if jump_to_queue:
            self._show_tab("queue")

    # ================= 2. PLAYLIST INSPECTOR MODAL ================= #

    def _open_playlist_inspector(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please enter a playlist or channel URL first.")
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Playlist & Channel Inspector")
        modal.geometry("720x560")
        modal.transient(self)
        modal.grab_set()

        head = ctk.CTkFrame(modal, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(20, 10))

        title_lbl = ctk.CTkLabel(head, text="Fetching playlist entries...", font=ctk.CTkFont(size=14, weight="bold"))
        title_lbl.pack(side="left")

        # Scrollable checklist
        scroll = ctk.CTkScrollableFrame(
            modal,
            fg_color=PALETTE["bg_card_subtle"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=10
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=5)

        # Controls bottom
        ctrl = ctk.CTkFrame(modal, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=15)

        format_seg = ctk.CTkSegmentedButton(ctrl, values=["Video (MP4)", "Audio (MP3)"])
        format_seg.set("Video (MP4)")
        format_seg.pack(side="left", padx=(0, 10))

        num_switch = ctk.CTkCheckBox(ctrl, text="Prefix Track # (01, 02...)", font=ctk.CTkFont(size=12))
        num_switch.select()
        num_switch.pack(side="left", padx=10)

        queue_btn = ctk.CTkButton(
            ctrl,
            text="Queue Selected (0)",
            font=ctk.CTkFont(weight="bold"),
            fg_color=PALETTE["btn_success"],
            hover_color=PALETTE["btn_success_hover"]
        )
        queue_btn.pack(side="right")

        checkbox_vars = {}

        def _on_fetched(entries: List[Dict[str, Any]]):
            title_lbl.configure(text=f"Found {len(entries)} items in playlist")
            for e in entries:
                var = ctk.BooleanVar(value=True)
                idx = e.get('index', 1)
                t_str = e.get('title', 'Video')
                dur = e.get('duration')
                d_str = f" ({dur//60}:{dur%60:02d})" if dur else ""

                cb = ctk.CTkCheckBox(scroll, text=f"#{idx:02d}  {t_str}{d_str}", variable=var, font=ctk.CTkFont(size=12))
                cb.pack(anchor="w", padx=10, pady=4)
                checkbox_vars[e['url']] = (var, f"{idx:02d} - {t_str}")

            queue_btn.configure(text=f"Queue Selected ({len(entries)})", command=lambda: _do_queue_selected(entries))

        def _do_queue_selected(entries: List[Dict[str, Any]]):
            f_type = "audio" if "Audio" in format_seg.get() else "video"
            output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            browser_val, cookie_file = self._get_auth_params()
            use_prefix = bool(num_switch.get())

            for e in entries:
                var, prefixed_title = checkbox_vars.get(e['url'], (None, None))
                if var and var.get():
                    final_title = prefixed_title if use_prefix else e.get('title', 'Media')
                    task = DownloadTask(
                        url=e['url'],
                        title=final_title,
                        format_type=f_type,
                        quality="best",
                        output_dir=output_dir,
                        browser_cookies=browser_val,
                        cookie_file=cookie_file
                    )
                    self.queue_mgr.add_task(task)

            modal.destroy()
            self._update_queue_badge()
            self._show_tab("queue")

        def _worker_fetch():
            browser_val, cookie_file = self._get_auth_params()
            try:
                entries = self.engine.extract_playlist_entries(url, browser_cookies=browser_val, cookie_file=cookie_file)
                self.after(0, _on_fetched, entries)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Playlist Error", str(e), parent=modal))

        threading.Thread(target=_worker_fetch, daemon=True).start()

    # ================= 3. BATCH URL MODAL ================= #

    def _open_batch_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Batch URL Importer")
        modal.geometry("580x480")
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="Paste Multiple URLs (One per line)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=(20, 5))

        txt = ctk.CTkTextbox(
            modal,
            height=220,
            fg_color=PALETTE["entry_bg"],
            border_color=PALETTE["entry_border"],
            border_width=1
        )
        txt.pack(fill="both", expand=True, padx=20, pady=5)
        txt.insert("0.0", "# Paste video links below:\n")

        opts_frame = ctk.CTkFrame(modal, fg_color="transparent")
        opts_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(opts_frame, text="Format:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 8))
        format_seg = ctk.CTkSegmentedButton(opts_frame, values=["Video (MP4)", "Audio (MP3)"])
        format_seg.set("Video (MP4)")
        format_seg.pack(side="left")

        def _do_batch_add():
            raw_text = txt.get("0.0", "end")
            lines = [l.strip() for l in raw_text.splitlines() if l.strip() and not l.strip().startswith("#")]
            if not lines:
                messagebox.showwarning("No URLs", "Please paste at least one valid URL.", parent=modal)
                return

            f_type = "audio" if "Audio" in format_seg.get() else "video"
            output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            browser_val, cookie_file = self._get_auth_params()

            self.queue_mgr.add_batch(
                urls=lines,
                format_type=f_type,
                quality="best",
                output_dir=output_dir,
                browser_cookies=browser_val,
                cookie_file=cookie_file
            )
            modal.destroy()
            self._update_queue_badge()
            self._show_tab("queue")

        ctk.CTkButton(
            modal,
            text="Queue All URLs",
            height=40,
            font=ctk.CTkFont(weight="bold"),
            fg_color=PALETTE["btn_success"],
            hover_color=PALETTE["btn_success_hover"],
            command=_do_batch_add
        ).pack(fill="x", padx=20, pady=(0, 20))

    # ================= 4. QUEUE VIEW ================= #

    def _build_queue_view(self):
        self.view_queue.grid_columnconfigure(0, weight=1)
        self.view_queue.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.view_queue, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.queue_stats_label = ctk.CTkLabel(
            bar,
            text="Queue: 0 tasks",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.queue_stats_label.pack(side="left")

        ctk.CTkButton(
            bar,
            text="Clear Finished",
            width=120,
            height=32,
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._clear_finished_queue
        ).pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(
            self.view_queue,
            fg_color=PALETTE["bg_card_subtle"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=10
        )
        self.queue_scroll.grid(row=1, column=0, sticky="nsew")

    def _clear_finished_queue(self):
        self.queue_mgr.clear_completed()
        self._render_queue_list()
        self._update_queue_badge()

    def _render_queue_list(self):
        tasks = self.queue_mgr.get_all_tasks()
        active = sum(1 for t in tasks if t.status in ("queued", "downloading"))
        finished = sum(1 for t in tasks if t.status in ("completed", "failed", "canceled"))

        self.queue_stats_label.configure(text=f"Active: {active}  •  Finished: {finished}  •  Total: {len(tasks)}")

        for child in self.queue_scroll.winfo_children():
            child.destroy()
        self.queue_widgets.clear()

        if not tasks:
            empty = ctk.CTkLabel(
                self.queue_scroll,
                text="Download queue is empty.\nAdd URLs from the Downloader tab, use 'Batch URLs', or 'Playlist'.",
                font=ctk.CTkFont(size=13),
                text_color=PALETTE["text_muted"],
                justify="center"
            )
            empty.pack(pady=60)
            return

        for task in tasks:
            self._create_task_card(task)

    def _create_task_card(self, task: DownloadTask):
        card = ctk.CTkFrame(
            self.queue_scroll,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=8
        )
        card.pack(fill="x", padx=10, pady=5)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))

        title_lbl = ctk.CTkLabel(
            top,
            text=task.title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text_primary"],
            anchor="w",
            wraplength=520
        )
        title_lbl.pack(side="left", fill="x", expand=True)

        fmt_lbl = ctk.CTkLabel(top, text=task.get_badge_text(), font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8")
        fmt_lbl.pack(side="left", padx=8)

        status_lbl = ctk.CTkLabel(top, text=task.status.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color=self._get_status_color(task.status))
        status_lbl.pack(side="right")

        pbar = ctk.CTkProgressBar(card, height=8, corner_radius=4, progress_color="#10b981")
        pbar.pack(fill="x", padx=14, pady=4)
        safe_prog = max(0.0, min(1.0, float(task.progress or 0.0)))
        pbar.set(safe_prog)

        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.pack(fill="x", padx=14, pady=(2, 10))

        info_lbl = ctk.CTkLabel(bot, text=f"{task.speed}  •  {task.size_info}  •  {task.eta}", font=ctk.CTkFont(size=11), text_color=PALETTE["text_muted"])
        info_lbl.pack(side="left")

        if task.status in ("queued", "downloading"):
            cancel_btn = ctk.CTkButton(
                bot,
                text="Cancel",
                width=65,
                height=24,
                corner_radius=4,
                fg_color=PALETTE["btn_secondary"],
                hover_color=PALETTE["btn_secondary_hover"],
                text_color=PALETTE["btn_secondary_text"],
                command=lambda tid=task.id: self._cancel_task(tid)
            )
            cancel_btn.pack(side="right")
        elif task.status == "completed":
            open_btn = ctk.CTkButton(
                bot,
                text="Play",
                width=60,
                height=24,
                corner_radius=4,
                fg_color=PALETTE["btn_success"],
                hover_color=PALETTE["btn_success_hover"],
                command=lambda p=task.saved_path: self._play_media(p)
            )
            open_btn.pack(side="right", padx=(4, 0))
        elif task.status in ("failed", "canceled"):
            retry_btn = ctk.CTkButton(
                bot,
                text="Retry",
                width=60,
                height=24,
                corner_radius=4,
                fg_color=PALETTE["btn_primary"],
                hover_color=PALETTE["btn_primary_hover"],
                command=lambda tid=task.id: self._retry_task(tid)
            )
            retry_btn.pack(side="right")

        self.queue_widgets[task.id] = {
            "title": title_lbl,
            "status": status_lbl,
            "pbar": pbar,
            "info": info_lbl,
            "last_status": task.status
        }

    def _get_status_color(self, status: str) -> str:
        if status == "downloading":
            return "#38bdf8"
        elif status == "completed":
            return "#10b981"
        elif status == "failed":
            return "#ef4444"
        elif status == "canceled":
            return "#6b7280"
        return "#f59e0b"

    def _cancel_task(self, task_id: str):
        self.queue_mgr.cancel_task(task_id)
        self._refresh_queue_view()

    def _retry_task(self, task_id: str):
        self.queue_mgr.retry_task(task_id)
        self._refresh_queue_view()

    def _on_queue_task_updated(self, task: DownloadTask):
        self.after(0, self._apply_task_update_to_ui, task)

    def _apply_task_update_to_ui(self, task: DownloadTask):
        self._update_queue_badge()
        w = self.queue_widgets.get(task.id)
        if w:
            prev_status = w.get("last_status")
            w["title"].configure(text=task.title)
            w["status"].configure(text=task.status.upper(), text_color=self._get_status_color(task.status))
            safe_prog = max(0.0, min(1.0, float(task.progress or 0.0)))
            w["pbar"].set(safe_prog)
            w["info"].configure(text=f"{task.speed}  •  {task.size_info}  •  {task.eta}")
            w["last_status"] = task.status
            if prev_status != task.status and task.status in ("completed", "failed", "canceled"):
                self._render_queue_list()

    def _on_queue_task_completed(self, task: DownloadTask):
        self.after(0, self._record_completed_task_to_library, task)

    def _record_completed_task_to_library(self, task: DownloadTask):
        file_size_str = "Completed"
        if task.saved_path and os.path.exists(task.saved_path):
            sz = os.path.getsize(task.saved_path) / (1024 * 1024)
            file_size_str = f"{sz:.1f} MB"

        entry = {
            "title": task.title,
            "format": task.format_type.upper(),
            "quality": task.quality,
            "size": file_size_str,
            "path": task.saved_path or self.config_data.get("download_dir", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.library_items.insert(0, entry)
        save_library(self.library_items)

    def _update_queue_badge(self):
        tasks = self.queue_mgr.get_all_tasks()
        active = sum(1 for t in tasks if t.status in ("queued", "downloading"))
        q_btn = self.nav_btns.get("queue")
        if q_btn:
            q_btn.configure(text=f"Queue ({active})")

    # ================= 5. SMART CLIPBOARD WATCHER ================= #

    def _check_clipboard_poll(self):
        if not self.config_data.get("clipboard_monitor", True):
            return

        video_regex = re.compile(
            r'(https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be|vimeo\.com|twitter\.com|x\.com|tiktok\.com|instagram\.com)/\S+)',
            re.IGNORECASE
        )
        try:
            clip = self.clipboard_get()
            if clip:
                clip = clip.strip()
                if clip and clip != self.last_clipboard_text:
                    self.last_clipboard_text = clip
                    if video_regex.search(clip):
                        self._show_clipboard_banner(clip)
        except Exception:
            pass
        finally:
            self.after(1500, self._check_clipboard_poll)

    def _show_clipboard_banner(self, url: str):
        self.clip_banner.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 0))
        self.detected_url = url

    def _load_detected_clipboard(self):
        if hasattr(self, 'detected_url') and self.detected_url:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.detected_url)
            self._show_tab("downloader")
            self._start_fetch_metadata()
        self.clip_banner.grid_forget()

    # ================= 6. LIBRARY VIEW ================= #

    def _build_library_view(self):
        self.view_library.grid_columnconfigure(0, weight=1)
        self.view_library.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.view_library, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.lib_count_label = ctk.CTkLabel(
            bar,
            text=f"Total Downloads: {len(self.library_items)}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.lib_count_label.pack(side="left")

        ctk.CTkButton(
            bar,
            text="Clear History",
            width=110,
            height=32,
            fg_color=PALETTE["btn_danger"],
            hover_color=PALETTE["btn_danger_hover"],
            command=self._clear_library_prompt
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            bar,
            text="Open Download Folder",
            width=160,
            height=32,
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._open_downloads_folder
        ).pack(side="right")

        self.lib_scroll = ctk.CTkScrollableFrame(
            self.view_library,
            fg_color=PALETTE["bg_card_subtle"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=10
        )
        self.lib_scroll.grid(row=1, column=0, sticky="nsew")

    def _refresh_library_ui(self):
        self.lib_count_label.configure(text=f"Total Downloads: {len(self.library_items)}")

        for child in self.lib_scroll.winfo_children():
            child.destroy()

        if not self.library_items:
            empty = ctk.CTkLabel(
                self.lib_scroll,
                text="No downloads yet. Completed items will appear here.",
                font=ctk.CTkFont(size=13),
                text_color=PALETTE["text_muted"]
            )
            empty.pack(pady=40)
            return

        for item in self.library_items:
            card = ctk.CTkFrame(
                self.lib_scroll,
                fg_color=PALETTE["bg_card"],
                border_color=PALETTE["border"],
                border_width=1,
                corner_radius=8
            )
            card.pack(fill="x", padx=10, pady=5)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=14, pady=10)

            title_lbl = ctk.CTkLabel(
                info_frame,
                text=item.get("title", "Media File"),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=PALETTE["text_primary"],
                anchor="w",
                wraplength=520
            )
            title_lbl.pack(anchor="w")

            meta_lbl = ctk.CTkLabel(
                info_frame,
                text=f"{item.get('format')} • {item.get('size')} • {item.get('timestamp')}",
                font=ctk.CTkFont(size=11),
                text_color=PALETTE["text_muted"],
                anchor="w"
            )
            meta_lbl.pack(anchor="w", pady=(2, 0))

            action_frame = ctk.CTkFrame(card, fg_color="transparent")
            action_frame.pack(side="right", padx=12, pady=10)

            file_path = item.get("path", "")
            ctk.CTkButton(
                action_frame,
                text="Play",
                width=60,
                height=30,
                corner_radius=6,
                fg_color=PALETTE["btn_success"],
                hover_color=PALETTE["btn_success_hover"],
                command=lambda p=file_path: self._play_media(p)
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                action_frame,
                text="Show",
                width=60,
                height=30,
                corner_radius=6,
                fg_color=PALETTE["btn_secondary"],
                hover_color=PALETTE["btn_secondary_hover"],
                text_color=PALETTE["btn_secondary_text"],
                command=lambda p=file_path: self._show_in_explorer(p)
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                action_frame,
                text="Remove",
                width=65,
                height=30,
                corner_radius=6,
                fg_color=PALETTE["btn_secondary"],
                hover_color=PALETTE["btn_danger_hover"],
                text_color=PALETTE["btn_secondary_text"],
                command=lambda itm=item: self._delete_library_item(itm)
            ).pack(side="left", padx=(4, 0))

    def _delete_library_item(self, item: Dict[str, Any]):
        title = item.get("title", "this item")
        if messagebox.askyesno("Remove from Library", f"Remove '{title}' from your library history?"):
            if item in self.library_items:
                self.library_items.remove(item)
                save_library(self.library_items)
                self._refresh_library_ui()

    def _clear_library_prompt(self):
        if not self.library_items:
            messagebox.showinfo("Library Empty", "Your library is already empty.")
            return

        confirm = messagebox.askyesno(
            "Clear Library History",
            f"Are you sure you want to clear all {len(self.library_items)} items from your library history?\n\n(Your downloaded media files on disk will NOT be deleted)."
        )
        if confirm:
            self.library_items.clear()
            save_library(self.library_items)
            self._refresh_library_ui()

    def _play_media(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Playback Error", f"Unable to open media player:\n{e}")
        else:
            messagebox.showwarning("File Missing", "The file could not be found at its saved location.")

    def _show_in_explorer(self, path: str):
        if path and os.path.exists(path):
            try:
                subprocess.run(["explorer", f"/select,{os.path.abspath(path)}"])
            except Exception:
                self._open_downloads_folder()
        else:
            self._open_downloads_folder()

    def _open_downloads_folder(self):
        d = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        if os.path.exists(d):
            os.startfile(d)
        else:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)

    # ================= 7. SETTINGS & PREFERENCES VIEW ================= #

    def _build_settings_view(self):
        # 1. Appearance & Theme Card
        theme_card = ctk.CTkFrame(
            self.view_settings,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        theme_card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            theme_card,
            text="Appearance & Theme",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 4))

        ctk.CTkLabel(
            theme_card,
            text="Select color theme for Argus Studio desktop interface.",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"]
        ).pack(anchor="w", padx=18, pady=(0, 10))

        theme_row = ctk.CTkFrame(theme_card, fg_color="transparent")
        theme_row.pack(fill="x", padx=18, pady=(0, 16))

        self.setting_theme_seg = ctk.CTkSegmentedButton(
            theme_row,
            values=["System", "Dark", "Light"],
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._set_theme
        )
        cur_t = self.config_data.get("theme", "System").capitalize()
        self.setting_theme_seg.set(cur_t)
        self.setting_theme_seg.pack(side="left")

        # 2. Download Location
        dir_card = ctk.CTkFrame(
            self.view_settings,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        dir_card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            dir_card,
            text="Default Download Location",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 4))

        dir_row = ctk.CTkFrame(dir_card, fg_color="transparent")
        dir_row.pack(fill="x", padx=18, pady=(0, 16))

        self.cfg_dir_entry = ctk.CTkEntry(
            dir_row,
            height=38,
            fg_color=PALETTE["entry_bg"],
            border_color=PALETTE["entry_border"],
            text_color=PALETTE["entry_text"]
        )
        self.cfg_dir_entry.insert(0, self.config_data.get("download_dir", ""))
        self.cfg_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            dir_row,
            text="Change...",
            width=90,
            height=38,
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._change_default_dir
        ).pack(side="right")

        # 3. Ingestion & Performance Card
        feat_card = ctk.CTkFrame(
            self.view_settings,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        feat_card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            feat_card,
            text="Ingestion Performance & Automation",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 8))

        row1 = ctk.CTkFrame(feat_card, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row1, text="Max Concurrent Downloads:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_primary"]).pack(side="left", padx=(0, 12))
        self.conc_combo = ctk.CTkComboBox(row1, values=["1", "2 (Default)", "3", "4", "5"], width=130, command=self._change_concurrency)
        cur_conc = str(self.config_data.get("max_concurrent", 2))
        self.conc_combo.set(cur_conc if cur_conc != "2" else "2 (Default)")
        self.conc_combo.pack(side="left")

        row_sp = ctk.CTkFrame(feat_card, fg_color="transparent")
        row_sp.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row_sp, text="Global Speed Limit:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_primary"]).pack(side="left", padx=(0, 12))
        self.cfg_speed_combo = ctk.CTkComboBox(row_sp, values=["Unlimited", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s"], width=130, command=self._change_speed_limit)
        self.cfg_speed_combo.set(self.config_data.get("speed_limit", "Unlimited"))
        self.cfg_speed_combo.pack(side="left")

        row2 = ctk.CTkFrame(feat_card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(6, 16))
        self.clip_mon_switch = ctk.CTkCheckBox(
            row2,
            text="Smart Clipboard Auto-Detector (Pops up when a media link is copied)",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_primary"],
            command=self._toggle_clipboard_mon
        )
        if self.config_data.get("clipboard_monitor", True):
            self.clip_mon_switch.select()
        self.clip_mon_switch.pack(side="left")

        # 4. FFmpeg Engine Integration Card
        self.ffmpeg_card = ctk.CTkFrame(
            self.view_settings,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        self.ffmpeg_card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            self.ffmpeg_card,
            text="Media Transcoding Engine (FFmpeg)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 4))

        ff_desc = ctk.CTkLabel(
            self.ffmpeg_card,
            text="FFmpeg enables YouTube 1080p/4K DASH stream multiplexing, MP3 audio conversion, and subtitle embedding.",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"],
            anchor="w",
            wraplength=680
        )
        ff_desc.pack(anchor="w", padx=18, pady=(0, 10))

        ff_row = ctk.CTkFrame(self.ffmpeg_card, fg_color="transparent")
        ff_row.pack(fill="x", padx=18, pady=(0, 12))

        self.ffmpeg_status_label = ctk.CTkLabel(ff_row, text="Checking FFmpeg status...", font=ctk.CTkFont(size=12))
        self.ffmpeg_status_label.pack(side="left")

        self.ffmpeg_install_btn = ctk.CTkButton(
            ff_row,
            text="Install Portable FFmpeg",
            width=175,
            height=32,
            font=ctk.CTkFont(weight="bold"),
            fg_color=PALETTE["btn_accent"],
            hover_color=PALETTE["btn_accent_hover"],
            command=self._start_ffmpeg_install
        )
        self.ffmpeg_install_btn.pack(side="right")

        self.ffmpeg_pbar = ctk.CTkProgressBar(self.ffmpeg_card, height=6, progress_color="#10b981")
        self.ffmpeg_plbl = ctk.CTkLabel(self.ffmpeg_card, text="", font=ctk.CTkFont(size=11), text_color=PALETTE["text_muted"])

        # 5. Diagnostics & Software Updates
        diag_card = ctk.CTkFrame(
            self.view_settings,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            border_width=1,
            corner_radius=12
        )
        diag_card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            diag_card,
            text="Diagnostics & Updates",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 4))

        diag_row = ctk.CTkFrame(diag_card, fg_color="transparent")
        diag_row.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            diag_row,
            text=f"Version v{APP_VERSION} • Runtime Log: {os.path.basename(LOG_FILE)}",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        ).pack(side="left")

        ctk.CTkButton(
            diag_row,
            text="Open Log",
            width=90,
            height=32,
            fg_color=PALETTE["btn_secondary"],
            hover_color=PALETTE["btn_secondary_hover"],
            text_color=PALETTE["btn_secondary_text"],
            command=self._open_log_file
        ).pack(side="right", padx=(8, 0))

        self.check_update_btn = ctk.CTkButton(
            diag_row,
            text="Check for Updates",
            width=140,
            height=32,
            font=ctk.CTkFont(weight="bold"),
            fg_color=PALETTE["btn_primary"],
            hover_color=PALETTE["btn_primary_hover"],
            command=lambda: self._check_updates_async(show_popup_if_none=True)
        )
        self.check_update_btn.pack(side="right")

        self.update_status_label = ctk.CTkLabel(diag_card, text="", font=ctk.CTkFont(size=11))
        self.apply_update_btn = ctk.CTkButton(
            diag_card,
            text="Update Now",
            width=120,
            height=32,
            font=ctk.CTkFont(weight="bold"),
            fg_color=PALETTE["btn_success"],
            hover_color=PALETTE["btn_success_hover"],
            command=self._start_inapp_update
        )
        self.update_pbar = ctk.CTkProgressBar(diag_card, height=6, progress_color="#16a34a")
        self.update_plbl = ctk.CTkLabel(diag_card, text="", font=ctk.CTkFont(size=11), text_color=PALETTE["text_muted"])

    def _check_updates_async(self, show_popup_if_none: bool = False):
        self.check_update_btn.configure(state="disabled", text="Checking...")
        self.update_status_label.configure(text="Contacting update server...", text_color=PALETTE["text_muted"])

        def _worker():
            custom_endpoint = self.config_data.get("update_server") or None
            mgr = UpdateManager(current_version=APP_VERSION, custom_endpoint=custom_endpoint)
            info = mgr.check_for_updates()
            self.after(0, self._on_update_check_result, info, show_popup_if_none)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_check_result(self, info: Dict[str, Any], show_popup_if_none: bool):
        self.check_update_btn.configure(state="normal", text="Check for Updates")
        self.cached_update_info = info

        if info.get("update_available"):
            latest = info.get("latest_version")
            self.update_status_label.configure(
                text=f"Version v{latest} available",
                text_color="#10b981"
            )
            self.apply_update_btn.pack(side="right", padx=(8, 0))

            self.update_banner_lbl.configure(text=f"Update Available: Argus Studio v{latest} is ready")
            self.update_banner.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 0))

            if show_popup_if_none:
                notes = info.get("release_notes", "")
                if messagebox.askyesno(
                    "Update Available",
                    f"A new version of Argus Studio (v{latest}) is available!\n\nRelease Notes:\n{notes}\n\nWould you like to install the update now?"
                ):
                    self._start_inapp_update()
        else:
            err = info.get("error")
            if err:
                self.update_status_label.configure(text=f"Notice: {err}", text_color="#f59e0b")
                if show_popup_if_none:
                    messagebox.showwarning("Update Check", f"Could not check for updates:\n{err}")
            else:
                self.update_status_label.configure(text=f"● You are running the latest version (v{APP_VERSION})", text_color="#10b981")
                if show_popup_if_none:
                    messagebox.showinfo("Up to Date", f"Argus Studio v{APP_VERSION} is the latest available version.")

    def _start_inapp_update(self):
        if not self.cached_update_info or not self.cached_update_info.get("download_url"):
            messagebox.showinfo("Update", "No update download package available.")
            return

        download_url = self.cached_update_info["download_url"]
        self.apply_update_btn.configure(state="disabled", text="Updating...")
        self.update_banner_btn.configure(state="disabled", text="Updating...")

        self.update_pbar.pack(fill="x", padx=18, pady=(0, 6))
        self.update_pbar.set(0)
        self.update_plbl.pack(anchor="w", padx=18, pady=(0, 12))
        self.update_plbl.configure(text="Connecting to download mirror...")

        def _worker():
            def _prog(msg: str, frac: float):
                self.after(0, lambda: (
                    self.update_pbar.set(frac),
                    self.update_plbl.configure(text=msg)
                ))
            try:
                mgr = UpdateManager(current_version=APP_VERSION)
                staged = mgr.download_update(download_url, progress_callback=_prog)
                self.after(0, self._on_update_ready, staged, mgr)
            except Exception as e:
                self.after(0, self._on_update_failed, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_ready(self, staged_path: str, mgr: UpdateManager):
        self.update_plbl.configure(text="Applying update in-place...")
        try:
            mgr.apply_update(staged_path, restart=True)
        except Exception as e:
            self._on_update_failed(str(e))

    def _on_update_failed(self, err_msg: str):
        self.update_pbar.pack_forget()
        self.update_plbl.pack_forget()
        self.apply_update_btn.configure(state="normal", text="Update Now")
        self.update_banner_btn.configure(state="normal", text="Update Now")
        messagebox.showerror("Update Failed", f"Unable to automatically apply update:\n\n{err_msg}")

    def _open_log_file(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            messagebox.showinfo("Log File", "No runtime log file exists yet.")

    def _refresh_ffmpeg_status_ui(self):
        loc = get_ffmpeg_location()
        if loc:
            self.ffmpeg_status_label.configure(
                text=f"● FFmpeg: Active ({loc})",
                text_color="#10b981"
            )
            self.ffmpeg_install_btn.configure(
                text="Reinstall FFmpeg",
                fg_color=PALETTE["btn_secondary"],
                hover_color=PALETTE["btn_secondary_hover"],
                text_color=PALETTE["btn_secondary_text"]
            )
            self.ffmpeg_banner.grid_forget()
        else:
            self.ffmpeg_status_label.configure(
                text="FFmpeg: Not Installed on this system",
                text_color="#ef4444"
            )
            self.ffmpeg_install_btn.configure(text="Install Portable FFmpeg", fg_color="#ea580c", hover_color="#c2410c")
            self.ffmpeg_banner.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 0))

    def _start_ffmpeg_install(self):
        self.ffmpeg_install_btn.configure(state="disabled", text="Installing...")
        self.ffmpeg_pbar.pack(fill="x", padx=18, pady=(0, 6))
        self.ffmpeg_pbar.set(0)
        self.ffmpeg_plbl.pack(anchor="w", padx=18, pady=(0, 12))
        self.ffmpeg_plbl.configure(text="Connecting to official release server...")

        def _worker():
            def _progress(msg: str, frac: float):
                self.after(0, lambda: (
                    self.ffmpeg_pbar.set(frac),
                    self.ffmpeg_plbl.configure(text=msg)
                ))
            try:
                success = download_portable_ffmpeg(progress_callback=_progress)
                self.after(0, self._on_ffmpeg_installed, success, None)
            except Exception as e:
                self.after(0, self._on_ffmpeg_installed, False, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ffmpeg_installed(self, success: bool, err: Optional[str]):
        self.ffmpeg_install_btn.configure(state="normal", text="Reinstall FFmpeg" if success else "Retry Install")
        self.ffmpeg_pbar.pack_forget()
        self.ffmpeg_plbl.pack_forget()

        if success:
            messagebox.showinfo("FFmpeg Configured", "Portable FFmpeg has been successfully installed and linked to Argus Studio!")
        else:
            messagebox.showerror("FFmpeg Installation Failed", f"Unable to automatically download FFmpeg:\n{err}")

        self._refresh_ffmpeg_status_ui()

    def _change_default_dir(self):
        sel = filedialog.askdirectory(initialdir=self.config_data.get("download_dir", ""))
        if sel:
            self.config_data["download_dir"] = sel
            save_config(self.config_data)
            self.cfg_dir_entry.delete(0, "end")
            self.cfg_dir_entry.insert(0, sel)

    def _change_concurrency(self, val: str):
        num = int(val.split()[0])
        self.config_data["max_concurrent"] = num
        self.queue_mgr.max_concurrent = num
        save_config(self.config_data)
        self.engine_dot.configure(text=f"● Engine Active ({num} slots)")

    def _change_speed_limit(self, val: str):
        self.config_data["speed_limit"] = val
        save_config(self.config_data)
        if hasattr(self, "speed_combo"):
            self.speed_combo.set(val)

    def _toggle_clipboard_mon(self):
        enabled = bool(self.clip_mon_switch.get())
        self.config_data["clipboard_monitor"] = enabled
        save_config(self.config_data)


def main():
    cfg = load_config()
    theme = cfg.get("theme", "System")
    ctk.set_appearance_mode(theme)
    ctk.set_default_color_theme("blue")
    app = ArgusStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
