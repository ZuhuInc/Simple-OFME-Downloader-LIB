"""
Fanta OFME Downloader - Version Checker
Live auditing engine: scrapes Online-Fix.me and SteamRIP to verify if live releases
differ from Download-DB.txt, and triggers Discord Webhook notifications.
"""

import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Callable, Tuple


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
        self.bypass_list: List[str] = []
        self.is_scanning = False
        self._stop_requested = False
        self._scan_thread: Optional[threading.Thread] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        })

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
        if bypass_list is not None: self.bypass_list = bypass_list

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_scanning": self.is_scanning,
            "webhook_configured": bool(self.webhook_url),
            "enable_notifications": self.enable_notifications,
            "has_credentials": bool(self.username and self.password)
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

    @staticmethod
    def clean_version_string(raw: str) -> str:
        """Strips all Russian characters (Cyrillic), modifier notes, and download keywords."""
        if not raw:
            return ""
        # Strip all Cyrillic Unicode characters and everything after them
        cleaned = re.sub(r"[\u0400-\u04FF].*", "", raw).strip()
        # Strip common action keywords
        cleaned = re.sub(r"(?:Download|Free|Direct|Torrent|Online\-Fix|Fix|Repair|Steam|Hosters|Drive).*", "", cleaned, flags=re.IGNORECASE).strip()
        # Strip leading labels
        cleaned = re.sub(r"^(?:Build|v|ver|version)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.rstrip(" :;,-_").strip()
        return cleaned

    @staticmethod
    def normalize_version(ver: Any) -> str:
        """Standardizes version string for comparison (removes v, Build, whitespace)."""
        if not ver:
            return ""
        s = str(ver).strip()
        s = re.sub(r"^(?:v|ver|version|build)\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"[\s\-_]+", "", s)
        return s.lower()

    def scrape_online_version(self, origin_url: str) -> Optional[str]:
        """Scrapes the live version string from Online-Fix.me or SteamRIP page."""
        if not origin_url or not origin_url.startswith("http"):
            return None

        try:
            resp = self.session.get(origin_url, timeout=10)
            if resp.status_code != 200:
                return None

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. Online-Fix.me Parser
            if "online-fix.me" in origin_url:
                quotes = soup.find_all(class_="quote")
                for q in quotes:
                    text = q.get_text(separator=" ")
                    m = re.search(r"(?:Версия\s*игры|Версия|Version)\s*:\s*([^\n\r<\|]+)", text, re.IGNORECASE)
                    if m:
                        cleaned = self.clean_version_string(m.group(1))
                        if cleaned:
                            return cleaned

                # Fallback: regex search in page html
                m = re.search(r"Версия\s*игры\s*:\s*<b>\s*([^<]+)\s*</b>", html, re.IGNORECASE)
                if m:
                    cleaned = self.clean_version_string(m.group(1))
                    if cleaned:
                        return cleaned

            # 2. SteamRIP Parser
            elif "steamrip.com" in origin_url:
                h1 = soup.find("h1")
                if h1:
                    h1_text = h1.get_text(separator=" ")
                    m = re.search(r"\(([^\)]+)\)", h1_text)
                    if m:
                        cleaned = self.clean_version_string(m.group(1))
                        if cleaned:
                            return cleaned
                    m2 = re.search(r"(?:v|Build\s*)([\d\.\w\-]+)", h1_text, re.IGNORECASE)
                    if m2:
                        cleaned = self.clean_version_string(m2.group(1))
                        if cleaned:
                            return cleaned

            # 3. Generic title/h1 parser
            title_elem = soup.find("title")
            if title_elem:
                t_text = title_elem.get_text()
                m = re.search(r"\[([^\]]+)\]|\(([^\)]+)\)", t_text)
                if m:
                    candidate = m.group(1) or m.group(2)
                    if re.search(r"\d", candidate):
                        cleaned = self.clean_version_string(candidate)
                        if cleaned:
                            return cleaned

        except Exception as e:
            print(f"[VersionChecker] Scrape error for {origin_url}: {e}")

        return None

    def _scan_worker(self, games: List[Dict[str, Any]], progress_cb: Optional[Callable]):
        total = len(games)
        updates_found = 0
        outdated_games: List[Dict[str, Any]] = []

        print(f"[VersionChecker] Starting live audit for {total} games...")

        for idx, game in enumerate(games, start=1):
            if self._stop_requested:
                print("[VersionChecker] Scan aborted by user.")
                break

            title = game.get("title") or game.get("name", "Unknown Game")
            db_version = str(game.get("version", "")).strip()
            installed_version = game.get("installed_version")
            origin_url = game.get("origin_url") or game.get("Origin", "")

            # Check if game is bypassed
            if title in self.bypass_list:
                continue

            # Step 1: Live scrape from origin URL
            scraped_ver = self.scrape_online_version(origin_url)

            # Step 2: Compare Download-DB Version vs Live Online Version
            has_update = False
            if scraped_ver:
                norm_db = self.normalize_version(db_version)
                norm_scraped = self.normalize_version(scraped_ver)
                
                # Flag as update ONLY if live site differs from Download-DB!
                if norm_scraped and norm_db and norm_scraped != norm_db:
                    has_update = True
                    updates_found += 1
                    outdated_games.append({
                        "title": title,
                        "db_version": db_version,
                        "latest_version": scraped_ver,
                        "origin_url": origin_url,
                        "game_id": game.get("id", "")
                    })

            local_display = str(installed_version) if installed_version else "Not Installed"

            # Progress update
            if progress_cb:
                progress_cb({
                    "status": "progress",
                    "current": idx,
                    "total": total,
                    "game": title,
                    "game_id": game.get("id", ""),
                    "local_version": local_display,
                    "db_version": db_version,
                    "remote_version": scraped_ver or db_version,
                    "scraped_version": scraped_ver or "---",
                    "scraped": bool(scraped_ver),
                    "origin_url": origin_url,
                    "update_available": has_update,
                    "is_installed": bool(installed_version)
                })

            time.sleep(0.08)

        self.is_scanning = False
        print(f"[VersionChecker] Audit complete. Found {updates_found} updates.")

        # Step 3: Dispatch Discord Webhook if configured and updates were found
        if outdated_games and self.webhook_url and self.enable_notifications:
            self.send_discord_bulk_notification(outdated_games)

        if progress_cb:
            progress_cb({
                "status": "completed",
                "total": total,
                "updates_found": updates_found,
                "outdated_list": outdated_games
            })

    def send_discord_bulk_notification(self, outdated_games: List[Dict[str, Any]]):
        """Dispatches a Discord webhook embed with all outdated games found."""
        if not self.webhook_url or not self.enable_notifications:
            return

        try:
            fields = []
            for g in outdated_games[:25]:  # Discord embed field limit
                fields.append({
                    "name": f"🎮 {g['title']}",
                    "value": f"**Download-DB:** `v{g['db_version']}` ➔ **Live Online:** `v{g['latest_version']}`\n[Open Release Page]({g['origin_url']})",
                    "inline": False
                })

            payload = {
                "username": "FANTA OFME Version Auditor",
                "embeds": [{
                    "title": f"🔔 {len(outdated_games)} New Game Updates Detected Online!",
                    "description": "The following releases have newer patches published on Online-Fix / SteamRIP:",
                    "color": 16753920,  # Fanta Gold/Orange
                    "fields": fields,
                    "footer": {"text": "FANTA OFME Downloader v2.0.0"}
                }]
            }

            requests.post(self.webhook_url, json=payload, timeout=8)
            print(f"[VersionChecker] Sent Discord webhook notification for {len(outdated_games)} games.")
        except Exception as e:
            print(f"[VersionChecker] Webhook send error: {e}")
