"""
Fanta OFME Downloader - Database Parser & Catalog Manager
Fetches, parses, indexes, caches, and searches Download-DB entries with status tracking.
"""

import os
import re
import time
import requests
from typing import List, Dict, Any, Optional


class GameEntry:
    def __init__(
        self,
        raw_id: str,
        index: int,
        title: str,
        version: str,
        host: str,
        approx_size: str,
        description: str,
        thumbnail: str,
        origin_url: str,
        main_game_url: str,
        fix_url: str,
        category: str = "General",
        installed_version: Optional[str] = None,
        is_downloaded: bool = False,
        location: Optional[str] = None
    ):
        self.id = raw_id
        self.index = index
        self.title = title
        self.version = version
        self.host = host
        self.approx_size = approx_size
        self.size_bytes = self._parse_size_bytes(approx_size)
        self.description = description
        self.thumbnail = thumbnail
        self.origin_url = origin_url
        self.main_game_url = main_game_url
        self.fix_url = fix_url
        self.category = category
        self.installed_version = installed_version
        self.is_downloaded = is_downloaded
        self.location = location

    @property
    def status_code(self) -> int:
        if not self.is_downloaded and not self.installed_version:
            return 0
        if self.installed_version:
            norm_inst = re.sub(r"^v", "", str(self.installed_version).strip().lower())
            norm_cat = re.sub(r"^v", "", str(self.version).strip().lower())
            if norm_inst != norm_cat and norm_inst != "":
                return 2
            return 1
        return 1

    @property
    def status(self) -> str:
        if not self.is_downloaded and not self.installed_version:
            return "not_downloaded"
        if self.installed_version:
            norm_inst = re.sub(r"^v", "", str(self.installed_version).strip().lower())
            norm_cat = re.sub(r"^v", "", str(self.version).strip().lower())
            if norm_inst != norm_cat and norm_inst != "":
                return "needs_update"
            return "up_to_date"
        return "downloaded"

    @staticmethod
    def _parse_size_bytes(size_str: str) -> int:
        if not size_str:
            return 0
        match = re.search(r"([\d\.]+)\s*([KMGT]?B)", size_str, re.IGNORECASE)
        if not match:
            return 0
        val = float(match.group(1))
        unit = match.group(2).upper()
        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024 ** 2,
            "GB": 1024 ** 3,
            "TB": 1024 ** 4
        }
        return int(val * multipliers.get(unit, 1))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "index": self.index,
            "title": self.title,
            "version": self.version,
            "host": self.host,
            "approx_size": self.approx_size,
            "size_bytes": self.size_bytes,
            "description": self.description,
            "thumbnail": self.thumbnail,
            "origin_url": self.origin_url,
            "main_game_url": self.main_game_url,
            "fix_url": self.fix_url,
            "category": self.category,
            "status": self.status_code,
            "status_text": self.status,
            "installed_version": self.installed_version,
            "is_downloaded": bool(self.is_downloaded or self.installed_version),
            "location": self.location
        }


class DatabaseManager:
    def __init__(self, cache_dir: str, default_url: str):
        self.cache_dir = cache_dir
        self.default_url = default_url
        self.local_db_path = os.path.join(cache_dir, "Download-DB.txt")
        self.games: List[GameEntry] = []
        self.hosts: List[str] = []
        self.last_updated: float = 0.0

    def fetch_and_load(
        self,
        url: Optional[str] = None,
        force_refresh: bool = False,
        installed_data: Optional[Dict[str, Any]] = None
    ) -> List[GameEntry]:
        target_url = url or self.default_url
        raw_text = ""

        # Check local cache validity unless force_refresh is requested
        if not force_refresh and os.path.exists(self.local_db_path):
            file_age = time.time() - os.path.getmtime(self.local_db_path)
            if file_age < 7200:
                try:
                    with open(self.local_db_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read()
                except Exception as e:
                    print(f"[Database] Cache read error: {e}")

        # Fetch remote if no text loaded yet
        if not raw_text:
            try:
                print(f"[Database] Fetching database from {target_url}...")
                resp = requests.get(target_url, timeout=8)
                resp.raise_for_status()
                raw_text = resp.text
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(self.local_db_path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(raw_text)
            except Exception as e:
                print(f"[Database] Remote fetch failed ({e}). Falling back to local cache.")
                if os.path.exists(self.local_db_path):
                    try:
                        with open(self.local_db_path, "r", encoding="utf-8", errors="ignore") as f:
                            raw_text = f.read()
                    except Exception:
                        pass
                
                # Check bundled database in package
                if not raw_text:
                    bundled_path = os.path.join(os.path.dirname(__file__), "data", "Download-DB.txt")
                    if os.path.exists(bundled_path):
                        print(f"[Database] Loading bundled database from {bundled_path}")
                        try:
                            with open(bundled_path, "r", encoding="utf-8", errors="ignore") as f:
                                raw_text = f.read()
                        except Exception as be:
                            print(f"[Database] Bundled DB read error: {be}")

        if raw_text:
            self.games = self.parse_database(raw_text, installed_data)
            self.hosts = sorted(list({g.host for g in self.games if g.host}))
            self.last_updated = time.time()

        return self.games

    @staticmethod
    def _normalize_key(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', str(s).lower())

    def _build_installed_lookup(self, installed_data: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        lookup = {}
        for k, v in (installed_data or {}).items():
            if isinstance(v, dict):
                lookup[self._normalize_key(k)] = v
        return lookup

    def parse_database(self, text: str, installed_data: Optional[Dict[str, Any]] = None) -> List[GameEntry]:
        entries: List[GameEntry] = []
        blocks = text.split("\n\n")
        lookup = self._build_installed_lookup(installed_data)
        entry_index = 0

        for block in blocks:
            lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
            if not lines:
                continue

            # Strip leading comment lines from the block
            while lines and (lines[0].startswith("#") or lines[0].startswith("=")):
                lines.pop(0)

            if not lines:
                continue

            header_line = lines[0]
            header_match = re.match(r"^([^\(]+)\s*\((.+?)\)\s*\[(.*?)\]", header_line)
            if not header_match:
                header_match = re.match(r"^(.+?)\s*\[(.*?)\]\s*\((.+?)\)", header_line)
                if header_match:
                    title = header_match.group(1).strip()
                    version = header_match.group(2).strip()
                    host = header_match.group(3).strip()
                else:
                    continue
            else:
                host = header_match.group(1).strip()
                title = header_match.group(2).strip()
                version = header_match.group(3).strip()

            fields: Dict[str, str] = {
                "approxsize": "Unknown",
                "description": "No description available.",
                "thumbnail": "",
                "origin": "",
                "maingame": "",
                "fix": ""
            }

            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip().lower()
                    v = val.strip()
                    if k in fields:
                        fields[k] = v

            raw_id = f"{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())}_{host.lower()}"
            norm_title = self._normalize_key(title)
            norm_id = self._normalize_key(raw_id)
            game_state = lookup.get(norm_id) or lookup.get(norm_title) or {}

            inst_ver = game_state.get("version") or game_state.get("installed_version")
            is_dl = bool(game_state.get("location") or game_state.get("downloaded", False) or inst_ver)
            loc = game_state.get("location")

            entry = GameEntry(
                raw_id=raw_id,
                index=entry_index,
                title=title,
                version=version,
                host=host,
                approx_size=fields["approxsize"],
                description=fields["description"],
                thumbnail=fields["thumbnail"],
                origin_url=fields["origin"],
                main_game_url=fields["maingame"],
                fix_url=fields["fix"],
                installed_version=inst_ver,
                is_downloaded=is_dl,
                location=loc
            )
            entries.append(entry)
            entry_index += 1

        return entries

    def update_installed_states(self, installed_data: Dict[str, Any]):
        lookup = self._build_installed_lookup(installed_data)
        for g in self.games:
            norm_title = self._normalize_key(g.title)
            norm_id = self._normalize_key(g.id)
            game_state = lookup.get(norm_id) or lookup.get(norm_title) or {}
            inst_ver = game_state.get("version") or game_state.get("installed_version")
            g.is_downloaded = bool(game_state.get("location") or game_state.get("downloaded", False) or inst_ver)
            g.installed_version = inst_ver
            g.location = game_state.get("location")

    def search_and_filter(
        self,
        query: str = "",
        host: str = "",
        status_filter: str = "all",
        sort_by: str = "default",
        sort_order: str = "asc"
    ) -> List[Dict[str, Any]]:
        results = list(self.games)

        # 1. Text Search
        if query:
            q = query.lower()
            results = [g for g in results if q in g.title.lower() or q in g.description.lower()]

        # 2. Host Filter
        if host and host.lower() != "all":
            results = [g for g in results if g.host.lower() == host.lower()]

        # 3. Status Filter (all, downloaded, needs_update, up_to_date)
        if status_filter and status_filter.lower() != "all":
            sf = status_filter.lower()
            if sf == "downloaded":
                results = [g for g in results if g.is_downloaded or g.installed_version]
            elif sf == "needs_update":
                results = [g for g in results if g.status == "needs_update"]
            elif sf == "up_to_date":
                results = [g for g in results if g.status == "up_to_date"]

        # 4. Sorting (default keeps database order)
        if sort_by == "title":
            results.sort(key=lambda x: x.title.lower(), reverse=(sort_order == "desc"))
        elif sort_by == "size":
            results.sort(key=lambda x: x.size_bytes, reverse=(sort_order == "desc"))
        elif sort_by == "host":
            results.sort(key=lambda x: x.host.lower(), reverse=(sort_order == "desc"))
        else:
            # Default order as in Download-DB.txt
            results.sort(key=lambda x: x.index, reverse=(sort_order == "desc"))

        return [g.to_dict() for g in results]
