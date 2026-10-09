"""
Fanta OFME Downloader - Steam Integration & Shortcut Manager
Detects Steam installation, parses user profiles, reads/writes binary shortcuts.vdf,
and manages non-Steam game shortcuts.
"""

import os
import re
import sys
import struct
import zlib
import shutil
from typing import List, Dict, Any, Optional

try:
    import winreg
except ImportError:
    winreg = None


class BinaryVDF:
    """Pure-Python Steam Binary KeyValues (VDF) encoder and decoder."""
    @staticmethod
    def parse(data: bytes) -> Dict[str, Any]:
        pos = 0

        def read_string() -> str:
            nonlocal pos
            end = data.find(b'\x00', pos)
            if end == -1:
                return ''
            s = data[pos:end].decode('utf-8', errors='ignore')
            pos = end + 1
            return s

        def parse_dict() -> Dict[str, Any]:
            nonlocal pos
            res: Dict[str, Any] = {}
            while pos < len(data):
                type_byte = data[pos]
                pos += 1
                if type_byte == 8:  # End of dict
                    break
                key = read_string()
                if type_byte == 0:  # Sub-dict
                    res[key] = parse_dict()
                elif type_byte == 1:  # String
                    res[key] = read_string()
                elif type_byte == 2:  # Int32
                    val = struct.unpack('<I', data[pos:pos + 4])[0]
                    pos += 4
                    res[key] = val
                elif type_byte == 7:  # Int64
                    val = struct.unpack('<Q', data[pos:pos + 8])[0]
                    pos += 8
                    res[key] = val
                else:
                    # Unknown type, break to avoid infinite loop
                    break
            return res

        return parse_dict()

    @staticmethod
    def serialize(data: Dict[str, Any]) -> bytes:
        out = bytearray()

        def write_string(s: str) -> None:
            out.extend(str(s).encode('utf-8', errors='ignore'))
            out.append(0)

        def write_dict(d: Dict[str, Any]) -> None:
            for k, v in d.items():
                if isinstance(v, dict):
                    out.append(0)
                    write_string(k)
                    write_dict(v)
                elif isinstance(v, str):
                    out.append(1)
                    write_string(k)
                    write_string(v)
                elif isinstance(v, int):
                    if v > 0xFFFFFFFF or v < -0x80000000:
                        out.append(7)
                        write_string(k)
                        out.extend(struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF))
                    else:
                        out.append(2)
                        write_string(k)
                        out.extend(struct.pack('<I', v & 0xFFFFFFFF))
                elif isinstance(v, bool):
                    out.append(2)
                    write_string(k)
                    out.extend(struct.pack('<I', 1 if v else 0))
            out.append(8)

        write_dict(data)
        return bytes(out)


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
        if os.path.exists(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Parse paths from libraryfolders.vdf
                paths = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                for p in paths:
                    norm = os.path.normpath(p)
                    if norm not in libraries and os.path.exists(norm):
                        libraries.append(norm)
            except Exception as e:
                print(f"[Steam] Error reading libraryfolders.vdf: {e}")

        return libraries

    _avatar_cache: Dict[str, str] = {}

    def get_account_avatar(self, steamid64: str) -> Optional[str]:
        """Fetches high-resolution avatar URL for a SteamID64 via Steam Community XML."""
        if not steamid64 or not str(steamid64).isdigit():
            return None
        sid = str(steamid64).strip()
        if sid in SteamManager._avatar_cache:
            return SteamManager._avatar_cache[sid]

        try:
            import urllib.request
            url = f"https://steamcommunity.com/profiles/{sid}/?xml=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = resp.read().decode('utf-8', errors='ignore')
            m = re.search(r'<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>', data) or \
                re.search(r'<avatarMedium><!\[CDATA\[(.*?)\]\]></avatarMedium>', data) or \
                re.search(r'<avatarIcon><!\[CDATA\[(.*?)\]\]></avatarIcon>', data)
            if m and m.group(1):
                avatar_url = m.group(1).strip()
                SteamManager._avatar_cache[sid] = avatar_url
                return avatar_url
        except Exception:
            pass
        return None

    def get_user_accounts(self) -> List[Dict[str, Any]]:
        """Discovers all Steam user accounts from loginusers.vdf and userdata directory."""
        accounts = []
        if not self.steam_path:
            return accounts

        seen_acc_ids = set()
        loginusers_path = os.path.join(self.steam_path, "config", "loginusers.vdf")

        if os.path.exists(loginusers_path):
            try:
                with open(loginusers_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Parse each block: "76561198964500765" { ... }
                user_blocks = re.findall(r'"(\d{15,20})"\s*\{([^}]+)\}', content, re.DOTALL)
                for sid64, block in user_blocks:
                    acc32 = str(int(sid64) & 0xFFFFFFFF) if sid64.isdigit() else sid64
                    seen_acc_ids.add(acc32)

                    persona_m = re.search(r'"PersonaName"\s+"([^"]*)"', block, re.IGNORECASE)
                    account_m = re.search(r'"AccountName"\s+"([^"]*)"', block, re.IGNORECASE)
                    most_recent_m = re.search(r'"MostRecent"\s+"([^"]*)"', block, re.IGNORECASE)
                    auto_login_m = re.search(r'"AutoLogin"\s+"([^"]*)"', block, re.IGNORECASE)

                    persona_name = persona_m.group(1) if persona_m else (account_m.group(1) if account_m else acc32)
                    account_name = account_m.group(1) if account_m else ""
                    is_recent = (most_recent_m and most_recent_m.group(1) == "1") or (auto_login_m and auto_login_m.group(1) == "1")

                    shortcuts_vdf = os.path.join(self.steam_path, "userdata", acc32, "config", "shortcuts.vdf")
                    has_shortcuts = os.path.exists(shortcuts_vdf)
                    shortcuts_count = 0
                    if has_shortcuts:
                        try:
                            with open(shortcuts_vdf, "rb") as sf:
                                sc_dict = BinaryVDF.parse(sf.read()).get("shortcuts", {})
                                shortcuts_count = len(sc_dict)
                        except Exception:
                            pass

                    # Fetch avatar
                    avatar_url = self.get_account_avatar(sid64) if (is_recent or len(accounts) < 3) else None

                    accounts.append({
                        "steamid64": sid64,
                        "account_id": acc32,
                        "persona_name": persona_name,
                        "account_name": account_name,
                        "avatar_url": avatar_url,
                        "most_recent": bool(is_recent),
                        "has_shortcuts_vdf": has_shortcuts,
                        "shortcuts_count": shortcuts_count
                    })
            except Exception as e:
                print(f"[Steam] Error parsing loginusers.vdf: {e}")

        # Check any additional userdata folders
        userdata_dir = os.path.join(self.steam_path, "userdata")
        if os.path.exists(userdata_dir):
            try:
                for entry in os.listdir(userdata_dir):
                    if entry.isdigit() and entry not in seen_acc_ids and entry != "0":
                        sc_vdf = os.path.join(userdata_dir, entry, "config", "shortcuts.vdf")
                        sc_count = 0
                        if os.path.exists(sc_vdf):
                            try:
                                with open(sc_vdf, "rb") as sf:
                                    sc_dict = BinaryVDF.parse(sf.read()).get("shortcuts", {})
                                    sc_count = len(sc_dict)
                            except Exception:
                                pass
                        accounts.append({
                            "steamid64": "",
                            "account_id": entry,
                            "persona_name": f"Account {entry}",
                            "account_name": "",
                            "avatar_url": None,
                            "most_recent": False,
                            "has_shortcuts_vdf": os.path.exists(sc_vdf),
                            "shortcuts_count": sc_count
                        })
            except Exception:
                pass

        # Sort accounts: Most recent first, then by shortcuts count
        accounts.sort(key=lambda a: (a.get("most_recent", False), a.get("shortcuts_count", 0)), reverse=True)
        return accounts

    def get_active_account_id(self, configured_id: Optional[str] = None) -> Optional[str]:
        """Resolves the active Steam account ID."""
        accounts = self.get_user_accounts()
        if not accounts:
            return configured_id or "1004235037"

        if configured_id:
            for acc in accounts:
                if acc["account_id"] == configured_id or acc["steamid64"] == configured_id:
                    return acc["account_id"]

        for acc in accounts:
            if acc.get("most_recent"):
                return acc["account_id"]

        return accounts[0]["account_id"]

    def _get_shortcuts_path(self, account_id: Optional[str] = None) -> Optional[str]:
        if not self.steam_path:
            return None
        acc_id = account_id or self.get_active_account_id()
        if not acc_id:
            return None
        return os.path.join(self.steam_path, "userdata", str(acc_id), "config", "shortcuts.vdf")

    @staticmethod
    def calculate_appid(exe_path: str, app_name: str) -> int:
        """Calculates standard Steam non-Steam game AppID."""
        key = f"{exe_path}{app_name}".encode('utf-8')
        crc = zlib.crc32(key)
        appid = (crc | 0x80000000) & 0xFFFFFFFF
        return appid

    @staticmethod
    def calculate_shortcut_id(appid: int) -> int:
        """Calculates 64-bit Steam shortcut ID for steam://rungameid/<id>."""
        return (int(appid) << 32) | 0x02000000

    @staticmethod
    def _clean_str(s: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

    def get_shortcuts(
        self,
        account_id: Optional[str] = None,
        fanta_games: Optional[Dict[str, Any]] = None,
        db_games: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """Loads all non-Steam shortcuts for the active or given Steam account, enriched with strict Fanta metadata."""
        shortcuts_list: List[Dict[str, Any]] = []
        path = self._get_shortcuts_path(account_id)
        if not path or not os.path.exists(path):
            return shortcuts_list

        clean_fanta: Dict[str, Dict[str, Any]] = {}
        if fanta_games and isinstance(fanta_games, dict):
            for k, v in fanta_games.items():
                if isinstance(v, dict):
                    clean_fanta[k] = v

        db_titles: Dict[str, Any] = {}
        if db_games and isinstance(db_games, list):
            for g in db_games:
                title = getattr(g, 'title', '') if hasattr(g, 'title') else (g.get('title', '') if isinstance(g, dict) else '')
                if title:
                    db_titles[self._clean_str(title)] = g

        generic_roots = {"c:", "d:", "e:", "c:\\", "d:\\", "e:\\", "c:\\games", "d:\\games", "d:\\games2", "e:\\games"}

        try:
            with open(path, "rb") as f:
                data = BinaryVDF.parse(f.read())

            shortcuts_dict = data.get("shortcuts", {})
            for idx, (key, s) in enumerate(shortcuts_dict.items()):
                if not isinstance(s, dict):
                    continue
                app_name = str(s.get("AppName") or s.get("appname") or "").strip()
                exe = str(s.get("Exe") or s.get("exe") or "").strip()
                clean_exe = exe.strip('"')
                appid = s.get("appid")
                if appid is None or appid == 0:
                    appid = self.calculate_appid(clean_exe, app_name)

                short_id_64 = self.calculate_shortcut_id(appid)
                steam_url = f"steam://rungameid/{short_id_64}"
                exists_on_disk = os.path.exists(clean_exe) if clean_exe else False
                tags = list(s.get("tags", {}).values()) if isinstance(s.get("tags"), dict) else []
                devkit_id = str(s.get("DevkitGameID", "")).strip()

                # Determine if this shortcut is from Fanta / OnlineFix
                is_fanta = False
                fanta_matched_title = ""
                fanta_thumbnail = ""
                fanta_version = ""

                # 1. Check explicit tags or DevkitGameID (injected by Fanta / OnlineFix)
                if devkit_id == "FantaOFME" or any(t.lower() in ["online-fix", "onlinefix", "fanta", "fanta ofme"] for t in tags):
                    is_fanta = True

                name_clean = self._clean_str(app_name)

                # 2. Check explicit steam_url recorded in Fanta installed games (Data.json)
                for fk, fv in clean_fanta.items():
                    db_steam_url = str(fv.get("steam_url", "")).strip()
                    if db_steam_url and (db_steam_url == steam_url or str(appid) in db_steam_url):
                        is_fanta = True
                        fanta_matched_title = fk
                        fanta_thumbnail = fv.get("thumbnail", "")
                        fanta_version = fv.get("version", "")
                        break

                # 3. Check location match or exact title match against installed games (Data.json) or OFME Database
                if not is_fanta:
                    norm_exe = os.path.normpath(clean_exe).lower() if clean_exe else ""
                    exe_dir = os.path.dirname(norm_exe) if norm_exe else ""

                    for fk, fv in clean_fanta.items():
                        fk_clean = self._clean_str(fk)
                        loc = os.path.normpath(fv.get("location", "")).lower() if fv.get("location") else ""

                        # Match by installed game folder location (e.g. D:\GAMES2\PEAK)
                        if loc and loc not in generic_roots:
                            if norm_exe == loc or norm_exe.startswith(loc + "\\") or exe_dir == loc or exe_dir.startswith(loc + "\\"):
                                is_fanta = True
                                fanta_matched_title = fk
                                fanta_thumbnail = fv.get("thumbnail", "")
                                fanta_version = fv.get("version", "")
                                break

                        # Strict exact title match
                        if fk_clean and (fk_clean == name_clean or app_name.strip().lower() == fk.strip().lower()):
                            is_fanta = True
                            fanta_matched_title = fk
                            fanta_thumbnail = fv.get("thumbnail", "")
                            fanta_version = fv.get("version", "")
                            break

                    if not is_fanta and db_titles and name_clean in db_titles:
                        is_fanta = True
                        g_obj = db_titles[name_clean]
                        fanta_matched_title = getattr(g_obj, 'title', '') if hasattr(g_obj, 'title') else g_obj.get('title', '')
                        fanta_thumbnail = getattr(g_obj, 'thumbnail', '') if hasattr(g_obj, 'thumbnail') else g_obj.get('thumbnail', '')
                        fanta_version = getattr(g_obj, 'version', '') if hasattr(g_obj, 'version') else g_obj.get('version', '')

                # 4. If matched, ensure thumbnail/version are populated if still missing
                if is_fanta and not fanta_thumbnail:
                    for fk, fv in clean_fanta.items():
                        if self._clean_str(fk) == name_clean:
                            fanta_matched_title = fk
                            fanta_thumbnail = fv.get("thumbnail", "")
                            fanta_version = fv.get("version", "")
                            break

                    if not fanta_thumbnail and db_titles and name_clean in db_titles:
                        g_obj = db_titles[name_clean]
                        fanta_matched_title = getattr(g_obj, 'title', '') if hasattr(g_obj, 'title') else g_obj.get('title', '')
                        fanta_thumbnail = getattr(g_obj, 'thumbnail', '') if hasattr(g_obj, 'thumbnail') else g_obj.get('thumbnail', '')
                        fanta_version = getattr(g_obj, 'version', '') if hasattr(g_obj, 'version') else g_obj.get('version', '')

                shortcuts_list.append({
                    "index": idx,
                    "key": key,
                    "name": app_name,
                    "exe": clean_exe,
                    "raw_exe": exe,
                    "start_dir": str(s.get("StartDir") or s.get("startdir") or "").strip('"'),
                    "icon": str(s.get("icon") or s.get("Icon") or ""),
                    "launch_options": str(s.get("LaunchOptions") or ""),
                    "appid": appid,
                    "shortcut_id": str(short_id_64),
                    "steam_url": steam_url,
                    "exists_on_disk": exists_on_disk,
                    "tags": tags,
                    "is_fanta": is_fanta,
                    "fanta_title": fanta_matched_title,
                    "fanta_thumbnail": fanta_thumbnail,
                    "fanta_version": fanta_version
                })
        except Exception as e:
            print(f"[Steam] Error reading shortcuts.vdf ({path}): {e}")

        return shortcuts_list

    def add_non_steam_game(
        self,
        name: str,
        exe_path: str,
        start_dir: str = "",
        icon_path: str = "",
        launch_options: str = "",
        tags: Optional[List[str]] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Injects or updates a non-Steam shortcut into shortcuts.vdf."""
        path = self._get_shortcuts_path(account_id)
        if not path:
            return {"success": False, "error": "Steam userdata directory not found"}

        clean_exe = os.path.normpath(exe_path.strip('"'))
        quoted_exe = f'"{clean_exe}"'
        clean_start_dir = start_dir.strip('"') if start_dir else os.path.dirname(clean_exe)
        quoted_start_dir = f'"{clean_start_dir}"'
        clean_icon = icon_path.strip('"') if icon_path else clean_exe

        appid = self.calculate_appid(clean_exe, name)
        short_id_64 = self.calculate_shortcut_id(appid)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        current_data = {"shortcuts": {}}

        if os.path.exists(path):
            try:
                # Backup before edit
                shutil.copy2(path, path + ".bak")
                with open(path, "rb") as f:
                    current_data = BinaryVDF.parse(f.read())
            except Exception as e:
                print(f"[Steam] Warning reading shortcuts.vdf: {e}")

        shortcuts_dict = current_data.setdefault("shortcuts", {})

        # Find existing index or append
        target_idx = None
        for k, v in shortcuts_dict.items():
            if isinstance(v, dict):
                v_name = str(v.get("AppName", "")).strip().lower()
                v_exe = str(v.get("Exe", "")).strip('"').lower()
                if v_name == name.lower() or v_exe == clean_exe.lower() or v.get("appid") == appid:
                    target_idx = k
                    break

        if target_idx is None:
            target_idx = str(len(shortcuts_dict))

        tags_list = tags or ["Online-Fix", "Fanta"]
        if "Online-Fix" not in tags_list and "OnlineFix" not in tags_list:
            tags_list.append("Online-Fix")
        if "Fanta" not in tags_list:
            tags_list.append("Fanta")

        tags_dict = {str(i): t for i, t in enumerate(tags_list)}

        shortcuts_dict[target_idx] = {
            "appid": int(appid),
            "AppName": name,
            "Exe": quoted_exe,
            "StartDir": quoted_start_dir,
            "icon": clean_icon,
            "ShortcutPath": "",
            "LaunchOptions": launch_options or "",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "FantaOFME",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "tags": tags_dict
        }

        try:
            serialized = BinaryVDF.serialize(current_data)
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(serialized)
            if os.path.exists(path):
                try: os.remove(path)
                except Exception: pass
            os.replace(tmp_path, path)

            print(f"[Steam] Successfully injected shortcut '{name}' (AppID: {appid}) into {path}")
            return {
                "success": True,
                "name": name,
                "appid": appid,
                "shortcut_id": str(short_id_64),
                "steam_url": f"steam://rungameid/{short_id_64}",
                "message": f"Added '{name}' to Steam shortcuts."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to save shortcuts.vdf: {e}"}

    def delete_shortcut(
        self,
        identifier: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deletes a shortcut from shortcuts.vdf by AppID, Shortcut ID, or Game Name."""
        path = self._get_shortcuts_path(account_id)
        if not path or not os.path.exists(path):
            return {"success": False, "error": "shortcuts.vdf not found"}

        try:
            # Backup before edit
            shutil.copy2(path, path + ".bak")
            with open(path, "rb") as f:
                current_data = BinaryVDF.parse(f.read())

            shortcuts_dict = current_data.get("shortcuts", {})
            new_shortcuts = {}
            deleted_name = None
            deleted_appid = None

            ident_str = str(identifier).strip().lower()

            cur_idx = 0
            for k, v in shortcuts_dict.items():
                if not isinstance(v, dict):
                    continue
                v_name = str(v.get("AppName", "")).strip()
                v_appid = str(v.get("appid", ""))
                v_exe = str(v.get("Exe", "")).strip('"')
                v_short_64 = str(self.calculate_shortcut_id(int(v_appid))) if v_appid.isdigit() else ""

                if (
                    ident_str == v_name.lower() or
                    ident_str == v_appid or
                    ident_str == v_short_64 or
                    ident_str == v_exe.lower() or
                    ident_str == str(k)
                ):
                    deleted_name = v_name
                    deleted_appid = v_appid
                    print(f"[Steam] Removing shortcut '{v_name}' (AppID: {v_appid}) from shortcuts.vdf")
                    continue

                new_shortcuts[str(cur_idx)] = v
                cur_idx += 1

            if deleted_name is None:
                return {"success": False, "error": f"Shortcut '{identifier}' not found"}

            current_data["shortcuts"] = new_shortcuts
            serialized = BinaryVDF.serialize(current_data)
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(serialized)
            if os.path.exists(path):
                try: os.remove(path)
                except Exception: pass
            os.replace(tmp_path, path)

            print(f"[Steam] Successfully saved shortcuts.vdf with {len(new_shortcuts)} items.")
            return {
                "success": True,
                "deleted_name": deleted_name,
                "deleted_appid": deleted_appid,
                "remaining_count": len(new_shortcuts),
                "message": f"Removed '{deleted_name}' from Steam."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to delete shortcut: {e}"}

    def get_installed_games(self) -> List[Dict[str, Any]]:
        games = []
        for lib in self.libraries:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.exists(steamapps):
                continue
            for item in os.listdir(steamapps):
                if item.startswith("appmanifest_") and item.endswith(".acf"):
                    acf_path = os.path.join(steamapps, item)
                    try:
                        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        appid_m = re.search(r'"appid"\s+"([^"]+)"', content)
                        name_m = re.search(r'"name"\s+"([^"]+)"', content)
                        install_m = re.search(r'"installdir"\s+"([^"]+)"', content)
                        size_m = re.search(r'"SizeOnDisk"\s+"([^"]+)"', content)

                        if appid_m and name_m:
                            appid = appid_m.group(1)
                            name = name_m.group(1)
                            installdir = install_m.group(1) if install_m else ""
                            full_install_path = os.path.join(steamapps, "common", installdir) if installdir else ""
                            games.append({
                                "appid": appid,
                                "name": name,
                                "install_dir": full_install_path,
                                "library_path": lib,
                                "size_bytes": int(size_m.group(1)) if size_m else 0
                            })
                    except Exception:
                        continue
        return games
