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
        
        game_id = data.get('game_id')
        installed_only = data.get('installed_only', False)
        source = str(data.get('source', 'all')).lower()

        # Step 1: Base game set
        if game_id:
            games = [g.to_dict() for g in db_manager.games if g.id == game_id]
        elif installed_only:
            games = [g.to_dict() for g in db_manager.games if g.installed_version or g.is_downloaded]
        elif 'games' in data and data['games']:
            games = data['games']
        else:
            games = [g.to_dict() for g in db_manager.games]

        # Step 2: Filter by source provider (OFME vs SteamRIP vs All)
        if source in ['ofme', 'onlinefix', 'online-fix']:
            games = [g for g in games if 'online-fix.me' in (g.get('origin_url') or '').lower()]
        elif source in ['sr', 'steamrip', 'steam-rip']:
            games = [g for g in games if 'steamrip.com' in (g.get('origin_url') or '').lower()]

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

    @bp.route('/scrape-game', methods=['POST'])
    def scrape_game_details():
        from ..scraper_service import OnlineFixScraper
        data = request.get_json(silent=True) or {}
        origin_url = data.get('origin_url', '').strip()
        preferred_host = data.get('preferred_host', 'GoFile')

        if not origin_url:
            # If game_id or game_title provided, find origin_url in db or installed data
            game_title = data.get('game_title') or data.get('title')
            if game_title and game_title in config.data:
                origin_url = config.data[game_title].get('origin_url', '')
            elif game_title:
                matching = [g for g in db_manager.games if g.title.lower() == game_title.lower()]
                if matching:
                    origin_url = matching[0].origin_url

        if not origin_url:
            return jsonify({"success": False, "error": "No origin URL found for this game."}), 400

        scraper = OnlineFixScraper(
            username=config.get("ofme_username", ""),
            password=config.get("ofme_password", "")
        )
        result = scraper.scrape_game_page(origin_url, preferred_host=preferred_host)

        # Comprehensive fallback to existing game info if scraped fields are missing / N/A
        requested_title = (data.get('game_title') or data.get('title') or '').strip()
        scraped_title = (result.get('title') or '').strip()
        
        existing = {}
        
        # 1. Try matching by origin_url in config.data
        if origin_url:
            for k, v in config.data.items():
                if isinstance(v, dict) and v.get('origin_url') and v.get('origin_url').strip().rstrip('/') == origin_url.rstrip('/'):
                    existing = v
                    if 'title' not in existing:
                        existing['title'] = k
                    break
        
        # 2. Try matching by origin_url in db_manager.games
        if not existing and origin_url and hasattr(db_manager, 'games'):
            matching = [g for g in db_manager.games if g.origin_url and g.origin_url.strip().rstrip('/') == origin_url.rstrip('/')]
            if matching:
                existing = matching[0].to_dict()
                
        # 3. Try matching by title in config.data (case-insensitive)
        if not existing:
            for cand in [requested_title, scraped_title]:
                if not cand:
                    continue
                for k, v in config.data.items():
                    if k.lower() == cand.lower() and isinstance(v, dict):
                        existing = v
                        if 'title' not in existing:
                            existing['title'] = k
                        break
                if existing:
                    break
                    
        # 4. Try matching by title in db_manager.games (case-insensitive)
        if not existing and hasattr(db_manager, 'games'):
            for cand in [requested_title, scraped_title]:
                if not cand:
                    continue
                matching = [g for g in db_manager.games if g.title.lower() == cand.lower()]
                if matching:
                    existing = matching[0].to_dict()
                    break

        if existing:
            old_size = existing.get('approx_size') or existing.get('size') or existing.get('ApproxSize')
            if (not result.get('approx_size') or result.get('approx_size') == 'N/A') and old_size and old_size != 'N/A':
                result['approx_size'] = old_size
            if not result.get('thumbnail') and existing.get('thumbnail'):
                result['thumbnail'] = existing.get('thumbnail')
            if not result.get('description') and existing.get('description'):
                result['description'] = existing.get('description')
            if not result.get('category') and existing.get('category'):
                result['category'] = existing.get('category')

        return jsonify(result)

    @bp.route('/apply-game-data', methods=['POST'])
    def apply_game_data():
        data = request.get_json(silent=True) or {}
        game_title = (data.get('title') or data.get('game_title') or '').strip()

        if not game_title:
            return jsonify({"success": False, "error": "Game title is required."}), 400

        installed = config.data
        game_entry = installed.get(game_title, {})

        if 'version' in data: game_entry['version'] = str(data['version']).strip()
        if 'host' in data: game_entry['host'] = data['host']
        if 'parts' in data:
            # Filter out empty or whitespace lines
            parts_clean = [p.strip() for p in data['parts'] if p and str(p).strip().startswith('http')]
            game_entry['parts'] = parts_clean
        if 'fix_url' in data: game_entry['fix_url'] = data['fix_url'].strip() if data['fix_url'] else ""
        if 'approx_size' in data and data['approx_size']: game_entry['approx_size'] = data['approx_size']
        if 'description' in data and data['description']: game_entry['description'] = data['description']
        if 'origin_url' in data and data['origin_url']: game_entry['origin_url'] = data['origin_url']
        if 'thumbnail' in data and data['thumbnail']: game_entry['thumbnail'] = data['thumbnail']
        if 'category' in data and data['category']: game_entry['category'] = data['category']
        elif 'category' not in game_entry: game_entry['category'] = 'General'

        # Remove legacy main_game_url if present
        game_entry.pop('main_game_url', None)

        installed[game_title] = game_entry
        config.save_installed_games(installed)

        # Sync db_manager in-memory list
        for g in db_manager.games:
            if g.title.lower() == game_title.lower():
                g.version = game_entry.get('version', g.version)
                g.host = game_entry.get('host', g.host)
                g.parts = game_entry.get('parts', g.parts)
                g.fix_url = game_entry.get('fix_url', g.fix_url)
                g.approx_size = game_entry.get('approx_size', g.approx_size)

        print(f"[VersionChecker] Successfully updated '{game_title}' in Data.json (v{game_entry.get('version')})")
        return jsonify({
            "success": True,
            "message": f"Successfully updated '{game_title}' in Data.json!",
            "game": game_entry
        })

    return bp
