"""
Downloads Controller Blueprint
Handles adding download jobs, pause/resume/cancel operations, queue querying, and archive extraction.
"""

import os
import re
import threading
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
