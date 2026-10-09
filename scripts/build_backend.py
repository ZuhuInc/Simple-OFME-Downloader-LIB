"""
Build Script: Freezes the Python backend into a standalone executable using PyInstaller.
Output is placed in dist_backend/ for bundling into the Electron package.
"""

import os
import sys
import shutil
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_BACKEND = os.path.join(ROOT_DIR, "src", "backend")
ENTRY_POINT = os.path.join(SRC_BACKEND, "bridge_server.py")
OUTPUT_DIR = os.path.join(ROOT_DIR, "dist_backend")
ICON_PATH = os.path.join(ROOT_DIR, "src", "renderer", "assets", "OFME-DWND-ICO.ico")

def build():
    print(f"[Build Backend] Starting PyInstaller compilation from {ENTRY_POINT}...")

    # Clean old output directory
    if os.path.exists(OUTPUT_DIR):
        print(f"[Build Backend] Cleaning previous output: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

    # Determine data separator (';' on Windows, ':' on Unix)
    sep = ";" if sys.platform == "win32" else ":"
    data_arg = f"{os.path.join(SRC_BACKEND, 'data')}{sep}data"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", "bridge_server",
        "--distpath", OUTPUT_DIR,
        "--workpath", os.path.join(ROOT_DIR, "dist_build_temp"),
        "--specpath", os.path.join(ROOT_DIR, "dist_build_temp"),
        f"--add-data={data_arg}",
        "--hidden-import=engineio.async_drivers.threading",
        "--hidden-import=flask_socketio",
        "--hidden-import=simple_websocket",
        "--hidden-import=psutil",
        "--hidden-import=curl_cffi",
        "--hidden-import=requests",
        "--hidden-import=bs4",
        "--hidden-import=winreg",
        "--hidden-import=zlib",
        "--hidden-import=struct",
    ]

    if os.path.exists(ICON_PATH):
        cmd.extend([f"--icon={ICON_PATH}"])

    cmd.append(ENTRY_POINT)

    print(f"[Build Backend] Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT_DIR)

    if result.returncode != 0:
        print(f"[Build Backend] ERROR: PyInstaller compilation failed with code {result.returncode}")
        sys.exit(result.returncode)

    print(f"[Build Backend] SUCCESS: Backend compiled into {OUTPUT_DIR}/bridge_server")

    # Ensure data folder exists directly in bridge_server output as well
    direct_data = os.path.join(OUTPUT_DIR, "bridge_server", "data")
    src_data = os.path.join(SRC_BACKEND, "data")
    if os.path.exists(src_data) and not os.path.exists(direct_data):
        shutil.copytree(src_data, direct_data, dirs_exist_ok=True)
        print(f"[Build Backend] Copied data folder to {direct_data}")

    # Clean temp build directory
    temp_dir = os.path.join(ROOT_DIR, "dist_build_temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    build()
