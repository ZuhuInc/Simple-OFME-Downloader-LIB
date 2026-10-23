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
        part_match = re.search(r'[\._\-\s]part0*([0-9]+)', lower_name)
        if part_match:
            try:
                part_num = int(part_match.group(1))
                if part_num > 1:
                    is_multipart_subsequent = True
            except ValueError:
                pass

        if is_multipart_subsequent and not ("forza horizon 2" in (game_title or "").lower() or "azimuth" in lower_name):
            dir_name = os.path.dirname(archive_path)
            part1_candidate = re.sub(r'([\._\-\s]part0*)([0-9]+)', r'\g<1>1', archive_name, flags=re.IGNORECASE)
            part1_path = os.path.join(dir_name, part1_candidate)
            if os.path.exists(part1_path):
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
        if password == "":
            passwords_to_try = [""]
        else:
            passwords_to_try = [password]
            for alt in ["online-fix.me", "cracked-games.org", ""]:
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

        # Detect the specific game directory inside extract_dir
        game_dir = extract_dir
        if is_fix:
            game_dir = extract_dir
        else:
            # 1. Look for matching folder name based on game_title
            if game_title:
                norm_title = re.sub(r'[^a-zA-Z0-9]', '', game_title).lower()
                for item in os.listdir(extract_dir):
                    item_path = os.path.join(extract_dir, item)
                    if os.path.isdir(item_path) and not item.startswith("_") and "redist" not in item.lower():
                        if re.sub(r'[^a-zA-Z0-9]', '', item).lower() == norm_title or norm_title in re.sub(r'[^a-zA-Z0-9]', '', item).lower():
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

        # Check for Azimuth compatibility layer (e.g. Forza Horizon 2)
        az_root = None
        if os.path.exists(os.path.join(game_dir, "azimuth.exe")):
            az_root = game_dir
        elif os.path.exists(os.path.join(extract_dir, "azimuth.exe")):
            az_root = extract_dir

        if az_root:
            game_dir = az_root
            exe_path = os.path.join(az_root, "azimuth.exe")
            self._ensure_azimuth_config(az_root)
        else:
            # Scan for game executable
            exe_path = self._find_game_exe(game_dir) or self._find_game_exe(extract_dir)

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
    def _find_game_exe(game_dir: str) -> Optional[str]:
        if not os.path.exists(game_dir) or not os.path.isdir(game_dir):
            return None

        # Direct Azimuth launcher check
        azimuth_exe = os.path.join(game_dir, "azimuth.exe")
        if os.path.isfile(azimuth_exe):
            return azimuth_exe

        candidates = []
        ignored_names = {
            "unitycrashhandler64.exe", "unitycrashhandler32.exe", "dxwebsetup.exe",
            "unins000.exe", "uninstall.exe", "forza_durango_release_final.exe"
        }

        for root, dirs, files in os.walk(game_dir):
            dirs[:] = [d for d in dirs if not d.startswith("_") and "redist" not in d.lower()]
            for f in files:
                f_lower = f.lower()
                if (
                    f_lower.endswith(".exe")
                    and f_lower not in ignored_names
                    and not f_lower.startswith("vcredist")
                    and "_durango_" not in f_lower
                ):
                    full = os.path.join(root, f)
                    candidates.append(full)

        if candidates:
            # If azimuth.exe is located inside any subfolder, prioritize it!
            for c in candidates:
                if os.path.basename(c).lower() == "azimuth.exe":
                    return c
            candidates.sort(key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0, reverse=True)
            return candidates[0]

        return None

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
