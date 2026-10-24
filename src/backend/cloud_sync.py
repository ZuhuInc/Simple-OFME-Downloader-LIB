"""
Cloud Sync Manager for Fanta OFME Downloader
Supports:
1. Google Drive REST API (Direct online OAuth2 sync without desktop client)
2. Local Cloud Folder sync (Google Drive Desktop "My Drive", OneDrive, Dropbox)
3. Auto-detection of Online-Fix / Goldberg SteamEmu / Unreal / Unity save games
4. Automatic and manual cross-PC save synchronization with safe local rollbacks
"""

import os
import sys
import re
import json
import time
import zipfile
import shutil
import tempfile
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import requests


# Default Desktop OAuth 2.0 Credentials (can be overridden in config)
DEFAULT_GDRIVE_CLIENT_ID = os.environ.get("FANTA_GDRIVE_CLIENT_ID", "")
DEFAULT_GDRIVE_CLIENT_SECRET = os.environ.get("FANTA_GDRIVE_CLIENT_SECRET", "")
GDRIVE_FOLDER_NAME = "Fanta OFME Cloud Saves"


class CloudSyncManager:
    def __init__(self, data_folder: Optional[str] = None, config: Optional[Any] = None):
        self.data_folder = data_folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.data_folder, exist_ok=True)
        self.config_file = os.path.join(self.data_folder, "CloudSync.json")
        self.config_ref = config
        self.settings: Dict[str, Any] = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        defaults = {
            "provider": "gdrive_api",  # 'gdrive_api' or 'local_folder'
            "auto_sync": False,
            "local_cloud_path": self._detect_default_cloud_folder(),
            "google_tokens": {},
            "custom_save_paths": {},
            "last_synced": {}
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[CloudSync] Error loading {self.config_file}: {e}", flush=True)
        return defaults

    def save_settings(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"[CloudSync] Error saving {self.config_file}: {e}", flush=True)

    def is_auto_sync_enabled(self) -> bool:
        return bool(self.settings.get("auto_sync", False))

    def get_provider(self) -> str:
        return self.settings.get("provider", "gdrive_api")

    # ──────────────────────────────────────────────────────────────────────────
    # Save Path Auto-Detection
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_default_cloud_folder() -> str:
        """Detects standard local cloud drive folders on Windows."""
        home = os.path.expanduser("~")
        candidates = [
            r"G:\My Drive\Fanta OFME Cloud Saves",
            os.path.join(home, "Google Drive", "Fanta OFME Cloud Saves"),
            os.path.join(home, "OneDrive", "Fanta OFME Cloud Saves"),
            os.path.join(home, "Dropbox", "Fanta OFME Cloud Saves"),
            os.path.join(home, "Documents", "Fanta OFME Cloud Saves")
        ]
        for c in candidates:
            parent = os.path.dirname(c)
            if os.path.exists(parent):
                return c
        return candidates[0]

    def detect_save_path(self, title: str, game_location: Optional[str] = None, app_id: Optional[Any] = None) -> Tuple[Optional[str], str]:
        """
        Auto-detects save folder for a game based on Goldberg SteamEmu, Unreal, Unity, or internal save folder.
        Returns (save_path_or_none, detection_type).
        """
        clean_title = (title or "").strip()
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', clean_title).lower()

        # 1. Check custom path saved in CloudSync.json or config
        custom = self.settings.get("custom_save_paths", {}).get(clean_title)
        if custom and os.path.exists(custom):
            return custom, "Custom"

        # 2. Extract Steam AppID from game directory if available
        detected_app_id = str(app_id) if app_id else None
        if not detected_app_id and game_location and os.path.isdir(game_location):
            detected_app_id = self._find_steam_appid_in_dir(game_location)

        # 3. Check Goldberg SteamEmu Saves (%AppData%\Goldberg SteamEmu Saves\<AppID>)
        appdata = os.environ.get("APPDATA")
        if appdata:
            goldberg_base = os.path.join(appdata, "Goldberg SteamEmu Saves")
            if os.path.isdir(goldberg_base):
                if detected_app_id:
                    appid_path = os.path.join(goldberg_base, str(detected_app_id))
                    if os.path.isdir(appid_path):
                        return appid_path, "Goldberg SteamEmu"

                # Check recent Goldberg subfolders or title matching
                try:
                    for sub in os.listdir(goldberg_base):
                        sub_path = os.path.join(goldberg_base, sub)
                        if os.path.isdir(sub_path):
                            if norm_title in sub.lower() or sub.lower() in norm_title:
                                return sub_path, "Goldberg SteamEmu"
                except Exception:
                    pass

            # Check %AppData%\OnlineFix\<AppID>
            of_base = os.path.join(appdata, "OnlineFix")
            if os.path.isdir(of_base):
                if detected_app_id:
                    of_appid = os.path.join(of_base, str(detected_app_id))
                    if os.path.isdir(of_appid):
                        return of_appid, "OnlineFix"

        # 4. Check Unreal Engine Saves (%LocalAppData%\<GameTitle>\Saved\SaveGames)
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            try:
                for entry in os.listdir(localappdata):
                    entry_norm = re.sub(r'[^a-zA-Z0-9]', '', entry).lower()
                    if entry_norm and (entry_norm == norm_title or entry.lower() == clean_title.lower()):
                        saved_path = os.path.join(localappdata, entry, "Saved", "SaveGames")
                        if os.path.isdir(saved_path):
                            return saved_path, "Unreal Engine"
                        cand_saved = os.path.join(localappdata, entry, "Saved")
                        if os.path.isdir(cand_saved):
                            return cand_saved, "Unreal Engine"
            except Exception:
                pass

        # 5. Check Unity Saves (%UserProfile%\AppData\LocalLow\<Company>\<GameTitle>)
        userprofile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        locallow = os.path.join(userprofile, "AppData", "LocalLow")
        if os.path.isdir(locallow):
            try:
                for company in os.listdir(locallow):
                    comp_path = os.path.join(locallow, company)
                    if os.path.isdir(comp_path):
                        for g in os.listdir(comp_path):
                            g_norm = re.sub(r'[^a-zA-Z0-9]', '', g).lower()
                            if g_norm and (g_norm == norm_title or g.lower() == clean_title.lower()):
                                return os.path.join(comp_path, g), "Unity LocalLow"
            except Exception:
                pass

        # 6. Check Game Directory saves (<GameLocation>\save or saves or profile)
        if game_location and os.path.isdir(game_location):
            for candidate_name in ["save", "saves", "SaveGames", "Profile", "user_data", "userdata"]:
                cand_path = os.path.join(game_location, candidate_name)
                if os.path.isdir(cand_path):
                    return cand_path, "Game Folder"

        # 7. Check Documents / Saved Games
        docs = os.path.join(userprofile, "Documents", "My Games")
        if os.path.isdir(docs):
            try:
                for entry in os.listdir(docs):
                    entry_norm = re.sub(r'[^a-zA-Z0-9]', '', entry).lower()
                    if entry_norm and (entry_norm == norm_title or entry.lower() == clean_title.lower()):
                        return os.path.join(docs, entry), "Documents My Games"
            except Exception:
                pass

        saved_games = os.path.join(userprofile, "Saved Games")
        if os.path.isdir(saved_games):
            try:
                for entry in os.listdir(saved_games):
                    entry_norm = re.sub(r'[^a-zA-Z0-9]', '', entry).lower()
                    if entry_norm and (entry_norm == norm_title or entry.lower() == clean_title.lower()):
                        return os.path.join(saved_games, entry), "Saved Games"
            except Exception:
                pass

        return None, "Not Found"

    @staticmethod
    def _find_steam_appid_in_dir(game_dir: str) -> Optional[str]:
        """Finds steam_appid.txt inside game directory."""
        try:
            for root, dirs, files in os.walk(game_dir):
                depth = len(os.path.normpath(root).split(os.sep)) - len(os.path.normpath(game_dir).split(os.sep))
                if depth > 4:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower() in ("steam_appid.txt", "app_id.txt", "appid.txt"):
                        full_p = os.path.join(root, f)
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                            val = fh.read().strip()
                            if val.isdigit() and len(val) >= 3:
                                return val
        except Exception:
            pass
        return None

    @staticmethod
    def get_folder_info(folder_path: Optional[str]) -> Dict[str, Any]:
        """Returns size in bytes and last modified timestamp for a folder."""
        if not folder_path or not os.path.exists(folder_path):
            return {"exists": False, "size_bytes": 0, "mtime": None, "mtime_str": "None", "file_count": 0}

        total_size = 0
        latest_mtime = 0
        file_count = 0

        if os.path.isfile(folder_path):
            stat = os.stat(folder_path)
            total_size = stat.st_size
            latest_mtime = stat.st_mtime
            file_count = 1
        else:
            for root, _, files in os.walk(folder_path):
                for f in files:
                    p = os.path.join(root, f)
                    try:
                        st = os.stat(p)
                        total_size += st.st_size
                        if st.st_mtime > latest_mtime:
                            latest_mtime = st.st_mtime
                        file_count += 1
                    except Exception:
                        continue

        mtime_str = datetime.fromtimestamp(latest_mtime).strftime("%b %d, %Y • %I:%M %p") if latest_mtime > 0 else "Never"
        return {
            "exists": True,
            "size_bytes": total_size,
            "mtime": latest_mtime,
            "mtime_str": mtime_str,
            "file_count": file_count
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Local Zipping & Restoring (with Safe Rollback)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def archive_save_folder(source_folder: str, target_zip: str) -> bool:
        """Zips source folder contents into target_zip."""
        if not os.path.exists(source_folder):
            return False
        os.makedirs(os.path.dirname(os.path.abspath(target_zip)), exist_ok=True)
        with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.isfile(source_folder):
                zf.write(source_folder, os.path.basename(source_folder))
            else:
                for root, _, files in os.walk(source_folder):
                    for f in files:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.relpath(full_p, source_folder)
                        zf.write(full_p, rel_p)
        return True

    @staticmethod
    def extract_save_zip(zip_path: str, target_folder: str) -> bool:
        """Extracts save zip into target_folder, first taking a safety rollback."""
        if not os.path.exists(zip_path):
            return False

        # Safety rollback if folder already exists with data
        if os.path.exists(target_folder) and os.listdir(target_folder):
            rollback_dir = os.path.join(os.path.expanduser("~"), "Documents", "Fanta_Save_Rollbacks")
            os.makedirs(rollback_dir, exist_ok=True)
            ts = int(time.time())
            folder_name = os.path.basename(os.path.normpath(target_folder))
            rollback_zip = os.path.join(rollback_dir, f"{folder_name}_rollback_{ts}.zip")
            try:
                CloudSyncManager.archive_save_folder(target_folder, rollback_zip)
                print(f"[CloudSync] Created safety rollback before restore at: {rollback_zip}", flush=True)
            except Exception as e:
                print(f"[CloudSync] Rollback creation warning: {e}", flush=True)

        os.makedirs(target_folder, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_folder)
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Google Drive REST API Integration (OAuth2 & Sync)
    # ──────────────────────────────────────────────────────────────────────────

    def get_oauth_auth_url(self, client_id: Optional[str] = None, redirect_uri: Optional[str] = None) -> str:
        """Generates Google OAuth 2.0 authorization URL."""
        cid = client_id or self.settings.get("gdrive_client_id") or DEFAULT_GDRIVE_CLIENT_ID
        r_uri = redirect_uri or "http://localhost:5004/api/cloud/oauth_callback"
        scope = "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email"
        params = {
            "client_id": cid,
            "redirect_uri": r_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent"
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    def exchange_oauth_code(self, code: str, client_id: Optional[str] = None, client_secret: Optional[str] = None, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges authorization code for refresh & access tokens."""
        cid = client_id or self.settings.get("gdrive_client_id") or DEFAULT_GDRIVE_CLIENT_ID
        csecret = client_secret or self.settings.get("gdrive_client_secret") or DEFAULT_GDRIVE_CLIENT_SECRET
        r_uri = redirect_uri or "http://localhost:5004/api/cloud/oauth_callback"

        data = {
            "code": code,
            "client_id": cid,
            "client_secret": csecret,
            "redirect_uri": r_uri,
            "grant_type": "authorization_code"
        }
        resp = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=15)
        if resp.status_code != 200:
            return {"success": False, "error": f"Token exchange failed: {resp.text}"}

        token_data = resp.json()
        token_data["created_at"] = time.time()

        # Fetch user email to display in UI
        access_token = token_data.get("access_token")
        email = "Connected Google Account"
        if access_token:
            try:
                u_resp = requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10
                )
                if u_resp.status_code == 200:
                    email = u_resp.json().get("email", email)
            except Exception:
                pass

        token_data["email"] = email
        self.settings["google_tokens"] = token_data
        self.settings["provider"] = "gdrive_api"
        self.save_settings()
        return {"success": True, "email": email}

    def _get_valid_access_token(self) -> Optional[str]:
        """Returns valid access token, auto-refreshing if expired."""
        tokens = self.settings.get("google_tokens", {})
        if not tokens:
            return None

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        created_at = tokens.get("created_at", 0)
        expires_in = tokens.get("expires_in", 3600)

        # If token is still valid with 2-minute margin
        if access_token and (time.time() < (created_at + expires_in - 120)):
            return access_token

        if not refresh_token:
            return access_token

        # Refresh token
        cid = self.settings.get("gdrive_client_id") or DEFAULT_GDRIVE_CLIENT_ID
        csecret = self.settings.get("gdrive_client_secret") or DEFAULT_GDRIVE_CLIENT_SECRET
        data = {
            "client_id": cid,
            "client_secret": csecret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        try:
            resp = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=15)
            if resp.status_code == 200:
                new_tokens = resp.json()
                tokens["access_token"] = new_tokens.get("access_token", access_token)
                tokens["expires_in"] = new_tokens.get("expires_in", 3600)
                tokens["created_at"] = time.time()
                self.settings["google_tokens"] = tokens
                self.save_settings()
                return tokens["access_token"]
        except Exception as e:
            print(f"[CloudSync] Token refresh error: {e}", flush=True)

        return access_token

    def is_gdrive_connected(self) -> bool:
        return bool(self.settings.get("google_tokens", {}).get("access_token"))

    def has_gdrive_credentials(self) -> bool:
        cid = (self.settings.get("gdrive_client_id") or DEFAULT_GDRIVE_CLIENT_ID or "").strip()
        if not cid or "dummy" in cid.lower() or "placeholder" in cid.lower() or cid == "484196144885-t6o304jkv7k2u08vj7f72m829p8r8c3k.apps.googleusercontent.com":
            return False
        return True

    def disconnect_gdrive(self):
        self.settings["google_tokens"] = {}
        self.save_settings()

    def _get_or_create_gdrive_folder(self) -> Optional[str]:
        """Finds or creates 'Fanta OFME Cloud Saves' folder in user's Google Drive."""
        token = self._get_valid_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        query = f"name = '{GDRIVE_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        try:
            resp = requests.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={"q": query, "spaces": "drive", "fields": "files(id, name)"},
                timeout=15
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    return files[0]["id"]

            # Create folder if not found
            create_resp = requests.post(
                "https://www.googleapis.com/drive/v3/files",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": GDRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
                timeout=15
            )
            if create_resp.status_code in (200, 201):
                return create_resp.json().get("id")
        except Exception as e:
            print(f"[CloudSync] Error getting/creating root Google Drive folder: {e}", flush=True)
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Unified Cloud Operations (Google Drive API + Local My Drive Folder)
    # ──────────────────────────────────────────────────────────────────────────

    def list_all_cloud_saves(self) -> Dict[str, Any]:
        """Pre-indexes all saves available in cloud storage (local folder or Google Drive) in one operation."""
        provider = self.get_provider()
        index = {}

        if provider == "local_folder":
            base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
            if os.path.isdir(base_dir):
                try:
                    for game_folder in os.listdir(base_dir):
                        folder_path = os.path.join(base_dir, game_folder)
                        if os.path.isdir(folder_path):
                            zip_path = os.path.join(folder_path, f"{game_folder}_save.zip")
                            if os.path.exists(zip_path):
                                st = os.stat(zip_path)
                                mtime = st.st_mtime
                                meta_path = os.path.join(folder_path, "metadata.json")
                                if os.path.exists(meta_path):
                                    try:
                                        with open(meta_path, "r", encoding="utf-8") as mf:
                                            m_data = json.load(mf)
                                            mtime = m_data.get("mtime", mtime)
                                    except Exception:
                                        pass
                                index[game_folder] = {
                                    "exists": True,
                                    "provider": "local_folder",
                                    "size_bytes": st.st_size,
                                    "mtime": mtime,
                                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p"),
                                    "path": zip_path
                                }
                except Exception as e:
                    print(f"[CloudSync] Error scanning local cloud directory: {e}", flush=True)

        else:
            token = self._get_valid_access_token()
            if token:
                folder_id = self._get_or_create_gdrive_folder()
                if folder_id:
                    headers = {"Authorization": f"Bearer {token}"}
                    query = f"'{folder_id}' in parents and trashed = false"
                    try:
                        resp = requests.get(
                            "https://www.googleapis.com/drive/v3/files",
                            headers=headers,
                            params={"q": query, "pageSize": 1000, "fields": "files(id, name, size, modifiedTime, description)"},
                            timeout=20
                        )
                        if resp.status_code == 200:
                            files = resp.json().get("files", [])
                            for f in files:
                                fname = f.get("name", "")
                                if fname.endswith("_save.zip"):
                                    safe_name = fname[:-9]
                                    size = int(f.get("size", 0))
                                    desc = f.get("description", "")
                                    mtime = None
                                    if desc and "mtime:" in desc:
                                        try:
                                            mtime = float(desc.split("mtime:")[1].split(";")[0])
                                        except Exception:
                                            pass
                                    if not mtime:
                                        iso = f.get("modifiedTime", "")
                                        try:
                                            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                                            mtime = dt.timestamp()
                                        except Exception:
                                            mtime = time.time()
                                    index[safe_name] = {
                                        "exists": True,
                                        "file_id": f["id"],
                                        "provider": "gdrive_api",
                                        "size_bytes": size,
                                        "mtime": mtime,
                                        "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p")
                                    }
                    except Exception as e:
                        print(f"[CloudSync] Error indexing Google Drive files: {e}", flush=True)

        return index

    def get_cloud_save_info(self, title: str, cloud_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inspects cloud save for given game under the active provider."""
        provider = self.get_provider()
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', title).strip()

        if cloud_index is not None:
            if safe_name in cloud_index:
                return cloud_index[safe_name]
            fallback_status = "None"
            if provider == "gdrive_api" and not self.is_gdrive_connected():
                fallback_status = "Not Connected"
            return {"exists": False, "provider": provider, "size_bytes": 0, "mtime": None, "mtime_str": fallback_status}

        if provider == "local_folder":
            base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
            game_cloud_dir = os.path.join(base_dir, safe_name)
            meta_path = os.path.join(game_cloud_dir, "metadata.json")
            zip_path = os.path.join(game_cloud_dir, f"{safe_name}_save.zip")

            if os.path.exists(zip_path):
                st = os.stat(zip_path)
                mtime = st.st_mtime
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            m_data = json.load(mf)
                            mtime = m_data.get("mtime", mtime)
                    except Exception:
                        pass
                return {
                    "exists": True,
                    "provider": "local_folder",
                    "size_bytes": st.st_size,
                    "mtime": mtime,
                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p"),
                    "path": zip_path
                }
            return {"exists": False, "provider": "local_folder", "size_bytes": 0, "mtime": None, "mtime_str": "None"}

        else:
            # Google Drive API provider
            token = self._get_valid_access_token()
            if not token:
                return {"exists": False, "provider": "gdrive_api", "size_bytes": 0, "mtime": None, "mtime_str": "Not Connected"}

            folder_id = self._get_or_create_gdrive_folder()
            if not folder_id:
                return {"exists": False, "provider": "gdrive_api", "size_bytes": 0, "mtime": None, "mtime_str": "None"}

            headers = {"Authorization": f"Bearer {token}"}
            filename = f"{safe_name}_save.zip"
            query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
            try:
                resp = requests.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers=headers,
                    params={"q": query, "fields": "files(id, name, size, modifiedTime, description)"},
                    timeout=15
                )
                if resp.status_code == 200:
                    files = resp.json().get("files", [])
                    if files:
                        f = files[0]
                        size = int(f.get("size", 0))
                        desc = f.get("description", "")
                        mtime = None
                        if desc and "mtime:" in desc:
                            try:
                                mtime = float(desc.split("mtime:")[1].split(";")[0])
                            except Exception:
                                pass
                        if not mtime:
                            iso = f.get("modifiedTime", "")
                            try:
                                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                                mtime = dt.timestamp()
                            except Exception:
                                mtime = time.time()

                        return {
                            "exists": True,
                            "file_id": f["id"],
                            "provider": "gdrive_api",
                            "size_bytes": size,
                            "mtime": mtime,
                            "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p")
                        }
            except Exception as e:
                print(f"[CloudSync] Error fetching cloud save for {title}: {e}", flush=True)

            return {"exists": False, "provider": "gdrive_api", "size_bytes": 0, "mtime": None, "mtime_str": "None"}

    def backup_game(self, title: str, custom_save_path: Optional[str] = None) -> Dict[str, Any]:
        """Zips local save and uploads to active cloud provider."""
        clean_title = (title or "").strip()
        save_path = custom_save_path or self.settings.get("custom_save_paths", {}).get(clean_title)

        if not save_path or not os.path.exists(save_path):
            detected, _ = self.detect_save_path(clean_title)
            save_path = detected

        if not save_path or not os.path.exists(save_path):
            return {"success": False, "error": f"No save folder found for '{clean_title}' to backup."}

        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', clean_title).strip()
        local_info = self.get_folder_info(save_path)
        if local_info["file_count"] == 0 and local_info["size_bytes"] == 0:
            return {"success": False, "error": f"Save folder is empty for '{clean_title}'."}

        temp_dir = tempfile.mkdtemp(prefix="fanta_save_")
        zip_path = os.path.join(temp_dir, f"{safe_name}_save.zip")
        try:
            if not self.archive_save_folder(save_path, zip_path):
                return {"success": False, "error": "Failed to create save archive."}

            mtime = local_info["mtime"] or time.time()
            provider = self.get_provider()

            if provider == "local_folder":
                base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
                dest_dir = os.path.join(base_dir, safe_name)
                os.makedirs(dest_dir, exist_ok=True)
                dest_zip = os.path.join(dest_dir, f"{safe_name}_save.zip")
                shutil.copy2(zip_path, dest_zip)

                meta_file = os.path.join(dest_dir, "metadata.json")
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump({
                        "title": clean_title,
                        "mtime": mtime,
                        "size_bytes": os.path.getsize(dest_zip),
                        "backed_up_at": datetime.now().isoformat()
                    }, mf, indent=2)

                self.settings.setdefault("last_synced", {})[clean_title] = mtime
                self.save_settings()
                return {"success": True, "message": f"Successfully backed up to Local Cloud Folder ({dest_dir})", "mtime": mtime}

            else:
                token = self._get_valid_access_token()
                if not token:
                    return {"success": False, "error": "Not connected to Google Drive. Please log in first."}

                folder_id = self._get_or_create_gdrive_folder()
                if not folder_id:
                    return {"success": False, "error": "Could not locate or create 'Fanta OFME Cloud Saves' on Google Drive."}

                filename = f"{safe_name}_save.zip"
                headers = {"Authorization": f"Bearer {token}"}

                existing = self.get_cloud_save_info(clean_title)
                existing_file_id = existing.get("file_id") if existing.get("exists") else None

                metadata = {
                    "name": filename,
                    "description": f"Fanta OFME Save Backup for {clean_title};mtime:{mtime};",
                }
                if not existing_file_id:
                    metadata["parents"] = [folder_id]

                file_size = os.path.getsize(zip_path)
                with open(zip_path, "rb") as zf:
                    file_bytes = zf.read()

                boundary = "===fanta_boundary==="
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: application/zip\r\n\r\n"
                ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

                upload_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                    "Content-Length": str(len(body))
                }

                if existing_file_id:
                    url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}?uploadType=multipart"
                    resp = requests.patch(url, headers=upload_headers, data=body, timeout=45)
                else:
                    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
                    resp = requests.post(url, headers=upload_headers, data=body, timeout=45)

                if resp.status_code in (200, 201):
                    self.settings.setdefault("last_synced", {})[clean_title] = mtime
                    self.save_settings()
                    return {"success": True, "message": f"Successfully backed up {clean_title} to Google Drive!", "mtime": mtime}
                else:
                    return {"success": False, "error": f"Google Drive upload failed: {resp.status_code} {resp.text}"}

        except Exception as e:
            return {"success": False, "error": f"Backup error: {str(e)}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def restore_game(self, title: str, custom_save_path: Optional[str] = None) -> Dict[str, Any]:
        """Downloads cloud save and extracts it into the local save folder."""
        clean_title = (title or "").strip()
        save_path = custom_save_path or self.settings.get("custom_save_paths", {}).get(clean_title)

        if not save_path:
            detected, _ = self.detect_save_path(clean_title)
            save_path = detected

        if not save_path:
            return {"success": False, "error": f"No target save folder identified for '{clean_title}'. Please specify a save path first."}

        cloud_info = self.get_cloud_save_info(clean_title)
        if not cloud_info.get("exists"):
            return {"success": False, "error": f"No cloud backup exists for '{clean_title}'."}

        temp_dir = tempfile.mkdtemp(prefix="fanta_restore_")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', clean_title).strip()
        zip_target = os.path.join(temp_dir, f"{safe_name}_downloaded.zip")

        try:
            provider = self.get_provider()
            if provider == "local_folder":
                source_zip = cloud_info.get("path")
                if not source_zip or not os.path.exists(source_zip):
                    return {"success": False, "error": "Local cloud archive not found."}
                shutil.copy2(source_zip, zip_target)
            else:
                token = self._get_valid_access_token()
                if not token:
                    return {"success": False, "error": "Google Drive authentication token expired."}

                file_id = cloud_info.get("file_id")
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                    headers=headers,
                    stream=True,
                    timeout=60
                )
                if resp.status_code == 200:
                    with open(zip_target, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                else:
                    return {"success": False, "error": f"Download failed from Google Drive: {resp.status_code}"}

            if not self.extract_save_zip(zip_target, save_path):
                return {"success": False, "error": "Failed to extract save archive."}

            return {
                "success": True,
                "message": f"Successfully restored {clean_title} save files to {save_path}!"
            }

        except Exception as e:
            return {"success": False, "error": f"Restore failed: {str(e)}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def check_and_restore_newer_cloud_save(self, title: str) -> bool:
        """
        Auto-sync helper called on game launch: if cloud save has newer timestamp than local save,
        automatically restores it. Returns True if restored.
        """
        if not self.is_auto_sync_enabled():
            return False

        clean_title = (title or "").strip()
        save_path = self.settings.get("custom_save_paths", {}).get(clean_title)
        if not save_path:
            save_path, _ = self.detect_save_path(clean_title)

        if not save_path:
            return False

        local_info = self.get_folder_info(save_path)
        cloud_info = self.get_cloud_save_info(clean_title)

        if not cloud_info.get("exists") or not cloud_info.get("mtime"):
            return False

        cloud_mtime = float(cloud_info["mtime"])
        local_mtime = float(local_info.get("mtime") or 0)

        # If cloud save is newer by more than 5 seconds
        if cloud_mtime > (local_mtime + 5):
            print(f"[CloudSync] Newer cloud save detected for '{clean_title}' ({cloud_info['mtime_str']} vs local {local_info['mtime_str']}). Auto-restoring...", flush=True)
            res = self.restore_game(clean_title, save_path)
            return bool(res.get("success"))

        return False

    def get_game_sync_status(self, title: str, game_location: Optional[str] = None, app_id: Optional[Any] = None, cloud_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculates full status for a game comparing local save vs cloud save.
        Returns paths, dates, and clear sync comparison direction.
        """
        clean_title = (title or "").strip()
        save_path, detect_type = self.detect_save_path(clean_title, game_location, app_id)

        local_info = self.get_folder_info(save_path)
        cloud_info = self.get_cloud_save_info(clean_title, cloud_index=cloud_index)

        local_mtime = local_info.get("mtime")
        cloud_mtime = cloud_info.get("mtime")

        if not cloud_info.get("exists") and not local_info.get("exists"):
            state = "no_saves"
            state_label = "No Saves Detected"
        elif not cloud_info.get("exists"):
            state = "local_only"
            state_label = "Ready to Backup"
        elif not local_info.get("exists"):
            state = "cloud_only"
            state_label = "Cloud Backup Available"
        else:
            diff = abs(float(cloud_mtime or 0) - float(local_mtime or 0))
            if diff <= 5:
                state = "in_sync"
                state_label = "In Sync"
            elif float(local_mtime or 0) > float(cloud_mtime or 0):
                state = "local_newer"
                state_label = "Local Save Newer"
            else:
                state = "cloud_newer"
                state_label = "Cloud Backup Newer"

        return {
            "title": clean_title,
            "save_path": save_path,
            "detection_type": detect_type,
            "local_exists": local_info.get("exists", False),
            "local_size_bytes": local_info.get("size_bytes", 0),
            "local_mtime": local_mtime,
            "local_mtime_str": local_info.get("mtime_str", "None"),
            "cloud_exists": cloud_info.get("exists", False),
            "cloud_size_bytes": cloud_info.get("size_bytes", 0),
            "cloud_mtime": cloud_mtime,
            "cloud_mtime_str": cloud_info.get("mtime_str", "None"),
            "sync_state": state,
            "sync_state_label": state_label
        }
