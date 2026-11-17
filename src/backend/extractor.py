"""
Fanta OFME Downloader - Archive Extractor & Fix Applicator
Automates extraction for RAR, ZIP, 7Z with password injection (WinRAR & 7-Zip), multi-part archive support,
automatic game directory detection, and fix patching.
"""

import os
import re
import shutil
import subprocess
import zipfile
from typing import Dict, Any, Optional, Callable, List, Tuple


class Extractor:
    DEFAULT_RAR_PASSWORD = "online-fix.me"

    def __init__(
        self,
        winrar_path: Optional[str] = None,
        sevenzip_path: Optional[str] = None
    ):
        self.winrar_path = winrar_path or self._find_winrar()
        self.sevenzip_path = sevenzip_path or self._find_sevenzip()

    @staticmethod
    def _find_winrar() -> Optional[str]:
        candidates = [
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        shutil_which = shutil.which("winrar") or shutil.which("WinRAR") or shutil.which("unrar")
        return shutil_which if shutil_which and os.path.exists(shutil_which) else None

    @staticmethod
    def _find_sevenzip() -> Optional[str]:
        candidates = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            r"C:\Program Files\7-Zip\7za.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        shutil_which = shutil.which("7z") or shutil.which("7za")
        return shutil_which if shutil_which and os.path.exists(shutil_which) else None

    def is_winrar_available(self) -> bool:
        return bool(self.winrar_path and os.path.exists(self.winrar_path))

    def is_sevenzip_available(self) -> bool:
        return bool(self.sevenzip_path and os.path.exists(self.sevenzip_path))

    def is_any_extractor_available(self) -> bool:
        return self.is_winrar_available() or self.is_sevenzip_available()

    @staticmethod
    def get_blocking_processes(target_dir: str) -> List[str]:
        """
        Checks if any active process has its executable inside target_dir.
        Returns a list of running process names.
        """
        if not target_dir or not os.path.exists(target_dir):
            return []
        try:
            import psutil
        except ImportError:
            return []

        try:
            target_abs = os.path.abspath(target_dir).lower()
            norm_parent = os.path.dirname(target_abs)
            if norm_parent == target_abs or re.match(r'^[a-z]:\\?$', target_abs):
                return []
            target_prefix = target_abs if target_abs.endswith(os.sep) else (target_abs + os.sep)
            blocking = []
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    exe = proc.info.get('exe')
                    if not exe or not os.path.isabs(exe) or not os.path.isfile(exe):
                        continue
                    exe_abs = os.path.abspath(exe).lower()
                    if exe_abs.startswith(target_prefix) or exe_abs == target_abs:
                        blocking.append(proc.info.get('name') or os.path.basename(exe))
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue
            return sorted(list(set(blocking)))
        except Exception as e:
            print(f"[Extractor] Warning inspecting active processes: {e}", flush=True)
            return []

    def extract_archive(
        self,
        archive_path: str,
        extract_dir: str,
        password: str = DEFAULT_RAR_PASSWORD,
        delete_after: bool = True,
        game_title: Optional[str] = None,
        is_fix: bool = False,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Extracts archive (RAR/ZIP/7Z) to target directory using WinRAR, 7-Zip, or Python zipfile.
        Detects the resulting game folder and automatically cleans up the raw archive when done.
        """
        if not os.path.exists(archive_path):
            return {"success": False, "error": f"Archive not found: {archive_path}"}

        archive_name = os.path.basename(archive_path)

        # Multi-part check: if user passed part2.rar onwards, auto-route to part 1 if present
        is_multipart_subsequent = False
        lower_name = archive_name.lower()
        part_match = re.search(r'(?:^|[\._\-\s])part0*([0-9]+)', lower_name)
        if part_match:
            try:
                part_num = int(part_match.group(1))
                if part_num > 1:
                    is_multipart_subsequent = True
            except ValueError:
                pass

        if is_multipart_subsequent and not ("forza horizon 2" in (game_title or "").lower() or "azimuth" in lower_name):
            dir_name = os.path.dirname(archive_path)
            part1_candidates = [
                re.sub(r'((?:^|[\._\-\s])part0*)([0-9]+)', r'\g<1>1', archive_name, flags=re.IGNORECASE),
                re.sub(r'((?:^|[\._\-\s])part)([0-9]+)', r'\g<1>01', archive_name, flags=re.IGNORECASE),
                re.sub(r'([\._\-\s])part[0-9]+', r'.part1', archive_name, flags=re.IGNORECASE),
                re.sub(r'([\._\-\s])part[0-9]+', r'_Part1', archive_name, flags=re.IGNORECASE),
            ]
            part1_path = None
            part1_candidate = None
            for cand in part1_candidates:
                cand_path = os.path.join(dir_name, cand)
                if os.path.exists(cand_path):
                    part1_path = cand_path
                    part1_candidate = cand
                    break

            if part1_path and part1_candidate:
                print(f"[Extractor] Multi-part {archive_name} routed to primary volume {part1_candidate}", flush=True)
                archive_path = part1_path
                archive_name = part1_candidate
            else:
                return {
                    "success": True,
                    "message": f"Skipping multi-part piece {archive_name} (handled by part 1)",
                    "extract_dir": extract_dir
                }

        # Check if the game or any process inside the specific game folder is currently running.
        # NEVER check a broad library root (like D:\Games or extract_dir when installing a new game).
        target_check_dir = None
        if is_fix:
            if extract_dir and os.path.exists(extract_dir):
                target_check_dir = extract_dir
        elif game_title and extract_dir and os.path.exists(extract_dir):
            candidate_game_dir = os.path.join(extract_dir, game_title)
            if os.path.exists(candidate_game_dir) and os.path.isdir(candidate_game_dir):
                target_check_dir = candidate_game_dir
            else:
                norm_title = re.sub(r'[^a-zA-Z0-9]', '', game_title).lower()
                try:
                    for entry in os.listdir(extract_dir):
                        full_entry = os.path.join(extract_dir, entry)
                        if os.path.isdir(full_entry):
                            entry_norm = re.sub(r'[^a-zA-Z0-9]', '', entry).lower()
                            if entry_norm and (entry_norm == norm_title or entry.lower() == game_title.lower()):
                                target_check_dir = full_entry
                                break
                except Exception:
                    pass

        blocking_procs = self.get_blocking_processes(target_check_dir) if target_check_dir else []
        if blocking_procs:
            proc_list = ", ".join(blocking_procs)
            err = f"The game is currently running ({proc_list}). Please close the game before extracting."
            print(f"[Extractor] Aborting extraction: {err}", flush=True)
            if progress_cb:
                progress_cb({"status": "error", "error": err, "file": archive_name})
            return {"success": False, "error": err}

        os.makedirs(extract_dir, exist_ok=True)

        if progress_cb:
            progress_cb({"status": "extracting", "file": archive_name, "dir": extract_dir})

        before_entries = set(os.listdir(extract_dir)) if os.path.exists(extract_dir) else set()

        success = False
        error_msg = ""

        # Determine passwords to try
        passwords_to_try = []
        if password:
            passwords_to_try.append(password)
        for alt in ["cracked-games.org", "online-fix.me", ""]:
            if alt not in passwords_to_try:
                passwords_to_try.append(alt)

        # Method 1: Python zipfile for .zip archives (native, instant, zero GUI dialogs)
        if archive_path.lower().endswith(".zip"):
            try:
                print(f"[Extractor] Running Python ZipFile extraction for {archive_name}...", flush=True)
                with zipfile.ZipFile(archive_path, "r") as zf:
                    is_encrypted = any(zinfo.flag_bits & 0x1 for zinfo in zf.infolist())
                    if not is_encrypted:
                        zf.extractall(extract_dir)
                        success = True
                        error_msg = ""
                    else:
                        for p in passwords_to_try:
                            if not p:
                                continue
                            try:
                                zf.extractall(extract_dir, pwd=p.encode("utf-8"))
                                success = True
                                error_msg = ""
                                break
                            except Exception:
                                pass
            except Exception as e:
                error_msg = f"Zip extraction error: {e}"

        # Method 2: WinRAR (silent background mode with GUI dialogs suppressed)
        if not success and self.is_winrar_available():
            for p in passwords_to_try:
                # -p- explicitly disables WinRAR's interactive password prompt dialog
                pwd_arg = f"-p{p}" if p else "-p-"
                cmd = [
                    self.winrar_path,
                    "x",                # Extract with full paths
                    "-ibck",            # Background mode
                    "-inul",            # Suppress all GUI error & dialog popups
                    pwd_arg,            # Password or -p- (DO NOT QUERY PASSWORD)
                    "-o+",              # Overwrite existing files
                    "-y",               # Assume Yes on all queries
                    archive_path,
                    extract_dir + os.sep
                ]
                try:
                    print(f"[Extractor] Running WinRAR: {' '.join(cmd[:5])} -> {extract_dir}", flush=True)
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                    if result.returncode in [0, 1]:
                        success = True
                        error_msg = ""
                        break
                    else:
                        error_msg = f"WinRAR code {result.returncode}: {result.stderr or result.stdout}"
                except Exception as e:
                    error_msg = f"WinRAR execution error: {e}"

        # Method 3: 7-Zip fallback
        if not success and self.is_sevenzip_available():
            for p in passwords_to_try:
                pwd_arg = f"-p{p}" if p else "-p-"
                cmd = [
                    self.sevenzip_path,
                    "x",
                    "-y",
                    "-aoa",             # Overwrite all without prompt
                    pwd_arg,
                    f"-o{extract_dir}",
                    archive_path
                ]
                try:
                    print(f"[Extractor] Running 7-Zip: {' '.join(cmd[:4])} -> {extract_dir}", flush=True)
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                    if result.returncode in [0, 1]:
                        success = True
                        error_msg = ""
                        break
                    else:
                        error_msg = f"7-Zip code {result.returncode}: {result.stderr or result.stdout}"
                except Exception as e:
                    error_msg = f"7-Zip execution error: {e}"

        # Method 4: Python zipfile secondary fallback
        if not success and archive_path.lower().endswith(".zip") and not error_msg:
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir)
                success = True
                error_msg = ""
            except Exception as e:
                error_msg = f"Zip extraction error: {e}"

        if not success:
            if not error_msg:
                error_msg = "No extraction tool found. Please install WinRAR or 7-Zip."
            if progress_cb:
                progress_cb({"status": "error", "error": error_msg, "file": archive_name})
            return {"success": False, "error": error_msg}

        # Unwrap hardcoded wrapper directories (e.g. GAMES2/...) if archive contained them
        if not is_fix:
            self._unwrap_archive_containers(extract_dir, before_entries=before_entries)

        # Detect the specific game directory inside extract_dir
        game_dir = extract_dir
        if is_fix:
            game_dir = extract_dir
        else:
            # 1. Look for matching folder name based on game_title
            if game_title:
                for item in sorted(os.listdir(extract_dir)):
                    item_path = os.path.join(extract_dir, item)
                    if self._is_title_matching_dir(item_path, game_title):
                        game_dir = item_path
                        break

            # 2. Look for newly created directories
            if game_dir == extract_dir:
                after_entries = set(os.listdir(extract_dir)) if os.path.exists(extract_dir) else set()
                new_entries = after_entries - before_entries
                new_dirs = [os.path.join(extract_dir, e) for e in new_entries if os.path.isdir(os.path.join(extract_dir, e))]
                real_dirs = [d for d in new_dirs if not os.path.basename(d).startswith("_") and "redist" not in os.path.basename(d).lower()]
                if len(real_dirs) == 1:
                    game_dir = real_dirs[0]

            # 3. Check one level deeper if single wrapper matched folder contains a matching title folder
            if game_title and game_dir != extract_dir and os.path.isdir(game_dir):
                try:
                    sub_dirs = [
                        os.path.join(game_dir, e) for e in os.listdir(game_dir)
                        if os.path.isdir(os.path.join(game_dir, e))
                        and not e.startswith("_") and "redist" not in e.lower()
                    ]
                    if len(sub_dirs) == 1 and self._is_title_matching_dir(sub_dirs[0], game_title):
                        game_dir = sub_dirs[0]
                except Exception:
                    pass

        # Check for Azimuth compatibility layer (e.g. Forza Horizon 2)
        az_root = None
        if os.path.exists(os.path.join(game_dir, "azimuth.exe")):
            az_root = game_dir

        if az_root:
            game_dir = az_root
            exe_path = os.path.join(az_root, "azimuth.exe")
            self._ensure_azimuth_config(az_root)
        else:
            # Scan for game executable inside game_dir only (never fall back to root extract_dir to avoid cross-game pollution)
            exe_path = self._find_game_exe(game_dir, game_title=game_title)

        # Automatic cleanup of raw archive file after extraction
        if delete_after and os.path.exists(archive_path):
            try:
                os.remove(archive_path)
                print(f"[Extractor] Successfully deleted raw archive after extraction: {archive_path}", flush=True)
            except Exception as del_err:
                print(f"[Extractor] Notice: Could not remove archive {archive_path}: {del_err}", flush=True)

        part_file = archive_path + ".part"
        if os.path.exists(part_file):
            try:
                os.remove(part_file)
            except Exception:
                pass

        if progress_cb:
            progress_cb({
                "status": "extracted",
                "file": archive_name,
                "extract_dir": extract_dir,
                "game_dir": game_dir,
                "exe_path": exe_path
            })

        print(f"[Extractor] Extraction COMPLETE: {archive_name} -> {game_dir}", flush=True)
        return {
            "success": True,
            "extract_dir": extract_dir,
            "game_dir": game_dir,
            "exe_path": exe_path
        }

    @staticmethod
    def _ensure_azimuth_config(az_root: str) -> None:
        """
        Automatically sets up data/azimuth.ini for Forza Horizon 2 with Storm Island DLC
        so the game launches with 0 manual user configuration needed.
        """
        try:
            data_dir = os.path.join(az_root, "data")
            os.makedirs(data_dir, exist_ok=True)
            ini_path = os.path.join(data_dir, "azimuth.ini")

            # Find Anthem game folder
            anthem_rel = "Anthem_1.0.0.64_x64__8wekyb3d8bbwe"
            for item in os.listdir(az_root):
                item_full = os.path.join(az_root, item)
                if os.path.isdir(item_full) and (item.lower().startswith("anthem") or os.path.exists(os.path.join(item_full, "Mount"))):
                    anthem_rel = item
                    break

            # Find Storm Island DLC folder
            storm_rel = r"Forza Horizon 2 Storm Island (1.0.0.36)\StormIsland_1.0.0.36_neutral__8wekyb3d8bbwe"
            found_dlc = False
            for root, dirs, _ in os.walk(az_root):
                for d in dirs:
                    if d.lower().startswith("stormisland"):
                        full_dlc_path = os.path.join(root, d)
                        storm_rel = os.path.relpath(full_dlc_path, az_root)
                        found_dlc = True
                        break
                if found_dlc:
                    break

            player_name = "Fanta OFME"

            # Check if azimuth.ini already has valid [title-1a96545b]
            if os.path.exists(ini_path):
                try:
                    with open(ini_path, "r", encoding="utf-16", errors="ignore") as f:
                        existing_text = f.read()
                    if "[title-1a96545b]" in existing_text:
                        return
                except Exception:
                    pass

            ini_content = (
                "[launcher]\n"
                "game=1a96545b\n"
                "resolution=1080\n"
                "aspect=16:9\n"
                "antialiasing=msaax4\n"
                "graphics=default\n"
                "shadows=default\n"
                "reflections=default\n"
                "car_detail=default\n"
                "particles=default\n"
                "motion_blur=default\n"
                "texture_filtering=default\n"
                "audio=stereo\n"
                "frame_rate=60\n"
                "frame_pacing=fixed\n"
                "vsync=on\n"
                "display=fullscreen\n"
                "hdr=off\n"
                "hdr_peak=\n"
                "hdr_paper_white=200\n"
                "hdr_black=0\n"
                "language=\n"
                "speech=\n"
                f"player_name={player_name}\n"
                "settings_version=1\n"
                "[title-1a96545b]\n"
                f"folder={anthem_rel}\n"
                f"content={storm_rel}\n"
                "name=Forza Horizon 2\n"
            )

            with open(ini_path, "w", encoding="utf-16") as f:
                f.write(ini_content)
            print(f"[Extractor] Generated azimuth.ini for Forza Horizon 2 at: {ini_path}", flush=True)
        except Exception as e:
            print(f"[Extractor] Notice setting up azimuth.ini: {e}", flush=True)

    @staticmethod
    def _norm_title_no_the(s: str) -> str:
        norm = re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()
        return re.sub(r'^the', '', norm)

    @classmethod
    def _is_title_matching_dir(cls, item_path: str, game_title: str) -> bool:
        if not game_title or not os.path.isdir(item_path):
            return False
        name = os.path.basename(item_path)
        if name.startswith("_") or "redist" in name.lower():
            return False
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', game_title).lower()
        norm_item = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        if not norm_title or not norm_item:
            return False
        if norm_item == norm_title or norm_title in norm_item:
            return True
        if len(norm_item) >= 5 and norm_item in norm_title:
            return True
        no_the_title = cls._norm_title_no_the(game_title)
        no_the_item = cls._norm_title_no_the(name)
        return bool(no_the_title and no_the_item and (no_the_item == no_the_title or no_the_title in no_the_item))

    @staticmethod
    def _unwrap_archive_containers(extract_dir: str, before_entries: Optional[set] = None) -> None:
        """
        Unwraps hardcoded top-level container folders (e.g. GAMES2/... or GAMES/...)
        so games unpack directly into the user's chosen extract_dir instead of <extract_dir>/GAMES2/<game>.
        """
        if not extract_dir or not os.path.isdir(extract_dir):
            return
        base_name_lower = os.path.basename(os.path.normpath(extract_dir)).lower()
        try:
            entries = list(os.listdir(extract_dir))
        except Exception:
            return

        for entry in entries:
            wrapper_dir = os.path.join(extract_dir, entry)
            if not os.path.isdir(wrapper_dir):
                continue
            entry_lower = entry.lower()
            is_games2 = (entry_lower == "games2")
            is_games_wrapper = (
                entry_lower == "games"
                and base_name_lower not in ("games", "games2")
                and (before_entries is None or entry not in before_entries)
            )
            if not (is_games2 or is_games_wrapper):
                continue

            try:
                children = list(os.listdir(wrapper_dir))
            except Exception:
                continue

            # Safety for 'games' folder: do not unwrap if it looks like a ROM subfolder (contains files like .nup/.rom/.bin and no dirs)
            if is_games_wrapper:
                has_dir = any(os.path.isdir(os.path.join(wrapper_dir, c)) for c in children)
                has_rom = any(c.lower().endswith((".nup", ".nsp", ".xci", ".rom", ".iso")) for c in children)
                if not has_dir or has_rom:
                    continue

            print(f"[Extractor] Unwrapping container folder '{entry}' in {extract_dir}...", flush=True)
            for child in children:
                src_item = os.path.join(wrapper_dir, child)
                dst_item = os.path.join(extract_dir, child)
                try:
                    if not os.path.exists(dst_item):
                        shutil.move(src_item, dst_item)
                    elif os.path.isdir(src_item) and os.path.isdir(dst_item):
                        shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                        shutil.rmtree(src_item, ignore_errors=True)
                    else:
                        shutil.copy2(src_item, dst_item)
                        os.remove(src_item)
                except Exception as move_err:
                    print(f"[Extractor] Warning moving unwrapped item '{child}': {move_err}", flush=True)

            try:
                if not os.listdir(wrapper_dir):
                    os.rmdir(wrapper_dir)
            except Exception as rm_err:
                print(f"[Extractor] Notice removing wrapper folder '{entry}': {rm_err}", flush=True)

    @staticmethod
    def _find_game_exe(game_dir: str, game_title: Optional[str] = None) -> Optional[str]:
        if not os.path.exists(game_dir) or not os.path.isdir(game_dir):
            return None

        # Protection: NEVER search a drive root or root games library directory
        norm_dir = os.path.normpath(game_dir).rstrip("\\/").upper()
        if norm_dir in ("C:", "D:", "E:", "F:", "C:\\GAMES", "D:\\GAMES", "D:\\GAMES2"):
            return None

        # Protection: Check if game_dir looks like a shared library folder (has many independent folders with exes)
        try:
            subdirs = [d for d in os.listdir(game_dir) if os.path.isdir(os.path.join(game_dir, d)) and not d.startswith((".", "_"))]
            if len(subdirs) > 10:
                return None
        except Exception:
            pass

        # Direct Azimuth launcher check (specifically for Forza Horizon 2)
        is_forza = bool((game_title and "forza" in game_title.lower()) or ("forza" in game_dir.lower()))
        if is_forza:
            azimuth_exe = os.path.join(game_dir, "azimuth.exe")
            if os.path.isfile(azimuth_exe):
                return azimuth_exe

        candidates = []
        ignored_names = {
            "unitycrashhandler64.exe", "unitycrashhandler32.exe", "dxwebsetup.exe",
            "unins000.exe", "uninstall.exe", "forza_durango_release_final.exe",
            "crashreport.exe", "crashreportclient.exe", "epicgameslauncher.exe",
            "steamservice.exe", "vcredist_x64.exe", "vcredist_x86.exe"
        }
        ignored_dirs = {"_redist", "redist", "commonredist", "_commonredist", "directx", "support", "dependencies", "tools", "crashreports"}

        for root, dirs, files in os.walk(game_dir):
            dirs[:] = [d for d in dirs if not d.startswith("_") and d.lower() not in ignored_dirs and "redist" not in d.lower()]
            for f in files:
                f_lower = f.lower()
                if (
                    f_lower.endswith(".exe")
                    and f_lower not in ignored_names
                    and not f_lower.startswith("vcredist")
                    and not f_lower.startswith("unins")
                    and "_durango_" not in f_lower
                ):
                    full = os.path.join(root, f)
                    candidates.append(full)

        if not candidates:
            return None

        # Score candidates to select the true game executable
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', game_title).lower() if game_title else ""
        norm_folder = re.sub(r'[^a-zA-Z0-9]', '', os.path.basename(game_dir)).lower()

        def score_candidate(path: str) -> float:
            base_name = os.path.basename(path).lower()
            stem = os.path.splitext(base_name)[0]
            norm_stem = re.sub(r'[^a-zA-Z0-9]', '', stem).lower()
            score = 0.0

            # 1. Exact title match
            if norm_title and norm_stem == norm_title:
                score += 1000.0
            elif norm_title and norm_title in norm_stem:
                score += 500.0
            elif norm_title and norm_stem in norm_title and len(norm_stem) >= 4:
                score += 300.0

            # 2. Folder name match
            if norm_folder and norm_stem == norm_folder:
                score += 400.0
            elif norm_folder and norm_folder in norm_stem:
                score += 200.0

            # 3. Known main executable stems
            if stem in ("launcher", "game", "play", "start", "shipping", "client", "boot"):
                score += 250.0

            # 4. Azimuth (only for Forza Horizon 2)
            if is_forza and base_name == "azimuth.exe":
                score += 1500.0

            # 5. Depth penalty (favor files closer to game root)
            rel_path = os.path.relpath(path, game_dir)
            depth = len(rel_path.split(os.sep)) - 1
            score -= (depth * 50.0)

            # 6. File size tie-breaker (prefer larger binaries over helper stubs)
            try:
                sz = os.path.getsize(path)
                score += min(50.0, sz / (1024 * 1024))
            except Exception:
                pass

            return score

        candidates.sort(key=score_candidate, reverse=True)
        return candidates[0]

    def apply_fix(
        self,
        fix_archive_path: str,
        game_dir: str,
        password: str = DEFAULT_RAR_PASSWORD,
        delete_after: bool = True
    ) -> Dict[str, Any]:
        """
        Applies fix/patch files directly over the target game directory.
        """
        return self.extract_archive(
            archive_path=fix_archive_path,
            extract_dir=game_dir,
            password=password,
            delete_after=delete_after,
            is_fix=True
        )
