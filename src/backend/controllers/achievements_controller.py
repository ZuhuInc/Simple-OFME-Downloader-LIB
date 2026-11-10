"""
Fanta OFME Downloader - Achievements Controller Blueprint
Serves endpoints for achievement summaries, full game progress,
manual test triggers, and schema refreshes.
"""

import re
from flask import Blueprint, jsonify, request


def create_achievements_blueprint(achievement_manager, config, db_manager=None):
    bp = Blueprint('achievements', __name__, url_prefix='/api/achievements')

    @bp.route('/summary', methods=['GET'])
    def get_installed_summary():
        try:
            installed_data = config.data if config and getattr(config, 'data', None) else {}

            # Map of clean title -> db game object
            db_games_map = {}
            if db_manager and hasattr(db_manager, 'games') and db_manager.games:
                for g in db_manager.games:
                    t = getattr(g, 'title', '')
                    clean_k = re.sub(r'[^a-zA-Z0-9]', '', t).lower()
                    if clean_k:
                        db_games_map[clean_k] = g

            enriched_installed = {}
            for title, info in installed_data.items():
                if not isinstance(info, dict):
                    continue
                # Only include installed / downloaded games
                if not info.get("downloaded") and not info.get("location"):
                    continue

                clean_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
                db_g = db_games_map.get(clean_title)
                display_title = getattr(db_g, 'title', title) if db_g else title
                thumbnail = getattr(db_g, 'thumbnail', '') if db_g else info.get('thumbnail', '')
                version = getattr(db_g, 'version', '') if db_g else info.get('version', '')

                enriched_installed[display_title] = {
                    **info,
                    "thumbnail": thumbnail,
                    "version": version
                }

            summaries = achievement_manager.get_installed_summary(enriched_installed)

            total_achievements = sum(s["total"] for s in summaries)
            total_unlocked = sum(s["unlocked_count"] for s in summaries)
            overall_pct = round((total_unlocked / total_achievements * 100), 1) if total_achievements > 0 else 0

            return jsonify({
                "success": True,
                "total_games": len(summaries),
                "total_achievements": total_achievements,
                "total_unlocked": total_unlocked,
                "overall_percentage": overall_pct,
                "games": summaries
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route('/game', methods=['GET'])
    def get_game_achievements():
        title = request.args.get('title', '').strip()
        appid = request.args.get('appid', '').strip() or None

        if not title and not appid:
            return jsonify({"success": False, "error": "Missing title or appid parameter"}), 400

        try:
            installed_data = config.data if config and getattr(config, 'data', None) else {}
            game_data = installed_data.get(title) if title else None

            if not game_data and db_manager and hasattr(db_manager, 'games') and db_manager.games:
                clean_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
                for g in db_manager.games:
                    if re.sub(r'[^a-zA-Z0-9]', '', getattr(g, 'title', '')).lower() == clean_title:
                        game_data = {
                            "thumbnail": getattr(g, 'thumbnail', ''),
                            "version": getattr(g, 'version', ''),
                            "origin_url": getattr(g, 'origin_url', '')
                        }
                        break

            progress = achievement_manager.get_game_achievements(
                title=title,
                appid=appid,
                game_data=game_data
            )
            return jsonify({
                "success": True,
                "data": progress
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route('/test-unlock', methods=['POST'])
    def test_unlock():
        body = request.get_json() or {}
        title = body.get('title', 'Fanta OFME').strip()
        appid = body.get('appid')
        api_name = body.get('api_name')

        try:
            result = achievement_manager.trigger_test_unlock(
                title=title,
                appid=appid,
                api_name=api_name
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route('/reset', methods=['POST'])
    def reset_unlocks():
        body = request.get_json() or {}
        title = body.get('title', '').strip()
        appid = body.get('appid')

        if not title and not appid:
            return jsonify({"success": False, "error": "Missing title or appid"}), 400

        try:
            result = achievement_manager.reset_game_unlocks(title=title, appid=appid)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return bp
