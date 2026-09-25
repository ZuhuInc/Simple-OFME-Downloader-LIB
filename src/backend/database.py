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
        location: Optional[str] = None,
        parts: Optional[List[str]] = None,
        steam_url: Optional[str] = None
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
        self.parts = parts or ([main_game_url] if main_game_url else [])
        self.main_game_url = main_game_url or (self.parts[0] if self.parts else "")
        self.fix_url = fix_url
        self.category = category
        self.installed_version = installed_version
        self.is_downloaded = is_downloaded
        self.location = location
        self.steam_url = steam_url

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
            "parts": self.parts,
            "fix_url": self.fix_url,
            "category": self.category,
            "status": self.status_code,
            "status_text": self.status,
            "installed_version": self.installed_version,
            "is_downloaded": bool(self.is_downloaded or self.installed_version),
            "location": self.location,
            "steam_url": self.steam_url
        }


class DatabaseManager:
    def __init__(self, cache_dir: str, default_url: str):
        self.cache_dir = cache_dir
        self.default_url = default_url
        self.local_json_path = os.path.join(cache_dir, "Data.json")
        self.local_txt_path = os.path.join(cache_dir, "Download-DB.txt")
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
        raw_content = ""

        # 1. Check local cached Data.json
        if not force_refresh and os.path.exists(self.local_json_path):
            file_age = time.time() - os.path.getmtime(self.local_json_path)
            if file_age < 7200:
                try:
                    with open(self.local_json_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_content = f.read()
                except Exception as e:
                    print(f"[Database] Cache JSON read error: {e}")

        # 2. Fetch remote if not loaded
        if not raw_content and target_url:
            try:
                print(f"[Database] Fetching database from {target_url}...")
                resp = requests.get(target_url, timeout=8)
                resp.raise_for_status()
                raw_content = resp.text
                os.makedirs(self.cache_dir, exist_ok=True)
                save_path = self.local_json_path if raw_content.strip().startswith(("{", "[")) else self.local_txt_path
                with open(save_path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(raw_content)
            except Exception as e:
                print(f"[Database] Remote fetch failed ({e}). Falling back to bundled Data.json.")

        # 3. Check bundled Data.json in backend package
        if not raw_content:
            bundled_json = os.path.join(os.path.dirname(__file__), "data", "Data.json")
            if os.path.exists(bundled_json):
                print(f"[Database] Loading bundled JSON database from {bundled_json}")
                try:
                    with open(bundled_json, "r", encoding="utf-8", errors="ignore") as f:
                        raw_content = f.read()
                except Exception as be:
                    print(f"[Database] Bundled JSON read error: {be}")

        # 4. Fallback to bundled Download-DB.txt
        if not raw_content:
            bundled_txt = os.path.join(os.path.dirname(__file__), "data", "Download-DB.txt")
            if os.path.exists(bundled_txt):
                print(f"[Database] Loading fallback text database from {bundled_txt}")
                try:
                    with open(bundled_txt, "r", encoding="utf-8", errors="ignore") as f:
                        raw_content = f.read()
                except Exception as be:
                    print(f"[Database] Bundled TXT read error: {be}")

        if raw_content:
            self.games = self.parse_database(raw_content, installed_data)
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

    def parse_database(self, raw_input: Any, installed_data: Optional[Dict[str, Any]] = None) -> List[GameEntry]:
        import json
        entries: List[GameEntry] = []
        lookup = self._build_installed_lookup(installed_data)

        # Case A: JSON format (dict keyed by game title, or list of game dicts)
        if isinstance(raw_input, (dict, list)) or (isinstance(raw_input, str) and raw_input.strip().startswith(("{", "["))):
            try:
                parsed = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                
                # Dict keyed by title: { "PEAK": { "version": "...", ... } }
                if isinstance(parsed, dict):
                    for idx, (title, info) in enumerate(parsed.items()):
                        host = info.get("host") or info.get("Host", "GoFile")
                        raw_id = f"{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())}_{host.lower()}"
                        norm_title = self._normalize_key(title)
                        norm_id = self._normalize_key(raw_id)
                        game_state = lookup.get(norm_id) or lookup.get(norm_title) or {}

                        inst_ver = game_state.get("version") or game_state.get("installed_version")
                        is_dl = bool(game_state.get("location") or game_state.get("downloaded", False) or inst_ver)
                        loc = game_state.get("location")

                        parts_list = info.get("parts") or []
                        main_url = info.get("main_game_url") or info.get("MainGame", "") or (parts_list[0] if parts_list else "")

                        entry = GameEntry(
                            raw_id=raw_id,
                            index=idx,
                            title=title,
                            version=str(info.get("version", "1.0")),
                            host=host,
                            approx_size=info.get("approx_size") or info.get("ApproxSize", "Unknown"),
                            description=info.get("description") or info.get("Description", "No description available."),
                            thumbnail=info.get("thumbnail") or info.get("Thumbnail", ""),
                            origin_url=info.get("origin_url") or info.get("Origin", ""),
                            main_game_url=main_url,
                            fix_url=info.get("fix_url") or info.get("Fix", ""),
                            category=info.get("category", "General"),
                            installed_version=inst_ver,
                            is_downloaded=is_dl,
                            location=loc,
                            parts=parts_list if parts_list else None,
                            steam_url=game_state.get("steam_url")
                        )
                        entries.append(entry)
                    return entries

                # Array of objects: [ { "title": "PEAK", ... } ]
                elif isinstance(parsed, list):
                    for idx, item in enumerate(parsed):
                        title = item.get("title") or item.get("name", "Unknown")
                        host = item.get("host", "GoFile")
                        raw_id = item.get("id") or f"{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())}_{host.lower()}"
                        norm_title = self._normalize_key(title)
                        norm_id = self._normalize_key(raw_id)
                        game_state = lookup.get(norm_id) or lookup.get(norm_title) or {}

                        inst_ver = game_state.get("version") or game_state.get("installed_version")
                        is_dl = bool(game_state.get("location") or game_state.get("downloaded", False) or inst_ver)
                        loc = game_state.get("location")
                        parts_list = item.get("parts") or []
                        main_url = item.get("main_game_url", "") or (parts_list[0] if parts_list else "")

                        entry = GameEntry(
                            raw_id=raw_id,
                            index=idx,
                            title=title,
                            version=str(item.get("version", "1.0")),
                            host=host,
                            approx_size=item.get("approx_size", "Unknown"),
                            description=item.get("description", "No description available."),
                            thumbnail=item.get("thumbnail", ""),
                            origin_url=item.get("origin_url", ""),
                            main_game_url=main_url,
                            fix_url=item.get("fix_url", ""),
                            category=item.get("category", "General"),
                            installed_version=inst_ver,
                            is_downloaded=is_dl,
                            location=loc,
                            parts=parts_list if parts_list else None,
                            steam_url=game_state.get("steam_url")
                        )
                        entries.append(entry)
                    return entries
            except Exception as je:
                print(f"[Database] JSON parsing failed: {je}")

        # Case B: Plain Text Legacy Parser
        text = str(raw_input)
        blocks = text.split("\n\n")
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
            txt_parts = []

            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip().lower()
                    v = val.strip()
                    if k in fields:
                        fields[k] = v
                    if "part" in k:
                        part_match = re.search(r"\d+", k)
                        num = int(part_match.group()) if part_match else 1
                        txt_parts.append((num, v))

            if txt_parts:
                txt_parts.sort(key=lambda x: x[0])
                ordered_parts = [url for _, url in txt_parts]
            else:
                ordered_parts = [fields["maingame"]] if fields.get("maingame") else []

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
                approx_size=fields.get("approxsize", "Unknown"),
                description=fields.get("description", "No description available."),
                thumbnail=fields.get("thumbnail", ""),
                origin_url=fields.get("origin", ""),
                main_game_url=ordered_parts[0] if ordered_parts else fields.get("maingame", ""),
                fix_url=fields.get("fix", ""),
                category="General",
                installed_version=inst_ver,
                is_downloaded=is_dl,
                location=loc,
                parts=ordered_parts if ordered_parts else None,
                steam_url=game_state.get("steam_url")
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
            g.steam_url = game_state.get("steam_url")

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
