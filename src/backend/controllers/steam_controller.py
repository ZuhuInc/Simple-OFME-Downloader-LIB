"""
Steam Controller Blueprint
Handles Steam library detection, user accounts, active account selection,
reading/adding/deleting non-Steam shortcuts, and cloud save sync paths.
"""

from flask import Blueprint, jsonify, request


def create_steam_blueprint(steam_manager, config, db_manager=None):
    bp = Blueprint('steam', __name__, url_prefix='/api/steam')

    def _get_db_games():
        if db_manager and hasattr(db_manager, 'games'):
            return db_manager.games
        return None

    @bp.route('/accounts', methods=['GET'])
    def get_steam_accounts():
        accounts = steam_manager.get_user_accounts()
        configured_id = config.get("steam_id") or config.get("steam_user_id") or ""
        active_id = steam_manager.get_active_account_id(configured_id)

        # Find active account details
        active_acc = None
        for a in accounts:
            if a.get("account_id") == active_id:
                active_acc = a
                break

        if not active_acc and accounts:
            active_acc = accounts[0]
            active_id = active_acc.get("account_id")

        return jsonify({
            "success": True,
            "steam_path": steam_manager.steam_path,
            "accounts": accounts,
            "active_user": active_id,
            "active_account": active_acc
        })

    @bp.route('/select-account', methods=['POST'])
    def select_steam_account():
        data = request.get_json() or {}
        account_id = str(data.get("account_id", "")).strip()
        if not account_id:
            return jsonify({"error": "Missing account_id"}), 400

        config.set("steam_id", account_id)
        config.set("steam_user_id", account_id)

        accounts = steam_manager.get_user_accounts()
        active_acc = next((a for a in accounts if a["account_id"] == account_id), None)

        fanta_data = getattr(config, 'data', {})
        shortcuts = steam_manager.get_shortcuts(account_id, fanta_games=fanta_data, db_games=_get_db_games())

        return jsonify({
            "success": True,
            "active_user": account_id,
            "active_account": active_acc,
            "shortcuts_count": len(shortcuts)
        })

    @bp.route('/avatar', methods=['GET'])
    def get_steam_avatar():
        steamid64 = request.args.get('steamid64', '').strip()
        if not steamid64:
            return jsonify({"error": "Missing steamid64"}), 400
        avatar_url = steam_manager.get_account_avatar(steamid64)
        return jsonify({
            "success": True,
            "steamid64": steamid64,
            "avatar_url": avatar_url
        })

    @bp.route('/shortcuts', methods=['GET'])
    def get_shortcuts():
        account_id = request.args.get("account_id") or config.get("steam_id") or config.get("steam_user_id")
        fanta_data = getattr(config, 'data', {})
        shortcuts = steam_manager.get_shortcuts(account_id, fanta_games=fanta_data, db_games=_get_db_games())
        fanta_count = sum(1 for s in shortcuts if s.get('is_fanta'))
        return jsonify({
            "success": True,
            "account_id": account_id,
            "shortcuts": shortcuts,
            "fanta_count": fanta_count,
            "total": len(shortcuts)
        })

    @bp.route('/shortcuts/add', methods=['POST'])
    @bp.route('/add-shortcut', methods=['POST'])
    def add_steam_shortcut():
        data = request.get_json() or {}
        name = data.get('name') or data.get('title')
        exe_path = data.get('exe_path') or data.get('exe')
        start_dir = data.get('start_dir', '')
        icon_path = data.get('icon_path') or data.get('icon', '')
        launch_options = data.get('launch_options', '')
        tags = data.get('tags', ['Online-Fix'])
        account_id = data.get('account_id') or config.get('steam_id') or config.get('steam_user_id')

        if not name or not exe_path:
            return jsonify({"error": "Missing name or exe_path"}), 400

        res = steam_manager.add_non_steam_game(
            name=name,
            exe_path=exe_path,
            start_dir=start_dir,
            icon_path=icon_path,
            launch_options=launch_options,
            tags=tags,
            account_id=account_id
        )

        # If matching game exists in Data.json, update steam_url
        if res.get("success") and config and hasattr(config, "data"):
            key = name.upper()
            record = config.data.get(key, {})
            record["steam_url"] = res.get("steam_url")
            config.data[key] = record
            config.save()

        return jsonify(res)

    @bp.route('/shortcuts/delete', methods=['POST'])
    def delete_steam_shortcut():
        data = request.get_json() or {}
        identifier = data.get('appid') or data.get('name') or data.get('shortcut_id') or data.get('id')
        account_id = data.get('account_id') or config.get('steam_id') or config.get('steam_user_id')

        if identifier is None:
            return jsonify({"error": "Missing appid or shortcut name"}), 400

        res = steam_manager.delete_shortcut(str(identifier), account_id=account_id)

        # If matching game in Data.json had this steam link, clear it
        name = data.get('name')
        if res.get("success") and name and config and hasattr(config, "data"):
            key = name.upper()
            if key in config.data:
                config.data[key]["steam_url"] = None
                config.save()

        return jsonify(res)

    @bp.route('/rescan', methods=['POST'])
    def rescan_steam():
        steam_manager.steam_path = steam_manager.detect_steam_path()
        steam_manager.libraries = steam_manager.detect_libraries()
        accounts = steam_manager.get_user_accounts()
        configured_id = config.get("steam_id") or config.get("steam_user_id") or ""
        active_id = steam_manager.get_active_account_id(configured_id)
        fanta_data = getattr(config, 'data', {})
        shortcuts = steam_manager.get_shortcuts(active_id, fanta_games=fanta_data, db_games=_get_db_games())

        return jsonify({
            "success": True,
            "steam_path": steam_manager.steam_path,
            "libraries": steam_manager.libraries,
            "accounts": accounts,
            "active_user": active_id,
            "shortcuts": shortcuts,
            "fanta_count": sum(1 for s in shortcuts if s.get('is_fanta')),
            "total_shortcuts": len(shortcuts)
        })

    @bp.route('/libraries', methods=['GET'])
    def get_steam_libraries():
        return jsonify({
            "steam_path": steam_manager.steam_path,
            "libraries": steam_manager.libraries,
            "games": steam_manager.get_installed_games()
        })

    return bp
