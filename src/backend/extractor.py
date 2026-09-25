"""
Fanta OFME Downloader - Archive Extractor & Fix Applicator
Automates WinRAR extraction with password injection, multi-part archive support, and fix patching.
"""

import os
import subprocess
import zipfile
import shutil
from typing import Dict, Any, Optional, Callable


class Extractor:
    DEFAULT_RAR_PASSWORD = "online-fix.me"

    def __init__(self, winrar_path: str = r"C:\Program Files\WinRAR\WinRAR.exe"):
        self.winrar_path = winrar_path

    def is_winrar_available(self) -> bool:
        return os.path.exists(self.winrar_path)

    def extract_archive(
        self,
        archive_path: str,
        extract_dir: str,
        password: str = DEFAULT_RAR_PASSWORD,
        delete_after: bool = False,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Extracts archive (RAR/ZIP/7Z) to target directory.
        """
        if not os.path.exists(archive_path):
            return {"success": False, "error": f"Archive not found: {archive_path}"}

        os.makedirs(extract_dir, exist_ok=True)
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

        if progress_cb:
            progress_cb({"status": "extracting", "file": archive_name, "dir": extract_dir})

        # 1. WinRAR extraction
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
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                # WinRAR return codes: 0 = Successful, 1 = Non-fatal error/warnings
                if result.returncode in [0, 1]:
                    if delete_after and os.path.exists(archive_path):
                        try:
                            os.remove(archive_path)
                        except Exception:
                            pass
                    if progress_cb:
                        progress_cb({"status": "extracted", "file": archive_name, "dir": extract_dir})
                    return {"success": True, "extract_dir": extract_dir}
                else:
                    err_msg = f"WinRAR exited with code {result.returncode}: {result.stderr}"
                    if progress_cb:
                        progress_cb({"status": "error", "error": err_msg})
                    return {"success": False, "error": err_msg}
            except Exception as e:
                err_msg = f"WinRAR execution failed: {e}"
                if progress_cb:
                    progress_cb({"status": "error", "error": err_msg})
                return {"success": False, "error": err_msg}

        # 2. Python Zipfile fallback for .zip files
        if archive_path.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir, pwd=password.encode("utf-8") if password else None)
                if delete_after and os.path.exists(archive_path):
                    try:
                        os.remove(archive_path)
                    except Exception:
                        pass
                if progress_cb:
                    progress_cb({"status": "extracted", "file": archive_name, "dir": extract_dir})
                return {"success": True, "extract_dir": extract_dir}
            except Exception as e:
                err_msg = f"Zip extraction error: {e}"
                if progress_cb:
                    progress_cb({"status": "error", "error": err_msg})
                return {"success": False, "error": err_msg}

        return {
            "success": False,
            "error": "WinRAR was not found at configured path. Please install WinRAR or set path in Settings."
        }

    def apply_fix(
        self,
        fix_archive_path: str,
        game_dir: str,
        password: str = DEFAULT_RAR_PASSWORD
    ) -> Dict[str, Any]:
        """
        Applies fix/patch files directly over the target game directory.
        """
        return self.extract_archive(
            archive_path=fix_archive_path,
            extract_dir=game_dir,
            password=password,
            delete_after=False
        )
