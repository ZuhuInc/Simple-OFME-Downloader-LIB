"""
Downloads Controller Blueprint
Handles adding download jobs, pause/resume/cancel operations, queue querying, and archive extraction.
"""

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

    @bp.route('/extract', methods=['POST'])
    def extract_archive():
        data = request.get_json() or {}
        archive_path = data.get('archive_path')
        extract_dir = data.get('extract_dir', config.get('extract_path'))
        password = data.get('password', config.get('rar_password', 'online-fix.me'))
        delete_after = data.get('delete_after', config.get('auto_delete_archive', False))

        def on_extract_progress(info):
            socketio.emit("extraction_status", info)

        res = extractor.extract_archive(
            archive_path=archive_path,
            extract_dir=extract_dir,
            password=password,
            delete_after=delete_after,
            progress_cb=on_extract_progress
        )
        return jsonify(res)

    return bp
