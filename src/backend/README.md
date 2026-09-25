Backend package for Fanta OFME Downloader

Files added:
- `config.py` - simple JSON-backed settings manager (`Config`)
- `utils.py` - DB parsing and request helper
- `web_template.py` - ensures web template is downloaded
- `browser.py` - browser detection helpers
- `version_checker.py` - DB fetch and parse helpers
- `downloader.py` - threaded `Downloader` and `DownloadJob`
- `ui_bridge.py` - minimal Flask bridge exposing backend functions to GUI

Run the minimal backend server (for development):

```bash
python src/backend/ui_bridge.py
```

Install runtime deps:

```bash
pip install -r src/backend/requirements.txt
```
