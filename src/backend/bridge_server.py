"""
Fanta OFME Downloader - HTTP & WebSocket Bridge Server
Modular server using decoupled controllers for games, downloads, steam, version checks, and settings.
"""

import os
import sys
from flask import Flask
from flask_socketio import SocketIO

# Ensure backend package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.config import Config
from backend.database import DatabaseManager
from backend.downloader import Downloader
from backend.extractor import Extractor
from backend.version_checker import VersionChecker
from backend.steam import SteamManager
from backend.controllers import (
    create_games_blueprint,
    create_downloads_blueprint,
    create_steam_blueprint,
    create_version_checker_blueprint,
    create_settings_blueprint
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fanta-ofme-secret'

# Native CORS handler (eliminates external flask_cors dependency)
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Core Services
config = Config()
db_manager = DatabaseManager(cache_dir=config.cache_folder, default_url=config.get("db_url"))
downloader = Downloader(
    download_path=config.get("download_path"),
    max_concurrency=int(config.get("concurrent_downloads", 2))
)
extractor = Extractor(winrar_path=config.get("winrar_path"))
version_checker = VersionChecker(
    webhook_url=config.get("webhook_url", ""),
    enable_notifications=config.get("enable_notifications", True)
)
steam_manager = SteamManager(custom_path=config.get("steam_path"))

# Connect downloader events to WebSocket
def on_download_progress(job_data):
    try:
        socketio.emit("download_progress", job_data)
    except Exception as e:
        print(f"[Bridge] Socket emit error: {e}")

downloader.set_callback(on_download_progress)

# Register Controller Blueprints
app.register_blueprint(create_games_blueprint(db_manager, config))
app.register_blueprint(create_downloads_blueprint(downloader, extractor, config, socketio))
app.register_blueprint(create_steam_blueprint(steam_manager, config))
app.register_blueprint(create_version_checker_blueprint(version_checker, db_manager, config, socketio))
app.register_blueprint(create_settings_blueprint(config, extractor, steam_manager, db_manager, downloader, version_checker))

# Initial database pre-fetch on startup
try:
    db_manager.fetch_and_load(installed_data=config.data)
except Exception as e:
    print(f"[Bridge] Initial DB fetch skipped: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('FANTA_BACKEND_PORT', '5004'))
    print(f"[Bridge] Starting Fanta OFME Backend Bridge on 127.0.0.1:{port}")
    socketio.run(app, host='127.0.0.1', port=port, debug=False, allow_unsafe_werkzeug=True)
