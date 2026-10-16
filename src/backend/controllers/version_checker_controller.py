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

        # Step 3: Configure bypass list
        use_bypass = bool(data.get('use_bypass', True))
        active_bypass_list = config.get("version_check_bypass_list", []) if use_bypass else []

        version_checker.update_credentials(
            username=config.get("ofme_username", ""),
            password=config.get("ofme_password", ""),
            webhook_url=config.get("webhook_url", ""),
            enable_webhook=config.get("enable_webhook", False),
            browser_path=config.get("browser_path", ""),
            bypass_list=active_bypass_list
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

    @bp.route('/bypass', methods=['GET'])
    def get_bypass_list():
        return jsonify({
            "success": True,
            "bypass_list": config.get("version_check_bypass_list", [])
        })

    @bp.route('/bypass/toggle', methods=['POST'])
    def toggle_game_bypass():
        data = request.get_json(silent=True) or {}
        title = (data.get('game_title') or data.get('title') or '').strip()
        if not title:
            return jsonify({"success": False, "error": "Game title is required"}), 400

        current_list = list(config.get("version_check_bypass_list", []))
        explicit_state = data.get('bypassed')  # Optional bool: True to bypass, False to unbypass

        existing_match = None
        for item in current_list:
            if item.lower() == title.lower():
                existing_match = item
                break

        if explicit_state is not None:
            if explicit_state and not existing_match:
                current_list.append(title)
                is_bypassed = True
            elif not explicit_state and existing_match:
                current_list.remove(existing_match)
                is_bypassed = False
            else:
                is_bypassed = bool(existing_match)
        else:
            if existing_match:
                current_list.remove(existing_match)
                is_bypassed = False
            else:
                current_list.append(title)
                is_bypassed = True

        config.set("version_check_bypass_list", current_list)
        config.save()
        version_checker.bypass_list = current_list

        return jsonify({
            "success": True,
            "game_title": title,
            "bypassed": is_bypassed,
            "bypass_list": current_list
        })

    @bp.route('/bypass/clear', methods=['POST'])
    def clear_bypass_list():
        config.set("version_check_bypass_list", [])
        config.save()
        version_checker.bypass_list = []
        return jsonify({"success": True, "bypass_list": []})

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

        # Find existing game in database to maintain thumbnail / description
        db_game = None
        origin_url_req = str(data.get('origin_url', '')).strip().rstrip('/').lower()
        for g in getattr(db_manager, 'games', []):
            if g.title.lower() == game_title.lower():
                db_game = g
                break
            if origin_url_req and g.origin_url and g.origin_url.strip().rstrip('/').lower() == origin_url_req:
                db_game = g
                break

        canonical_title = db_game.title if db_game else game_title

        # Clean parts list
        parts_clean = []
        if 'parts' in data and data['parts']:
            parts_clean = [p.strip() for p in data['parts'] if p and str(p).strip().startswith('http')]

        approx_size = data.get('approx_size')
        if not approx_size or str(approx_size).lower() in ('none', 'null', 'unknown', 'n/a'):
            approx_size = db_game.approx_size if db_game else "Unknown"

        description = data.get('description')
        if not description or str(description).lower() in ('none', 'null'):
            description = db_game.description if db_game else "No description available."

        origin_url = data.get('origin_url')
        if not origin_url or str(origin_url).lower() in ('none', 'null'):
            origin_url = db_game.origin_url if db_game else ""

        thumbnail = data.get('thumbnail')
        if not thumbnail or str(thumbnail).lower() in ('none', 'null'):
            thumbnail = db_game.thumbnail if db_game else ""

        category = data.get('category')
        if not category:
            category = db_game.category if (db_game and db_game.category) else "General"

        raw_ver = data.get('version') or (db_game.version if db_game else "1.0")
        clean_ver = version_checker.clean_version_string(str(raw_ver)) or "1.0"

        catalog_entry = {
            "title": canonical_title,
            "version": clean_ver,
            "host": data.get('host', 'GoFile'),
            "parts": parts_clean,
            "fix_url": data.get('fix_url', '').strip() if data.get('fix_url') else "",
            "approx_size": approx_size,
            "description": description,
            "thumbnail": thumbnail,
            "origin_url": origin_url,
            "category": category
        }

        # If this game had a spurious placeholder in installed games without location or downloaded flag, remove it
        installed = config.data
        keys_to_clean = [k for k in list(installed.keys()) if k.lower() == game_title.lower()]
        for k in keys_to_clean:
            entry = installed.get(k)
            if isinstance(entry, dict) and not entry.get('location') and not entry.get('downloaded'):
                installed.pop(k, None)
                config.save_installed_games(installed)

        # Save ONLY to catalog Data.json file and sync in-memory list (never overwrite user's installed game version)
        try:
            db_manager.add_or_update_game(catalog_entry, installed_data=installed)
        except Exception as de:
            print(f"[VersionChecker] Warning saving to local Data.json: {de}")

        print(f"[VersionChecker] Successfully updated catalog for '{game_title}' in Data.json (v{clean_ver})")
        return jsonify({
            "success": True,
            "message": f"Successfully updated '{game_title}' in Data.json!",
            "game": catalog_entry
        })

    return bp
