"""
Flask Controller Blueprint for Cloud Saves & Google Drive Sync
Mounted at /api/cloud
"""

import os
import re
from flask import Blueprint, request, jsonify, render_template_string


def create_cloud_blueprint(cloud_sync, config, db_manager):
    bp = Blueprint('cloud', __name__, url_prefix='/api/cloud')

    @bp.route('/status', methods=['GET'])
    def get_cloud_status():
        tokens = cloud_sync.settings.get("google_tokens", {})
        email = tokens.get("email") if tokens else None
        connected = cloud_sync.is_gdrive_connected()
        provider = cloud_sync.get_provider()
        local_path = cloud_sync.settings.get("local_cloud_path") or cloud_sync._detect_default_cloud_folder()
        has_creds = cloud_sync.has_gdrive_credentials()
        client_id = (cloud_sync.settings.get("gdrive_client_id") or "").strip()

        return jsonify({
            "provider": provider,
            "auto_sync": cloud_sync.is_auto_sync_enabled(),
            "gdrive_connected": connected,
            "gdrive_email": email,
            "has_credentials": has_creds,
            "gdrive_client_id": client_id,
            "local_cloud_path": local_path,
            "default_local_path": cloud_sync._detect_default_cloud_folder()
        })

    @bp.route('/credentials', methods=['POST'])
    def save_credentials():
        data = request.get_json() or {}
        client_id = (data.get("client_id") or "").strip()
        client_secret = (data.get("client_secret") or "").strip()

        # Support raw or parsed credentials.json file content
        json_content = data.get("credentials_json")
        if json_content and isinstance(json_content, dict):
            app_dict = json_content.get("installed") or json_content.get("web") or json_content
            if isinstance(app_dict, dict):
                client_id = (app_dict.get("client_id") or client_id).strip()
                client_secret = (app_dict.get("client_secret") or client_secret).strip()

        if not client_id:
            return jsonify({"success": False, "error": "Client ID is required"}), 400

        cloud_sync.settings["gdrive_client_id"] = client_id
        if client_secret:
            cloud_sync.settings["gdrive_client_secret"] = client_secret
        cloud_sync.save_settings()
        return jsonify({"success": True, "message": "Google Drive API credentials saved successfully!"})

    @bp.route('/configure', methods=['POST'])
    def configure_cloud():
        data = request.get_json() or {}
        if "provider" in data:
            cloud_sync.settings["provider"] = data["provider"]
        if "auto_sync" in data:
            cloud_sync.settings["auto_sync"] = bool(data["auto_sync"])
        if "local_cloud_path" in data and data["local_cloud_path"]:
            cloud_sync.settings["local_cloud_path"] = data["local_cloud_path"]
        if "gdrive_client_id" in data and data["gdrive_client_id"]:
            cloud_sync.settings["gdrive_client_id"] = data["gdrive_client_id"].strip()
        if "gdrive_client_secret" in data and data["gdrive_client_secret"]:
            cloud_sync.settings["gdrive_client_secret"] = data["gdrive_client_secret"].strip()

        cloud_sync.save_settings()
        return jsonify({"success": True, "settings": cloud_sync.settings})

    @bp.route('/auth_url', methods=['GET'])
    def get_auth_url():
        needs_setup = not cloud_sync.has_gdrive_credentials()
        url = cloud_sync.get_oauth_auth_url()
        return jsonify({
            "success": True,
            "auth_url": url,
            "needs_setup": needs_setup
        })

    @bp.route('/oauth_callback', methods=['GET'])
    def oauth_callback():
        code = request.args.get('code')
        error = request.args.get('error')

        if error:
            html = f"""<!DOCTYPE html>
            <html><head><title>Authorization Denied</title><style>
                body {{ background: #0a0a0d; color: #f0eee9; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: #121217; padding: 32px; border-radius: 12px; border: 1px solid #e05252; text-align: center; max-width: 450px; }}
                h2 {{ color: #e05252; margin-top: 0; }}
            </style></head><body><div class="card">
                <h2>Authorization Cancelled</h2>
                <p>Google authentication was cancelled: {error}</p>
                <p>You can close this tab and return to Fanta OFME Downloader.</p>
            </div></body></html>"""
            return render_template_string(html), 400

        if not code:
            return "Missing authorization code", 400

        res = cloud_sync.exchange_oauth_code(code)
        if res.get("success"):
            email = res.get("email", "Google Account")
            html = f"""<!DOCTYPE html>
            <html><head><title>Google Drive Connected</title><style>
                body {{ background: #0a0a0d; color: #f0eee9; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: #121217; padding: 40px; border-radius: 14px; border: 1px solid #d4a853; text-align: center; max-width: 480px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); }}
                h2 {{ color: #d4a853; margin-top: 0; font-size: 24px; }}
                .badge {{ background: rgba(62, 207, 142, 0.15); color: #3ecf8e; border: 1px solid #3ecf8e; padding: 6px 14px; border-radius: 20px; font-weight: bold; display: inline-block; margin-bottom: 16px; }}
                p {{ color: #a3a098; line-height: 1.6; }}
            </style></head><body><div class="card">
                <div class="badge">✓ Authorization Successful</div>
                <h2>Google Drive Connected!</h2>
                <p>Logged in as <strong>{email}</strong></p>
                <p>Your game saves will now automatically sync to your private <code>Fanta OFME Cloud Saves</code> folder.</p>
                <p style="margin-top: 24px; font-size: 13px; color: #6e6b63;">You can close this browser window and return to Fanta OFME Downloader.</p>
            </div></body></html>"""
            return render_template_string(html)
        else:
            return f"OAuth token exchange failed: {res.get('error')}", 500

    @bp.route('/disconnect', methods=['POST'])
    def disconnect():
        cloud_sync.disconnect_gdrive()
        return jsonify({"success": True})

    @bp.route('/games', methods=['GET'])
    def list_games():
        results = []
        installed_games = {}

        if config and hasattr(config, "data"):
            installed_games = config.data

        # Build list of games from installed records and db_manager
        game_names = set(installed_games.keys())
        thumb_map = {}

        if db_manager and hasattr(db_manager, "games"):
            # Safely iterate db_manager.games whether it is a list or dict
            games_source = db_manager.games.values() if isinstance(db_manager.games, dict) else (db_manager.games or [])
            for g in games_source:
                title = getattr(g, "title", None) or (g.get("title") if isinstance(g, dict) else None)
                if title:
                    game_names.add(title)
                    thumb = getattr(g, "thumbnail", None) or (g.get("thumbnail") if isinstance(g, dict) else "")
                    if thumb:
                        thumb_map[title.strip().lower()] = thumb

        # Pre-index cloud saves for fast responses
        cloud_index = cloud_sync.list_all_cloud_saves()

        for title in sorted(list(game_names)):
            record = installed_games.get(title.upper()) or installed_games.get(title) or {}
            is_downloaded = record.get("downloaded", False)
            location = record.get("location")
            app_id = record.get("app_id")

            # Get thumbnail in O(1)
            thumbnail = thumb_map.get(title.strip().lower(), "")

            # Calculate sync status
            status = cloud_sync.get_game_sync_status(title, game_location=location, app_id=app_id, cloud_index=cloud_index)
            status["is_installed"] = is_downloaded
            status["game_location"] = location
            status["thumbnail"] = thumbnail
            results.append(status)

        return jsonify({"success": True, "games": results, "total": len(results)})

    @bp.route('/backup', methods=['POST'])
    def backup_game():
        data = request.get_json() or {}
        title = data.get('title')
        custom_save_path = data.get('save_path')
        if not title:
            return jsonify({"success": False, "error": "Missing game title"}), 400

        res = cloud_sync.backup_game(title, custom_save_path)
        return jsonify(res)

    @bp.route('/restore', methods=['POST'])
    def restore_game():
        data = request.get_json() or {}
        title = data.get('title')
        custom_save_path = data.get('save_path')
        if not title:
            return jsonify({"success": False, "error": "Missing game title"}), 400

        res = cloud_sync.restore_game(title, custom_save_path)
        return jsonify(res)

    @bp.route('/set_save_path', methods=['POST'])
    def set_save_path():
        data = request.get_json() or {}
        title = data.get('title')
        save_path = data.get('save_path')
        if not title:
            return jsonify({"success": False, "error": "Missing game title"}), 400

        cloud_sync.settings.setdefault("custom_save_paths", {})[title] = save_path
        cloud_sync.save_settings()
        return jsonify({"success": True, "save_path": save_path})

    return bp
