"""
Fanta OFME Downloader - Steam Artwork Manager
Downloads official Steam library artwork (Cover, Background Hero, Logo, Wide Cover),
saves high-res assets to C:\\Users\\ZUHU\\Documents\\ZuhuProjects\\ZuhuOFME\\SteamArtwork,
and automatically injects them into Steam's config/grid/ directory for non-Steam shortcuts.
"""

import os
import re
import json
import zlib
import shutil
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

class SteamArtworkManager:
    # Valve Store / Fastly CDN Base
    STEAM_CDN_BASE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"
    STEAMGRIDDB_AUTOCOMPLETE_URL = "https://www.steamgriddb.com/api/public/search/autocomplete?term={term}"
    STEAMGRIDDB_GAME_URL = "https://www.steamgriddb.com/api/public/game/{game_id}"

    def __init__(self, steam_manager=None, custom_artwork_dir: Optional[str] = None):
        self.steam_manager = steam_manager
        
        # Priority default project folder requested by user:
        # C:\Users\ZUHU\Documents\ZuhuProjects\ZuhuOFME\SteamArtwork
        if custom_artwork_dir:
            self.artwork_dir = custom_artwork_dir
        else:
            user_docs = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\ZUHU"), "Documents")
            self.artwork_dir = os.path.join(user_docs, "ZuhuProjects", "ZuhuOFME", "SteamArtwork")
            
        os.makedirs(self.artwork_dir, exist_ok=True)

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitizes game name to be safe for Windows file paths."""
        clean = re.sub(r'[\\/*?:"<>|]', '-', str(name)).strip()
        clean = re.sub(r'-+', '-', clean)
        return clean.strip('- ')

    def _http_get_json(self, url: str, referer: str = "https://www.steamgriddb.com") -> Optional[Dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
            "Accept": "application/json, text/plain, */*"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[Artwork] HTTP JSON error for {url}: {e}", flush=True)
        return None

    def _download_file(self, url: str, target_path: str) -> bool:
        """Downloads an image URL with standard browser User-Agent to disk."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://store.steampowered.com/"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 500:  # Validate non-empty valid image
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, "wb") as f:
                            f.write(data)
                        return True
        except Exception as e:
            print(f"[Artwork] Download failed for {url}: {e}", flush=True)
        return False

    def resolve_artwork_urls(self, game_title: str, appid: Optional[str] = None) -> Dict[str, str]:
        """
        Resolves the 4 official artwork URLs:
        - Cover (Vertical 600x900)
        - Background (Hero 1920x620 / 3840x1240)
        - Logo (Transparent Title PNG)
        - WideCover (Header 920x430 / 460x215)
        """
        assets = {}
        clean_title = self.sanitize_filename(game_title)
        resolved_appid = str(appid).strip() if appid and str(appid).isdigit() else None

        # 1. Query SteamGridDB for Original Steam Assets metadata
        sgdb_data = self._fetch_steamgriddb_metadata(game_title, resolved_appid)
        if sgdb_data and "steam" in sgdb_data.get("platforms", {}):
            steam_info = sgdb_data["platforms"]["steam"]
            sgdb_appid = steam_info.get("id")
            if sgdb_appid and not resolved_appid:
                resolved_appid = str(sgdb_appid)

            meta = steam_info.get("metadata", {})
            base_cdn = f"{self.STEAM_CDN_BASE}/{resolved_appid}/"

            # Cover (library_capsule_2x or library_capsule)
            capsule_full = meta.get("library_capsule_full", {})
            if "image2x" in capsule_full and capsule_full["image2x"]:
                rel = list(capsule_full["image2x"].values())[0]
                assets["Cover"] = base_cdn + rel
            elif "image" in capsule_full and capsule_full["image"]:
                rel = list(capsule_full["image"].values())[0]
                assets["Cover"] = base_cdn + rel

            # Background (library_hero_2x or library_hero)
            hero_full = meta.get("library_hero_full", {})
            if "image2x" in hero_full and hero_full["image2x"]:
                rel = list(hero_full["image2x"].values())[0]
                assets["Background"] = base_cdn + rel
            elif "image" in hero_full and hero_full["image"]:
                rel = list(hero_full["image"].values())[0]
                assets["Background"] = base_cdn + rel

            # Logo (logo_2x or logo)
            logo_full = meta.get("library_logo_full", {})
            if "image2x" in logo_full and logo_full["image2x"]:
                rel = list(logo_full["image2x"].values())[0]
                assets["Logo"] = base_cdn + rel
            elif "image" in logo_full and logo_full["image"]:
                rel = list(logo_full["image"].values())[0]
                assets["Logo"] = base_cdn + rel

            # WideCover (header_image_full or header.jpg)
            header_full = meta.get("header_image_full", {})
            if header_full:
                rel = list(header_full.values())[0]
                assets["WideCover"] = base_cdn + rel

        # 2. Fallback to standard Steam Store unhashed patterns if any are missing
        if resolved_appid:
            std_base = f"{self.STEAM_CDN_BASE}/{resolved_appid}"
            if "Cover" not in assets:
                assets["Cover"] = f"{std_base}/library_600x900_2x.jpg"
            if "Background" not in assets:
                assets["Background"] = f"{std_base}/library_hero.jpg"
            if "Logo" not in assets:
                assets["Logo"] = f"{std_base}/logo.png"
            if "WideCover" not in assets:
                assets["WideCover"] = f"{std_base}/header.jpg"

        return assets

    def _fetch_steamgriddb_metadata(self, title: str, appid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Queries SteamGridDB public autocomplete & game API to extract official Steam artwork."""
        search_term = title
        encoded_term = urllib.parse.quote(search_term)
        search_url = self.STEAMGRIDDB_AUTOCOMPLETE_URL.format(term=encoded_term)
        
        search_res = self._http_get_json(search_url)
        if not search_res or not search_res.get("success") or not search_res.get("data"):
            # Try cleaning version numbers or subtitles
            simple_title = re.sub(r'(\s*-\s*.*|\s*v\d+.*)', '', title).strip()
            if simple_title and simple_title != title:
                search_url = self.STEAMGRIDDB_AUTOCOMPLETE_URL.format(term=urllib.parse.quote(simple_title))
                search_res = self._http_get_json(search_url)

        if not search_res or not search_res.get("data"):
            return None

        # Pick first game with steam types or best match
        candidates = search_res["data"]
        target_game = None
        for c in candidates:
            if "steam" in c.get("types", []):
                target_game = c
                break
        if not target_game and candidates:
            target_game = candidates[0]

        game_id = target_game.get("id")
        if not game_id:
            return None

        game_url = self.STEAMGRIDDB_GAME_URL.format(game_id=game_id)
        game_res = self._http_get_json(game_url, referer=f"https://www.steamgriddb.com/game/{game_id}")
        if game_res and game_res.get("success"):
            return game_res.get("data")
        return None

    def download_and_save_artwork(self, game_title: str, appid: Optional[str] = None) -> Dict[str, str]:
        """
        Downloads all 4 pieces of artwork and saves them into:
        C:\\Users\\ZUHU\\Documents\\ZuhuProjects\\ZuhuOFME\\SteamArtwork
        - <GameName>-Cover.jpg
        - <GameName>-Background.jpg
        - <GameName>-Logo.png
        - <GameName>-WideCover.jpg
        Returns mapping: { "Cover": path, "Background": path, "Logo": path, "WideCover": path }
        """
        safe_name = self.sanitize_filename(game_title)
        urls = self.resolve_artwork_urls(game_title, appid=appid)
        saved_paths = {}

        file_specs = [
            ("Cover", f"{safe_name}-Cover.jpg"),
            ("Background", f"{safe_name}-Background.jpg"),
            ("Logo", f"{safe_name}-Logo.png"),
            ("WideCover", f"{safe_name}-WideCover.jpg")
        ]

        for asset_key, filename in file_specs:
            dest_path = os.path.join(self.artwork_dir, filename)
            url = urls.get(asset_key)
            if url:
                success = self._download_file(url, dest_path)
                if success:
                    saved_paths[asset_key] = dest_path
                    print(f"[Artwork] Saved {asset_key} to {dest_path}", flush=True)
                else:
                    # If high-res URL failed, try standard fallback
                    if "_2x" in url:
                        fallback_url = url.replace("_2x", "")
                        if self._download_file(fallback_url, dest_path):
                            saved_paths[asset_key] = dest_path
            
            # If already on disk from previous download, register it
            if asset_key not in saved_paths and os.path.exists(dest_path):
                saved_paths[asset_key] = dest_path

        return saved_paths

    def apply_artwork_to_steam_grid(
        self,
        exe_path: str,
        game_name: str,
        artwork_paths: Dict[str, str],
        account_id: Optional[str] = None
    ) -> bool:
        """
        Injects the downloaded artwork into Steam's config/grid folder for the shortcut.
        Supports both 64-bit shortcut ID and 32-bit CRC appid for maximum Steam compatibility.
        """
        if not self.steam_manager or not self.steam_manager.steam_path:
            print("[Artwork] Steam installation path not found.", flush=True)
            return False

        acc_id = account_id or self.steam_manager.get_active_account_id()
        if not acc_id:
            print("[Artwork] Could not determine active Steam account ID.", flush=True)
            return False

        grid_dir = os.path.join(self.steam_manager.steam_path, "userdata", str(acc_id), "config", "grid")
        os.makedirs(grid_dir, exist_ok=True)

        clean_exe = os.path.normpath(exe_path.strip('"'))
        key = f"{clean_exe}{game_name}".encode('utf-8')
        crc = zlib.crc32(key)
        appid32 = (crc | 0x80000000) & 0xFFFFFFFF
        shortcut_id64 = ((int(appid32) & 0xFFFFFFFF) << 32) | 0x02000000

        print(f"[Artwork] Applying grid artwork for '{game_name}': appid32={appid32}, shortcut_id64={shortcut_id64}", flush=True)

        # Steam Grid Filename Mappings:
        # Cover (Vertical Capsule): <id>p.jpg
        # Background (Hero): <id>_hero.jpg
        # Logo: <id>_logo.png
        # WideCover: <id>.jpg
        mappings = [
            ("Cover", "p.jpg"),
            ("Background", "_hero.jpg"),
            ("Logo", "_logo.png"),
            ("WideCover", ".jpg")
        ]

        copied_count = 0
        for asset_key, suffix in mappings:
            src = artwork_paths.get(asset_key)
            if src and os.path.exists(src):
                # Copy for 64-bit shortcut ID (modern Steam)
                dest64 = os.path.join(grid_dir, f"{shortcut_id64}{suffix}")
                shutil.copy2(src, dest64)
                
                # Copy for 32-bit AppID (classic Steam / Big Picture)
                dest32 = os.path.join(grid_dir, f"{appid32}{suffix}")
                shutil.copy2(src, dest32)

                copied_count += 1

        print(f"[Artwork] Injected {copied_count} assets into Steam grid ({grid_dir})", flush=True)
        return copied_count > 0
