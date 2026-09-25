"""
Settings Controller Blueprint
Handles app configuration, browser discovery, system status, and system path settings.
"""

from flask import Blueprint, jsonify, request
from backend.resolver import get_installed_browsers

def create_settings_blueprint(config, extractor, steam_manager, db_manager, downloader, version_checker):
    bp = Blueprint('settings', __name__, url_prefix='/api')

    @bp.route('/status', methods=['GET'])
    def get_status():
        return jsonify({
            "status": "online",
            "version": "2.0.0",
            "winrar_installed": extractor.is_winrar_available(),
            "steam_detected": bool(steam_manager.steam_path),
            "total_games": len(db_manager.games)
        })

    @bp.route('/settings', methods=['GET', 'POST'])
    def handle_settings():
        if request.method == 'POST':
            new_settings = request.get_json() or {}
            config.update(new_settings)
            
            # Update live managers
            if hasattr(downloader, 'download_path'):
                downloader.download_path = config.get("download_path")
            if hasattr(downloader, 'max_concurrency'):
                downloader.max_concurrency = int(config.get("concurrent_downloads", 2))
            if hasattr(extractor, 'winrar_path'):
                extractor.winrar_path = config.get("winrar_path")
            if hasattr(version_checker, 'webhook_url'):
                version_checker.webhook_url = config.get("webhook_url", "")
            if hasattr(version_checker, 'enable_notifications'):
                version_checker.enable_notifications = config.get("enable_notifications", True)

            return jsonify({"success": True, "settings": config.to_dict()})

        return jsonify({"settings": config.to_dict()})

    @bp.route('/browsers', methods=['GET'])
    def get_browsers():
        browsers = get_installed_browsers()
        return jsonify({"browsers": browsers})

    @bp.route('/open-url', methods=['POST'])
    def open_external_url():
        import webbrowser
        data = request.get_json(silent=True) or {}
        url = data.get('url', '')
        if url and (url.startswith('http://') or url.startswith('https://')):
            try:
                webbrowser.open(url)
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Invalid URL"}), 400

    return bp
