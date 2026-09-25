"""
Games Controller Blueprint
Handles game database retrieval, searching, filtering, and manual status overrides.
Includes critical safety protections for game removals and folder operations.
"""

import os
import re
import shutil
from flask import Blueprint, jsonify, request


def create_games_blueprint(db_manager, config):
    bp = Blueprint('games', __name__, url_prefix='/api/games')

    @bp.route('', methods=['GET'])
    def get_games():
        query = request.args.get('q', '')
        host = request.args.get('host', '')
        status_filter = request.args.get('status', 'all')
        sort_by = request.args.get('sort', 'default')
        sort_order = request.args.get('order', 'asc')

        if not db_manager.games:
            db_manager.fetch_and_load(config.get("db_url"), installed_data=config.data)
        else:
            db_manager.update_installed_states(config.data)

        games = db_manager.search_and_filter(
            query=query,
            host=host,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return jsonify({
            "games": games,
            "total": len(games),
            "hosts": db_manager.hosts
        })

    @bp.route('/refresh', methods=['POST'])
    def refresh_games():
        games = db_manager.fetch_and_load(config.get("db_url"), force_refresh=True, installed_data=config.data)
        return jsonify({
            "success": True,
            "total": len(games),
            "hosts": db_manager.hosts
        })

    @bp.route('/mark-status', methods=['POST'])
    def mark_game_status():
        data = request.get_json() or {}
        game_id = data.get('id')
        title = data.get('title') or game_id
        if not game_id:
            return jsonify({"error": "Missing game id"}), 400

        key = title.upper()
        game_state = config.data.get(key, {})
        if 'downloaded' in data:
            game_state['downloaded'] = data['downloaded']
        if 'installed_version' in data:
            game_state['version'] = data['installed_version']
        if 'location' in data:
            game_state['location'] = data['location']

        config.data[key] = game_state
        config.save()
        db_manager.update_installed_states(config.data)
        return jsonify({"success": True, "game_state": game_state})

    @bp.route('/remove', methods=['POST'])
    def remove_game():
        data = request.get_json() or {}
        game_id = data.get('id', '')
        title = data.get('title', '')
        delete_folder = data.get('delete_folder', False)

        if not game_id and not title:
            return jsonify({"error": "Missing game id or title"}), 400

        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
        norm_id = re.sub(r'[^a-zA-Z0-9]', '', game_id.lower())

        found_key = None
        for k in list(config.data.keys()):
            k_norm = re.sub(r'[^a-zA-Z0-9]', '', k.lower())
            if k.upper() == title.upper() or k_norm in (norm_title, norm_id):
                found_key = k
                break

        game_location = ""
        if found_key:
            game_location = config.data[found_key].get('location', '')
            del config.data[found_key]
            config.save()

        # Strict safety protections: never delete root drives or base games directories
        if delete_folder and game_location:
            protected_roots = {
                "", "c:\\", "d:\\", "e:\\",
                os.path.normpath(config.get("default_download_path", r"D:\GAMES2")).lower(),
                os.path.normpath(config.get("extract_path", "")).lower(),
                os.path.normpath(config.get("download_path", "")).lower(),
                r"d:\games2", r"d:\games", r"c:\games"
            }

            norm_loc = os.path.normpath(game_location).lower()
            target_to_delete = None

            if norm_loc in protected_roots:
                # Location was pointing to the root container (e.g. D:\GAMES2); only target the game's subfolder!
                sub_candidate = os.path.join(game_location, title)
                if os.path.exists(sub_candidate) and os.path.isdir(sub_candidate):
                    target_to_delete = sub_candidate
            else:
                target_to_delete = game_location

            # Double-check target is valid, existing, and NOT protected
            if target_to_delete and os.path.normpath(target_to_delete).lower() not in protected_roots:
                if os.path.exists(target_to_delete) and os.path.isdir(target_to_delete):
                    try:
                        shutil.rmtree(target_to_delete, ignore_errors=True)
                        print(f"[Games] Safely deleted specific game subfolder: {target_to_delete}")
                    except Exception as e:
                        print(f"[Games] Error deleting game subfolder: {e}")

        db_manager.update_installed_states(config.data)
        return jsonify({"success": True, "removed": found_key or title})

    @bp.route('/remove-steam', methods=['POST'])
    def remove_steam_link():
        data = request.get_json() or {}
        game_id = data.get('id', '')
        title = data.get('title', '')

        if not game_id and not title:
            return jsonify({"error": "Missing game id or title"}), 400

        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
        norm_id = re.sub(r'[^a-zA-Z0-9]', '', game_id.lower())

        found_key = None
        for k in list(config.data.keys()):
            k_norm = re.sub(r'[^a-zA-Z0-9]', '', k.lower())
            if k.upper() == title.upper() or k_norm in (norm_title, norm_id):
                found_key = k
                break

        if found_key and 'steam_url' in config.data[found_key]:
            del config.data[found_key]['steam_url']
            config.save()
            db_manager.update_installed_states(config.data)
            return jsonify({"success": True, "message": "Steam shortcut link removed", "game": found_key})

        return jsonify({"success": True, "message": "No Steam shortcut link was found for this title"})

    return bp
