Project design and mapping notes

Goals:
- Use Electron frontend based on Fanta-Menu-Base / Fanta-CS2 renderer.
- Run Python backend (OFME downloader core) as a separate process or via IPC/HTTP.
- Keep core downloader code modular and importable from a `backend/` package.

Mapping from existing repo (`Simple-OFME-Downloader-LIB`):
- `OFME-DWNLDR.py` -> `backend/ofme_downloader.py` (refactor into classes/functions)
- `OFME-VC.py` -> `backend/version_checker.py` (split CLI utility)
- `Assets/` -> `renderer/assets/` (icons, index.html templates)
- `Download-DB.txt` -> `backend/data/Download-DB.txt` (or remote fetch)

Frontend integration:
- Copy `src/renderer` from `Fanta-Menu-Base` or `Fanta-CS2` into `src/renderer/` here.
- Wire frontend events to backend via a small HTTP API (Flask + Socket.IO) or spawn Python subprocess and use IPC (stdin/stdout or sockets).

Suggested structure:
- src/
  - main/ (electron main + preload)
  - renderer/ (Fanta GUI JS/HTML/CSS)
  - backend/ (python package with CLI entrypoints)
  - scripts/ (helpers to run backend during dev)

Next steps:
1. Copy the Fanta renderer into this repo and verify Electron loads it.
2. Refactor Python code into `backend/` and expose a minimal HTTP API.
3. Implement IPC bridge for live events (Socket.IO or WebSocket).
