"""
Fanta OFME Downloader - Game Runners & Launch Modes Manager
Handles multi-runner games (e.g. Zelda: Ocarina of Time with NX2navi, Hookshot, Fritchii).
Fetches updates from GitHub releases, manages downloads, and resolves launch executables.
"""

import os
import re
import json
import time
import shutil
import zipfile
import tempfile
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Any, Callable

# Simple in-memory cache for GitHub release queries (TTL 15 minutes)
_GITHUB_RELEASE_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900


class RunnersManager:
    @staticmethod
    def get_latest_github_release(repo: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest release info for a GitHub repo (owner/repo).
        Uses memory caching to stay well under GitHub API rate limits.
        """
        now = time.time()
        cached = _GITHUB_RELEASE_CACHE.get(repo)
        if cached and (now - cached["timestamp"] < CACHE_TTL_SECONDS):
            return cached["data"]

        headers = {
            "User-Agent": "Fanta-OFME-Downloader",
            "Accept": "application/vnd.github.v3+json"
        }

        # Try /releases/latest first, fallback to /releases if no latest tag
        urls = [
            f"https://api.github.com/repos/{repo}/releases/latest",
            f"https://api.github.com/repos/{repo}/releases"
        ]

        release_data = None
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        raw = json.loads(resp.read().decode("utf-8"))
                        if isinstance(raw, list) and len(raw) > 0:
                            release_data = raw[0]
                        elif isinstance(raw, dict) and "tag_name" in raw:
                            release_data = raw
                        if release_data:
                            break
            except Exception as e:
                print(f"[RunnersManager] Release check notice for {repo} ({url}): {e}", flush=True)

        if release_data:
            _GITHUB_RELEASE_CACHE[repo] = {
                "timestamp": now,
                "data": release_data
            }
            return release_data

        return None

    @classmethod
    def get_runners_status(
        cls,
        game_location: str,
        runners_def: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Returns status for each runner defined for a game:
        Whether it is installed, executable exists, and latest available version.
        """
        statuses = []
        for r in runners_def:
            rid = r.get("id", "")
            rname = r.get("name", rid)
            repo = r.get("repo", "")
            rel_path = r.get("rel_path", "")
            folder = r.get("folder", "")
            args = r.get("args", [])

            # Check local install state
            raw_exe = os.path.join(game_location, rel_path) if game_location and rel_path else ""
            target_exe = os.path.normpath(raw_exe) if raw_exe else ""
            is_installed = bool(target_exe and os.path.isfile(target_exe))

            # Check alternative executable candidates in runner folder (e.g. HookshotBuilder.exe, bin/hookshot.exe)
            if not is_installed and game_location and folder:
                folder_dir = os.path.join(game_location, folder)
                alt_candidates = [
                    os.path.join(folder_dir, "hookshot.exe"),
                    os.path.join(folder_dir, "HookshotBuilder.exe"),
                    os.path.join(folder_dir, "bin", "hookshot.exe"),
                    os.path.join(folder_dir, "ocarina.exe"),
                    os.path.join(folder_dir, "lichii.exe")
                ]
                for alt in alt_candidates:
                    if os.path.isfile(alt):
                        target_exe = alt
                        is_installed = True
                        break

                if not is_installed and os.path.isdir(folder_dir):
                    # Check for any Setup, Builder, or Installer executables (e.g. NX2navi-Setup-x.x.x.exe)
                    try:
                        for f in sorted(os.listdir(folder_dir), reverse=True):
                            fl = f.lower()
                            if fl.endswith(".exe") and any(k in fl for k in ("setup", "builder", "installer", "nx2navi")):
                                target_exe = os.path.join(folder_dir, f)
                                is_installed = True
                                break
                    except Exception:
                        pass

            # Check installed version from .runner_version.json in runner folder
            folder_dir = os.path.join(game_location, folder) if game_location and folder else ""
            version_file = os.path.join(folder_dir, ".runner_version.json") if folder_dir else ""
            installed_version = ""
            if version_file and os.path.isfile(version_file):
                try:
                    with open(version_file, "r", encoding="utf-8") as vf:
                        v_data = json.load(vf)
                        installed_version = str(v_data.get("version") or "").strip()
                except Exception:
                    pass

            # Query GitHub latest version
            latest_version = ""
            download_url = ""
            asset_name = ""
            asset_size = 0

            if repo:
                rel_info = cls.get_latest_github_release(repo)
                if rel_info:
                    latest_version = rel_info.get("tag_name", "")
                    pattern = r.get("asset_pattern", r"windows.*\.zip|\.zip$")
                    for asset in rel_info.get("assets", []):
                        aname = asset.get("name", "")
                        if re.search(pattern, aname, re.IGNORECASE):
                            download_url = asset.get("browser_download_url", "")
                            asset_name = aname
                            asset_size = asset.get("size", 0)
                            break

            # Determine if an update is available
            update_available = False
            if is_installed and latest_version and installed_version:
                v_clean_inst = re.sub(r'^[vV]', '', installed_version).strip()
                v_clean_latest = re.sub(r'^[vV]', '', latest_version).strip()
                if v_clean_inst != v_clean_latest:
                    update_available = True

            subtitle = r.get("subtitle", "")

            statuses.append({
                "id": rid,
                "name": rname,
                "subtitle": subtitle,
                "repo": repo,
                "rel_path": rel_path,
                "folder": folder,
                "args": args,
                "installed": is_installed,
                "installed_version": installed_version,
                "target_exe": target_exe if is_installed else "",
                "latest_version": latest_version,
                "update_available": update_available,
                "download_url": download_url,
                "asset_name": asset_name,
                "asset_size": asset_size
            })

        return statuses

    @classmethod
    def install_or_update_runner(
        cls,
        game_location: str,
        runner_def: Dict[str, Any],
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Downloads the runner's latest GitHub release zip and extracts it into the runner's subfolder.
        """
        if not game_location or not os.path.isdir(game_location):
            return {"success": False, "error": f"Game directory '{game_location}' does not exist"}

        repo = runner_def.get("repo")
        if not repo:
            return {"success": False, "error": "Runner definition missing GitHub repository"}

        folder_name = runner_def.get("folder") or runner_def.get("id")
        target_dir = os.path.join(game_location, folder_name)
        os.makedirs(target_dir, exist_ok=True)

        rel_info = cls.get_latest_github_release(repo)
        if not rel_info:
            return {"success": False, "error": f"Could not fetch releases for {repo}"}

        tag_name = rel_info.get("tag_name", "latest")
        pattern = runner_def.get("asset_pattern", r"windows.*\.zip|\.zip$")
        matched_asset = None
        for asset in rel_info.get("assets", []):
            aname = asset.get("name", "")
            if re.search(pattern, aname, re.IGNORECASE):
                matched_asset = asset
                break

        if not matched_asset:
            return {"success": False, "error": f"No compatible Windows zip asset found in {repo} release {tag_name}"}

        download_url = matched_asset.get("browser_download_url")
        asset_name = matched_asset.get("name")
        total_size = matched_asset.get("size", 0)

        print(f"[RunnersManager] Downloading {asset_name} ({total_size} bytes) from {download_url}...", flush=True)

        # Download to a temporary file
        temp_zip = os.path.join(tempfile.gettempdir(), f"runner_{runner_def.get('id')}_{int(time.time())}.zip")
        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "Fanta-OFME-Downloader"}
            )
            downloaded = 0
            with urllib.request.urlopen(req, timeout=30) as resp, open(temp_zip, "wb") as out_f:
                chunk_size = 64 * 1024
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if total_size and progress_callback:
                        pct = int((downloaded / total_size) * 100)
                        progress_callback(f"Downloading {asset_name}: {pct}%", pct)

            if asset_name.lower().endswith(".zip"):
                print(f"[RunnersManager] Download completed. Extracting to {target_dir}...", flush=True)
                if progress_callback:
                    progress_callback("Extracting runner files...", 95)
                with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
            else:
                # Standalone executable installer (e.g. NX2navi-Setup-x.x.x.exe)
                dest_exe = os.path.join(target_dir, asset_name)
                shutil.copyfile(temp_zip, dest_exe)
                print(f"[RunnersManager] Saved standalone installer to: {dest_exe}", flush=True)

            # Persist version metadata in .runner_version.json
            version_meta_path = os.path.join(target_dir, ".runner_version.json")
            try:
                with open(version_meta_path, "w", encoding="utf-8") as vf:
                    json.dump({
                        "id": runner_def.get("id"),
                        "name": runner_def.get("name"),
                        "version": tag_name,
                        "installed_at": time.time(),
                        "repo": repo
                    }, vf, indent=2)
            except Exception as e_meta:
                print(f"[RunnersManager] Notice: Could not save .runner_version.json: {e_meta}", flush=True)

            print(f"[RunnersManager] Successfully installed {runner_def.get('name')} to {target_dir}", flush=True)
            if progress_callback:
                progress_callback("Installed successfully!", 100)

            return {
                "success": True,
                "version": tag_name,
                "installed_path": target_dir,
                "message": f"Successfully installed {runner_def.get('name')} ({tag_name})!"
            }

        except Exception as e:
            print(f"[RunnersManager] Install error: {e}", flush=True)
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
