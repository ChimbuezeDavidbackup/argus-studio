"""
Argus Studio - In-App Automated Update System
Provides seamless background update checking, binary staging, and in-place application replacement
without requiring users to manually visit websites or run setup wizards.
"""

import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, Optional, Tuple

import certifi
import requests

from .config import APP_VERSION


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse semver string like 'v2.2.0' or '2.3.1' into integer tuple."""
    if not v_str:
        return (0, 0, 0)
    cleaned = re.sub(r"^[vV]", "", v_str.strip())
    # Extract numeric components
    numbers = re.findall(r"\d+", cleaned)
    return tuple(int(n) for n in numbers) if numbers else (0, 0, 0)


class UpdateManager:
    """Manages update discovery, streaming downloads, and seamless in-place replacement."""

    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo: str = "ChimbuezeDavid/argus-studio",
        custom_endpoint: Optional[str] = None
    ):
        self.current_version = current_version
        self.repo = repo
        self.custom_endpoint = custom_endpoint

    def check_for_updates(self) -> Dict[str, Any]:
        """
        Query remote releases to check if a newer version is available.
        Supports GitHub Releases API and custom JSON endpoints.
        """
        urls_to_try = []
        if self.custom_endpoint:
            urls_to_try.append(self.custom_endpoint)
        if self.repo:
            urls_to_try.append(f"https://api.github.com/repos/{self.repo}/releases/latest")

        headers = {
            "User-Agent": f"ArgusStudio/{self.current_version} ({platform.system()})",
            "Accept": "application/vnd.github.v3+json, application/json",
        }

        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=headers, timeout=8, verify=certifi.where())
                if resp.status_code == 200:
                    data = resp.json()
                    tag = data.get("tag_name") or data.get("version", "")
                    remote_ver = parse_version(tag)
                    local_ver = parse_version(self.current_version)

                    has_update = remote_ver > local_ver
                    notes = data.get("body") or data.get("notes", "Performance improvements and bug fixes.")

                    # Locate installer and portable assets
                    installer_url = None
                    portable_url = None

                    assets = data.get("assets", [])
                    for a in assets:
                        name = a.get("name", "").lower()
                        d_url = a.get("browser_download_url")
                        if "setup" in name and name.endswith(".exe"):
                            installer_url = d_url
                        elif ("portable" in name or name == "argusstudio.exe") and name.endswith(".exe"):
                            portable_url = d_url

                    # Fallback to direct download url if custom endpoint provided it
                    if not installer_url and not portable_url:
                        direct = data.get("download_url")
                        if direct:
                            if "setup" in direct.lower():
                                installer_url = direct
                            else:
                                portable_url = direct

                    return {
                        "update_available": has_update,
                        "current_version": self.current_version,
                        "latest_version": tag.lstrip("vV"),
                        "release_notes": notes.strip(),
                        "installer_url": installer_url,
                        "portable_url": portable_url,
                        "download_url": installer_url or portable_url,
                        "is_installer": bool(installer_url),
                        "checked_at": time.time(),
                        "error": None,
                    }
                elif resp.status_code == 403:
                    return {
                        "update_available": False,
                        "current_version": self.current_version,
                        "latest_version": self.current_version,
                        "error": "Update server rate limit or access restriction encountered.",
                    }
            except Exception as e:
                continue

        return {
            "update_available": False,
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "error": "Unable to connect to update server.",
        }

    def download_update(
        self,
        download_url: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """
        Download update payload with real-time byte telemetry.
        Returns path to staged executable file.
        """
        temp_dir = os.path.join(tempfile.gettempdir(), "ArgusStudio_Update")
        os.makedirs(temp_dir, exist_ok=True)

        filename = os.path.basename(download_url.split("?")[0]) or "ArgusStudio-Update.exe"
        if not filename.endswith(".exe"):
            filename += ".exe"

        dest_file = os.path.join(temp_dir, filename)

        session = requests.Session()
        session.headers.update({"User-Agent": f"ArgusStudio-Updater/{self.current_version}"})

        with session.get(download_url, stream=True, timeout=30, verify=certifi.where()) as resp:
            resp.raise_for_status()
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            block_size = 131072  # 128 KB chunks

            with open(dest_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            ratio = min(0.99, downloaded / total_size) if total_size > 0 else 0.5
                            mb_dl = downloaded / (1024 * 1024)
                            mb_tot = total_size / (1024 * 1024)
                            txt = f"Downloading update: {mb_dl:.1f} / {mb_tot:.1f} MB ({ratio * 100:.0f}%)"
                            progress_callback(txt, ratio)

        if progress_callback:
            progress_callback("Download complete. Preparing update...", 1.0)

        return dest_file

    def apply_update(self, staged_file: str, restart: bool = True):
        """
        Apply downloaded update in-place.
        - For Inno Setup installers: triggers silent upgrade with /SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
        - For standalone portables: spawns detached PowerShell supervisor that hot-swaps the binary and relaunches.
        """
        if not os.path.exists(staged_file):
            raise FileNotFoundError(f"Staged update file not found at: {staged_file}")

        is_frozen = getattr(sys, "frozen", False)
        current_exe = os.path.abspath(sys.executable)
        current_pid = os.getpid()

        # If user is running in developer python mode
        if not is_frozen:
            raise RuntimeError(
                "In-app binary update is only supported when running the compiled Argus Studio executable.\n"
                "In developer mode, pull latest source with: git pull"
            )

        # Detect if staged update is an Inno Setup installer
        is_installer = "setup" in os.path.basename(staged_file).lower()

        if is_installer:
            # Inno Setup flags for completely hands-off in-place upgrade
            args = [
                staged_file,
                "/SILENT",
                "/SUPPRESSMSGBOXES",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
            ]
            flags = 0
            if platform.system() == "Windows":
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW

            subprocess.Popen(args, creationflags=flags)
            if restart:
                time.sleep(0.5)
                sys.exit(0)
        else:
            # Portable standalone executable replacement via detached supervisor script
            if platform.system() == "Windows":
                # PowerShell detached hot-swapper
                ps_script = (
                    f"Start-Sleep -Milliseconds 800; "
                    f"Stop-Process -Id {current_pid} -Force -ErrorAction SilentlyContinue; "
                    f"Move-Item -Path '{staged_file}' -Destination '{current_exe}' -Force; "
                    f"Start-Process -FilePath '{current_exe}'"
                )
                cmd = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script]
                subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000,
                )
                if restart:
                    time.sleep(0.3)
                    sys.exit(0)
            else:
                # Unix fallback
                sh_cmd = (
                    f"sleep 1 && kill -9 {current_pid} 2>/dev/null; "
                    f"mv -f '{staged_file}' '{current_exe}' && '{current_exe}' &"
                )
                subprocess.Popen(["sh", "-c", sh_cmd])
                if restart:
                    sys.exit(0)
