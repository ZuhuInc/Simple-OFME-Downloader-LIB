"""
Fanta OFME Downloader - Steam Integration & Library Detector
Detects Steam installation, parses library folders via vdf, and lists installed games.
"""

import os
import sys
from typing import List, Dict, Any, Optional

try:
    import winreg
except ImportError:
    winreg = None

try:
    import vdf
except ImportError:
    vdf = None


class SteamManager:
    DEFAULT_PATHS = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"E:\Steam",
        r"D:\SteamLibrary",
        r"E:\SteamLibrary"
    ]

    def __init__(self, custom_path: Optional[str] = None):
        self.steam_path = custom_path or self.detect_steam_path()
        self.libraries: List[str] = []
        if self.steam_path:
            self.libraries = self.detect_libraries()

    def detect_steam_path(self) -> Optional[str]:
        if winreg:
            registry_locations = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ]
            for hive, subkey, val_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, val_name)
                        if val and os.path.exists(val):
                            return os.path.normpath(val)
                except OSError:
                    continue

        for p in self.DEFAULT_PATHS:
            if os.path.exists(p):
                return os.path.normpath(p)
        return None

    def detect_libraries(self) -> List[str]:
        libraries = []
        if not self.steam_path or not os.path.exists(self.steam_path):
            return libraries

        libraries.append(self.steam_path)
        vdf_path = os.path.join(self.steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path) and vdf:
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = vdf.loads(f.read())
                    lib_folders = data.get("libraryfolders", {})
                    for idx_or_key, lib_info in lib_folders.items():
                        if isinstance(lib_info, dict) and "path" in lib_info:
                            lib_p = os.path.normpath(lib_info["path"])
                            if lib_p not in libraries and os.path.exists(lib_p):
                                libraries.append(lib_p)
            except Exception as e:
                print(f"[Steam] Error reading libraryfolders.vdf: {e}")

        return libraries

    def get_installed_games(self) -> List[Dict[str, Any]]:
        games = []
        if not vdf:
            return games

        for lib in self.libraries:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.exists(steamapps):
                continue
            for item in os.listdir(steamapps):
                if item.startswith("appmanifest_") and item.endswith(".acf"):
                    acf_path = os.path.join(steamapps, item)
                    try:
                        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                            manifest = vdf.loads(f.read()).get("AppState", {})
                            appid = manifest.get("appid")
                            name = manifest.get("name")
                            installdir = manifest.get("installdir")
                            if name and appid:
                                full_install_path = os.path.join(steamapps, "common", installdir) if installdir else ""
                                games.append({
                                    "appid": appid,
                                    "name": name,
                                    "install_dir": full_install_path,
                                    "library_path": lib,
                                    "size_bytes": int(manifest.get("SizeOnDisk", 0))
                                })
                    except Exception:
                        continue
        return games
