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

        # Multi-part check: if user passed part2.rar onwards, skip since part1 handles all
        if ".part" in archive_name.lower() and not (
            ".part01." in archive_name.lower() or ".part1." in archive_name.lower() or ".part001." in archive_name.lower()
        ):
            return {
                "success": True,
                "message": "Skipping multi-part piece (handled by part 1)",
                "extract_dir": extract_dir
            }

        os.makedirs(extract_dir, exist_ok=True)

        if progress_cb:
            progress_cb({"status": "extracting", "file": archive_name, "dir": extract_dir})

        before_entries = set(os.listdir(extract_dir)) if os.path.exists(extract_dir) else set()

        success = False
        error_msg = ""

        # Method 1: WinRAR
        if self.is_winrar_available():
            cmd = [
                self.winrar_path,
                "x",                # Extract with full paths
                "-ibck",            # Background mode
                f"-p{password}",    # Password
                "-o+",              # Overwrite existing files
                "-y",               # Assume Yes on all queries
                archive_path,
                extract_dir + os.sep
            ]
            try:
                print(f"[Extractor] Running WinRAR: {' '.join(cmd[:4])} -> {extract_dir}", flush=True)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                if result.returncode in [0, 1]:
                    success = True
                else:
                    error_msg = f"WinRAR code {result.returncode}: {result.stderr or result.stdout}"
            except Exception as e:
                error_msg = f"WinRAR execution error: {e}"

        # Method 2: 7-Zip fallback
        if not success and self.is_sevenzip_available():
            cmd = [
                self.sevenzip_path,
                "x",
                "-y",
                f"-p{password}",
                f"-o{extract_dir}",
                archive_path
            ]
            try:
                print(f"[Extractor] Running 7-Zip: {' '.join(cmd[:4])} -> {extract_dir}", flush=True)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                if result.returncode in [0, 1]:
                    success = True
                    error_msg = ""
                else:
                    error_msg = f"7-Zip code {result.returncode}: {result.stderr or result.stdout}"
            except Exception as e:
                error_msg = f"7-Zip execution error: {e}"

        # Method 3: Python zipfile fallback for .zip files
        if not success and archive_path.lower().endswith(".zip"):
            try:
                print(f"[Extractor] Running Python ZipFile extraction for {archive_name}...", flush=True)
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir, pwd=password.encode("utf-8") if password else None)
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
    def _find_game_exe(game_dir: str) -> Optional[str]:
        if not os.path.exists(game_dir) or not os.path.isdir(game_dir):
            return None

        candidates = []
        ignored_names = {"unitycrashhandler64.exe", "unitycrashhandler32.exe", "dxwebsetup.exe", "unins000.exe", "uninstall.exe"}

        for root, dirs, files in os.walk(game_dir):
            dirs[:] = [d for d in dirs if not d.startswith("_") and "redist" not in d.lower()]
            for f in files:
                if f.lower().endswith(".exe") and f.lower() not in ignored_names and not f.lower().startswith("vcredist"):
                    full = os.path.join(root, f)
                    candidates.append(full)

        if candidates:
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
