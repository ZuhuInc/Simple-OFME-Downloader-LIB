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

        # Step 2: Filter by source provider (OFME vs SteamRIP vs CG vs All)
        if source in ['ofme', 'onlinefix', 'online-fix']:
            games = [g for g in games if 'online-fix.me' in (g.get('origin_url') or '').lower()]
        elif source in ['sr', 'steamrip', 'steam-rip']:
            games = [g for g in games if 'steamrip.com' in (g.get('origin_url') or '').lower()]
        elif source in ['cg', 'crackedgames', 'cracked-games']:
            games = [g for g in games if 'cracked-games.org' in (g.get('origin_url') or '').lower()]

        # Step 3: Configure bypass list, multi-threading, and caching
        use_bypass = bool(data.get('use_bypass', False))
        active_bypass_list = config.get("version_check_bypass_list", []) if use_bypass else []

        multi_threaded = bool(data.get('multi_threaded', config.get('multi_threaded_scan', False)))
        scan_workers = int(config.get('scan_workers', 6))
        enable_cache = bool(data.get('enable_cache', config.get('enable_scrape_cache', False)))
        cache_ttl_minutes = int(config.get('scrape_cache_ttl_minutes', 15))

        version_checker.update_credentials(
            username=config.get("ofme_username", ""),
            password=config.get("ofme_password", ""),
            webhook_url=config.get("webhook_url", ""),
            enable_webhook=config.get("enable_webhook", False),
            browser_path=config.get("browser_path", ""),
            bypass_list=active_bypass_list,
            multi_threaded=multi_threaded,
            scan_workers=scan_workers,
            enable_cache=enable_cache,
            cache_ttl_minutes=cache_ttl_minutes
        )

        def on_vc_progress(info):
            try:
                socketio.emit("version_check_progress", info, namespace='/')
            except Exception as e:
                print(f"[Bridge] VC Socket error: {e}")

        started = version_checker.start_scan_async(
            games,
            on_vc_progress,
            multi_threaded=multi_threaded,
            scan_workers=scan_workers,
            audit_source=source
        )
        return jsonify({
            "success": started,
            "is_scanning": version_checker.is_scanning,
            "total": len(games),
            "multi_threaded": multi_threaded
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
            old_size = str(existing.get('approx_size') or existing.get('size') or existing.get('ApproxSize') or '').strip()
            scraped_size = str(result.get('approx_size') or '').strip()
            if (not scraped_size or scraped_size.lower() in ('n/a', 'unknown', 'none', 'null')) and old_size and old_size.lower() not in ('n/a', 'unknown', 'none', 'null'):
                result['approx_size'] = old_size
            if existing.get('thumbnail'):
                result['thumbnail'] = existing.get('thumbnail')
            elif not result.get('thumbnail'):
                result['thumbnail'] = ''
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

        raw_size = str(data.get('approx_size') or '').strip()
        existing_size = str(db_game.approx_size if db_game else '').strip()
        if raw_size and raw_size.lower() not in ('none', 'null', 'unknown', 'n/a'):
            approx_size = raw_size
        elif existing_size and existing_size.lower() not in ('none', 'null', 'unknown', 'n/a'):
            approx_size = existing_size
        else:
            approx_size = "Unknown"

        description = data.get('description')
        if not description or str(description).lower() in ('none', 'null'):
            description = db_game.description if db_game else "No description available."

        origin_url = data.get('origin_url')
        if not origin_url or str(origin_url).lower() in ('none', 'null'):
            origin_url = db_game.origin_url if db_game else ""

        # Always preserve existing database thumbnail when updating
        existing_thumb = str(db_game.thumbnail if db_game else '').strip()
        req_thumb = str(data.get('thumbnail') or '').strip()
        if existing_thumb and existing_thumb.lower() not in ('none', 'null'):
            thumbnail = existing_thumb
        else:
            thumbnail = req_thumb if req_thumb.lower() not in ('none', 'null') else ""

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

    @bp.route('/cache/clear', methods=['POST'])
    def clear_scrape_cache():
        cleared = version_checker.clear_cache()
        return jsonify({
            "success": True,
            "cleared_entries": cleared
        })

    @bp.route('/batch-update', methods=['POST'])
    def batch_update_outdated_games():
        data = request.get_json(silent=True) or {}
        games_to_update = data.get('games', [])
        if not games_to_update:
            return jsonify({"success": False, "error": "No outdated games provided to update."}), 400

        preferred_host = data.get('preferred_host', 'GoFile')
        total = len(games_to_update)
        success_count = 0
        updated_list = []

        from ..scraper_service import OnlineFixScraper
        scraper = OnlineFixScraper(
            username=config.get("ofme_username", ""),
            password=config.get("ofme_password", "")
        )

        for idx, item in enumerate(games_to_update, start=1):
            title = (item.get('title') or item.get('game') or '').strip()
            origin_url = (item.get('origin_url') or '').strip()
            latest_version = item.get('latest_version') or item.get('version')

            # Live Socket progress update: "Updating [3/15]: Game Title..."
            try:
                socketio.emit("batch_update_progress", {
                    "status": "updating",
                    "current": idx,
                    "total": total,
                    "game": title
                }, namespace='/')
            except Exception as se:
                print(f"[BatchUpdate] Socket emit error: {se}")

            try:
                # Locate game in database for canonical naming and existing assets
                db_game = None
                origin_url_clean = origin_url.rstrip('/').lower() if origin_url else ''
                for g in getattr(db_manager, 'games', []):
                    if g.title.lower() == title.lower():
                        db_game = g
                        break
                    if origin_url_clean and g.origin_url and g.origin_url.strip().rstrip('/').lower() == origin_url_clean:
                        db_game = g
                        break

                canonical_title = db_game.title if db_game else title

                # Scrape fresh data from online page
                scraped_result = {}
                if origin_url:
                    try:
                        scraped_result = scraper.scrape_game_page(origin_url, preferred_host=preferred_host)
                    except Exception as e:
                        print(f"[BatchUpdate] Error scraping {origin_url}: {e}")

                parts = []
                if isinstance(scraped_result, dict) and scraped_result.get('parts'):
                    parts = [p.strip() for p in scraped_result['parts'] if p and str(p).strip().startswith('http')]
                if not parts and db_game and db_game.parts:
                    parts = list(db_game.parts)

                fix_url = (scraped_result.get('fix_url') if isinstance(scraped_result, dict) else '') or (db_game.fix_url if db_game else '')
                # Size: ensure scraped 'N/A' or missing size does not overwrite valid existing size
                raw_scraped_size = str(scraped_result.get('approx_size', '')).strip() if isinstance(scraped_result, dict) else ''
                existing_size = str(db_game.approx_size if db_game else '').strip()
                if raw_scraped_size and raw_scraped_size.lower() not in ('none', 'null', 'unknown', 'n/a'):
                    approx_size = raw_scraped_size
                elif existing_size and existing_size.lower() not in ('none', 'null', 'unknown', 'n/a'):
                    approx_size = existing_size
                else:
                    approx_size = "Unknown"

                description = (scraped_result.get('description') if isinstance(scraped_result, dict) else None) or (db_game.description if db_game else "No description available.")

                # Thumbnail: Always prioritize existing catalog thumbnail over SteamRIP / Cracked-Games
                existing_thumb = str(db_game.thumbnail if db_game else '').strip()
                scraped_thumb = str(scraped_result.get('thumbnail', '')).strip() if isinstance(scraped_result, dict) else ''
                thumbnail = existing_thumb or scraped_thumb or ""
                category = (db_game.category if (db_game and db_game.category) else "General")

                raw_ver = latest_version or (scraped_result.get('version') if isinstance(scraped_result, dict) else None) or (db_game.version if db_game else "1.0")
                clean_ver = version_checker.clean_version_string(str(raw_ver)) or "1.0"

                host = (scraped_result.get('host') if isinstance(scraped_result, dict) else None) \
                    or item.get('host') \
                    or (getattr(db_game, 'host', None) if db_game else None) \
                    or preferred_host \
                    or 'GoFile'

                catalog_entry = {
                    "title": canonical_title,
                    "version": clean_ver,
                    "host": host,
                    "parts": parts,
                    "fix_url": fix_url,
                    "approx_size": approx_size,
                    "description": description,
                    "thumbnail": thumbnail,
                    "origin_url": origin_url or (db_game.origin_url if db_game else ""),
                    "category": category
                }

                # Update catalog in Data.json & in-memory catalog
                try:
                    db_manager.add_or_update_game(catalog_entry, installed_data=config.data)
                    success_count += 1
                    updated_list.append(canonical_title)
                except Exception as de:
                    print(f"[BatchUpdate] Failed updating '{canonical_title}' in catalog: {de}")
            except Exception as ge:
                print(f"[BatchUpdate] Unexpected error updating '{title}': {ge}")

        # Final completion event
        try:
            socketio.emit("batch_update_progress", {
                "status": "completed",
                "current": total,
                "total": total,
                "success_count": success_count,
                "updated_list": updated_list
            }, namespace='/')
        except Exception:
            pass

        return jsonify({
            "success": True,
            "total": total,
            "updated_count": success_count,
            "updated_games": updated_list
        })

    return bp
