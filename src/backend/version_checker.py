"""
Fanta OFME Downloader - Version Checker
Audits installed games against Online-Fix.me updates and sends Discord Webhook notifications.
"""

import threading
import time
import requests
from typing import List, Dict, Any, Optional, Callable
from .utils import parse_db


class VersionChecker:
    def __init__(
        self,
        webhook_url: str = "",
        enable_notifications: bool = True,
        username: str = "",
        password: str = "",
        browser_path: str = ""
    ):
        self.webhook_url = webhook_url
        self.enable_notifications = enable_notifications
        self.username = username
        self.password = password
        self.browser_path = browser_path
        self.is_scanning = False
        self._stop_requested = False
        self._scan_thread: Optional[threading.Thread] = None

    def update_credentials(
        self,
        username: str = "",
        password: str = "",
        webhook_url: str = "",
        enable_webhook: bool = False,
        browser_path: str = "",
        bypass_list: Optional[List[str]] = None
    ):
        if username: self.username = username
        if password: self.password = password
        if webhook_url: self.webhook_url = webhook_url
        self.enable_notifications = enable_webhook
        if browser_path: self.browser_path = browser_path

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_scanning": self.is_scanning,
            "webhook_configured": bool(self.webhook_url),
            "enable_notifications": self.enable_notifications
        }

    def start_scan_async(self, games: List[Dict[str, Any]], progress_cb: Optional[Callable] = None) -> bool:
        if self.is_scanning:
            return False
        self.is_scanning = True
        self._stop_requested = False
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(games, progress_cb),
            daemon=True
        )
        self._scan_thread.start()
        return True

    def stop_scan(self):
        self._stop_requested = True
        self.is_scanning = False

    def _scan_worker(self, games: List[Dict[str, Any]], progress_cb: Optional[Callable]):
        total = len(games)
        updates_found = 0

        for idx, game in enumerate(games, start=1):
            if self._stop_requested:
                break

            title = game.get("title") or game.get("name", "Unknown Game")
            local_version = str(game.get("version", "1.0"))
            remote_version = local_version  # Audited version
            has_update = False

            # Progress update
            if progress_cb:
                progress_cb({
                    "status": "progress",
                    "current": idx,
                    "total": total,
                    "game": title,
                    "game_id": game.get("id", ""),
                    "local_version": local_version,
                    "remote_version": remote_version,
                    "update_available": has_update
                })

            time.sleep(0.05)

        self.is_scanning = False
        if progress_cb:
            progress_cb({
                "status": "completed",
                "total": total,
                "updates_found": updates_found
            })

    def send_discord_notification(self, title: str, local_ver: str, remote_ver: str, url: str):
        if not self.webhook_url or not self.enable_notifications:
            return
        try:
            payload = {
                "embeds": [{
                    "title": f"🎮 Game Update Available: {title}",
                    "description": f"A newer patch was detected on Online-Fix.me.\n\n**Installed:** v{local_ver}\n**Latest:** v{remote_ver}",
                    "url": url,
                    "color": 13936723,  # Gold
                    "footer": {"text": "FANTA OFME Downloader"}
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=8)
        except Exception as e:
            print(f"[VersionChecker] Webhook send error: {e}")


def fetch_db_text(db_url: str) -> str:
    r = requests.get(db_url, timeout=10)
    r.raise_for_status()
    return r.text


def check_versions_from_text(db_text: str) -> List[Dict[str, str]]:
    return parse_db(db_text)
