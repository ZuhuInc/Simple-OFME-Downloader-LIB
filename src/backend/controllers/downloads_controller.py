"""
Downloads Controller Blueprint
Handles adding download jobs, pause/resume/cancel operations, queue querying, and archive extraction.
"""

import os
import re
import shutil
import threading
from typing import Any
from flask import Blueprint, jsonify, request

def create_downloads_blueprint(downloader, extractor, config, socketio):
    bp = Blueprint('downloads', __name__, url_prefix='/api')

    @bp.route('/downloads', methods=['GET'])
    def get_downloads():
        return jsonify({"jobs": downloader.get_all_jobs()})

    @bp.route('/downloads/add', methods=['POST'])
    def add_download():
        data = request.get_json() or {}
        url = data.get('url')
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        filename = data.get('filename')
        meta = data.get('meta', {})
        job_id = downloader.add_job(url, filename, meta)
        return jsonify({"success": True, "job_id": job_id})

    @bp.route('/downloads/pause', methods=['POST'])
    def pause_download():
        data = request.get_json() or {}
        job_id = data.get('job_id')
        success = downloader.pause_job(job_id)
        return jsonify({"success": success})

    @bp.route('/downloads/resume', methods=['POST'])
    def resume_download():
        data = request.get_json() or {}
        job_id = data.get('job_id')
        success = downloader.resume_job(job_id)
        return jsonify({"success": success})

    @bp.route('/downloads/cancel', methods=['POST'])
    def cancel_download():
        data = request.get_json() or {}
        job_id = data.get('job_id')
        success = downloader.cancel_job(job_id)
        return jsonify({"success": success})

    @bp.route('/downloads/retry', methods=['POST'])
    def retry_download():
        data = request.get_json() or {}
        job_id = data.get('job_id')
        new_url = data.get('url')
        success = downloader.retry_job(job_id, new_url)
        return jsonify({"success": success})

    @bp.route('/downloads/disk_space', methods=['POST'])
    def check_disk_space():
        data = request.get_json() or {}
        install_path = (data.get('install_path') or '').strip()
        download_path = (data.get('download_path') or '').strip() or getattr(downloader, 'download_path', '')
        if not download_path:
            download_path = os.path.join(os.path.expanduser("~"), "Downloads", "OFME")

        game_size_raw = data.get('game_size') or data.get('approx_size') or '10GB'
        auto_delete = bool(data.get('auto_delete', True))

        # Helper to parse string size e.g. "24GB", "500MB", "1.5 GB"
        def parse_size_str(s: Any) -> int:
            if isinstance(s, (int, float)):
                return int(s)
            s_str = str(s).strip().upper()
            m = re.search(r'([\d\.]+)\s*([KMGT]?B?)', s_str)
            if not m:
                return 10 * 1024 * 1024 * 1024  # default 10GB
            val = float(m.group(1))
            unit = m.group(2)
            if 'T' in unit:
                return int(val * (1024 ** 4))
            elif 'G' in unit:
                return int(val * (1024 ** 3))
            elif 'M' in unit:
                return int(val * (1024 ** 2))
            elif 'K' in unit:
                return int(val * 1024)
            return int(val)

        def format_bytes(b: int) -> str:
            if b >= 1024 ** 4:
                return f"{b / (1024 ** 4):.1f} TB"
            elif b >= 1024 ** 3:
                return f"{b / (1024 ** 3):.1f} GB"
            elif b >= 1024 ** 2:
                return f"{b / (1024 ** 2):.1f} MB"
            elif b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"

        download_bytes = parse_size_str(game_size_raw)
        # Extracted files are typically around 1.05 - 1.1x download archive size
        extract_bytes = int(download_bytes * 1.08)

        # Normalize paths and find existing ancestor for disk_usage
        def get_existing_dir_for_disk(path: str) -> str:
            cur = os.path.abspath(path) if path else os.path.abspath(os.getcwd())
            while cur and not os.path.exists(cur):
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
            return cur if os.path.exists(cur) else os.path.abspath(os.path.splitdrive(cur)[0] + "\\")

        dl_check_path = get_existing_dir_for_disk(download_path)
        inst_check_path = get_existing_dir_for_disk(install_path or download_path)

        dl_drive = os.path.splitdrive(dl_check_path)[0].upper() or "C:"
        inst_drive = os.path.splitdrive(inst_check_path)[0].upper() or dl_drive

        same_drive = (dl_drive == inst_drive)

        try:
            dl_usage = shutil.disk_usage(dl_check_path)
            dl_free = dl_usage.free
        except Exception:
            dl_free = 100 * (1024 ** 3)

        try:
            inst_usage = shutil.disk_usage(inst_check_path)
            inst_free = inst_usage.free
        except Exception:
            inst_free = 100 * (1024 ** 3)

        warning = None
        has_sufficient = True

        if same_drive:
            # On the same drive, both archive and extracted game will coexist during extraction
            total_needed = download_bytes + extract_bytes
            dl_needed = download_bytes
            inst_needed = extract_bytes

            dl_ok = dl_free >= total_needed
            inst_ok = dl_ok

            if not dl_ok:
                has_sufficient = False
                warning = (
                    f"Drive {dl_drive} has only {format_bytes(dl_free)} free, but needs at least "
                    f"{format_bytes(total_needed)} ({format_bytes(download_bytes)} download + "
                    f"{format_bytes(extract_bytes)} extraction) for both to co-exist on the same drive."
                )
        else:
            dl_needed = download_bytes
            inst_needed = extract_bytes

            dl_ok = dl_free >= dl_needed
            inst_ok = inst_free >= inst_needed

            if not dl_ok and not inst_ok:
                has_sufficient = False
                warning = (
                    f"Both drives are low on space! Download Drive ({dl_drive}) needs {format_bytes(dl_needed)} "
                    f"(has {format_bytes(dl_free)}) and Install Drive ({inst_drive}) needs {format_bytes(inst_needed)} "
                    f"(has {format_bytes(inst_free)})."
                )
            elif not dl_ok:
                has_sufficient = False
                warning = (
                    f"Download Drive ({dl_drive}) has only {format_bytes(dl_free)} free, but needs "
                    f"{format_bytes(dl_needed)} for the download archives."
                )
            elif not inst_ok:
                has_sufficient = False
                warning = (
                    f"Install Drive ({inst_drive}) has only {format_bytes(inst_free)} free, but needs "
                    f"{format_bytes(inst_needed)} to extract the game files."
                )

        return jsonify({
            "success": True,
            "same_drive": same_drive,
            "has_sufficient_space": has_sufficient,
            "warning": warning,
            "download": {
                "drive": dl_drive,
                "path": download_path,
                "free_bytes": dl_free,
                "free_str": format_bytes(dl_free),
                "needed_bytes": dl_needed,
                "needed_str": format_bytes(dl_needed),
                "ok": dl_ok
            },
            "install": {
                "drive": inst_drive,
                "path": install_path,
                "free_bytes": inst_free,
                "free_str": format_bytes(inst_free),
                "needed_bytes": inst_needed,
                "needed_str": format_bytes(inst_needed),
                "ok": inst_ok
            },
            "total_needed_str": format_bytes(download_bytes + extract_bytes)
        })

    @bp.route('/extract', methods=['POST'])
    def extract_archive():
        data = request.get_json() or {}
        job_id = data.get('job_id')
        archive_path = data.get('archive_path')
        title = data.get('title', '')
        custom_extract_dir = data.get('extract_dir')
        password = data.get('password') or config.get('rar_password', 'online-fix.me')
        delete_after = data.get('delete_after', config.get('auto_delete_archive', True))

        if not archive_path:
            return jsonify({"error": "Missing archive_path"}), 400

        # Match job(s) in downloader.jobs to update card status in UI
        matching_jobs = []
        if job_id and job_id in downloader.jobs:
            matching_jobs.append(downloader.jobs[job_id])
        norm_archive = os.path.normpath(archive_path) if archive_path else ""
        for j in downloader.jobs.values():
            if j not in matching_jobs:
                j_norm = os.path.normpath(j.dest_file) if j.dest_file else ""
                if (norm_archive and j_norm == norm_archive) or (title and j.meta.get('title') and j.meta.get('title').strip().lower() == title.strip().lower()):
                    matching_jobs.append(j)

        # Determine if this is a fix or main game
        is_fix = ("fix" in os.path.basename(archive_path).lower()) or ("_fix." in archive_path.lower())

        # Check existing game install location from Data.json
        existing_location = None
        if config and hasattr(config, "data") and title:
            norm_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
            for k, v in config.data.items():
                k_norm = re.sub(r'[^a-zA-Z0-9]', '', k).lower()
                if k.upper() == title.upper() or k_norm == norm_title:
                    existing_location = v.get("location")
                    break

        default_base = (
            config.get("default_download_path") or
            config.get("extract_path") or
            os.path.join(os.path.expanduser("~"), "Games")
        )

        if custom_extract_dir:
            extract_dir = custom_extract_dir
        elif is_fix:
            extract_dir = existing_location if (existing_location and os.path.isdir(existing_location)) else os.path.join(default_base, title)
        else:
            if existing_location and os.path.isdir(existing_location):
                parent_dir = os.path.dirname(os.path.normpath(existing_location))
                extract_dir = parent_dir if (parent_dir and (os.path.exists(parent_dir) or len(parent_dir) <= 3)) else existing_location
            else:
                extract_dir = default_base

        # Notify initial extracting status
        for mj in matching_jobs:
            mj.status = "extracting"
            mj.eta = f"Extracting {mj.filename}..."
            mj.error_msg = ""
            downloader._notify(mj)

        def do_extract():
            def on_progress(info):
                socketio.emit("extraction_status", {**info, "title": title, "job_id": job_id})

            on_progress({"status": "extracting", "file": archive_path, "message": f"Extracting {title or 'archive'}..."})
            res = extractor.extract_archive(
                archive_path=archive_path,
                extract_dir=extract_dir,
                password=password,
                delete_after=delete_after,
                game_title=title,
                is_fix=is_fix,
                progress_cb=on_progress
            )

            if res.get("success"):
                game_dir = res.get("game_dir") or res.get("extract_dir")
                exe_path = res.get("exe_path")
                if title and hasattr(config, "data"):
                    key = title.upper()
                    record = config.data.get(key, {})
                    record["downloaded"] = True
                    record["location"] = game_dir
                    if exe_path:
                        record["exe_path"] = exe_path
                    config.data[key] = record
                    config.save()

                for mj in matching_jobs:
                    mj.status = "completed"
                    mj.progress = 100.0
                    mj.speed_bytes = 0
                    mj.eta = "Installed / Ready"
                    mj.error_msg = ""
                    mj.meta["extracted_dir"] = game_dir
                    if exe_path:
                        mj.meta["exe_path"] = exe_path
                    downloader._notify(mj)

                socketio.emit("extraction_status", {
                    "status": "success",
                    "title": title,
                    "file": archive_path,
                    "dest": game_dir,
                    "exe_path": exe_path,
                    "job_id": job_id
                })
            else:
                err_msg = res.get("error", "Unknown extraction error")
                for mj in matching_jobs:
                    mj.status = "completed"
                    mj.eta = "Done (Extraction Failed)"
                    mj.error_msg = f"Extraction notice: {err_msg}"
                    downloader._notify(mj)

                socketio.emit("extraction_status", {
                    "status": "error",
                    "title": title,
                    "file": archive_path,
                    "error": err_msg,
                    "job_id": job_id
                })

        threading.Thread(target=do_extract, daemon=True).start()
        return jsonify({"success": True, "message": "Extraction started in background"})

    return bp
