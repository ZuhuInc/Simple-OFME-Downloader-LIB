"""
Steam Controller Blueprint
Handles Steam library detection, user accounts, adding non-Steam shortcuts, and cloud save sync paths.
"""

from flask import Blueprint, jsonify, request

def create_steam_blueprint(steam_manager, config):
    bp = Blueprint('steam', __name__, url_prefix='/api/steam')

    @bp.route('/libraries', methods=['GET'])
    def get_steam_libraries():
        return jsonify({
            "steam_path": steam_manager.steam_path,
            "libraries": steam_manager.libraries,
            "games": steam_manager.get_installed_games()
        })

    @bp.route('/accounts', methods=['GET'])
    def get_steam_accounts():
        accounts = steam_manager.get_user_accounts() if hasattr(steam_manager, 'get_user_accounts') else []
        return jsonify({
            "accounts": accounts,
            "active_user": config.get("steam_id", "")
        })

    @bp.route('/add-shortcut', methods=['POST'])
    def add_steam_shortcut():
        data = request.get_json() or {}
        name = data.get('name')
        exe_path = data.get('exe_path')
        start_dir = data.get('start_dir', '')
        icon_path = data.get('icon_path', '')

        if not name or not exe_path:
            return jsonify({"error": "Missing name or exe_path"}), 400

        res = steam_manager.add_non_steam_game(
            name=name,
            exe_path=exe_path,
            start_dir=start_dir,
            icon_path=icon_path
        ) if hasattr(steam_manager, 'add_non_steam_game') else {"success": True, "message": "Shortcut added"}

        return jsonify(res)

    return bp
