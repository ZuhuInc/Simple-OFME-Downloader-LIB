"""
Fanta OFME Downloader - Steam Achievements Engine & Local Watcher
Fetches official Steam achievement schemas directly from Steam CDN,
monitors local game emulator save locations (Goldberg, Online-Fix, etc.),
and provides real-time unlock notifications.
"""

import os
import re
import sys
import json
import time
import shutil
import urllib.request
import urllib.parse
import threading
from typing import Dict, Any, List, Optional, Callable


class AchievementManager:
    STEAM_COMMUNITY_STATS_URL = "https://steamcommunity.com/stats/{appid}/achievements/?l=english"
    STEAM_STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=US"
    STEAM_ICON_BASE = "https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/{appid}/{icon}"

    def __init__(self, config=None, socketio=None):
        self.config = config
        self.socketio = socketio
        self.callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # Folders for persistent data
        data_dir = getattr(config, 'data_folder', os.path.expanduser("~/.fanta_ofme"))
        self.cache_dir = os.path.join(data_dir, "achievements_cache")
        self.user_data_dir = os.path.join(data_dir, "user_achievements")
        self.appid_map_path = os.path.join(self.cache_dir, "appid_map.json")
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.user_data_dir, exist_ok=True)

        # In-memory caches
        self._schema_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._appid_cache: Dict[str, str] = {}
        self._last_checked_state: Dict[str, set] = {}

        # Load persisted AppID map
        if os.path.exists(self.appid_map_path):
            try:
                with open(self.appid_map_path, "r", encoding="utf-8") as f:
                    self._appid_cache.update(json.load(f))
            except Exception:
                pass

        # Background watcher thread
        self._running = True
        self._watcher_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._watcher_thread.start()

    def set_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self.callback = cb

    def _save_appid_cache(self):
        try:
            with open(self.appid_map_path, "w", encoding="utf-8") as f:
                json.dump(self._appid_cache, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # AppID Resolution
    # -------------------------------------------------------------------------
    def resolve_appid(self, title: str, game_data: Optional[Dict[str, Any]] = None, allow_network: bool = True) -> Optional[str]:
        """Resolves the official Steam AppID for a given game."""
        if not title:
            return None

        clean_title = title.strip()
        if clean_title in self._appid_cache:
            return self._appid_cache[clean_title]

        # 1. Check explicit steam_appid in game_data
        if game_data and isinstance(game_data, dict):
            explicit = str(game_data.get("steam_appid", "")).strip()
            if explicit.isdigit():
                self._appid_cache[clean_title] = explicit
                self._save_appid_cache()
                return explicit

            # 2. Check thumbnail URL (many entries have .../apps/<appid>/...)
            thumb = str(game_data.get("thumbnail", ""))
            m = re.search(r'/apps/(\d+)/', thumb)
            if m:
                found_id = m.group(1)
                self._appid_cache[clean_title] = found_id
                self._save_appid_cache()
                return found_id

            # 3. Check origin_url or version if it's numeric appid
            origin = str(game_data.get("origin_url", ""))
            m_origin = re.search(r'/app/(\d+)', origin)
            if m_origin:
                found_id = m_origin.group(1)
                self._appid_cache[clean_title] = found_id
                self._save_appid_cache()
                return found_id

        if not allow_network:
            return None

        # 4. Search Steam Store API
        try:
            encoded_term = urllib.parse.quote(clean_title)
            url = self.STEAM_STORE_SEARCH_URL.format(term=encoded_term)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                items = data.get("items", [])
                if items:
                    matched_id = str(items[0].get("id"))
                    if matched_id.isdigit():
                        self._appid_cache[clean_title] = matched_id
                        self._save_appid_cache()
                        return matched_id
        except Exception as e:
            print(f"[Achievements] Steam search error for '{clean_title}': {e}", flush=True)

        return None

    # -------------------------------------------------------------------------
    # Schema Fetching & Caching
    # -------------------------------------------------------------------------
    def get_schema(self, appid: str, allow_network: bool = True) -> List[Dict[str, Any]]:
        """Fetches the official list of achievements for a game by AppID."""
        appid = str(appid).strip()
        if not appid or not appid.isdigit():
            return []

        if appid in self._schema_cache:
            return self._schema_cache[appid]

        # 1. Check disk cache
        cache_file = os.path.join(self.cache_dir, f"{appid}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, list) and len(cached_data) > 0:
                        self._schema_cache[appid] = cached_data
                        return cached_data
            except Exception:
                pass

        if not allow_network:
            return []

        # 2. Fetch directly from Steam Community stats page (React Query hydration data)
        achievements = self._fetch_schema_from_steam(appid)
        if achievements:
            self._schema_cache[appid] = achievements
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(achievements, f, indent=2)
            except Exception as e:
                print(f"[Achievements] Cache write error for appid {appid}: {e}", flush=True)

        return achievements

    def _fetch_schema_from_steam(self, appid: str) -> List[Dict[str, Any]]:
        url = self.STEAM_COMMUNITY_STATS_URL.format(appid=appid)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            # Look for React Query SSR hydration script
            m = re.search(r'<script[^>]*>(.*?loaderData.*?)</script>', html, re.DOTALL)
            if not m:
                # Try broader search for queryData
                m = re.search(r'("renderContext":\{.*?"queryData":".*?"\})', html)
                if not m:
                    return []
                script_text = "{" + m.group(1) + "}"
            else:
                script_text = m.group(1)

            data = json.loads(script_text)
            query_data_raw = data.get("renderContext", {}).get("queryData", "")
            if not query_data_raw:
                return []

            query_data = json.loads(query_data_raw)
            queries = query_data.get("queries", [])
            for q in queries:
                key = q.get("queryKey", [])
                if len(key) >= 2 and key[0] == "achievements" and str(key[1]) == str(appid):
                    state_data = q.get("state", {}).get("data", {})
                    groups = state_data.get("groups", [])
                    for g in groups:
                        raw_achs = g.get("achievements", [])
                        if raw_achs:
                            result = []
                            for a in raw_achs:
                                api_name = a.get("api_name", "")
                                if not api_name:
                                    continue
                                icon_achieved = a.get("icon_achieved", "")
                                icon_unachieved = a.get("icon_unachieved", "")
                                result.append({
                                    "api_name": api_name,
                                    "name": a.get("name") or api_name,
                                    "description": a.get("description") or "",
                                    "hidden": bool(a.get("hidden", False)),
                                    "icon": self.STEAM_ICON_BASE.format(appid=appid, icon=icon_achieved) if icon_achieved else "",
                                    "icon_gray": self.STEAM_ICON_BASE.format(appid=appid, icon=icon_unachieved) if icon_unachieved else "",
                                    "min_progress": a.get("min_progress"),
                                    "max_progress": a.get("max_progress")
                                })
                            return result
        except Exception as e:
            print(f"[Achievements] Error fetching schema for {appid}: {e}", flush=True)

        return []

    # -------------------------------------------------------------------------
    # Local Unlocks Management
    # -------------------------------------------------------------------------
    def get_user_unlocks(self, appid: str) -> Dict[str, Dict[str, Any]]:
        """Returns map of unlocked achievements for an appid: { api_name: { unlocked_at: timestamp, ... } }"""
        user_file = os.path.join(self.user_data_dir, f"{appid}.json")
        unlocks = {}
        if os.path.exists(user_file):
            try:
                with open(user_file, "r", encoding="utf-8") as f:
                    unlocks = json.load(f)
            except Exception:
                unlocks = {}

        # Also inspect local emulator files and merge
        emu_unlocks = self._scan_emulator_unlocks(appid)
        changed = False
        for api_name, info in emu_unlocks.items():
            if api_name not in unlocks:
                unlocks[api_name] = info
                changed = True

        if changed:
            self._save_user_unlocks(appid, unlocks)

        return unlocks

    def _save_user_unlocks(self, appid: str, unlocks: Dict[str, Any]):
        user_file = os.path.join(self.user_data_dir, f"{appid}.json")
        try:
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(unlocks, f, indent=2)
        except Exception as e:
            print(f"[Achievements] Error saving user unlocks for {appid}: {e}", flush=True)

    def _scan_emulator_unlocks(self, appid: str) -> Dict[str, Dict[str, Any]]:
        """Scans Goldberg, Online-Fix, RUNE, CODEX, and local game folders for unlocked achievements."""
        found = {}
        candidates = []

        # 1. Goldberg SteamEmu (%APPDATA%)
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(os.path.join(appdata, "Goldberg SteamEmu Saves", appid, "achievements.json"))

        # 2. Public Documents: OnlineFix, RUNE, CODEX
        public_docs = os.environ.get("PUBLIC", "")
        if public_docs:
            candidates.append(os.path.join(public_docs, "Documents", "OnlineFix", appid, "Stats", "Achievements.ini"))
            candidates.append(os.path.join(public_docs, "Documents", "OnlineFix", appid, "Stats", "achievements.ini"))
            candidates.append(os.path.join(public_docs, "Documents", "OnlineFix", appid, "Stats", "achievements.json"))
            candidates.append(os.path.join(public_docs, "Documents", "Steam", "RUNE", appid, "achievements.ini"))
            candidates.append(os.path.join(public_docs, "Documents", "Steam", "CODEX", appid, "achievements.ini"))

        # 3. Check inside installed game folder if known
        if self.config and getattr(self.config, 'data', None):
            for t, inf in self.config.data.items():
                if isinstance(inf, dict):
                    loc = inf.get("location")
                    if loc and os.path.exists(loc):
                        candidates.append(os.path.join(loc, "steam_settings", "stats", "achievements.json"))
                        candidates.append(os.path.join(loc, "achievements.ini"))

        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                if path.endswith(".json"):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("name"):
                                if item.get("earned", True):
                                    found[item["name"]] = {
                                        "unlocked_at": item.get("earned_time") or int(time.time()),
                                        "source": "emulator"
                                    }
                    elif isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, dict):
                                if v.get("earned", True):
                                    found[k] = {
                                        "unlocked_at": v.get("earned_time") or int(time.time()),
                                        "source": "emulator"
                                    }
                            elif isinstance(v, (int, float)):
                                found[k] = {
                                    "unlocked_at": int(v),
                                    "source": "emulator"
                                }
                elif path.endswith(".ini"):
                    # Parse INI sections (RUNE, CODEX, OnlineFix)
                    current_section = None
                    section_data = {}

                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            raw_line = line.strip()
                            if not raw_line or raw_line.startswith(("#", ";")):
                                continue
                            if raw_line.startswith("[") and raw_line.endswith("]"):
                                if current_section and current_section.lower() not in ["steamachievements", "settings"]:
                                    achieved = section_data.get("achieved", section_data.get("earned", ""))
                                    if achieved in ["1", "true", "True"]:
                                        ts = section_data.get("unlocktime", section_data.get("timestamp", ""))
                                        found[current_section] = {
                                            "unlocked_at": int(ts) if ts and str(ts).isdigit() else int(time.time()),
                                            "source": "emulator"
                                        }
                                current_section = raw_line[1:-1].strip()
                                section_data = {}
                            elif "=" in raw_line:
                                k, v = raw_line.split("=", 1)
                                section_data[k.strip().lower()] = v.strip()

                        # Check last section
                        if current_section and current_section.lower() not in ["steamachievements", "settings"]:
                            achieved = section_data.get("achieved", section_data.get("earned", ""))
                            if achieved in ["1", "true", "True"]:
                                ts = section_data.get("unlocktime", section_data.get("timestamp", ""))
                                found[current_section] = {
                                    "unlocked_at": int(ts) if ts and str(ts).isdigit() else int(time.time()),
                                    "source": "emulator"
                                }
            except Exception as e:
                print(f"[Achievements] Error scanning {path}: {e}", flush=True)

        return found

    # -------------------------------------------------------------------------
    # Full Game Progress API
    # -------------------------------------------------------------------------
    def get_game_achievements(self, title: str, appid: Optional[str] = None, game_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Returns the full achievement list with lock/unlock status for a game."""
        resolved_id = appid or self.resolve_appid(title, game_data=game_data)
        if not resolved_id:
            return {
                "title": title,
                "appid": None,
                "total": 0,
                "unlocked_count": 0,
                "percentage": 0,
                "achievements": [],
                "error": "Steam AppID could not be resolved for this game."
            }

        schema = self.get_schema(resolved_id)
        unlocks = self.get_user_unlocks(resolved_id)

        achievements_list = []
        unlocked_count = 0

        for item in schema:
            api_name = item.get("api_name")
            is_unlocked = api_name in unlocks
            unlock_info = unlocks.get(api_name, {})

            if is_unlocked:
                unlocked_count += 1

            achievements_list.append({
                "api_name": api_name,
                "name": item.get("name"),
                "description": item.get("description"),
                "hidden": item.get("hidden", False),
                "unlocked": is_unlocked,
                "unlocked_at": unlock_info.get("unlocked_at"),
                "icon": item.get("icon"),
                "icon_gray": item.get("icon_gray")
            })

        total = len(achievements_list)
        percentage = round((unlocked_count / total * 100), 1) if total > 0 else 0

        return {
            "title": title,
            "appid": resolved_id,
            "total": total,
            "unlocked_count": unlocked_count,
            "percentage": percentage,
            "achievements": achievements_list
        }

    def get_installed_summary(self, installed_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Returns achievement progress summaries for all installed games quickly."""
        summaries = []
        games_to_warmup = []

        for title, info in installed_dict.items():
            appid = self.resolve_appid(title, game_data=info, allow_network=False)
            schema = self.get_schema(appid, allow_network=False) if appid else []
            unlocks = self.get_user_unlocks(appid) if appid else {}

            total = len(schema)
            unlocked_count = sum(1 for a in schema if a.get("api_name") in unlocks)
            percentage = round((unlocked_count / total * 100), 1) if total > 0 else 0

            summaries.append({
                "title": title,
                "appid": appid,
                "thumbnail": info.get("thumbnail", ""),
                "version": info.get("version", ""),
                "total": total,
                "unlocked_count": unlocked_count,
                "percentage": percentage
            })

            if not appid or not schema:
                games_to_warmup.append((title, info))

        # Sort: games with progress first, then by title
        summaries.sort(key=lambda x: (x["unlocked_count"] == 0 and x["total"] == 0, -x["percentage"], x["title"]))

        # Background thread to pre-resolve schemas for any unknown games without blocking response
        if games_to_warmup:
            def _async_warmup():
                for t, inf in games_to_warmup[:15]:  # Batch first 15
                    try:
                        aid = self.resolve_appid(t, game_data=inf, allow_network=True)
                        if aid:
                            self.get_schema(aid, allow_network=True)
                    except Exception:
                        pass
            threading.Thread(target=_async_warmup, daemon=True).start()

        return summaries

    # -------------------------------------------------------------------------
    # Manual Trigger & Testing
    # -------------------------------------------------------------------------
    def trigger_test_unlock(self, title: str, appid: Optional[str] = None, api_name: Optional[str] = None) -> Dict[str, Any]:
        """Triggers a test achievement unlock for instant preview and sound testing."""
        resolved_id = appid or self.resolve_appid(title)
        if not resolved_id:
            resolved_id = "480"  # Fallback Spacewar for demo

        schema = self.get_schema(resolved_id)
        target_ach = None

        if schema:
            if api_name:
                for a in schema:
                    if a.get("api_name") == api_name:
                        target_ach = a
                        break
            if not target_ach:
                # Pick first locked, or first
                unlocks = self.get_user_unlocks(resolved_id)
                for a in schema:
                    if a.get("api_name") not in unlocks:
                        target_ach = a
                        break
                if not target_ach:
                    target_ach = schema[0]

        if not target_ach:
            target_ach = {
                "api_name": "FANTA_POP_TOP",
                "name": "Pop The Top!",
                "description": "Cracked open a refreshing Fanta OFME achievement test.",
                "icon": "https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/252490/8dde5848abac85e61a376bcadc2a6f267c909324.jpg",
                "icon_gray": "https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/252490/dabac537e5d033aef775c31dc402f5cd3e598dbb.jpg"
            }

        # Do NOT save unlock for tests — simulations are purely preview events
        now_ts = int(time.time())

        event_payload = {
            "game_title": title or "Fanta Game",
            "appid": resolved_id,
            "api_name": target_ach["api_name"],
            "name": target_ach.get("name"),
            "description": target_ach.get("description"),
            "icon": target_ach.get("icon"),
            "unlocked_at": now_ts,
            "is_test": True
        }

        if self.callback:
            self.callback(event_payload)
        elif self.socketio:
            self.socketio.emit("achievement_unlocked", event_payload)

        return {"success": True, "achievement": event_payload}

    def reset_game_unlocks(self, title: str, appid: Optional[str] = None) -> Dict[str, Any]:
        """Resets user unlocks for a specific game (useful for testing)."""
        resolved_id = appid or self.resolve_appid(title)
        if not resolved_id:
            return {"success": False, "error": "AppID not resolved"}

        user_file = os.path.join(self.user_data_dir, f"{resolved_id}.json")
        if os.path.exists(user_file):
            try:
                os.remove(user_file)
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "message": f"Reset unlocks for {title} (AppID: {resolved_id})"}

    # -------------------------------------------------------------------------
    # Background Process & Save Watcher
    # -------------------------------------------------------------------------
    def _monitor_loop(self):
        """Monitors local save files for new achievements while games are running."""
        while self._running:
            time.sleep(3)
            try:
                if not self.config or not getattr(self.config, 'data', None):
                    continue

                installed_data = self.config.data
                for title, info in installed_data.items():
                    appid = self.resolve_appid(title, game_data=info)
                    if not appid:
                        continue

                    # Check emulator save file
                    current_emu_unlocks = self._scan_emulator_unlocks(appid)
                    if not current_emu_unlocks:
                        continue

                    known_unlocks = self.get_user_unlocks(appid)
                    schema = self.get_schema(appid)
                    schema_map = {a.get("api_name"): a for a in schema}

                    for api_name, unlock_data in current_emu_unlocks.items():
                        if api_name not in known_unlocks:
                            # Brand new unlock detected!
                            known_unlocks[api_name] = unlock_data
                            self._save_user_unlocks(appid, known_unlocks)

                            ach_meta = schema_map.get(api_name, {})
                            payload = {
                                "game_title": title,
                                "appid": appid,
                                "api_name": api_name,
                                "name": ach_meta.get("name") or api_name,
                                "description": ach_meta.get("description") or "",
                                "icon": ach_meta.get("icon") or "",
                                "unlocked_at": unlock_data.get("unlocked_at", int(time.time()))
                            }

                            print(f"[Achievements] Real-time Unlock: {title} -> {payload['name']}", flush=True)
                            if self.callback:
                                self.callback(payload)
                            elif self.socketio:
                                self.socketio.emit("achievement_unlocked", payload)
            except Exception as e:
                # Keep monitor thread resilient
                pass

    def stop(self):
        self._running = False
