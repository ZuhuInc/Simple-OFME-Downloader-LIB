import os
import sys
import json
from flask import Flask, jsonify, request

# Ensure local package imports work when running this file directly
sys.path.insert(0, os.path.dirname(__file__))

from backend.config import Config
from backend.downloader import Downloader
from backend.version_checker import fetch_db_text, check_versions_from_text

app = Flask('fanta_ofme_backend')

DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
config = Config(DATA_FOLDER)
config.load()

downloader = Downloader(download_path=os.path.join(DATA_FOLDER, 'downloads'))


@app.route('/api/status')
def status():
    return jsonify({'status': 'ok', 'version': '0.1.0'})


@app.route('/api/check_db', methods=['POST'])
def check_db():
    data = request.get_json() or {}
    db_url = data.get('db_url')
    if not db_url:
        return jsonify({'error': 'db_url required'}), 400
    try:
        text = fetch_db_text(db_url)
        games = check_versions_from_text(text)
        return jsonify({'games': games})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json() or {}
    url = data.get('url')
    filename = data.get('filename')
    if not url:
        return jsonify({'error': 'url required'}), 400
    job_id = downloader.add_job(url, filename)
    return jsonify({'job_id': job_id})


@app.route('/api/start', methods=['POST'])
def api_start():
    downloader.start()
    return jsonify({'started': True})


if __name__ == '__main__':
    port = int(os.environ.get('FANTA_BACKEND_PORT', '5004'))
    print('Starting backend UI bridge on port', port)
    app.run(host='127.0.0.1', port=port, debug=False)
