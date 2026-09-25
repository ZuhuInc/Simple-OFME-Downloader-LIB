"""
Fanta OFME Downloader - Browser Detection & Dynamic Link Resolvers
Resolves complex hosters (GoFile, PixelDrain, etc.) to direct downloadable stream URLs.
"""

import os
import re
import requests
from typing import Dict, Optional, Tuple

try:
    import winreg
except ImportError:
    winreg = None


def normalize_browser_name(raw_name: str) -> str:
    raw = raw_name.lower()
    if "brave" in raw:
        return "Brave"
    if "opera gx" in raw or "operagx" in raw:
        return "Opera GX"
    if "chrome" in raw and "google" in raw:
        return "Google Chrome"
    if "firefox" in raw:
        return "Firefox"
    if "opera" in raw and "gx" not in raw:
        return "Opera"
    if "vivaldi" in raw:
        return "Vivaldi"
    if "edge" in raw:
        return "Microsoft Edge"
    return raw_name


def get_installed_browsers() -> Dict[str, str]:
    found_browsers = {}
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")

    potential_paths = {
        "Opera GX": [
            os.path.join(local_appdata, "Programs", "Opera GX", "launcher.exe"),
            os.path.join(local_appdata, "Programs", "Opera GX", "opera.exe")
        ],
        "Google Chrome": [
            os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe")
        ],
        "Brave": [
            os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
        ],
        "Firefox": [
            os.path.join(prog_files, "Mozilla Firefox", "firefox.exe"),
            os.path.join(local_appdata, "Mozilla Firefox", "firefox.exe")
        ],
        "Opera": [
            os.path.join(local_appdata, "Programs", "Opera", "launcher.exe"),
            os.path.join(prog_files, "Opera", "launcher.exe")
        ],
        "Vivaldi": [
            os.path.join(local_appdata, "Vivaldi", "Application", "vivaldi.exe"),
            os.path.join(prog_files, "Vivaldi", "Application", "vivaldi.exe")
        ],
        "Microsoft Edge": [
            os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe")
        ]
    }

    for name, paths in potential_paths.items():
        for path in paths:
            if os.path.exists(path):
                found_browsers[name] = path
                break

    if winreg:
        registry_locations = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Clients\StartMenuInternet"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Clients\StartMenuInternet"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet")
        ]
        for hive, reg_path in registry_locations:
            try:
                with winreg.OpenKey(hive, reg_path) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            i += 1
                            if "iexplore" in subkey_name.lower():
                                continue
                            name = normalize_browser_name(subkey_name)
                            if name in found_browsers:
                                continue
                            cmd_path = f"{reg_path}\\{subkey_name}\\shell\\open\\command"
                            with winreg.OpenKey(hive, cmd_path) as cmd_key:
                                val, _ = winreg.QueryValueEx(cmd_key, "")
                                val = val.strip('"')
                                if os.path.exists(val):
                                    found_browsers[name] = val
                        except OSError:
                            break
            except OSError:
                continue

    priority = ["Brave", "Opera GX", "Google Chrome", "Firefox", "Opera", "Vivaldi", "Microsoft Edge"]
    sorted_browsers = {}
    for p in priority:
        if p in found_browsers:
            sorted_browsers[p] = found_browsers[p]
    for k, v in found_browsers.items():
        if k not in sorted_browsers:
            sorted_browsers[k] = v

    return sorted_browsers


class LinkResolver:
    @staticmethod
    def resolve_url(url: str, browser_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Resolves input URL to a direct downloadable URL and suggested filename.
        Returns: (direct_url, filename)
        """
        if not url:
            raise ValueError("Empty URL provided")

        url = url.strip()

        # 1. PixelDrain resolver
        if "pixeldrain.com/u/" in url:
            file_id = url.split("/u/")[-1].split("?")[0].split("/")[0]
            direct_url = f"https://pixeldrain.com/api/file/{file_id}"
            return direct_url, f"pixeldrain_{file_id}.zip"

        # 2. GoFile API direct resolution
        if "gofile.io/d/" in url:
            folder_id = url.split("/d/")[-1].split("?")[0].split("/")[0]
            try:
                # Obtain anonymous guest account token from GoFile
                acc_resp = requests.post("https://api.gofile.io/accounts", timeout=8)
                token = ""
                if acc_resp.status_code == 200:
                    token = acc_resp.json().get("data", {}).get("token", "")

                headers = {"Authorization": f"Bearer {token}"} if token else {}
                content_resp = requests.get(
                    f"https://api.gofile.io/contents/{folder_id}?wt=4fd6sg89d7s6",
                    headers=headers,
                    timeout=10
                )
                if content_resp.status_code == 200:
                    data = content_resp.json().get("data", {})
                    children = data.get("children", {})
                    for child_id, child_info in children.items():
                        direct_link = child_info.get("link")
                        name = child_info.get("name")
                        if direct_link:
                            return direct_link, name
            except Exception as e:
                print(f"[Resolver] GoFile API fast resolve failed: {e}")

        # 3. Direct links or fallback
        # Try a HEAD request to grab content-disposition header if available
        try:
            head_resp = requests.head(url, allow_redirects=True, timeout=6)
            cd = head_resp.headers.get("content-disposition", "")
            filename = None
            if "filename=" in cd:
                filename_match = re.search(r'filename=["\']?([^"\';]+)["\']?', cd)
                if filename_match:
                    filename = filename_match.group(1)
            return head_resp.url, filename
        except Exception:
            pass

        return url, None
