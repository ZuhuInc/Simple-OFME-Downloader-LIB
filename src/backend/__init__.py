"""Fanta OFME Downloader backend package
Modular Python backend for Fanta OFME Downloader.
"""

import json
import os
import sys

__all__ = [
    'config', 'database', 'downloader', 'extractor', 'resolver', 'steam', 'version_checker'
]


def get_app_version() -> str:
    """Dynamically resolves the application version from environment, package.json, or fallback."""
    # 1. Environment variable injected by Electron Main process
    env_ver = os.environ.get("FANTA_APP_VERSION")
    if env_ver and env_ver.strip():
        return env_ver.strip()

    # 2. Check candidate locations for package.json
    candidates = [
        # Source mode: <project_root>/package.json
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "package.json")),
        # Packaged mode: resources/app/package.json
        os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", "..", "package.json")),
        os.path.abspath(os.path.join(os.path.dirname(sys.executable), "package.json")),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "version" in data and data["version"]:
                        return str(data["version"]).strip()
            except Exception:
                pass

    # 3. Fallback default
    return "2.0.9"


__version__ = get_app_version()

