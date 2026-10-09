import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class ConfigDefaults:
    winrar_path: str = r"C:\Program Files\WinRAR\WinRAR.exe"
    download_path: str = r"C:\Users\ZUHU\Documents\ZuhuProjects\ZuhuOFME\downloads"
    extract_path: str = r"D:\GAMES2"
    default_download_path: str = r"D:\GAMES2"
    steam_path: str = r"C:\Program Files (x86)\Steam"
    steam_user_id: str = "1004235037"
    steam_id: str = "1004235037"
    rar_password: str = "online-fix.me"
    concurrent_downloads: int = 2
    speed_unit: str = "MB/s"
    show_size_in_gb: bool = True
    enable_notifications: bool = True
    enable_webhook: bool = True
    webhook_url: str = ""
    ofme_username: str = ""
    ofme_password: str = ""
    browser_path: str = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    db_url: str = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/BetaRework/src/backend/data/Data.json"
    use_local_db: bool = False
    sevenzip_path: str = r"C:\Program Files\7-Zip\7z.exe"
    auto_extract: bool = True
    auto_delete_archive: bool = True
    gofile_token: str = ""


class Config:
    def __init__(self, data_folder: Optional[str] = None):
        zuhu_default = r"C:\Users\ZUHU\Documents\ZuhuProjects\ZuhuOFME"
        if not data_folder:
            data_folder = zuhu_default if os.path.exists(zuhu_default) else os.path.join(os.path.expanduser("~"), ".fanta_ofme")
        
        self.data_folder = data_folder
        self.cache_folder = os.path.join(self.data_folder, "cache")
        os.makedirs(self.data_folder, exist_ok=True)
        os.makedirs(self.cache_folder, exist_ok=True)

        self.path = os.path.join(self.data_folder, "Settings.json")
        self.data_json_path = os.path.join(self.data_folder, "Data.json")
        self.data_bak_path = os.path.join(self.data_folder, "Data.json.bak")
        self.data_old_path = os.path.join(self.data_folder, "old.Data.json")
        self.login_json_path = os.path.join(self.data_folder, "Login.json")
        self._data: Dict[str, Any] = asdict(ConfigDefaults())

        # Set default local database path if bundled in source
        bundled_json = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "Data.json"))
        if os.path.exists(bundled_json):
            self._data["local_db_path"] = bundled_json
            if self.is_source_mode():
                self._data["use_local_db"] = True

        self._installed_data: Dict[str, Any] = {}
        self.load()

    @property
    def data(self) -> Dict[str, Any]:
        return self._installed_data

    def load(self) -> None:
        # Load Settings.json
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                    saved = json.load(f)
                self._data.update(saved)
                # Auto-migrate legacy Download-DB.txt db_url
                if not self._data.get("db_url") or "Download-DB.txt" in str(self._data.get("db_url")):
                    self._data["db_url"] = ConfigDefaults.db_url
            except Exception as e:
                print(f"[Config] Settings load error: {e}")

        # Load Login.json (legacy & cross-compatibility credentials)
        if os.path.exists(self.login_json_path):
            try:
                with open(self.login_json_path, "r", encoding="utf-8", errors="ignore") as f:
                    login_data = json.load(f)
                if login_data.get("username"):
                    self._data["ofme_username"] = login_data["username"]
                if login_data.get("password"):
                    self._data["ofme_password"] = login_data["password"]
                if login_data.get("webhook_url"):
                    self._data["webhook_url"] = login_data["webhook_url"]
                print(f"[Config] Loaded credentials and webhook from Login.json ({self._data.get('ofme_username')})")
            except Exception as e:
                print(f"[Config] Login.json load error: {e}")

        # Load Data.json (installed games database) with corruption protection
        if os.path.exists(self.data_json_path):
            try:
                with open(self.data_json_path, "r", encoding="utf-8", errors="ignore") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._installed_data = loaded
                    print(f"[Config] Loaded {len(self._installed_data)} installed games from Data.json")
            except Exception as e:
                print(f"[Config] Data.json load error / syntax issue: {e}")
                # Save corrupted file as old.Data.json so user never loses their changes
                try:
                    import shutil
                    shutil.copy2(self.data_json_path, self.data_old_path)
                    print(f"[Config] Preserved corrupted Data.json copy as: {self.data_old_path}")
                except Exception:
                    pass

                # Try to recover from backup Data.json.bak
                if os.path.exists(self.data_bak_path):
                    try:
                        with open(self.data_bak_path, "r", encoding="utf-8", errors="ignore") as bf:
                            recovered = json.load(bf)
                        if isinstance(recovered, dict) and recovered:
                            self._installed_data = recovered
                            print(f"[Config] Successfully recovered {len(self._installed_data)} installed games from Data.json.bak")
                    except Exception:
                        pass

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Config] Settings save error: {e}")

        # Keep Login.json in sync
        if self._data.get("ofme_username") or self._data.get("webhook_url"):
            try:
                login_payload = {
                    "username": self._data.get("ofme_username", ""),
                    "password": self._data.get("ofme_password", ""),
                    "webhook_url": self._data.get("webhook_url", "")
                }
                with open(self.login_json_path, "w", encoding="utf-8") as f:
                    json.dump(login_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"[Config] Login.json save error: {e}")

        # Save Data.json with automatic backup rotation and atomic writing
        if self._installed_data is not None:
            # Avoid wiping a non-empty file on disk with an empty dict
            if not self._installed_data and os.path.exists(self.data_json_path):
                try:
                    if os.path.getsize(self.data_json_path) > 100:
                        print("[Config] Prevented saving empty installed games dictionary over existing Data.json")
                        return
                except Exception:
                    pass

            try:
                # Rotate backup if current Data.json is valid
                if os.path.exists(self.data_json_path) and os.path.getsize(self.data_json_path) > 20:
                    try:
                        import shutil
                        shutil.copy2(self.data_json_path, self.data_bak_path)
                        shutil.copy2(self.data_json_path, self.data_old_path)
                    except Exception:
                        pass

                tmp_path = self.data_json_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._installed_data, f, ensure_ascii=False, indent=4)
                if os.path.exists(self.data_json_path):
                    try: os.remove(self.data_json_path)
                    except Exception: pass
                os.replace(tmp_path, self.data_json_path)
            except Exception as e:
                print(f"[Config] Data.json save error: {e}")

    @staticmethod
    def is_source_mode() -> bool:
        env_mode = os.environ.get('FANTA_SOURCE_MODE')
        if env_mode == '1':
            return True
        if env_mode == '0':
            return False
        return not getattr(sys, 'frozen', False)

    def get_local_db_path(self) -> str:
        custom_path = self.get("local_db_path")
        if custom_path and os.path.exists(custom_path):
            return custom_path
        bundled = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "Data.json"))
        return bundled if os.path.exists(bundled) else self.data_json_path

    def get_installed_games(self) -> Dict[str, Any]:
        return self._installed_data

    def save_installed_games(self, games_dict: Dict[str, Any]) -> None:
        self._installed_data = games_dict
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, new_data: Dict[str, Any]) -> None:
        self._data.update(new_data)
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)
