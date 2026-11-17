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
    PRIMARY_EXE_CANDIDATES = (
        "hookshot.exe",
        os.path.join("bin", "hookshot.exe"),
        "longshot.exe",
        "Longshot.exe",
        os.path.join("bin", "longshot.exe"),
        "ocarina.exe",
        "lichii.exe",
    )
    BUILDER_EXE_CANDIDATES = (
        "TriforceSetup.exe",
        "HookshotBuilder.exe",
        "LongshotBuilder.exe",
        "LongshotLauncher.exe",
    )
    FALLBACK_EXE_KEYWORDS = (
        "builder",
        "launcher",
        "setup",
        "installer",
        "triforce",
        "nx2navi",
        "longshot",
        "hookshot",
    )

    @staticmethod
    def get_release_page_url(repo: str) -> str:
        """Builds the human-facing releases page URL for GitHub or self-hosted Gitea/Forgejo repos."""
        clean = (repo or "").strip().rstrip("/")
        if not clean:
            return ""
        if clean.startswith(("http://", "https://")):
            if "git.triforceproject.com" in clean.lower() and clean.lower().endswith("/triforce/source"):
                return clean
            clean = re.sub(r"/releases/?$", "", clean, flags=re.IGNORECASE).rstrip("/")
            return f"{clean}/releases"
        clean = clean.lstrip("/")
        return f"https://github.com/{clean}/releases"

    @staticmethod
    def _build_api_urls(repo: str):
        """Returns (api_urls, headers) for GitHub or Gitea/Forgejo release APIs."""
        clean = (repo or "").strip().rstrip("/")
        if clean.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(clean)
            netloc = parsed.netloc.lower()
            repo_path = re.sub(r"/releases/?$", "", parsed.path, flags=re.IGNORECASE).strip("/")
            if "github.com" in netloc:
                return (
                    [
                        f"https://api.github.com/repos/{repo_path}/releases/latest",
                        f"https://api.github.com/repos/{repo_path}/releases",
                    ],
                    {
                        "User-Agent": "Fanta-OFME-Downloader",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            api_urls = [
                f"{base_url}/api/v1/repos/{repo_path}/releases",
                f"{base_url}/api/v1/repos/{repo_path}/releases/latest",
            ]
            if "git.triforceproject.com" in netloc and repo_path.lower() == "triforce/source":
                api_urls = [
                    f"{base_url}/api/v1/repos/triforce/downloads/releases",
                    f"{base_url}/api/v1/repos/triforce/downloads/releases/latest",
                ] + api_urls
            return (
                api_urls,
                {
                    "User-Agent": "Fanta-OFME-Downloader",
                    "Accept": "application/json",
                },
            )

        repo_path = clean.strip("/")
        return (
            [
                f"https://api.github.com/repos/{repo_path}/releases/latest",
                f"https://api.github.com/repos/{repo_path}/releases",
            ],
            {
                "User-Agent": "Fanta-OFME-Downloader",
                "Accept": "application/vnd.github.v3+json",
            },
        )

    @staticmethod
    def _select_release_from_list(releases: List[Dict[str, Any]], asset_pattern: Optional[str]) -> Optional[Dict[str, Any]]:
        """Picks the first real (non-nightly) release matching asset_pattern, falling back to Windows binary assets or raw[0]."""
        if not releases:
            return None
        real_releases = [
            r for r in releases
            if "nightly" not in str(r.get("tag_name") or "").lower()
            and "nightly" not in str(r.get("name") or "").lower()
        ]
        pool = real_releases if real_releases else releases

        if asset_pattern:
            for rel in pool:
                for asset in rel.get("assets", []) or []:
                    if re.search(asset_pattern, asset.get("name", ""), re.IGNORECASE):
                        return rel
            for rel in pool:
                for asset in rel.get("assets", []) or []:
                    if re.search(r'(?:windows|win64|win-x64).*\.(?:zip|exe)$|\.exe$', asset.get("name", ""), re.IGNORECASE):
                        return rel
        for rel in pool:
            if rel.get("assets"):
                return rel
        return pool[0] if pool else None

    @staticmethod
    def get_latest_github_release(repo: str, asset_pattern: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest release info for a GitHub or self-hosted Gitea/Forgejo repo.
        Uses memory caching to stay well under API rate limits.
        """
        now = time.time()
        cache_key = f"{repo}::{asset_pattern or ''}"
        cached = _GITHUB_RELEASE_CACHE.get(cache_key)
        if cached and (now - cached["timestamp"] < CACHE_TTL_SECONDS):
            return cached["data"]

        urls, headers = RunnersManager._build_api_urls(repo)

        release_data = None
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        raw = json.loads(resp.read().decode("utf-8"))
                        if isinstance(raw, list) and len(raw) > 0:
                            release_data = RunnersManager._select_release_from_list(raw, asset_pattern)
                        elif isinstance(raw, dict) and "tag_name" in raw:
                            tag_l = str(raw.get("tag_name") or "").lower()
                            name_l = str(raw.get("name") or "").lower()
                            if "nightly" not in tag_l and "nightly" not in name_l:
                                if asset_pattern:
                                    has_match = any(
                                        re.search(asset_pattern, a.get("name", ""), re.IGNORECASE)
                                        for a in (raw.get("assets", []) or [])
                                    )
                                    if has_match:
                                        release_data = raw
                                else:
                                    release_data = raw
                        if release_data:
                            break
            except Exception as e:
                print(f"[RunnersManager] Release check notice for {repo} ({url}): {e}", flush=True)

        if release_data:
            _GITHUB_RELEASE_CACHE[cache_key] = {
                "timestamp": now,
                "data": release_data
            }
            return release_data

        return None

    @classmethod
    def _candidate_game_bases(cls, game_location: str) -> List[str]:
        if not game_location or not os.path.isdir(game_location):
            return []
        bases = [os.path.normpath(game_location)]
        games2_sub = os.path.join(game_location, "GAMES2")
        if os.path.isdir(games2_sub):
            bases.append(os.path.normpath(games2_sub))
        for b in list(bases):
            try:
                for entry in sorted(os.listdir(b)):
                    sub = os.path.join(b, entry)
                    if os.path.isdir(sub) and not entry.startswith((".", "_")):
                        norm_sub = os.path.normpath(sub)
                        if norm_sub not in bases:
                            bases.append(norm_sub)
            except Exception:
                pass
        return bases

    @classmethod
    def resolve_runner_launch_options(cls, game_location: str, runner_def: Dict[str, Any]) -> str:
        raw_args = runner_def.get("args", []) or []
        if not raw_args:
            return ""
        bases = cls._candidate_game_bases(game_location) if game_location else []
        resolved_parts: List[str] = []
        for arg in raw_args:
            arg_str = str(arg)
            if isinstance(arg, str) and not arg.startswith("-") and not os.path.isabs(arg) and bases:
                found = ""
                for base in bases:
                    cand = os.path.normpath(os.path.join(base, arg))
                    if os.path.exists(cand):
                        found = cand
                        break
                if not found:
                    found = os.path.normpath(os.path.join(bases[0], arg))
                resolved_parts.append(f'"{found}"' if " " in found else found)
            else:
                resolved_parts.append(f'"{arg_str}"' if (" " in arg_str and not arg_str.startswith("-")) else arg_str)
        return " ".join(resolved_parts)

    @classmethod
    def _is_builder_name(cls, exe_path_or_name: str) -> bool:
        bname = os.path.basename(str(exe_path_or_name or "")).lower()
        if not bname:
            return False
        if any(b.lower() == bname for b in cls.BUILDER_EXE_CANDIDATES):
            return True
        return any(k in bname for k in ("builder", "setup", "installer"))

    @classmethod
    def _find_runner_folder_dir(cls, game_location: str, runner_def: Dict[str, Any]) -> str:
        folder = runner_def.get("folder") or runner_def.get("id") or ""
        rel_path = runner_def.get("rel_path", "")
        if not game_location:
            return ""
        bases = cls._candidate_game_bases(game_location)
        folder_candidates = [folder] if folder else []
        if folder and folder.lower() == "nx2navi":
            folder_candidates.append("Triforce")
        if folder_candidates:
            for cand_name in folder_candidates:
                for base_loc in bases:
                    cand = os.path.normpath(os.path.join(base_loc, cand_name))
                    if os.path.isdir(cand):
                        return cand
                    # Case-insensitive directory check
                    try:
                        for entry in os.listdir(base_loc):
                            sub = os.path.join(base_loc, entry)
                            if os.path.isdir(sub) and entry.lower() == cand_name.lower():
                                return os.path.normpath(sub)
                    except Exception:
                        pass
            return os.path.normpath(os.path.join(game_location, folder_candidates[0]))
        if rel_path:
            return os.path.normpath(os.path.dirname(os.path.join(game_location, rel_path)))
        return os.path.normpath(game_location)

    @classmethod
    def _walk_runner_exes(cls, folder_dir: str) -> List[str]:
        if not folder_dir or not os.path.isdir(folder_dir):
            return []
        discovered: List[str] = []
        base_depth = folder_dir.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(folder_dir):
            dirs[:] = sorted([d for d in dirs if not d.startswith((".", "_"))])
            cur_depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if cur_depth > 3:
                dirs[:] = []
                continue
            for f in sorted(files):
                fl = f.lower()
                if fl.endswith(".exe") and not fl.startswith(("unins", "vcredist")) and "crash" not in fl:
                    discovered.append(os.path.normpath(os.path.join(root, f)))
        return discovered

    @classmethod
    def find_builder_executable(cls, game_location: str, runner_def: Dict[str, Any]) -> str:
        """
        Resolves the builder/setup executable (e.g. TriforceSetup.exe, HookshotBuilder.exe, LongshotBuilder.exe)
        for a runner within game_location, preferring the most recently modified match.
        """
        if not game_location or not runner_def:
            return ""
        folder = runner_def.get("folder", "")
        rel_path = runner_def.get("rel_path", "")
        bases = cls._candidate_game_bases(game_location)
        candidate_dirs: List[str] = []
        for base_loc in bases:
            folder_dir = os.path.normpath(os.path.join(base_loc, folder)) if folder else (
                os.path.dirname(os.path.join(base_loc, rel_path)) if rel_path else ""
            )
            if folder_dir:
                candidate_dirs.append(folder_dir)
        resolved_dir = cls._find_runner_folder_dir(game_location, runner_def)
        if resolved_dir and os.path.normcase(resolved_dir) not in {os.path.normcase(d) for d in candidate_dirs}:
            candidate_dirs.append(resolved_dir)

        discovered_all: List[str] = []
        seen = set()

        for folder_dir in candidate_dirs:
            for p in cls._walk_runner_exes(folder_dir):
                lp = p.lower()
                if lp not in seen and cls._is_builder_name(p):
                    seen.add(lp)
                    discovered_all.append(p)

        if not discovered_all:
            return ""

        builder_names = [os.path.basename(c).lower() for c in cls.BUILDER_EXE_CANDIDATES]

        def _score(p: str):
            bn = os.path.basename(p).lower()
            is_known = bn in builder_names
            prio = builder_names.index(bn) if is_known else 99
            try:
                mtime = os.path.getmtime(p)
            except Exception:
                mtime = 0.0
            return (0 if is_known else 1, prio, -mtime)

        discovered_all.sort(key=_score)
        return discovered_all[0]

    @classmethod
    def find_primary_game_executable(cls, game_location: str, runner_def: Dict[str, Any], saved_exe: str = "") -> str:
        """
        Resolves only the built/actual game executable (never a builder/setup/installer binary).
        """
        if saved_exe and os.path.isfile(saved_exe) and not cls._is_builder_name(saved_exe):
            return os.path.normpath(saved_exe)
        if not game_location or not runner_def:
            return ""

        rel_path = runner_def.get("rel_path", "")
        folder = runner_def.get("folder", "")
        target_basename = os.path.basename(rel_path).lower() if rel_path else ""
        bases = cls._candidate_game_bases(game_location)
        primary_names = [os.path.basename(c).lower() for c in cls.PRIMARY_EXE_CANDIDATES]
        candidate_dirs: List[str] = []

        for base_loc in bases:
            raw_exe = os.path.normpath(os.path.join(base_loc, rel_path)) if rel_path else ""
            if raw_exe and os.path.isfile(raw_exe) and not cls._is_builder_name(raw_exe):
                return raw_exe

            folder_dir = os.path.normpath(os.path.join(base_loc, folder)) if folder else (
                os.path.dirname(raw_exe) if raw_exe else ""
            )
            if folder_dir:
                candidate_dirs.append(folder_dir)

        resolved_dir = cls._find_runner_folder_dir(game_location, runner_def)
        if resolved_dir and os.path.normcase(resolved_dir) not in {os.path.normcase(d) for d in candidate_dirs}:
            candidate_dirs.append(resolved_dir)

        for folder_dir in candidate_dirs:
            discovered_exes = [p for p in cls._walk_runner_exes(folder_dir) if not cls._is_builder_name(p)]
            if not discovered_exes:
                continue

            if target_basename and not cls._is_builder_name(target_basename):
                for p in discovered_exes:
                    if os.path.basename(p).lower() == target_basename:
                        return p

            for pname in primary_names:
                for p in discovered_exes:
                    if os.path.basename(p).lower() == pname:
                        return p

        return ""

    @staticmethod
    def _infer_local_version(folder_dir: str) -> str:
        """Scans runner-specific subfolder or .exe/.zip names inside folder_dir for a version string."""
        if not folder_dir or not os.path.isdir(folder_dir):
            return ""
        runner_keywords = ("nx2navi", "triforce", "hookshot", "longshot", "fritchii", "lichii", "ocarina")

        def _extract_ver(name: str, is_dir: bool) -> str:
            nl = name.lower()
            if nl.startswith((".", "_")):
                return ""
            if not is_dir and not nl.endswith((".exe", ".zip")):
                return ""
            if not any(k in nl for k in runner_keywords):
                return ""
            m = re.search(r'(?:^|[-_\s])(v?\d+\.\d+(?:\.\d+)?(?:-rc\.?\d+)?)', name, re.IGNORECASE)
            if m:
                return m.group(1)
            return ""

        try:
            entries = sorted(os.listdir(folder_dir))
            for entry in entries:
                full_p = os.path.join(folder_dir, entry)
                ver = _extract_ver(entry, os.path.isdir(full_p))
                if ver:
                    return ver
            for entry in entries:
                sub = os.path.join(folder_dir, entry)
                if os.path.isdir(sub) and not entry.startswith((".", "_")):
                    for sub_entry in sorted(os.listdir(sub)):
                        sub_p = os.path.join(sub, sub_entry)
                        ver = _extract_ver(sub_entry, os.path.isdir(sub_p))
                        if ver:
                            return ver
        except Exception:
            pass
        return ""

    @staticmethod
    def _versions_differ(installed_ver: str, latest_ver: str) -> bool:
        if not latest_ver:
            return False
        if not installed_ver or installed_ver.strip().lower() == "bundled":
            return True
        v_inst = re.sub(r'^[vV]+', '', installed_ver).strip().lower()
        v_latest = re.sub(r'^[vV]+', '', latest_ver).strip().lower()
        return v_inst != v_latest

    @classmethod
    def mark_builder_completed(cls, game_location: str, runner_def: Dict[str, Any]) -> str:
        """Marks needs_build=False after the builder finishes and returns the built primary exe path if found."""
        if not game_location or not runner_def:
            return ""
        primary_exe = cls.find_primary_game_executable(game_location, runner_def)
        folder_dir = cls._find_runner_folder_dir(game_location, runner_def)
        version_file = os.path.join(folder_dir, ".runner_version.json") if folder_dir else ""
        if version_file and os.path.isfile(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as vf:
                    v_data = json.load(vf)
                if isinstance(v_data, dict):
                    v_data["needs_build"] = False
                    if primary_exe and os.path.isfile(primary_exe):
                        v_data["prev_exe_mtime"] = os.path.getmtime(primary_exe)
                    else:
                        v_data["prev_exe_mtime"] = time.time()
                    with open(version_file, "w", encoding="utf-8") as out_f:
                        json.dump(v_data, out_f, indent=2)
            except Exception as e:
                print(f"[RunnersManager] Notice updating .runner_version.json: {e}", flush=True)
        return primary_exe

    @classmethod
    def find_runner_executable(cls, game_location: str, runner_def: Dict[str, Any], saved_exe: str = "") -> str:
        """
        Resolves the best launchable executable for a runner within game_location.
        Prioritizes saved custom path, then primary/built executables over builder/launcher/setup binaries,
        searching the runner folder up to depth 3.
        """
        if saved_exe and os.path.isfile(saved_exe):
            return os.path.normpath(saved_exe)

        primary = cls.find_primary_game_executable(game_location, runner_def, saved_exe=saved_exe)
        if primary:
            return primary

        builder = cls.find_builder_executable(game_location, runner_def)
        if builder:
            return builder

        if not game_location or not runner_def:
            return ""

        folder = runner_def.get("folder", "")
        rel_path = runner_def.get("rel_path", "")
        for base_loc in cls._candidate_game_bases(game_location):
            folder_dir = os.path.normpath(os.path.join(base_loc, folder)) if folder else (
                os.path.dirname(os.path.join(base_loc, rel_path)) if rel_path else ""
            )
            for p in cls._walk_runner_exes(folder_dir):
                fl = os.path.basename(p).lower()
                if any(k in fl for k in cls.FALLBACK_EXE_KEYWORDS):
                    return p

        return ""

    @classmethod
    def get_runners_status(
        cls,
        game_location: str,
        runners_def: List[Dict[str, Any]],
        saved_runner_exes: Optional[Dict[str, str]] = None,
        saved_runner_steam_urls: Optional[Dict[str, str]] = None,
        check_remote: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Returns status for each runner defined for a game:
        Whether it is installed, executable exists, saved per-runner paths, builder status, and version comparison.
        """
        statuses = []
        saved_exes_map = saved_runner_exes if isinstance(saved_runner_exes, dict) else {}
        saved_steam_map = saved_runner_steam_urls if isinstance(saved_runner_steam_urls, dict) else {}
        for r in runners_def:
            rid = r.get("id", "")
            rname = r.get("name", rid)
            repo = r.get("repo", "")
            rel_path = r.get("rel_path", "")
            folder = r.get("folder", "")
            args = r.get("args", [])

            saved_exe = str(saved_exes_map.get(rid) or "")
            primary_exe = cls.find_primary_game_executable(game_location, r, saved_exe=saved_exe)
            builder_exe = cls.find_builder_executable(game_location, r)
            target_exe = primary_exe or builder_exe or cls.find_runner_executable(game_location, r, saved_exe=saved_exe)
            is_installed = bool(target_exe and os.path.isfile(target_exe))
            default_exe = os.path.normpath(os.path.join(game_location, rel_path)) if (game_location and rel_path) else ""
            launch_options = cls.resolve_runner_launch_options(game_location, r) if game_location else ""

            # Check installed version & builder state from .runner_version.json in runner folder
            folder_dir = cls._find_runner_folder_dir(game_location, r) if game_location else ""
            version_file = os.path.join(folder_dir, ".runner_version.json") if folder_dir else ""
            installed_version = ""
            needs_build = False
            prev_exe_mtime = 0.0
            v_data: Dict[str, Any] = {}
            if version_file and os.path.isfile(version_file):
                try:
                    with open(version_file, "r", encoding="utf-8") as vf:
                        loaded = json.load(vf)
                        if isinstance(loaded, dict):
                            v_data = loaded
                            installed_version = str(v_data.get("version") or "").strip()
                            needs_build = bool(v_data.get("needs_build", False))
                            prev_exe_mtime = float(v_data.get("prev_exe_mtime") or 0.0)
                except Exception:
                    pass

            # Auto-clear needs_build once the compiled primary exe is newer than pre-update mtime
            if needs_build and primary_exe and os.path.isfile(primary_exe):
                try:
                    cur_mtime = os.path.getmtime(primary_exe)
                    if (prev_exe_mtime <= 0 and cur_mtime > 0) or (cur_mtime > prev_exe_mtime + 1.0):
                        needs_build = False
                        if v_data and version_file:
                            v_data["needs_build"] = False
                            v_data["prev_exe_mtime"] = cur_mtime
                            with open(version_file, "w", encoding="utf-8") as out_vf:
                                json.dump(v_data, out_vf, indent=2)
                except Exception:
                    pass

            if is_installed and builder_exe and not primary_exe:
                needs_build = True

            # Pre-bundled runner (from base .rar without .runner_version.json): infer local version or mark Bundled
            if is_installed and not installed_version:
                inferred = cls._infer_local_version(folder_dir)
                installed_version = inferred if inferred else "Bundled"

            # Query latest release version
            latest_version = ""
            download_url = ""
            asset_name = ""
            asset_size = 0
            pattern = r.get("asset_pattern", r"windows.*\.zip|\.zip$")

            if check_remote and repo:
                rel_info = cls.get_latest_github_release(repo, asset_pattern=pattern)
                if rel_info:
                    latest_version = rel_info.get("tag_name", "")
                    for asset in rel_info.get("assets", []):
                        aname = asset.get("name", "")
                        if re.search(pattern, aname, re.IGNORECASE):
                            download_url = asset.get("browser_download_url", "")
                            asset_name = aname
                            asset_size = asset.get("size", 0)
                            break

            # Determine if an update is available
            update_available = False
            if is_installed and latest_version:
                update_available = cls._versions_differ(installed_version, latest_version)

            subtitle = r.get("subtitle", "")

            statuses.append({
                "id": rid,
                "name": rname,
                "subtitle": subtitle,
                "repo": repo,
                "release_url": cls.get_release_page_url(repo) if repo else "",
                "rel_path": rel_path,
                "folder": folder,
                "args": args,
                "launch_options": launch_options,
                "installed": is_installed,
                "installed_version": installed_version if is_installed else "",
                "target_exe": target_exe if is_installed else "",
                "primary_exe": primary_exe,
                "builder_exe": builder_exe,
                "has_builder": bool(builder_exe),
                "needs_build": bool(needs_build and is_installed),
                "default_exe": default_exe,
                "saved_exe": saved_exe,
                "steam_url": str(saved_steam_map.get(rid) or ""),
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
        Downloads the runner's latest release zip/installer and extracts it into the runner's subfolder.
        Tracks whether a post-update Builder run is required to recompile the game binary.
        """
        if not game_location or not os.path.isdir(game_location):
            return {"success": False, "error": f"Game directory '{game_location}' does not exist"}

        repo = runner_def.get("repo")
        if not repo:
            return {"success": False, "error": "Runner definition missing Git repository"}

        target_dir = cls._find_runner_folder_dir(game_location, runner_def)
        os.makedirs(target_dir, exist_ok=True)

        existing_primary = cls.find_primary_game_executable(game_location, runner_def)
        prev_exe_mtime = os.path.getmtime(existing_primary) if (existing_primary and os.path.isfile(existing_primary)) else 0.0

        pattern = runner_def.get("asset_pattern", r"windows.*\.zip|\.zip$")
        rel_info = cls.get_latest_github_release(repo, asset_pattern=pattern)
        if not rel_info:
            return {"success": False, "error": f"Could not fetch releases for {repo}"}

        tag_name = rel_info.get("tag_name", "latest")
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
                # Standalone executable/builder binary (e.g. HookshotBuilder.exe or NX2navi-Setup-x.x.x.exe)
                dest_exe = os.path.join(target_dir, asset_name)
                shutil.copyfile(temp_zip, dest_exe)
                print(f"[RunnersManager] Saved standalone executable to: {dest_exe}", flush=True)

            builder_exe = cls.find_builder_executable(game_location, runner_def)
            after_primary = cls.find_primary_game_executable(game_location, runner_def)

            needs_build = False
            if builder_exe:
                if not after_primary:
                    needs_build = True
                else:
                    try:
                        after_mtime = os.path.getmtime(after_primary)
                        if prev_exe_mtime > 0 and abs(after_mtime - prev_exe_mtime) <= 1.0:
                            needs_build = True
                    except Exception:
                        pass

            # Persist version and builder metadata in .runner_version.json
            version_meta_path = os.path.join(target_dir, ".runner_version.json")
            try:
                with open(version_meta_path, "w", encoding="utf-8") as vf:
                    json.dump({
                        "id": runner_def.get("id"),
                        "name": runner_def.get("name"),
                        "version": tag_name,
                        "installed_at": time.time(),
                        "repo": repo,
                        "needs_build": needs_build,
                        "prev_exe_mtime": prev_exe_mtime,
                        "builder_exe": builder_exe
                    }, vf, indent=2)
            except Exception as e_meta:
                print(f"[RunnersManager] Notice: Could not save .runner_version.json: {e_meta}", flush=True)

            print(f"[RunnersManager] Successfully installed {runner_def.get('name')} to {target_dir} (needs_build={needs_build})", flush=True)
            if progress_callback:
                progress_callback("Installed successfully!", 100)

            return {
                "success": True,
                "version": tag_name,
                "installed_path": target_dir,
                "needs_build": needs_build,
                "builder_exe": builder_exe,
                "primary_exe": after_primary,
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
