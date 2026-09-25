import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class ConfigDefaults:
    winrar_path: str = r"C:\Program Files\WinRAR\WinRAR.exe"
    download_path: str = r"C:\Users\ZUHU\Documents\ZuhuProjects\ZuhuOFME\downloads"
    extract_path: str = r"C:\Users\ZUHU\Documents\ZuhuProjects\ZuhuOFME\extracted"
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
    db_url: str = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"


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
        self.login_json_path = os.path.join(self.data_folder, "Login.json")
        self._data: Dict[str, Any] = asdict(ConfigDefaults())
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

        # Load Data.json (installed games database)
        if os.path.exists(self.data_json_path):
            try:
                with open(self.data_json_path, "r", encoding="utf-8", errors="ignore") as f:
                    self._installed_data = json.load(f)
                print(f"[Config] Loaded {len(self._installed_data)} installed games from Data.json")
            except Exception as e:
                print(f"[Config] Data.json load error: {e}")

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

        try:
            with open(self.data_json_path, "w", encoding="utf-8") as f:
                json.dump(self._installed_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Config] Data.json save error: {e}")

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
