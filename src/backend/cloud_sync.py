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


# Default Web OAuth 2.0 Credentials (can be overridden in config)
DEFAULT_GDRIVE_CLIENT_ID = os.environ.get(
    "FANTA_GDRIVE_CLIENT_ID",
    "63637058417-uqpmtfihh81ddo16rqng9gh5aue612be.apps.googleusercontent.com"
)
DEFAULT_GDRIVE_API_KEY = os.environ.get(
    "FANTA_GDRIVE_API_KEY",
    "AIzaSyDZ_fTrJ2q0bkh0AiLlLkQPqXwAnYE_n84"
)
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
            "provider": "gdrive_api",  # 'gdrive_api', 'local_folder', or 'self_hosted'
            "auto_sync": False,
            "local_cloud_path": self._detect_default_cloud_folder(),
            "self_hosted_url": "",
            "self_hosted_api_key": "",
            "google_tokens": {},
            "custom_save_paths": {},
            "last_synced": {},
            "auto_exclude_steam_cloud": True,
            "excluded_games": [],
            "included_override_games": []
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

    def _resolve_game_metadata(self, title: str, game_location: Optional[str] = None, app_id: Optional[Any] = None) -> Tuple[Optional[str], Optional[Any]]:
        """Resolves game_location and app_id from config.data or standard game directories when not explicitly provided."""
        clean_title = (title or "").strip()
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', clean_title).lower()

        if (not game_location or not app_id) and self.config_ref and hasattr(self.config_ref, "data"):
            installed_games = self.config_ref.data
            if isinstance(installed_games, dict):
                record = installed_games.get(clean_title.upper()) or installed_games.get(clean_title)
                if not record:
                    for k, v in installed_games.items():
                        if not isinstance(v, dict):
                            continue
                        k_clean = str(k).strip()
                        k_norm = re.sub(r'[^a-zA-Z0-9]', '', k_clean).lower()
                        if k_clean.lower() == clean_title.lower() or (norm_title and k_norm == norm_title):
                            record = v
                            break
                if isinstance(record, dict):
                    if not game_location:
                        game_location = record.get("location") or record.get("install_path")
                    if not app_id:
                        app_id = record.get("app_id") or record.get("appid")

        # If game_location points to a parent games directory containing a subfolder for this title, prefer the subfolder
        if game_location and os.path.isdir(game_location) and clean_title:
            sub_cand = os.path.join(game_location, clean_title)
            if os.path.isdir(sub_cand):
                game_location = sub_cand

        # Fallback: check configured / standard game directories if game_location is still missing
        if (not game_location or not os.path.isdir(game_location)) and clean_title:
            candidate_bases: List[str] = []
            if self.config_ref and hasattr(self.config_ref, "get"):
                for cfg_key in ("extract_path", "default_download_path", "download_path"):
                    val = self.config_ref.get(cfg_key)
                    if val and isinstance(val, str):
                        candidate_bases.append(val)
            candidate_bases.extend([r"D:\games", r"D:\Games", r"D:\GAMES2", r"C:\Games"])
            for base in candidate_bases:
                cand_dir = os.path.join(base, clean_title)
                if os.path.isdir(cand_dir):
                    game_location = cand_dir
                    break

        return game_location, app_id

    def detect_save_path(self, title: str, game_location: Optional[str] = None, app_id: Optional[Any] = None) -> Tuple[Optional[str], str]:
        """
        Auto-detects save folder for a game based on Goldberg SteamEmu, Unreal, Unity, or internal save folder.
        Returns (save_path_or_none, detection_type).
        """
        clean_title = (title or "").strip()
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', clean_title).lower()

        # 1. Check custom path saved in CloudSync.json or config (case-insensitive fallback)
        custom_paths = self.settings.get("custom_save_paths", {})
        custom = custom_paths.get(clean_title)
        if not custom and isinstance(custom_paths, dict):
            for k, v in custom_paths.items():
                if str(k).strip().lower() == clean_title.lower():
                    custom = v
                    break
        if custom and os.path.exists(custom):
            return custom, "Custom"

        # Resolve game_location and app_id from config if not provided by caller
        game_location, app_id = self._resolve_game_metadata(clean_title, game_location, app_id)

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
            try:
                rollback_dir = os.path.join(os.path.expanduser("~"), "Documents", "Fanta_Save_Rollbacks")
                os.makedirs(rollback_dir, exist_ok=True)
                ts = int(time.time())
                folder_name = os.path.basename(os.path.normpath(target_folder))
                rollback_zip = os.path.join(rollback_dir, f"{folder_name}_rollback_{ts}.zip")
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
            if created_at and (time.time() >= created_at + expires_in):
                return None
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
        tokens = self.settings.get("google_tokens", {})
        if not tokens or not tokens.get("access_token"):
            return False
        if tokens.get("refresh_token"):
            return True
        created_at = tokens.get("created_at", 0)
        expires_in = tokens.get("expires_in", 3600)
        if created_at and (time.time() >= created_at + expires_in):
            return False
        return True

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
        cached_id = self.settings.get("gdrive_folder_id")
        if cached_id:
            return cached_id

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
                timeout=25
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    folder_id = files[0]["id"]
                    self.settings["gdrive_folder_id"] = folder_id
                    self.save_settings()
                    return folder_id

            # Create folder if not found
            create_resp = requests.post(
                "https://www.googleapis.com/drive/v3/files",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": GDRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
                timeout=25
            )
            if create_resp.status_code in (200, 201):
                folder_id = create_resp.json().get("id")
                self.settings["gdrive_folder_id"] = folder_id
                self.save_settings()
                return folder_id
        except Exception as e:
            print(f"[CloudSync] Error getting/creating root Google Drive folder: {e}", flush=True)
            if cached_id:
                return cached_id
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Self-Hosted Cloud Server Provider Helpers (Fanta-OFME-Cloud)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_self_hosted_base_url(self, custom_url: Optional[str] = None) -> Optional[str]:
        raw = (custom_url if custom_url is not None else self.settings.get("self_hosted_url") or "").strip()
        if not raw:
            return None
        if not raw.startswith("http://") and not raw.startswith("https://"):
            raw = "http://" + raw
        return raw.rstrip("/")

    def _get_self_hosted_headers(self, custom_api_key: Optional[str] = None) -> Dict[str, str]:
        key = (custom_api_key if custom_api_key is not None else self.settings.get("self_hosted_api_key") or "").strip()
        headers: Dict[str, str] = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FantaOFME/2.1.0"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
            headers["X-API-Key"] = key
        return headers

    def is_self_hosted_configured(self) -> bool:
        return bool(self._get_self_hosted_base_url())

    def test_self_hosted_connection(self, url: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Pings GET /api/status on the self-hosted server and returns connection & auth info."""
        base_url = self._get_self_hosted_base_url(url)
        if not base_url:
            return {"success": False, "error": "Server URL is required."}

        headers = self._get_self_hosted_headers(api_key)
        start_time = time.time()
        try:
            resp = requests.get(f"{base_url}/api/status", headers=headers, timeout=10)
            latency_ms = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                return {
                    "success": True,
                    "status": data.get("status", "ok"),
                    "version": data.get("version", "1.0.0"),
                    "server_name": data.get("server_name", "Fanta-OFME-Cloud"),
                    "authenticated": data.get("authenticated", True),
                    "latency_ms": latency_ms,
                    "url": base_url
                }
            elif resp.status_code in (401, 403):
                return {
                    "success": False,
                    "error": "Authentication failed (Invalid or missing API Key).",
                    "status_code": resp.status_code
                }
            else:
                return {
                    "success": False,
                    "error": f"Server returned HTTP {resp.status_code}",
                    "status_code": resp.status_code
                }
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": f"Could not connect to {base_url}. Ensure the server is running."}
        except requests.exceptions.Timeout:
            return {"success": False, "error": f"Connection to {base_url} timed out."}
        except Exception as e:
            return {"success": False, "error": f"Connection error: {str(e)}"}

    # ──────────────────────────────────────────────────────────────────────────
    # Unified Cloud Operations (Google Drive API + Local Folder + Self-Hosted)
    # ──────────────────────────────────────────────────────────────────────────

    def list_all_cloud_saves(self) -> Dict[str, Any]:
        """Pre-indexes all saves available in cloud storage (local folder, self-hosted, or Google Drive) in one operation."""
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
                                item_data = {
                                    "exists": True,
                                    "provider": "local_folder",
                                    "safe_name": game_folder,
                                    "title": game_folder,
                                    "size_bytes": st.st_size,
                                    "mtime": mtime,
                                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p"),
                                    "path": zip_path
                                }
                                if os.path.exists(meta_path):
                                    try:
                                        with open(meta_path, "r", encoding="utf-8") as mf:
                                            m_data = json.load(mf)
                                            if m_data.get("title"):
                                                item_data["title"] = m_data.get("title")
                                    except Exception:
                                        pass
                                index[game_folder] = item_data
                                index[game_folder.lower()] = item_data
                                norm_key = re.sub(r'[^a-zA-Z0-9]', '', game_folder).lower()
                                if norm_key:
                                    alias_item = dict(item_data)
                                    alias_item["is_alias"] = True
                                    index[norm_key] = alias_item
                except Exception as e:
                    print(f"[CloudSync] Error scanning local cloud directory: {e}", flush=True)

        elif provider == "self_hosted":
            base_url = self._get_self_hosted_base_url()
            if base_url:
                headers = self._get_self_hosted_headers()
                try:
                    resp = requests.get(f"{base_url}/api/saves", headers=headers, timeout=20)
                    if resp.status_code == 200:
                        payload = resp.json()
                        saves_list = payload.get("saves", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
                        for s in saves_list:
                            if not isinstance(s, dict):
                                continue
                            safe_name = (s.get("safe_name") or s.get("title") or "").strip()
                            if safe_name.endswith("_save.zip"):
                                safe_name = safe_name[:-9]
                            if not safe_name:
                                continue
                            size = int(s.get("size_bytes") or s.get("size") or 0)
                            raw_mtime = s.get("mtime")
                            try:
                                mtime = float(raw_mtime) if raw_mtime is not None else time.time()
                            except Exception:
                                mtime = time.time()
                            item_data = {
                                "exists": True,
                                "safe_name": safe_name,
                                "title": s.get("title") or safe_name,
                                "provider": "self_hosted",
                                "size_bytes": size,
                                "mtime": mtime,
                                "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p")
                            }
                            index[safe_name] = item_data
                            index[safe_name.lower()] = item_data
                            norm_key = re.sub(r'[^a-zA-Z0-9]', '', safe_name).lower()
                            if norm_key:
                                alias_item = dict(item_data)
                                alias_item["is_alias"] = True
                                index[norm_key] = alias_item
                except Exception as e:
                    print(f"[CloudSync] Error indexing self-hosted cloud saves: {e}", flush=True)

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
                            timeout=25
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
                                    real_title = safe_name
                                    if desc and "Fanta OFME Save Backup for " in desc:
                                        try:
                                            real_title = desc.split("Fanta OFME Save Backup for ")[1].split(";")[0].strip()
                                        except Exception:
                                            pass

                                    item_data = {
                                        "exists": True,
                                        "file_id": f["id"],
                                        "safe_name": safe_name,
                                        "title": real_title,
                                        "provider": "gdrive_api",
                                        "size_bytes": size,
                                        "mtime": mtime,
                                        "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p")
                                    }
                                    index[safe_name] = item_data
                                    index[safe_name.lower()] = item_data
                                    norm_key = re.sub(r'[^a-zA-Z0-9]', '', safe_name).lower()
                                    if norm_key:
                                        alias_item = dict(item_data)
                                        alias_item["is_alias"] = True
                                        index[norm_key] = alias_item
                    except Exception as e:
                        print(f"[CloudSync] Error indexing Google Drive files: {e}", flush=True)

        return index

    def get_cloud_save_info(self, title: str, cloud_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inspects cloud save for given game under the active provider."""
        provider = self.get_provider()
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', title).strip()
        norm_key = re.sub(r'[^a-zA-Z0-9]', '', title).lower()

        if cloud_index is not None:
            if safe_name in cloud_index:
                return cloud_index[safe_name]
            if safe_name.lower() in cloud_index:
                return cloud_index[safe_name.lower()]
            if norm_key in cloud_index:
                return cloud_index[norm_key]
            fallback_status = "None"
            if provider == "gdrive_api" and not self.is_gdrive_connected():
                fallback_status = "Not Connected"
            elif provider == "self_hosted" and not self.is_self_hosted_configured():
                fallback_status = "Not Configured"
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

        elif provider == "self_hosted":
            base_url = self._get_self_hosted_base_url()
            if not base_url:
                return {"exists": False, "provider": "self_hosted", "size_bytes": 0, "mtime": None, "mtime_str": "Not Configured"}

            headers = self._get_self_hosted_headers()
            encoded_name = urllib.parse.quote(safe_name)
            try:
                resp = requests.get(f"{base_url}/api/saves/{encoded_name}", headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("exists", True):
                        size = int(data.get("size_bytes") or data.get("size") or 0)
                        raw_mtime = data.get("mtime")
                        mtime = float(raw_mtime) if raw_mtime is not None else time.time()
                        return {
                            "exists": True,
                            "safe_name": data.get("safe_name") or safe_name,
                            "provider": "self_hosted",
                            "size_bytes": size,
                            "mtime": mtime,
                            "mtime_str": datetime.fromtimestamp(mtime).strftime("%b %d, %Y • %I:%M %p")
                        }
            except Exception as e:
                print(f"[CloudSync] Error fetching self-hosted save info for {title}: {e}", flush=True)

            return {"exists": False, "provider": "self_hosted", "size_bytes": 0, "mtime": None, "mtime_str": "None"}

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

            elif provider == "self_hosted":
                base_url = self._get_self_hosted_base_url()
                if not base_url:
                    return {"success": False, "error": "Self-hosted server URL is not configured."}

                headers = self._get_self_hosted_headers()
                encoded_name = urllib.parse.quote(safe_name)
                filename = f"{safe_name}_save.zip"

                with open(zip_path, "rb") as zf:
                    files = {"file": (filename, zf, "application/zip")}
                    form_data = {
                        "title": clean_title,
                        "safe_name": safe_name,
                        "mtime": str(mtime)
                    }
                    resp = requests.post(
                        f"{base_url}/api/saves/{encoded_name}",
                        headers=headers,
                        files=files,
                        data=form_data,
                        timeout=60
                    )

                if resp.status_code in (200, 201):
                    self.settings.setdefault("last_synced", {})[clean_title] = mtime
                    self.save_settings()
                    return {
                        "success": True,
                        "message": f"Successfully backed up {clean_title} to Self-Hosted Server!",
                        "mtime": mtime
                    }
                elif resp.status_code in (401, 403):
                    return {"success": False, "error": "Self-hosted server rejected authentication (check API key)."}
                else:
                    return {"success": False, "error": f"Self-hosted upload failed: HTTP {resp.status_code} {resp.text}"}

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

            elif provider == "self_hosted":
                base_url = self._get_self_hosted_base_url()
                if not base_url:
                    return {"success": False, "error": "Self-hosted server URL is not configured."}

                target_name = cloud_info.get("safe_name") or safe_name
                encoded_name = urllib.parse.quote(target_name)
                headers = self._get_self_hosted_headers()
                resp = requests.get(
                    f"{base_url}/api/saves/{encoded_name}/download",
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
                    return {"success": False, "error": f"Download failed from Self-Hosted Server: HTTP {resp.status_code}"}

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

    def delete_cloud_save(self, title: str) -> Dict[str, Any]:
        """Deletes cloud save backup for a game from the active cloud provider."""
        clean_title = (title or "").strip()
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', clean_title).strip()
        provider = self.get_provider()

        try:
            if provider == "local_folder":
                base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
                game_cloud_dir = os.path.join(base_dir, safe_name)
                if os.path.exists(game_cloud_dir):
                    shutil.rmtree(game_cloud_dir, ignore_errors=True)
                    return {"success": True, "message": f"Deleted local cloud backup for {clean_title}."}
                return {"success": False, "error": f"No local cloud backup found for '{clean_title}'."}

            elif provider == "self_hosted":
                base_url = self._get_self_hosted_base_url()
                if not base_url:
                    return {"success": False, "error": "Self-hosted server URL is not configured."}
                headers = self._get_self_hosted_headers()
                encoded_name = urllib.parse.quote(safe_name)
                resp = requests.delete(f"{base_url}/api/saves/{encoded_name}", headers=headers, timeout=20)
                if resp.status_code in (200, 204):
                    return {"success": True, "message": f"Deleted backup for {clean_title} from Self-Hosted Server."}
                elif resp.status_code == 404:
                    return {"success": False, "error": f"No backup found on server for '{clean_title}'."}
                else:
                    return {"success": False, "error": f"Failed to delete from server: HTTP {resp.status_code}"}

            else:
                cloud_info = self.get_cloud_save_info(clean_title)
                if not cloud_info.get("exists") or not cloud_info.get("file_id"):
                    return {"success": False, "error": f"No Google Drive backup found for '{clean_title}'."}
                token = self._get_valid_access_token()
                if not token:
                    return {"success": False, "error": "Not connected to Google Drive."}
                file_id = cloud_info["file_id"]
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.delete(f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=headers, timeout=20)
                if resp.status_code in (200, 204):
                    return {"success": True, "message": f"Deleted Google Drive backup for {clean_title}."}
                else:
                    return {"success": False, "error": f"Google Drive delete failed: HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Delete failed: {str(e)}"}

    # ──────────────────────────────────────────────────────────────────────────
    # Provider-to-Provider Cloud Save Transfer & Migration
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _provider_label(provider: str) -> str:
        labels = {
            "gdrive_api": "Google Drive Online",
            "local_folder": "Local Cloud Folder",
            "self_hosted": "Self-Hosted Cloud Server",
            "local_pc": "This PC (Local Saves)"
        }
        return labels.get(provider, provider)

    def validate_provider_ready(self, provider: str) -> Tuple[bool, str]:
        """Checks whether a given provider is properly configured and reachable."""
        if provider == "local_folder":
            base_dir = (self.settings.get("local_cloud_path") or self._detect_default_cloud_folder() or "").strip()
            if not base_dir:
                return False, "Local Cloud Folder path is not configured."
            try:
                os.makedirs(base_dir, exist_ok=True)
            except Exception as e:
                return False, f"Cannot access Local Cloud Folder '{base_dir}': {e}"
            return True, ""

        elif provider == "self_hosted":
            base_url = self._get_self_hosted_base_url()
            if not base_url:
                return False, "Self-Hosted Server URL is not configured."
            ping = self.test_self_hosted_connection()
            if not ping.get("success"):
                return False, f"Self-Hosted Server error: {ping.get('error', 'Unreachable')}"
            return True, ""

        elif provider == "gdrive_api":
            token = self._get_valid_access_token()
            if not token:
                return False, "Google Drive is not connected. Please sign in with Google first."
            folder_id = self._get_or_create_gdrive_folder()
            if not folder_id:
                return False, "Could not access 'Fanta OFME Cloud Saves' folder on Google Drive."
            return True, ""

        elif provider == "local_pc":
            return True, ""

        return False, f"Unknown provider '{provider}'."

    def list_provider_saves(self, provider: str, games_catalog: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Returns a deduplicated list of save items available in the specified provider."""
        items: List[Dict[str, Any]] = []
        seen_keys = set()

        if provider == "local_folder":
            base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
            if base_dir and os.path.isdir(base_dir):
                try:
                    for game_folder in sorted(os.listdir(base_dir)):
                        folder_path = os.path.join(base_dir, game_folder)
                        if not os.path.isdir(folder_path):
                            continue
                        zip_path = os.path.join(folder_path, f"{game_folder}_save.zip")
                        if not os.path.exists(zip_path):
                            continue
                        st = os.stat(zip_path)
                        mtime = st.st_mtime
                        title = game_folder
                        meta_path = os.path.join(folder_path, "metadata.json")
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, "r", encoding="utf-8") as mf:
                                    m_data = json.load(mf)
                                    mtime = float(m_data.get("mtime", mtime))
                                    title = m_data.get("title") or game_folder
                            except Exception:
                                pass
                        norm = re.sub(r'[^a-zA-Z0-9]', '', game_folder).lower() or game_folder.lower()
                        if norm in seen_keys:
                            continue
                        seen_keys.add(norm)
                        items.append({
                            "safe_name": game_folder,
                            "title": title,
                            "norm_key": norm,
                            "provider": "local_folder",
                            "size_bytes": st.st_size,
                            "mtime": mtime,
                            "path": zip_path
                        })
                except Exception as e:
                    print(f"[CloudSync] Error listing local_folder saves: {e}", flush=True)

        elif provider == "self_hosted":
            base_url = self._get_self_hosted_base_url()
            if base_url:
                headers = self._get_self_hosted_headers()
                try:
                    resp = requests.get(f"{base_url}/api/saves", headers=headers, timeout=25)
                    if resp.status_code == 200:
                        payload = resp.json()
                        saves_list = payload.get("saves", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
                        for s in saves_list:
                            if not isinstance(s, dict):
                                continue
                            safe_name = (s.get("safe_name") or s.get("title") or "").strip()
                            if safe_name.endswith("_save.zip"):
                                safe_name = safe_name[:-9]
                            if not safe_name:
                                continue
                            title = (s.get("title") or safe_name).strip()
                            size = int(s.get("size_bytes") or s.get("size") or 0)
                            raw_mtime = s.get("mtime")
                            try:
                                mtime = float(raw_mtime) if raw_mtime is not None else time.time()
                            except Exception:
                                mtime = time.time()
                            norm = re.sub(r'[^a-zA-Z0-9]', '', safe_name).lower() or safe_name.lower()
                            if norm in seen_keys:
                                continue
                            seen_keys.add(norm)
                            items.append({
                                "safe_name": safe_name,
                                "title": title,
                                "norm_key": norm,
                                "provider": "self_hosted",
                                "size_bytes": size,
                                "mtime": mtime
                            })
                except Exception as e:
                    print(f"[CloudSync] Error listing self_hosted saves: {e}", flush=True)

        elif provider == "gdrive_api":
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
                            timeout=25
                        )
                        if resp.status_code == 200:
                            for f in resp.json().get("files", []):
                                fname = f.get("name", "")
                                if not fname.endswith("_save.zip"):
                                    continue
                                safe_name = fname[:-9]
                                if not safe_name:
                                    continue
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
                                norm = re.sub(r'[^a-zA-Z0-9]', '', safe_name).lower() or safe_name.lower()
                                if norm in seen_keys:
                                    continue
                                seen_keys.add(norm)
                                items.append({
                                    "safe_name": safe_name,
                                    "title": safe_name,
                                    "norm_key": norm,
                                    "provider": "gdrive_api",
                                    "file_id": f["id"],
                                    "size_bytes": size,
                                    "mtime": mtime
                                })
                    except Exception as e:
                        print(f"[CloudSync] Error listing gdrive_api saves: {e}", flush=True)

        elif provider == "local_pc":
            candidates: List[Tuple[str, Optional[str], Optional[Any]]] = []
            if games_catalog:
                for g in games_catalog:
                    t = (g.get("title") or g.get("name") or "").strip()
                    if t:
                        candidates.append((t, g.get("location") or g.get("install_path"), g.get("app_id") or g.get("appid")))
            for custom_title in self.settings.get("custom_save_paths", {}).keys():
                if custom_title and not any(c[0].lower() == custom_title.lower() for c in candidates):
                    candidates.append((custom_title, None, None))

            for title, loc, app_id in candidates:
                save_path, det_type = self.detect_save_path(title, loc, app_id)
                is_sc = self.is_steam_cloud_game(title, game_location=loc, app_id=app_id, detection_type=det_type, save_path=save_path)
                if self.get_game_exclusion_state(title, is_steam_cloud=is_sc)[0]:
                    continue
                if not save_path or not os.path.exists(save_path):
                    continue
                info = self.get_folder_info(save_path)
                if not info.get("exists") or (info.get("file_count", 0) == 0 and info.get("size_bytes", 0) == 0):
                    continue
                safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', title).strip()
                norm = re.sub(r'[^a-zA-Z0-9]', '', safe_name).lower() or safe_name.lower()
                if norm in seen_keys:
                    continue
                seen_keys.add(norm)
                items.append({
                    "safe_name": safe_name,
                    "title": title,
                    "norm_key": norm,
                    "provider": "local_pc",
                    "size_bytes": info.get("size_bytes", 0),
                    "mtime": info.get("mtime") or time.time(),
                    "path": save_path
                })

        return items

    def _download_provider_save_zip(self, provider: str, item: Dict[str, Any], target_zip_path: str) -> Dict[str, Any]:
        """Fetches or archives a save item from `provider` into `target_zip_path`."""
        try:
            if provider == "local_folder":
                src_zip = item.get("path")
                if not src_zip or not os.path.exists(src_zip):
                    return {"success": False, "error": "Source archive missing in Local Cloud Folder."}
                shutil.copy2(src_zip, target_zip_path)
                return {"success": True}

            elif provider == "local_pc":
                src_folder = item.get("path")
                if not src_folder or not os.path.exists(src_folder):
                    return {"success": False, "error": "Local save folder not found."}
                if not self.archive_save_folder(src_folder, target_zip_path):
                    return {"success": False, "error": "Failed to zip local save folder."}
                return {"success": True}

            elif provider == "self_hosted":
                base_url = self._get_self_hosted_base_url()
                headers = self._get_self_hosted_headers()
                encoded_name = urllib.parse.quote(item["safe_name"])
                resp = requests.get(
                    f"{base_url}/api/saves/{encoded_name}/download",
                    headers=headers,
                    stream=True,
                    timeout=60
                )
                if resp.status_code == 200:
                    with open(target_zip_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    return {"success": True}
                return {"success": False, "error": f"Self-Hosted download returned HTTP {resp.status_code}"}

            elif provider == "gdrive_api":
                token = self._get_valid_access_token()
                if not token:
                    return {"success": False, "error": "Google Drive token expired."}
                file_id = item.get("file_id")
                if not file_id:
                    return {"success": False, "error": "Missing Google Drive file_id."}
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                    headers=headers,
                    stream=True,
                    timeout=60
                )
                if resp.status_code == 200:
                    with open(target_zip_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    return {"success": True}
                return {"success": False, "error": f"Google Drive download returned HTTP {resp.status_code}"}

            return {"success": False, "error": f"Unsupported source provider '{provider}'."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _upload_provider_save_zip(
        self,
        provider: str,
        safe_name: str,
        title: str,
        mtime: float,
        source_zip_path: str,
        existing_target_item: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Uploads or extracts `source_zip_path` into `provider`, preserving `mtime`."""
        try:
            if provider == "local_folder":
                base_dir = self.settings.get("local_cloud_path") or self._detect_default_cloud_folder()
                dest_dir = os.path.join(base_dir, safe_name)
                os.makedirs(dest_dir, exist_ok=True)
                dest_zip = os.path.join(dest_dir, f"{safe_name}_save.zip")
                shutil.copy2(source_zip_path, dest_zip)
                meta_file = os.path.join(dest_dir, "metadata.json")
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump({
                        "title": title,
                        "mtime": mtime,
                        "size_bytes": os.path.getsize(dest_zip),
                        "backed_up_at": datetime.now().isoformat()
                    }, mf, indent=2)
                return {"success": True}

            elif provider == "self_hosted":
                base_url = self._get_self_hosted_base_url()
                headers = self._get_self_hosted_headers()
                encoded_name = urllib.parse.quote(safe_name)
                filename = f"{safe_name}_save.zip"
                with open(source_zip_path, "rb") as zf:
                    files = {"file": (filename, zf, "application/zip")}
                    form_data = {
                        "title": title,
                        "safe_name": safe_name,
                        "mtime": str(mtime)
                    }
                    resp = requests.post(
                        f"{base_url}/api/saves/{encoded_name}",
                        headers=headers,
                        files=files,
                        data=form_data,
                        timeout=60
                    )
                if resp.status_code in (200, 201):
                    return {"success": True}
                return {"success": False, "error": f"Self-Hosted upload returned HTTP {resp.status_code}"}

            elif provider == "gdrive_api":
                token = self._get_valid_access_token()
                if not token:
                    return {"success": False, "error": "Google Drive token expired."}
                folder_id = self._get_or_create_gdrive_folder()
                if not folder_id:
                    return {"success": False, "error": "Could not access Google Drive folder."}

                filename = f"{safe_name}_save.zip"
                existing_file_id = existing_target_item.get("file_id") if existing_target_item else None
                metadata: Dict[str, Any] = {
                    "name": filename,
                    "description": f"Fanta OFME Save Backup for {title};mtime:{mtime};"
                }
                if not existing_file_id:
                    metadata["parents"] = [folder_id]

                with open(source_zip_path, "rb") as zf:
                    file_bytes = zf.read()

                boundary = "===fanta_transfer_boundary==="
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
                    resp = requests.patch(url, headers=upload_headers, data=body, timeout=60)
                else:
                    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
                    resp = requests.post(url, headers=upload_headers, data=body, timeout=60)

                if resp.status_code in (200, 201):
                    return {"success": True}
                return {"success": False, "error": f"Google Drive upload returned HTTP {resp.status_code}"}

            elif provider == "local_pc":
                save_path = existing_target_item.get("path") if existing_target_item else None
                if not save_path:
                    save_path = self.settings.get("custom_save_paths", {}).get(title)
                if not save_path:
                    save_path, _ = self.detect_save_path(title)
                if not save_path:
                    return {"success": False, "error": f"No local save path detected on this PC for '{title}'."}
                if not self.extract_save_zip(source_zip_path, save_path):
                    return {"success": False, "error": f"Failed to extract save to '{save_path}'."}
                return {"success": True}

            return {"success": False, "error": f"Unsupported target provider '{provider}'."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def transfer_saves(
        self,
        source_provider: str,
        target_provider: str,
        mode: str = "newer_or_missing",
        switch_to_target: bool = True,
        games_catalog: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Transfers all saves from `source_provider` to `target_provider`.
        Supports any combination of: 'gdrive_api', 'local_folder', 'self_hosted', 'local_pc'.
        """
        src = (source_provider or "").strip()
        dst = (target_provider or "").strip()
        if not src or not dst:
            return {"success": False, "error": "Both source and destination providers are required."}
        if src == dst:
            return {"success": False, "error": "Source and destination providers must be different."}

        src_ok, src_err = self.validate_provider_ready(src)
        if not src_ok:
            return {"success": False, "error": f"Source ({self._provider_label(src)}): {src_err}"}

        dst_ok, dst_err = self.validate_provider_ready(dst)
        if not dst_ok:
            return {"success": False, "error": f"Destination ({self._provider_label(dst)}): {dst_err}"}

        source_items = self.list_provider_saves(src, games_catalog=games_catalog)
        if not source_items:
            return {
                "success": False,
                "error": f"No save backups were found in {self._provider_label(src)} to transfer."
            }

        target_items = self.list_provider_saves(dst, games_catalog=games_catalog)
        target_by_norm: Dict[str, Dict[str, Any]] = {item["norm_key"]: item for item in target_items}

        transferred = 0
        skipped = 0
        failed = 0
        details: List[Dict[str, Any]] = []

        temp_dir = tempfile.mkdtemp(prefix="fanta_transfer_")
        try:
            for item in source_items:
                safe_name = item["safe_name"]
                title = item.get("title") or safe_name
                src_mtime = float(item.get("mtime") or time.time())
                norm_key = item["norm_key"]
                existing_target = target_by_norm.get(norm_key)

                if mode == "newer_or_missing" and existing_target:
                    dst_mtime = float(existing_target.get("mtime") or 0)
                    if dst_mtime >= (src_mtime - 5):
                        skipped += 1
                        details.append({
                            "title": title,
                            "status": "skipped",
                            "reason": "Destination already has same or newer save"
                        })
                        continue

                temp_zip = os.path.join(temp_dir, f"{safe_name}_transfer.zip")
                dl_res = self._download_provider_save_zip(src, item, temp_zip)
                if not dl_res.get("success"):
                    failed += 1
                    details.append({
                        "title": title,
                        "status": "failed",
                        "reason": dl_res.get("error", "Download failed")
                    })
                    continue

                up_res = self._upload_provider_save_zip(
                    dst,
                    safe_name=safe_name,
                    title=title,
                    mtime=src_mtime,
                    source_zip_path=temp_zip,
                    existing_target_item=existing_target
                )
                try:
                    if os.path.exists(temp_zip):
                        os.remove(temp_zip)
                except Exception:
                    pass

                if up_res.get("success"):
                    transferred += 1
                    details.append({"title": title, "status": "transferred"})
                else:
                    failed += 1
                    details.append({
                        "title": title,
                        "status": "failed",
                        "reason": up_res.get("error", "Upload failed")
                    })

            if switch_to_target and dst in ("gdrive_api", "local_folder", "self_hosted") and transferred > 0:
                self.settings["provider"] = dst
                self.save_settings()

            src_label = self._provider_label(src)
            dst_label = self._provider_label(dst)
            summary_msg = (
                f"Transferred {transferred} save(s) from {src_label} to {dst_label}"
                + (f" ({skipped} already up-to-date" + (f", {failed} failed)" if failed else ")") if skipped else (f" ({failed} failed)" if failed else "!"))
            )
            return {
                "success": transferred > 0 or (skipped > 0 and failed == 0),
                "source_provider": src,
                "target_provider": dst,
                "source_label": src_label,
                "target_label": dst_label,
                "total_found": len(source_items),
                "transferred": transferred,
                "skipped": skipped,
                "failed": failed,
                "details": details,
                "switched_provider": bool(switch_to_target and dst in ("gdrive_api", "local_folder", "self_hosted") and transferred > 0),
                "message": summary_msg
            }
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
            save_path, det_type = self.detect_save_path(clean_title)
        else:
            det_type = "Custom"
        if self.get_game_exclusion_state(clean_title, is_steam_cloud=self.is_steam_cloud_game(clean_title, detection_type=det_type, save_path=save_path))[0]:
            return False

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

    # ──────────────────────────────────────────────────────────────────────────
    # Steam Cloud Auto-Detection & Per-Game Exclusion / Exceptions
    # ──────────────────────────────────────────────────────────────────────────

    def get_official_steam_games_index(self) -> Dict[str, Any]:
        """
        Scans local Steam libraryfolders.vdf, appmanifest_*.acf, and userdata remotecache.vdf
        to identify games officially installed/managed via Steam Cloud. Cached for 60s.
        """
        now = time.time()
        if hasattr(self, "_steam_acf_cache") and (now - getattr(self, "_steam_acf_cache_time", 0)) < 60:
            return self._steam_acf_cache

        index: Dict[str, Any] = {"by_norm": {}, "by_appid": set(), "cloud_appids": set()}
        steam_roots: List[str] = []

        if self.config_ref and hasattr(self.config_ref, "get"):
            cfg_steam = self.config_ref.get("steam_path")
            if cfg_steam and os.path.isdir(cfg_steam):
                steam_roots.append(os.path.normpath(cfg_steam))

        for default_p in [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
            r"D:\Steam",
            r"E:\Steam",
            r"D:\SteamLibrary",
            r"E:\SteamLibrary"
        ]:
            if os.path.isdir(default_p):
                norm_p = os.path.normpath(default_p)
                if norm_p not in steam_roots:
                    steam_roots.append(norm_p)

        libraries: List[str] = list(steam_roots)
        for root in steam_roots:
            vdf_p = os.path.join(root, "steamapps", "libraryfolders.vdf")
            if os.path.exists(vdf_p):
                try:
                    with open(vdf_p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for m in re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE):
                        norm_lib = os.path.normpath(m.replace("\\\\", "\\"))
                        if os.path.isdir(norm_lib) and norm_lib not in libraries:
                            libraries.append(norm_lib)
                except Exception:
                    pass

            # Check userdata/<uid>/<appid>/remotecache.vdf for active Steam Cloud games
            userdata_dir = os.path.join(root, "userdata")
            if os.path.isdir(userdata_dir):
                try:
                    for uid in os.listdir(userdata_dir):
                        uid_path = os.path.join(userdata_dir, uid)
                        if not os.path.isdir(uid_path):
                            continue
                        for appid_dir in os.listdir(uid_path):
                            if appid_dir.isdigit() and os.path.exists(os.path.join(uid_path, appid_dir, "remotecache.vdf")):
                                index["cloud_appids"].add(appid_dir)
                except Exception:
                    pass

        for lib in libraries:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.isdir(steamapps):
                continue
            try:
                for fname in os.listdir(steamapps):
                    if not (fname.startswith("appmanifest_") and fname.endswith(".acf")):
                        continue
                    acf_path = os.path.join(steamapps, fname)
                    try:
                        with open(acf_path, "r", encoding="utf-8", errors="ignore") as af:
                            acf_txt = af.read()
                        appid_m = re.search(r'"appid"\s+"(\d+)"', acf_txt, re.IGNORECASE)
                        name_m = re.search(r'"name"\s+"([^"]+)"', acf_txt, re.IGNORECASE)
                        installdir_m = re.search(r'"installdir"\s+"([^"]+)"', acf_txt, re.IGNORECASE)
                        appid_val = appid_m.group(1) if appid_m else ""
                        name_val = name_m.group(1) if name_m else ""
                        install_val = installdir_m.group(1) if installdir_m else ""
                        full_install = os.path.join(steamapps, "common", install_val) if install_val else ""

                        # Ensure this install folder doesn't contain OnlineFix files
                        if full_install and os.path.isdir(full_install) and self._has_ofme_markers(full_install):
                            continue

                        if appid_val:
                            index["by_appid"].add(appid_val)
                        if name_val:
                            norm = re.sub(r'[^a-zA-Z0-9]', '', name_val).lower()
                            if norm:
                                index["by_norm"][norm] = {
                                    "appid": appid_val,
                                    "name": name_val,
                                    "install_path": full_install
                                }
                        if install_val:
                            norm_inst = re.sub(r'[^a-zA-Z0-9]', '', install_val).lower()
                            if norm_inst and norm_inst not in index["by_norm"]:
                                index["by_norm"][norm_inst] = {
                                    "appid": appid_val,
                                    "name": name_val or install_val,
                                    "install_path": full_install
                                }
                    except Exception:
                        continue
            except Exception:
                continue

        self._steam_acf_cache = index
        self._steam_acf_cache_time = now
        return index

    @staticmethod
    def _has_ofme_markers(game_dir: str) -> bool:
        """Returns True if directory contains OnlineFix or Goldberg markers."""
        if not game_dir or not os.path.isdir(game_dir):
            return False
        marker_names = {
            "onlinefix.ini", "onlinefix64.dll", "onlinefix.dll",
            "dlllist.txt", "steam_settings", "goldberg"
        }
        try:
            for root, dirs, files in os.walk(game_dir):
                depth = len(os.path.normpath(root).split(os.sep)) - len(os.path.normpath(game_dir).split(os.sep))
                if depth > 3:
                    dirs.clear()
                    continue
                for d in dirs:
                    if d.lower() in marker_names:
                        return True
                for f in files:
                    if f.lower() in marker_names:
                        return True
        except Exception:
            pass
        return False

    def is_steam_cloud_game(
        self,
        title: str,
        game_location: Optional[str] = None,
        app_id: Optional[Any] = None,
        detection_type: Optional[str] = None,
        steam_index: Optional[Dict[str, Any]] = None,
        save_path: Optional[str] = None
    ) -> bool:
        """Determines if a game is an official Steam / Steam Cloud game rather than an OFME game."""
        if detection_type in ("Goldberg SteamEmu", "OnlineFix", "Custom"):
            return False

        if game_location and os.path.isdir(game_location):
            if self._has_ofme_markers(game_location):
                return False
            if "steamapps" in game_location.lower():
                return True

        idx = steam_index if steam_index is not None else self.get_official_steam_games_index()
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', (title or "")).lower()
        if norm_title and norm_title in idx.get("by_norm", {}):
            return True

        str_appid = str(app_id).strip() if app_id else ""
        if str_appid and (str_appid in idx.get("by_appid", set()) or str_appid in idx.get("cloud_appids", set())):
            return True

        # Check save_path for Steam Auto-Cloud (steam_autocloud.vdf) or Unity Player.log launched from steamapps/common
        if save_path and os.path.isdir(save_path):
            try:
                for root, dirs, files in os.walk(save_path):
                    depth = len(os.path.normpath(root).split(os.sep)) - len(os.path.normpath(save_path).split(os.sep))
                    if depth > 3:
                        dirs.clear()
                        continue
                    for f in files:
                        fl = f.lower()
                        if fl == "steam_autocloud.vdf":
                            return True
                        if depth == 0 and fl in ("player.log", "player-prev.log"):
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as lf:
                                    head = lf.read(1500).replace("\\", "/").lower()
                                if "steamapps/common/" in head:
                                    return True
                            except Exception:
                                pass
            except Exception:
                pass

        return False

    def get_game_exclusion_state(self, title: str, is_steam_cloud: bool = False) -> Tuple[bool, str]:
        """Returns (is_excluded, reason) for a game."""
        t_low = (title or "").strip().lower()
        excluded_list = [x.strip().lower() for x in self.settings.get("excluded_games", []) if isinstance(x, str)]
        override_list = [x.strip().lower() for x in self.settings.get("included_override_games", []) if isinstance(x, str)]

        if t_low in excluded_list:
            return True, "Ignored"
        if is_steam_cloud and self.settings.get("auto_exclude_steam_cloud", True) and t_low not in override_list:
            return True, "Steam Cloud"
        return False, ""

    def set_game_exclusion(self, title: str, excluded: bool) -> Dict[str, Any]:
        """Manually excludes or includes a game in Fanta Cloud Sync."""
        clean_title = (title or "").strip()
        t_low = clean_title.lower()

        excluded_list: List[str] = [x for x in self.settings.get("excluded_games", []) if isinstance(x, str)]
        override_list: List[str] = [x for x in self.settings.get("included_override_games", []) if isinstance(x, str)]

        excluded_list = [x for x in excluded_list if x.strip().lower() != t_low]
        override_list = [x for x in override_list if x.strip().lower() != t_low]

        if excluded:
            excluded_list.append(clean_title)
        else:
            override_list.append(clean_title)

        self.settings["excluded_games"] = excluded_list
        self.settings["included_override_games"] = override_list
        self.save_settings()
        return {
            "success": True,
            "title": clean_title,
            "is_excluded": excluded,
            "excluded_games": excluded_list
        }

    def get_game_sync_status(self, title: str, game_location: Optional[str] = None, app_id: Optional[Any] = None, cloud_index: Optional[Dict[str, Any]] = None, steam_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            "is_steam_cloud": self.is_steam_cloud_game(clean_title, game_location=game_location, app_id=app_id, detection_type=detect_type, steam_index=steam_index, save_path=save_path),
            "is_excluded": self.get_game_exclusion_state(clean_title, is_steam_cloud=self.is_steam_cloud_game(clean_title, game_location=game_location, app_id=app_id, detection_type=detect_type, steam_index=steam_index, save_path=save_path))[0],
            "exclude_reason": self.get_game_exclusion_state(clean_title, is_steam_cloud=self.is_steam_cloud_game(clean_title, game_location=game_location, app_id=app_id, detection_type=detect_type, steam_index=steam_index, save_path=save_path))[1],
            "sync_state_label": state_label
        }
