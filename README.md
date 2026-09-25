# FANTA OFME Downloader (v2.0.0)

> **WORK IN PROGRESS (BETA REWORK)**  
> This branch (`BetaRework`) contains the rewritten Fanta OFME Downloader v2.0.0 featuring a modular architecture, modern Electron glassmorphism interface, and unified Python backend bridge. Features and UI are actively being refined.

---

## Overview

**Fanta OFME Downloader** is a modern desktop game library manager and downloader for Online-Fix.me releases. It pairs a responsive Electron frontend with a modular Python backend service to handle downloads, WinRAR extractions, version checking, and Steam shortcuts.

---

## Features

- **Interactive Game Library**: Browse 150+ games with instant live search, tag filtering, installed status tracking, and update indicators.
- **Multi-Threaded Downloader**: Resume-capable downloads with live download speeds, progress indicators, and host resolution (GoFile, PixelDrain, Mega, etc.).
- **Automated Extraction**: Automatic password-protected WinRAR extraction (`online-fix.me`) directly to your games directory.
- **Online-Fix.me Version Checker**: Live scraping and audit scanner to detect outdated local installations and notify you of new updates.
- **Steam Shortcut Integration**: One-click detection of local Steam installations, user accounts, and direct injection of Non-Steam shortcuts.
- **Safety-First Game Management**: 3-way uninstall dialog (Files + Registry, Unregister Only, or Cancel) with strict root-path deletion prevention.
- **Fanta UI Aesthetics**: Dark glassmorphism design, gold accent palette, skeleton loaders, and responsive controls.

---

## Tech Stack & Architecture

- **Frontend**: Electron, HTML5, Vanilla CSS3 (Glassmorphism), Vanilla JavaScript, FontAwesome 6, Socket.IO Client
- **Backend Bridge**: Python 3.10+, Flask, Flask-SocketIO, Requests, BeautifulSoup4
- **Communication**: REST API + WebSockets (`localhost:5004`) for real-time progress streaming

```
├── src/
│   ├── main/                 # Electron main process & IPC window handlers
│   ├── renderer/             # Frontend GUI
│   │   ├── js/controllers/   # Modular UI & subsystem controllers
│   │   ├── styles/           # Main theme and glassmorphism styling
│   │   ├── assets/           # Game posters, icons, and fonts
│   │   ├── index.html        # Single-page UI workspace
│   │   └── app.js            # Frontend bootstrap entry point
│   └── backend/              # Python modular service
│       ├── controllers/      # Flask Blueprints (games, downloads, steam, etc.)
│       ├── config.py         # Persistent Settings & Data manager
│       ├── database.py       # Download database & metadata parser
│       ├── downloader.py     # Multi-threaded download manager
│       ├── extractor.py      # WinRAR automation
│       ├── steam.py          # Steam VDF shortcut parser & writer
│       ├── version_checker.py# Online-fix.me update scanner
│       └── bridge_server.py  # Central Flask + SocketIO bridge runner
```

---

## Getting Started

### Prerequisites
- **Node.js**: v18.0.0 or higher
- **Python**: 3.10 or higher
- **WinRAR**: Installed in default path or configured via Settings

### 1. Clone the repository
```bash
git clone -b BetaRework https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB.git
cd Simple-OFME-Downloader-LIB
```

### 2. Install Node Dependencies
```bash
npm install
```

### 3. Install Python Dependencies
```bash
pip install -r src/backend/requirements.txt
```

### 4. Run Development Build
```bash
npm run dev
```

---

## Running Tests

Backend unit tests can be run via:
```bash
python -m unittest discover -s src/backend/tests
```

---

## License

Internal project by ZuhuInc. All rights reserved.
