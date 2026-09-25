"""
Version Checker Controller Blueprint
Scrapes Online-Fix.me to verify game updates and triggers Discord webhooks.
"""

from flask import Blueprint, jsonify, request

def create_version_checker_blueprint(version_checker, db_manager, config, socketio):
    bp = Blueprint('version_checker', __name__, url_prefix='/api/version-check')

    @bp.route('/status', methods=['GET'])
    def get_version_check_status():
        return jsonify(version_checker.get_status())

    @bp.route('/scan', methods=['POST'])
    def scan_versions():
        data = request.get_json(silent=True) or {}
        games = data.get('games') or [g.to_dict() for g in db_manager.games]

        version_checker.update_credentials(
            username=config.get("ofme_username", ""),
            password=config.get("ofme_password", ""),
            webhook_url=config.get("webhook_url", ""),
            enable_webhook=config.get("enable_webhook", False),
            browser_path=config.get("browser_path", ""),
            bypass_list=config.get("version_check_bypass_list", [])
        )

        def on_vc_progress(info):
            try:
                socketio.emit("version_check_progress", info, namespace='/')
            except Exception as e:
                print(f"[Bridge] VC Socket error: {e}")

        started = version_checker.start_scan_async(games, on_vc_progress)
        return jsonify({
            "success": started,
            "is_scanning": version_checker.is_scanning,
            "total": len(games)
        })

    @bp.route('/stop', methods=['POST'])
    def stop_version_scan():
        version_checker.stop_scan()
        return jsonify({"success": True})

    @bp.route('/save-creds', methods=['POST'])
    def save_vc_credentials():
        data = request.get_json(silent=True) or {}
        if 'username' in data: config.set('ofme_username', data['username'])
        if 'password' in data: config.set('ofme_password', data['password'])
        if 'browser_path' in data: config.set('browser_path', data['browser_path'])
        if 'webhook_url' in data: config.set('webhook_url', data['webhook_url'])
        if 'enable_webhook' in data: config.set('enable_webhook', data['enable_webhook'])
        config.save()

        version_checker.update_credentials(
            username=config.get('ofme_username'),
            password=config.get('ofme_password'),
            browser_path=config.get('browser_path'),
            webhook_url=config.get('webhook_url'),
            enable_webhook=config.get('enable_webhook')
        )
        return jsonify({"success": True})

    return bp
