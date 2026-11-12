"""
Games Controller Blueprint
Handles game database retrieval, searching, filtering, and manual status overrides.
Includes critical safety protections for game removals and folder operations.
"""

import os
import re
import shutil
import subprocess
import sys
import webbrowser
from flask import Blueprint, jsonify, request
from ..runners_manager import RunnersManager


def create_games_blueprint(db_manager, config, cloud_sync=None):
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

    @bp.route('/add', methods=['POST'])
    def add_game():
        data = request.get_json(silent=True) or {}
        title = (data.get('title') or data.get('name') or '').strip()
        if not title:
            return jsonify({"success": False, "error": "Game title is required."}), 400

        try:
            entry = db_manager.add_or_update_game(data, installed_data=config.data)
            return jsonify({
                "success": True,
                "message": f"Successfully added '{title}' to Data.json!",
                "game": entry.to_dict()
            })
        except Exception as e:
            print(f"[GamesController] Error adding game: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route('/scrape-info', methods=['POST'])
    def scrape_game_info():
        from ..scraper_service import OnlineFixScraper
        data = request.get_json(silent=True) or {}
        url = (data.get('url') or data.get('origin_url') or '').strip()
        host = data.get('preferred_host') or 'GoFile'

        if not url:
            return jsonify({"success": False, "error": "URL is required for scraping."}), 400

        try:
            scraper = OnlineFixScraper(
                username=config.get("ofme_username", ""),
                password=config.get("ofme_password", "")
            )
            scraped = scraper.scrape_game_page(url, preferred_host=host)
            return jsonify(scraped)
        except Exception as e:
            print(f"[GamesController] Scrape info error: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route('/runners', methods=['GET'])
    def get_game_runners():
        game_id = request.args.get('id', '')
        title = request.args.get('title', '')
        if not game_id and not title:
            return jsonify({"error": "Missing game id or title"}), 400

        # Find matching game in db_manager
        matched_game = None
        for g in db_manager.games:
            if (game_id and g.id == game_id) or (title and g.title.lower() == title.lower()):
                matched_game = g
                break

        if not matched_game:
            return jsonify({"error": "Game not found"}), 404

        runners_def = getattr(matched_game, 'runners', []) or []
        location = matched_game.location or ''
        if not location:
            # Check config.data with exact and normalized matching
            norm_title = re.sub(r'[^a-zA-Z0-9]', '', matched_game.title).lower()
            for k, v in config.data.items():
                if isinstance(v, dict) and (v.get('downloaded') or v.get('status') == 1 or v.get('location')):
                    k_norm = re.sub(r'[^a-zA-Z0-9]', '', str(k)).lower()
                    if k_norm == norm_title or str(k).strip().lower() == matched_game.title.strip().lower():
                        loc = v.get('location', '')
                        if loc and os.path.isdir(loc):
                            location = loc
                            break

        statuses = RunnersManager.get_runners_status(location, runners_def)
        preferred = ""
        for k, v in config.data.items():
            if k.lower() == matched_game.title.lower() and isinstance(v, dict):
                preferred = v.get('preferred_runner', '')
                break

        return jsonify({
            "success": True,
            "game": matched_game.title,
            "location": location,
            "preferred_runner": preferred,
            "runners": statuses
        })

    @bp.route('/runners/install', methods=['POST'])
    def install_game_runner():
        data = request.get_json(silent=True) or {}
        game_id = data.get('id', '')
        title = data.get('title', '')
        runner_id = data.get('runner_id', '')

        if not runner_id:
            return jsonify({"success": False, "error": "Missing runner_id"}), 400

        matched_game = None
        for g in db_manager.games:
            if (game_id and g.id == game_id) or (title and g.title.lower() == title.lower()):
                matched_game = g
                break

        if not matched_game:
            return jsonify({"success": False, "error": "Game not found"}), 404

        runners_def = getattr(matched_game, 'runners', []) or []
        runner_def = next((r for r in runners_def if r.get('id') == runner_id), None)
        if not runner_def:
            return jsonify({"success": False, "error": f"Runner '{runner_id}' not found for game"}), 404

        location = data.get('location') or matched_game.location or ''
        if not location:
            norm_title = re.sub(r'[^a-zA-Z0-9]', '', matched_game.title).lower()
            for k, v in config.data.items():
                if isinstance(v, dict) and (v.get('downloaded') or v.get('status') == 1 or v.get('location')):
                    k_norm = re.sub(r'[^a-zA-Z0-9]', '', str(k)).lower()
                    if k_norm == norm_title or str(k).strip().lower() == matched_game.title.strip().lower():
                        loc = v.get('location', '')
                        if loc and os.path.isdir(loc):
                            location = loc
                            break

        if not location or not os.path.exists(location):
            return jsonify({"success": False, "error": "Game installation folder not found. Please download the game first before installing runners."}), 404

        res = RunnersManager.install_or_update_runner(location, runner_def)
        return jsonify(res)

    @bp.route('/launch', methods=['POST'])
    def launch_game():
        data = request.get_json(silent=True) or {}
        game_id = data.get('id', '')
        title = data.get('title', '')
        direct_only = data.get('direct_only', False)
        runner_id = data.get('runner_id') or data.get('runner')

        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
        norm_id = re.sub(r'[^a-zA-Z0-9]', '', game_id.lower())

        found_key = None
        for k in list(config.data.keys()):
            k_norm = re.sub(r'[^a-zA-Z0-9]', '', k.lower())
            if k.upper() == title.upper() or k_norm in (norm_title, norm_id):
                found_key = k
                break

        game_data = config.data.get(found_key, {}) if found_key else {}

        # 1. Check if launched via Steam
        steam_url = data.get('steam_url') or game_data.get('steam_url')
        if steam_url and not direct_only and not runner_id:
            try:
                if sys.platform == 'win32' and hasattr(os, 'startfile'):
                    os.startfile(steam_url)
                else:
                    webbrowser.open(steam_url)
                return jsonify({
                    "success": True,
                    "method": "steam",
                    "steam_url": steam_url,
                    "message": f"Launching {title or found_key} on Steam..."
                })
            except Exception as e:
                return jsonify({"success": False, "error": f"Failed to launch on Steam: {e}"}), 500

        # 2. Locate executable and determine launch args
        target_exe = None
        launch_args = []

        # Find matching game in db_manager for runner lookup
        matched_game = None
        for g in db_manager.games:
            if (game_id and g.id == game_id) or (title and g.title.lower() == title.lower()):
                matched_game = g
                break

        game_runners = getattr(matched_game, 'runners', []) if matched_game else []
        chosen_runner = None
        if runner_id:
            chosen_runner = next((r for r in game_runners if r.get('id') == runner_id), None)
        elif not data.get('exe_path') and not game_data.get('exe_path') and game_runners:
            # Check if there is a preferred runner stored
            pref_id = game_data.get('preferred_runner')
            if pref_id:
                chosen_runner = next((r for r in game_runners if r.get('id') == pref_id), None)
            if not chosen_runner:
                chosen_runner = game_runners[0]

        location = data.get('location') or game_data.get('location')
        if not location:
            default_bases = [
                config.get("extract_path"),
                config.get("default_download_path"),
                config.get("download_path"),
                r"D:\GAMES2",
                r"D:\Games",
                r"C:\Games"
            ]
            for base in default_bases:
                if base and title:
                    cand = os.path.join(base, title)
                    if os.path.exists(cand):
                        location = cand
                        break

        if chosen_runner and location:
            rel_p = chosen_runner.get('rel_path', '')
            folder = chosen_runner.get('folder', '')
            cand_p = os.path.normpath(os.path.join(location, rel_p))

            # 1. Check if the primary runner executable exists
            if os.path.isfile(cand_p):
                target_exe = cand_p
            else:
                # 2. Check alternative runner executables or builder (e.g. HookshotBuilder.exe)
                folder_dir = os.path.normpath(os.path.join(location, folder)) if folder else os.path.dirname(cand_p)
                if os.path.isdir(folder_dir):
                    alt_candidates = [
                        os.path.join(folder_dir, "hookshot.exe"),
                        os.path.join(folder_dir, "HookshotBuilder.exe"),
                        os.path.join(folder_dir, "bin", "hookshot.exe"),
                        os.path.join(folder_dir, "ocarina.exe"),
                        os.path.join(folder_dir, "lichii.exe")
                    ]
                    for alt in alt_candidates:
                        if os.path.isfile(alt):
                            target_exe = alt
                            break
                    if not target_exe:
                        for f in sorted(os.listdir(folder_dir), reverse=True):
                            fl = f.lower()
                            if fl.endswith(".exe") and any(k in fl for k in ("builder", "setup", "installer", "nx2navi")):
                                target_exe = os.path.join(folder_dir, f)
                                break

            if target_exe:
                # Resolve any launch arguments
                raw_args = chosen_runner.get('args', [])
                for arg in raw_args:
                    if isinstance(arg, str) and not arg.startswith("-") and not os.path.isabs(arg):
                        arg_path = os.path.normpath(os.path.join(location, arg))
                        if not os.path.exists(arg_path):
                            # Try searching inside immediate subfolders (e.g. Legend of Zelda - Ocarina of Time/games/...)
                            try:
                                for sub in os.listdir(location):
                                    sub_p = os.path.join(location, sub, arg)
                                    if os.path.exists(sub_p):
                                        arg_path = os.path.normpath(sub_p)
                                        break
                            except Exception:
                                pass
                        launch_args.append(arg_path)
                    else:
                        launch_args.append(str(arg))

                if found_key:
                    config.data[found_key]['preferred_runner'] = chosen_runner.get('id')
                    config.save()
            elif runner_id:
                # Specific runner explicitly requested, but its files are not found
                return jsonify({
                    "success": False,
                    "error": f"Runner '{chosen_runner.get('name', runner_id)}' executable not found ({rel_p}). Please install the runner or run its builder."
                }), 404

        if not target_exe:
            target_exe = data.get('exe_path') or game_data.get('exe_path')

        if not target_exe or not os.path.exists(target_exe):
            possible_locations = []
            protected_roots = {"C:", "D:", "E:", "F:", "C:\\GAMES", "D:\\GAMES", "D:\\GAMES2"}
            for p in [config.get("extract_path"), config.get("default_download_path"), config.get("download_path")]:
                if p:
                    protected_roots.add(os.path.normpath(p).rstrip("\\/").upper())

            if location:
                norm_loc = os.path.normpath(location).rstrip("\\/").upper()
                if norm_loc not in protected_roots:
                    possible_locations.append(location)
                if title:
                    possible_locations.append(os.path.join(location, title))

            default_bases = [
                config.get("extract_path"),
                config.get("default_download_path"),
                config.get("download_path"),
                r"D:\GAMES2",
                r"D:\Games",
                r"C:\Games"
            ]
            for base in default_bases:
                if base and title:
                    possible_locations.append(os.path.join(base, title))

            from ..extractor import Extractor
            for loc in possible_locations:
                if loc and os.path.exists(loc):
                    cand_exe = Extractor._find_game_exe(loc, game_title=title)
                    if cand_exe and os.path.exists(cand_exe):
                        target_exe = cand_exe
                        break

        if not target_exe or not os.path.exists(target_exe):
            return jsonify({
                "success": False,
                "error": f"Could not find game executable for '{title}'. Please check the installation folder in settings."
            }), 404

        # Cache found exe_path in config.data
        if found_key:
            config.data[found_key]['exe_path'] = target_exe
            config.save()

        # 3. Launch the game executable with its working directory set
        exe_dir = os.path.dirname(target_exe)
        try:
            # Check and restore newer cloud save before launching if auto-sync is enabled
            if cloud_sync and cloud_sync.is_auto_sync_enabled():
                try:
                    cloud_sync.check_and_restore_newer_cloud_save(title)
                except Exception as sync_err:
                    print(f"[CloudSync] Launch check warning: {sync_err}", flush=True)

            flags = 0
            if sys.platform == 'win32':
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                [target_exe] + launch_args,
                cwd=exe_dir,
                creationflags=flags,
                close_fds=True
            )
            print(f"[Games] Executable launched: {target_exe} (PID: {proc.pid}) in {exe_dir}", flush=True)

            # Auto-sync save when game exits if auto-sync is enabled
            if cloud_sync and cloud_sync.is_auto_sync_enabled():
                import threading
                def monitor_and_sync(proc_handle, game_title):
                    try:
                        proc_handle.wait()
                        print(f"[CloudSync] Game '{game_title}' process exited. Auto-backing up save...", flush=True)
                        res = cloud_sync.backup_game(game_title)
                        print(f"[CloudSync] Auto-backup result: {res}", flush=True)
                    except Exception as e:
                        print(f"[CloudSync] Auto-backup on exit error: {e}", flush=True)
                threading.Thread(target=monitor_and_sync, args=(proc, title), daemon=True).start()

            return jsonify({
                "success": True,
                "method": "executable",
                "exe_path": target_exe,
                "pid": proc.pid,
                "message": f"Successfully launched {os.path.basename(target_exe)}!"
            })
        except Exception as proc_err:
            print(f"[Games] Popen failed for {target_exe}, attempting startfile fallback: {proc_err}", flush=True)
            if sys.platform == 'win32' and hasattr(os, 'startfile'):
                try:
                    os.startfile(target_exe)
                    return jsonify({
                        "success": True,
                        "method": "startfile",
                        "exe_path": target_exe,
                        "message": f"Launched {os.path.basename(target_exe)} via Windows!"
                    })
                except Exception as sf_err:
                    return jsonify({"success": False, "error": f"Failed to launch executable: {sf_err}"}), 500
            return jsonify({"success": False, "error": f"Failed to launch executable: {proc_err}"}), 500

    return bp
