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

def build(tauri_sidecar: bool = False):
    print(f"[Build Backend] Starting PyInstaller compilation from {ENTRY_POINT} (tauri_sidecar={tauri_sidecar})...")

    target_dist = os.path.join(ROOT_DIR, "src-tauri", "binaries") if tauri_sidecar else OUTPUT_DIR
    sidecar_name = "bridge_server-x86_64-pc-windows-msvc" if tauri_sidecar else "bridge_server"

    if tauri_sidecar:
        os.makedirs(target_dist, exist_ok=True)
        old_bin = os.path.join(target_dist, f"{sidecar_name}.exe")
        if os.path.exists(old_bin):
            os.remove(old_bin)
    elif os.path.exists(OUTPUT_DIR):
        print(f"[Build Backend] Cleaning previous output: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

    # Determine data separator (';' on Windows, ':' on Unix)
    sep = ";" if sys.platform == "win32" else ":"
    data_arg = f"{os.path.join(SRC_BACKEND, 'data')}{sep}data"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onefile" if tauri_sidecar else "--onedir",
        "--name", sidecar_name,
        "--distpath", target_dist,
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
        "--collect-all=selenium",
        "--hidden-import=selenium",
        "--hidden-import=selenium.webdriver",
        "--hidden-import=selenium.webdriver.chrome.webdriver",
        "--hidden-import=selenium.webdriver.chrome.options",
        "--hidden-import=selenium.webdriver.chrome.service",
        "--hidden-import=selenium.webdriver.firefox.webdriver",
        "--hidden-import=selenium.webdriver.firefox.options",
        "--hidden-import=selenium.webdriver.firefox.service",
        "--hidden-import=selenium.webdriver.edge.webdriver",
        "--hidden-import=selenium.webdriver.edge.options",
        "--hidden-import=selenium.webdriver.edge.service",
        "--hidden-import=selenium.webdriver.common.by",
        "--hidden-import=selenium.webdriver.support.ui",
        "--hidden-import=selenium.webdriver.support.expected_conditions",
        "--hidden-import=selenium.common.exceptions",
    ]

    if os.path.exists(ICON_PATH):
        cmd.extend([f"--icon={ICON_PATH}"])

    cmd.append(ENTRY_POINT)

    print(f"[Build Backend] Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT_DIR)

    if result.returncode != 0:
        print(f"[Build Backend] ERROR: PyInstaller compilation failed with code {result.returncode}")
        sys.exit(result.returncode)

    if tauri_sidecar:
        out_exe = os.path.join(target_dist, f"{sidecar_name}.exe")
        print(f"[Build Backend] SUCCESS: Tauri sidecar compiled -> {out_exe}")
    else:
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
    build(tauri_sidecar="--tauri-sidecar" in sys.argv)
