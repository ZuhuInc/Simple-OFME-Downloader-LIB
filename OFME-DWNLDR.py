"""
Zuhu's OFME GUI Downloader V1.5.3

By Zuhu | DC: ZuhuInc | DCS: https://discord.gg/Wr3wexQcD3

--- MODIFIED TO INCLUDE BUZZHEAVIER SUPPORT ---
"""
import sys
import os
import requests
import json
import re
import time
import subprocess
import hashlib
import ctypes
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QScrollArea, QGridLayout, QSizePolicy,
                             QGraphicsOpacityEffect, QStackedWidget, QPushButton,
                             QProgressBar, QLineEdit, QFormLayout, QTabWidget,
                             QPlainTextEdit, QFileDialog)
from PyQt6.QtGui import QPixmap, QFontDatabase, QFont, QTextCursor, QIcon
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject, QThread, QTimer, pyqtSlot

# --- CONFIGURATION ---
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-DWND-ICO.ico"
ICON_PATH = os.path.join(DATA_FOLDER, 'cache', 'OFME-DWND-ICO.ico')
DATA_FILE = os.path.join(DATA_FOLDER, 'Data.json')
SETTINGS_FILE = os.path.join(DATA_FOLDER, 'Settings.json')
FONT_URL = "https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/raw/main/Assets/pixelmix.ttf"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
DEFAULT_DOWNLOAD_PATH = ""

# --- STYLING ---
STYLESHEET = """
    QWidget { background-color: #2c2c2c; }
    QProgressBar {
        border: 1px solid #5A5A5A; border-radius: 5px; text-align: center;
        background-color: #404040; height: 12px;
    }
    QProgressBar::chunk { background-color: #00ff7f; border-radius: 4px; }
    QPushButton {
        background-color: #404040; border: 1px solid #5A5A5A;
        padding: 5px 10px; color: #cccccc;
    }
    QPushButton:hover { background-color: #505050; }
    QLineEdit {
        border: 1px solid #5A5A5A; background-color: #404040;
        padding: 5px; color: #cccccc; min-height: 20px;
    }
    QScrollArea { border: none; }
    QTabWidget::pane { border: 1px solid #5A5A5A; }
    QTabBar::tab {
        background-color: #404040; color: #cccccc; padding: 8px;
        border: 1px solid #5A5A5A; border-bottom: none;
    }
    QTabBar::tab:selected { background-color: #2c2c2c; }
    QTabBar::tab:!selected { background-color: #404040; }
    QPlainTextEdit { color: #cccccc; background-color: #333333; border: 1px solid #5A5A5A; }
"""

# --- FUNCTIONS TO LOAD AND SAVE SETTINGS ---
def load_settings():
    """Loads settings from settings.json if it exists."""
    global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                WINRAR_PATH = settings.get('winrar_path', WINRAR_PATH)
                DEFAULT_DOWNLOAD_PATH = settings.get('default_download_path', DEFAULT_DOWNLOAD_PATH)
                print("Settings loaded from file.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Could not load settings file: {e}. Using defaults.")
    else:
        print("No settings file found. Using defaults.")

def save_settings_to_file():
    """Saves the current settings to settings.json."""
    os.makedirs(DATA_FOLDER, exist_ok=True)
    settings = {
        'winrar_path': WINRAR_PATH,
        'default_download_path': DEFAULT_DOWNLOAD_PATH
    }
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        print("Settings saved to file.")
    except IOError as e:
        print(f"ERROR: Could not save settings to file: {e}")

# --- STATUS DEFINITIONS ---
class GameStatus:
    UP_TO_DATE = 1; UPDATE_AVAILABLE = 2; NOT_DOWNLOADED = 3
STATUS_INFO = {
    GameStatus.UP_TO_DATE: {'color': '#00ff7f', 'text': 'UP-TO-DATE'},
    GameStatus.UPDATE_AVAILABLE: {'color': '#ffd700', 'text': 'UPDATE AVAILABLE'},
    GameStatus.NOT_DOWNLOADED: {'color': '#ff4500', 'text': 'NOT DOWNLOADED'}
}

# --- CONSOLE REDIRECTION ---
class ConsoleStream(QObject):
    _text_written = pyqtSignal(str)
    def write(self, text): self._text_written.emit(str(text))
    def flush(self): pass

# --- SETTINGS AND CONSOLE PAGE ---
class SettingsPage(QWidget):
    back_requested = pyqtSignal()
    def __init__(self, main_font):
        super().__init__()
        self.main_font = main_font
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)

        header_layout = QHBoxLayout()
        back_button = QPushButton("« Back to Library"); back_button.setFont(self.main_font)
        back_button.setStyleSheet("padding: 2px 8px;"); back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft); header_layout.addStretch()
        layout.addLayout(header_layout)

        tabs = QTabWidget(); layout.addWidget(tabs, 1)

        console_widget = QWidget(); console_layout = QVBoxLayout(console_widget)
        self.console_output = QPlainTextEdit(); self.console_output.setReadOnly(True)
        console_font = QFont("pixelmix", 12); self.console_output.setFont(console_font)
        console_layout.addWidget(self.console_output)
        tabs.addTab(console_widget, "Console")

        settings_widget = QWidget(); settings_layout = QVBoxLayout(settings_widget)
        form_layout = QFormLayout(); form_layout.setSpacing(10)
        self.winrar_path_edit = QLineEdit(WINRAR_PATH); self.winrar_path_edit.setFont(self.main_font)
        self.download_path_edit = QLineEdit(DEFAULT_DOWNLOAD_PATH); self.download_path_edit.setFont(self.main_font)
        self.data_folder_label = QLabel(DATA_FOLDER); self.data_folder_label.setFont(self.main_font); self.data_folder_label.setStyleSheet("color: #cccccc;")
        form_layout.addRow(QLabel("WinRAR Path:", font=self.main_font, styleSheet="color: #cccccc;"), self.winrar_path_edit)
        form_layout.addRow(QLabel("Default Download Path:", font=self.main_font, styleSheet="color: #cccccc;"), self.download_path_edit)
        form_layout.addRow(QLabel("Data Folder:", font=self.main_font, styleSheet="color: #cccccc;"), self.data_folder_label)
        settings_layout.addLayout(form_layout)
        settings_layout.addStretch()
        save_button = QPushButton("Save Settings"); save_button.setFont(self.main_font); save_button.clicked.connect(self.save_settings)
        settings_layout.addWidget(save_button, 0, Qt.AlignmentFlag.AlignRight)
        tabs.addTab(settings_widget, "Settings")

    def append_to_console(self, text):
        self.console_output.moveCursor(QTextCursor.MoveOperation.End); self.console_output.insertPlainText(text)

    def save_settings(self):
        global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH
        new_winrar_path = self.winrar_path_edit.text()
        if os.path.exists(new_winrar_path):
            WINRAR_PATH = new_winrar_path
            print(f"WinRAR path set to: {WINRAR_PATH}")
        else: print(f"ERROR: WinRAR path does not exist: {new_winrar_path}")
        new_download_path = self.download_path_edit.text()
        if os.path.isdir(new_download_path) or not new_download_path:
            DEFAULT_DOWNLOAD_PATH = new_download_path
            print(f"Default download path set to: '{DEFAULT_DOWNLOAD_PATH}'")
        else: print(f"ERROR: Default download path is not a valid directory: {new_download_path}")
        save_settings_to_file()

# --- DATA AND ASSET MANAGEMENT ---
class DataManager:
    def __init__(self):
        self.games_db = self._parse_github_db()
        self.local_data = self._load_local_data()
        self.games = self._determine_game_statuses()
    def _parse_github_db(self):
        print("Fetching game database from GitHub...");
        try:
            response = requests.get(DB_URL, timeout=15); response.raise_for_status(); text_data = response.text
        except requests.exceptions.RequestException as e: print(f"FATAL: {e}"); return {}
        games = {}; pattern = re.compile(r"^(\w+) \((.+?)\) \[(.+?)\]$", re.MULTILINE)
        for match in pattern.finditer(text_data):
            source, game_name, version = match.groups()
            start_pos = match.end(); next_match = pattern.search(text_data, start_pos)
            end_pos = next_match.start() if next_match else len(text_data)
            game_info = {'name': game_name.strip(), 'version': version.strip(), 'Sources': source.strip()}
            for line in text_data[start_pos:end_pos].strip().split('\n'):
                if ':' in line: key, value = line.split(':', 1); game_info[key.strip()] = value.strip()
            games[game_name.upper().strip()] = game_info
        print(f"Found {len(games)} games in the database.")
        return games
    def _load_local_data(self):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f: return {k.upper(): v for k, v in json.load(f).items()}
            except (json.JSONDecodeError, IOError) as e: print(f"ERROR: {e}")
        return {}
    def save_downloaded_game(self, game_name, version, location):
        data = self._load_local_data()
        data[game_name.upper()] = {'version': version, 'location': location}
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Saved game data for {game_name.upper()} at location {location}")
    def _determine_game_statuses(self):
        processed_games = []
        for game_key, db_info in self.games_db.items():
            game_data = db_info.copy()
            if game_key in self.local_data:
                local_version = self.local_data[game_key].get('version', '0.0')
                game_data['status'] = GameStatus.UP_TO_DATE if local_version == db_info['version'] else GameStatus.UPDATE_AVAILABLE
            else: game_data['status'] = GameStatus.NOT_DOWNLOADED
            processed_games.append(game_data)
        return processed_games
class AssetManager:
    def __init__(self):
        self.cache_dir = os.path.join(DATA_FOLDER, 'cache'); os.makedirs(self.cache_dir, exist_ok=True)
    def get_asset(self, url):
        if not url: return None
        filename = url.split('/')[-1]; local_path = os.path.join(self.cache_dir, filename)
        if not os.path.exists(local_path):
            print(f"Downloading asset: {filename}...")
            try:
                response = requests.get(url, timeout=15); response.raise_for_status()
                with open(local_path, 'wb') as f: f.write(response.content)
            except requests.exceptions.RequestException as e: print(f"ERROR: {e}"); return None
        return local_path

# --- CLICKABLE GAME WIDGET ---
class GameWidget(QWidget):
    clicked = pyqtSignal(dict)
    def __init__(self, game_data, asset_manager, pixel_font):
        super().__init__()
        self.game_data = game_data; self._pixmap = None; self.setFixedSize(200, 300)
        self.status = game_data.get('status', GameStatus.NOT_DOWNLOADED)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        status_info = STATUS_INFO[self.status]; border_color = status_info['color']
        self.content_label = QLabel()
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(self.content_label)
        thumbnail_path = asset_manager.get_asset(game_data.get('Thumbnail'))
        if thumbnail_path and os.path.exists(thumbnail_path):
            self._pixmap = QPixmap(thumbnail_path); self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_label.setStyleSheet(f"QLabel {{ background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 0px; }}")
        else:
            self.content_label.setText(game_data.get('name', 'Unknown')); self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_label.setFont(QFont(pixel_font.family(), 20, QFont.Weight.Bold)); self.content_label.setWordWrap(True)
            self.content_label.setStyleSheet(f"QLabel {{ color: #cccccc; background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 0px; padding: 5px; }}")
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.game_data)
        super().mousePressEvent(event)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap:
            scaled_pixmap = self._pixmap.scaled(self.content_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.content_label.setPixmap(scaled_pixmap)

# --- CLICKABLE STATUS BUTTON ---
class StatusButton(QWidget):
    clicked = pyqtSignal(int)
    def __init__(self, text, color, status_id, pixel_font):
        super().__init__()
        self.status_id = status_id; self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        text_label = QLabel(text); text_label.setFont(pixel_font); text_label.setStyleSheet("color: #cccccc;")
        line = QWidget(); line.setFixedHeight(3); line.setStyleSheet(f"background-color: {color}; border-radius: 1px;")
        layout.addWidget(text_label); layout.addWidget(line)
        self.opacity_effect = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity_effect)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.status_id)
        super().mousePressEvent(event)
    def set_active(self, is_active): self.opacity_effect.setOpacity(1.0 if is_active else 0.4)

# --- DOWNLOAD MANAGER ---
class DownloadManager(QObject):
    progress = pyqtSignal(int, str)
    status_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, game_data):
        super().__init__()
        self.game_data = game_data
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        temp_download_folder = "temp_downloads"
        os.makedirs(temp_download_folder, exist_ok=True)

        main_parts = {}
        for key, value in self.game_data.items():
            if key == 'MainGame': main_parts[0] = value
            elif key.startswith('MainPart'):
                try: part_num = int(key.replace('MainPart', '')); main_parts[part_num] = value
                except ValueError: pass
        sorted_keys = sorted(main_parts.keys())
        main_urls = [main_parts[key] for key in sorted_keys]
        fix_url = self.game_data.get('Fix')

        urls_to_download = main_urls + ([fix_url] if fix_url else [])

        if not urls_to_download:
            self.finished.emit(False, "No valid download links found.", {})
            return

        downloaded_main_paths = []
        downloaded_fix_path = ""
        total_downloads = len(urls_to_download)

        for i, url in enumerate(urls_to_download):
            if not self._is_running:
                self.finished.emit(False, "Download cancelled.", {}); return
            self.status_update.emit(f"Downloading Part {i+1}/{total_downloads}...")

            direct_url, token = url, None
            if "gofile.io" in url:
                direct_url, token = self._resolve_gofile_link(url)
                if not direct_url:
                    self.finished.emit(False, "Failed to resolve GoFile link.", {}); return
            elif "buzzheavier.com" in url:
                direct_url = self._resolve_buzzheavier_link(url)
                if not direct_url:
                    self.finished.emit(False, "Failed to resolve BuzzHeavier link.", {}); return

            downloaded_path = self._download_file(direct_url, temp_download_folder, token)
            if not downloaded_path:
                self.finished.emit(False, "Download failed.", {}); return

            if url == fix_url:
                downloaded_fix_path = downloaded_path
            else:
                downloaded_main_paths.append(downloaded_path)

        if not self._is_running:
            self.finished.emit(False, "Download cancelled.", {}); return

        result_paths = {'main': downloaded_main_paths, 'fix': downloaded_fix_path}
        self.finished.emit(True, "Download complete.", result_paths)

    def _resolve_buzzheavier_link(self, buzzheavier_url):
        self.status_update.emit("Resolving BuzzHeavier link...")
        try:
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'HX-Request': 'true',
                'Referer': buzzheavier_url.rstrip('/') + '/'
            }
            session.headers.update(headers)
            download_trigger_url = buzzheavier_url.rstrip('/') + "/download"
            self.status_update.emit("Downloading From BuzzHeavier...")
            response = session.get(download_trigger_url, allow_redirects=False, timeout=15)

            if response.status_code >= 400:
                print(f"ERROR: Server returned status code {response.status_code}")
                return None

            if 'hx-redirect' in response.headers:
                final_url = response.headers['hx-redirect']
                print(f"Successfully extracted final URL from hx-redirect header: {final_url}")
                if "buzzheavier.com" in final_url:
                    print("ERROR: Server sent a circular redirect. Anti-bot measure likely triggered.")
                    return None
                return final_url
            else:
                print(f"ERROR: 'hx-redirect' header not found. Status: {response.status_code}. Headers: {response.headers}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"BuzzHeavier resolution error: {e}")
            return None

    def _resolve_gofile_link(self, gofile_url):
        self.status_update.emit("Downloading From GoFile...")
        try:
            headers = {"User-Agent": "Mozilla/5.0"}; token_response = requests.post("https://api.gofile.io/accounts", headers=headers).json()
            if token_response.get("status") != "ok": return None, None
            account_token = token_response["data"]["token"]; content_id = gofile_url.split("/")[-1]; hashed_password = hashlib.sha256(RAR_PASSWORD.encode()).hexdigest()
            api_url = f"https://api.gofile.io/contents/{content_id}"; params = {'wt': '4fd6sg89d7s6', 'password': hashed_password}
            auth_headers = {"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {account_token}"}
            content_response = requests.get(api_url, params=params, headers=auth_headers).json()
            if content_response.get("status") != "ok": return None, None
            data = content_response.get("data", {})
            if data.get("type") == "folder":
                for child_id, child_data in data.get("children", {}).items():
                    if child_data.get("type") == "file": return child_data.get("link"), account_token
            elif data.get("type") == "file": return data.get("link"), account_token
            return None, None
        except Exception as e: print(f"GoFile resolution error: {e}"); return None, None

    def _download_file(self, url, dest_folder, token):
        headers = {'User-Agent': 'Mozilla/5.0'}
        if token: headers['Cookie'] = f'accountToken={token}'    
        try:
            with requests.get(url, stream=True, headers=headers, timeout=(10, 30)) as r:
                r.raise_for_status()
                content_type = r.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    print(f"ERROR: Download link returned an HTML page instead of a file. Aborting.")
                    return None
                local_filename = ""
                if "Content-Disposition" in r.headers:
                    disposition = r.headers['content-disposition']
                    filenames = re.findall('filename="?([^"]+)"?', disposition)
                    if filenames:
                        local_filename = filenames[0]
                if not local_filename:
                    final_url = r.url
                    local_filename = final_url.split('/')[-1].split('?')[0]
                if not local_filename:
                    local_filename = "download.tmp"
                local_filepath = os.path.join(dest_folder, local_filename)
                print(f"Downloading to: {local_filepath}")
                total_size = int(r.headers.get('content-length', 0)); bytes_downloaded = 0; start_time = time.time()
                with open(local_filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if not self._is_running: return None
                        f.write(chunk); bytes_downloaded += len(chunk)
                        if total_size > 0:
                            percentage = int(100 * bytes_downloaded / total_size); elapsed_time = time.time() - start_time
                            speed = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
                            stats = f"{bytes_downloaded/1024/1024:.2f}MB / {total_size/1024/1024:.2f}MB | {speed/1024/1024:.2f} MB/s | {percentage}%"
                            self.progress.emit(percentage, stats)
                return local_filepath
        except requests.exceptions.RequestException as e:
            print(f"Download error: {e}")
            return None

# --- INSTALL MANAGER ---
class InstallManager(QObject):
    main_extraction_finished = pyqtSignal(bool, str, str)
    fix_extraction_finished = pyqtSignal(bool, str)
    cleanup_finished = pyqtSignal(bool, str)
    status_update = pyqtSignal(str)

    def __init__(self, main_paths, fix_path, install_path, is_new_install):
        super().__init__()
        self.main_paths = main_paths or []
        self.fix_path = fix_path
        self.base_install_path = install_path
        self.is_new_install = is_new_install

    @pyqtSlot()
    def start_main_extraction(self):
        if not self.main_paths:
            self.main_extraction_finished.emit(True, "No main game to extract.", self.base_install_path)
            return

        self.status_update.emit("Extracting main game...")
        
        try:
            os.makedirs(self.base_install_path, exist_ok=True)
            before_contents = set(os.listdir(self.base_install_path))
        except OSError as e:
            self.main_extraction_finished.emit(False, f"Failed to access install path: {e}", self.base_install_path)
            return

        success = self._winrar_extraction(self.main_paths[0], self.base_install_path)
        final_install_path = self.base_install_path

        if success:
            if self.is_new_install:
                after_contents = set(os.listdir(self.base_install_path))
                new_items = after_contents - before_contents
                if len(new_items) == 1:
                    new_folder_name = new_items.pop()
                    full_new_path = os.path.join(self.base_install_path, new_folder_name)
                    if os.path.isdir(full_new_path):
                        final_install_path = full_new_path
                        print(f"Detected new game folder: {final_install_path}")
                else:
                    print(f"Multiple or no new items ({len(new_items)}). Using base install path.")
            
            self.main_extraction_finished.emit(True, "Main game extracted.", final_install_path)
        else:
            self.main_extraction_finished.emit(False, "Main game extraction failed!", self.base_install_path)

    @pyqtSlot(str)
    def start_fix_extraction(self, fix_target_path):
        if not self.fix_path:
            self.fix_extraction_finished.emit(True, "No fix to extract.")
            return

        self.status_update.emit(f"Extracting fix to {fix_target_path}...")
        if self._winrar_extraction(self.fix_path, fix_target_path):
            self.fix_extraction_finished.emit(True, "Fix extracted.")
        else:
            self.fix_extraction_finished.emit(False, "Fix extraction failed!")

    @pyqtSlot()
    def cleanup_files(self):
        self.status_update.emit("Cleaning up temporary files...")
        try:
            all_files_to_delete = self.main_paths + ([self.fix_path] if self.fix_path else [])
            for path in all_files_to_delete:
                if path and os.path.exists(path):
                    os.remove(path)
            temp_folder = "temp_downloads"
            if os.path.exists(temp_folder) and not os.listdir(temp_folder):
                os.rmdir(temp_folder)
            self.cleanup_finished.emit(True, "Cleanup complete.")
        except OSError as e:
            error_msg = f"Cleanup failed: {e}"
            print(error_msg)
            self.cleanup_finished.emit(False, error_msg)

    def _winrar_extraction(self, rar_path, dest_folder):
        self.status_update.emit(f"Extracting {os.path.basename(rar_path)}...")
        if not os.path.exists(WINRAR_PATH):
            self.status_update.emit("WinRAR not found!"); return False
        command = [WINRAR_PATH, "x", f"-p{RAR_PASSWORD}", "-ibck", "-o+", os.path.abspath(rar_path), os.path.abspath(dest_folder) + os.sep]
        try:
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(command, check=True, capture_output=True, text=True, startupinfo=si)
            return True
        except subprocess.CalledProcessError as e:
            print(f"WinRAR Error: {e.stderr}"); self.status_update.emit("WinRAR Error! Check console."); return False

# --- GAME DETAILS WIDGET ---
class GameDetailsWidget(QWidget):
    back_requested = pyqtSignal(); refresh_library = pyqtSignal()
    def __init__(self, asset_manager, pixel_font, data_manager):
        super().__init__()
        self.asset_manager = asset_manager; self.pixel_font = pixel_font
        self.data_manager = data_manager
        self.worker_thread = None; self.installer_thread = None
        self.current_game_data = {}
        self.downloaded_file_paths = {}
        self.final_game_path = ""
        self.path_manually_changed = False
        self.installer = None
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20, 20, 20, 20); main_layout.setSpacing(15)
        top_panel_layout = QHBoxLayout(); top_panel_layout.setSpacing(20)
        self.thumbnail_label = QLabel(); self.thumbnail_label.setFixedSize(400, 600)
        top_panel_layout.addWidget(self.thumbnail_label)
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        top_panel_layout.addWidget(right_panel, 1)
        back_button = QPushButton("« Back to Library"); back_button.setFont(self.pixel_font)
        back_button.setStyleSheet("padding: 2px 8px;"); back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self.back_requested.emit)
        info_panel = QWidget(); info_layout = QVBoxLayout(info_panel)
        self.game_name_label = self._create_info_label(); self.sources_label = self._create_info_label()
        self.size_label = self._create_info_label(); self.version_label = self._create_info_label()
        info_layout.addWidget(self._create_info_row("GameName:", self.game_name_label)); info_layout.addWidget(self._create_info_row("Sources:", self.sources_label))
        info_layout.addWidget(self._create_info_row("AproxSize:", self.size_label)); info_layout.addWidget(self._create_info_row("Version:", self.version_label))
        self.description_label = self._create_info_label(); self.description_label.setWordWrap(True); self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.location_bar = QLineEdit(); self.location_bar.setFont(self.pixel_font)
        
        self.fix_prompt_widget = QWidget(); fix_layout = QHBoxLayout(self.fix_prompt_widget); fix_layout.setContentsMargins(0,0,0,0)
        self.fix_label = self._create_info_label("Fix is available. Apply it?"); yes_button = QPushButton("Yes"); yes_button.setFont(self.pixel_font)
        no_button = QPushButton("No"); no_button.setFont(self.pixel_font)
        self.change_path_button = QPushButton("Change Path"); self.change_path_button.setFont(self.pixel_font)
        yes_button.clicked.connect(self.on_fix_yes); no_button.clicked.connect(self.on_fix_no); self.change_path_button.clicked.connect(self.select_fix_path)
        fix_layout.addWidget(self.fix_label, 1); fix_layout.addWidget(yes_button); fix_layout.addWidget(no_button); fix_layout.addWidget(self.change_path_button)
        
        right_layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft); right_layout.addSpacing(20)
        right_layout.addWidget(info_panel); right_layout.addSpacing(20)
        right_layout.addWidget(self._create_info_label("Description:")); right_layout.addWidget(self.description_label, 1)
        right_layout.addStretch(); right_layout.addWidget(self.location_bar); right_layout.addWidget(self.fix_prompt_widget)
        bottom_controls = QWidget(); bottom_layout = QVBoxLayout(bottom_controls)
        bottom_layout.setContentsMargins(0,0,0,0); bottom_layout.setSpacing(5)
        self.status_label = self._create_info_label(""); self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.stats_label = self._create_info_label(""); self.stats_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.download_progress = QProgressBar(); self.download_progress.setTextVisible(False)
        self.download_button = QPushButton("DOWNLOAD"); self.download_button.setFont(self.pixel_font)
        self.download_button.setFixedWidth(150); self.download_button.clicked.connect(self.start_or_cancel_download)
        bar_and_button_layout = QHBoxLayout(); bar_and_button_layout.addWidget(self.download_progress, 1); bar_and_button_layout.addWidget(self.download_button)
        status_line_layout = QHBoxLayout(); status_line_layout.addWidget(self.status_label)
        status_line_layout.addStretch(); status_line_layout.addWidget(self.stats_label)
        bottom_layout.addLayout(status_line_layout); bottom_layout.addLayout(bar_and_button_layout)
        main_layout.addLayout(top_panel_layout, 1); main_layout.addWidget(bottom_controls)

    def _create_info_row(self, title, data_label):
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0,0,0,0)
        title_label = self._create_info_label(title);
        layout.addWidget(title_label); layout.addStretch(); layout.addWidget(data_label)
        return row
    def _create_info_label(self, text=""):
        label = QLabel(text); label.setFont(self.pixel_font); label.setStyleSheet("color: #cccccc;")
        return label

    def set_game_data(self, game_data):
        self.current_game_data = game_data
        self.final_game_path = ""
        self.path_manually_changed = False
        self.downloaded_file_paths = {}
        self.download_progress.setValue(0); self.stats_label.setText(""); self.status_label.setText("")
        self.fix_prompt_widget.setVisible(False)
        
        self.game_name_label.setText(game_data.get('name', 'N/A')); self.sources_label.setText(game_data.get('Sources', 'N/A'))
        self.size_label.setText(game_data.get('ApproxSize', 'N/A')); self.version_label.setText(game_data.get('version', 'N/A'))
        self.description_label.setText(game_data.get('Description', 'No description available.'))
        status = game_data.get('status', GameStatus.NOT_DOWNLOADED); border_color = STATUS_INFO[status]['color']
        self.thumbnail_label.setStyleSheet(f"background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 0px;")
        thumbnail_path = self.asset_manager.get_asset(game_data.get('Thumbnail'))
        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            scaled_pixmap = pixmap.scaled(self.thumbnail_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled_pixmap)
        else: self.thumbnail_label.clear(); self.thumbnail_label.setText("No Image")

        self.download_button.setEnabled(True)
        if status == GameStatus.NOT_DOWNLOADED:
            self.download_button.setText("DOWNLOAD")
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setPlaceholderText("Select a base download folder...")
            self.location_bar.setVisible(True)
        else:
            game_name_key = game_data.get('name', '').upper()
            self.final_game_path = self.data_manager.local_data.get(game_name_key, {}).get('location', '')
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setVisible(True)
            if status == GameStatus.UPDATE_AVAILABLE: self.download_button.setText("UPDATE")
            else: self.download_button.setText("RE-DOWNLOAD")

    def start_or_cancel_download(self):
        if self.worker_thread and self.worker_thread.isRunning():
            if hasattr(self, 'worker'): self.worker.stop()
            self.download_button.setText("DOWNLOAD"); return
        if self.installer_thread and self.installer_thread.isRunning():
            self.status_label.setText("Installation in progress..."); return

        is_new_install = self.current_game_data['status'] == GameStatus.NOT_DOWNLOADED
        path_to_use = ""

        if is_new_install:
            path_to_use = self.location_bar.text()
        else:
            path_to_use = os.path.dirname(self.final_game_path) if self.final_game_path else ""

        if not os.path.isdir(path_to_use):
            self.status_label.setText("Invalid location path!"); return
        
        self.download_button.setText("CANCEL")
        self.worker_thread = QThread()
        self.worker = DownloadManager(self.current_game_data)
        self.worker.moveToThread(self.worker_thread); self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(lambda s, m, p: self.on_download_complete(s, m, p, path_to_use, is_new_install))
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater); self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.progress.connect(self.update_progress); self.worker.status_update.connect(self.status_label.setText)
        self.worker_thread.start()

    def on_download_complete(self, success, message, path_dict, base_path, is_new_install):
        self.status_label.setText(message)
        if success:
            self.downloaded_file_paths = path_dict
            self.installer_thread = QThread()
            self.installer = InstallManager(
                main_paths=self.downloaded_file_paths.get('main', []),
                fix_path=self.downloaded_file_paths.get('fix', ''),
                install_path=base_path,
                is_new_install=is_new_install
)
            self.installer.moveToThread(self.installer_thread)
            self.installer.main_extraction_finished.connect(self.on_main_extraction_complete)
            self.installer.fix_extraction_finished.connect(self.on_fix_extraction_complete)
            self.installer.cleanup_finished.connect(self.on_cleanup_complete)
            self.installer.status_update.connect(self.status_label.setText)
            self.installer_thread.started.connect(self.installer.start_main_extraction)
            self.installer_thread.finished.connect(self.installer.deleteLater)
            self.installer_thread.finished.connect(self.installer_thread.deleteLater)
            self.download_button.setText("EXTRACTING..."); self.download_button.setEnabled(False)
            self.download_progress.setValue(0); self.stats_label.setText("")
            self.installer_thread.start()
        else:
            self.set_game_data(self.current_game_data)

    def on_main_extraction_complete(self, success, message, detected_path):
        self.status_label.setText(message)
        if success:
            self.final_game_path = detected_path
            self.data_manager.save_downloaded_game(
                self.current_game_data['name'], 
                self.current_game_data['version'], 
                self.final_game_path
            )
            self.refresh_library.emit()
            if self.downloaded_file_paths.get('fix'):
                self.fix_prompt_widget.setVisible(True)
                self.location_bar.setVisible(False)
                self.fix_label.setText(f"Apply fix to: {self.final_game_path}?")
                self.download_button.setText("..."); self.download_button.setEnabled(False)
            else:
                if self.installer: self.installer.cleanup_files()
        else:
            self.status_label.setText("Extraction failed. Cleaning up...")
            if self.installer: self.installer.cleanup_files()

    def select_fix_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if directory:
            self.final_game_path = directory
            self.path_manually_changed = True
            self.fix_label.setText(f"Apply fix to: {self.final_game_path}?")
            print(f"User changed fix path to: {self.final_game_path}")

    def on_fix_yes(self):
        self.fix_prompt_widget.setVisible(False)
        if self.installer: self.installer.start_fix_extraction(self.final_game_path)

    def on_fix_no(self):
        self.fix_prompt_widget.setVisible(False)
        if self.installer: self.installer.cleanup_files()

    def on_fix_extraction_complete(self, success, message):
        self.status_label.setText(message)
        if self.installer: self.installer.cleanup_files()

    def on_cleanup_complete(self, success, message):
        self.status_label.setText(message)
        if self.path_manually_changed:
            self.data_manager.save_downloaded_game(
                self.current_game_data['name'], 
                self.current_game_data['version'], 
                self.final_game_path
            )
            self.refresh_library.emit()

        if self.installer_thread and self.installer_thread.isRunning():
            self.installer_thread.quit()
            self.installer_thread.wait()
        self.download_button.setText("UP-TO-DATE")
        self.download_button.setEnabled(False)
        self.downloaded_file_paths = {}
        self.installer = None
        self.installer_thread = None
        if not success: self.set_game_data(self.current_game_data)

    def update_progress(self, value, stats_text):
        self.download_progress.setValue(value); self.stats_label.setText(stats_text)

# --- MAIN LAUNCHER WINDOW ---
class GameLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zuhu's OFME Download GUI 1.5.3")

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        else:
            print(f"Warning: Icon file not found at {ICON_PATH}")

        self.setMinimumSize(640, 480); self.resize(1130, 725)
        self.setStyleSheet(STYLESHEET)

        self.main_layout = QVBoxLayout(self)
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading_label = QLabel("Downloading database and assets, please wait...")
        loading_font = QFont("Arial", 16); self.loading_label.setFont(loading_font)
        self.loading_label.setStyleSheet("color: #cccccc;")

        self.progress_label = QLabel("")
        progress_font = QFont("Arial", 12); self.progress_label.setFont(progress_font)
        self.progress_label.setStyleSheet("color: #cccccc;")

        loading_layout.addWidget(self.loading_label, 0, Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self.progress_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.loading_widget)
        QTimer.singleShot(100, self.perform_initialization)

    def perform_initialization(self):
        self.console_stream = ConsoleStream(); self.console_buffer = []
        self.console_stream._text_written.connect(self.console_buffer.append)
        sys.stdout = self.console_stream; sys.stderr = self.console_stream
        load_settings()
        
        self.asset_manager = AssetManager()
        self.loading_label.setText("Initializing...")
        QApplication.processEvents() 
        self.asset_manager.get_asset(ICON_URL) 

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            QApplication.instance().setWindowIcon(QIcon(ICON_PATH))
            print(f"Successfully set window icon.")
        else:
            print(f"ERROR: Could not download or find icon at: {ICON_PATH}")

        self.loading_label.setText("Fetching game database...")
        QApplication.processEvents()
        self.data_manager = DataManager()
        self.loading_label.setText("Downloading assets, please wait...")
        QApplication.processEvents()

        all_urls = [FONT_URL]
        for game in self.data_manager.games:
            if thumbnail_url := game.get('Thumbnail'):
                all_urls.append(thumbnail_url)

        unique_urls = list(set(all_urls))
        total_assets = len(unique_urls)

        self.asset_manager = AssetManager()
        for i, url in enumerate(unique_urls):
            self.progress_label.setText(f"Downloading asset {i + 1} of {total_assets}")
            self.asset_manager.get_asset(url)
            QApplication.processEvents()

        self.finish_ui_setup()

    def finish_ui_setup(self):
        self.pixel_font = QFont("Arial", 12); self.game_widgets = []
        self.status_buttons = {}; self.current_filter = None
        self.initUI()
        self.loading_widget.hide()
        self.main_layout.removeWidget(self.loading_widget)
        self.loading_widget.deleteLater()
        self.main_layout.addWidget(self.stack)
        QTimer.singleShot(0, self._reflow_games)

    def initUI(self):
        self._load_font()
        self.reflow_timer = QTimer(self); self.reflow_timer.setSingleShot(True)
        self.reflow_timer.setInterval(50); self.reflow_timer.timeout.connect(self._reflow_games)
        self.stack = QStackedWidget()

        grid_page = QWidget(); grid_page_layout = QVBoxLayout(grid_page)
        grid_page_layout.setContentsMargins(0,0,0,0)
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True)
        self.games_container = QWidget(); self.games_layout = QGridLayout(self.games_container)
        self.games_layout.setSpacing(15); self.games_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        for game_data in self.data_manager.games:
            widget = GameWidget(game_data, self.asset_manager, self.pixel_font)
            widget.clicked.connect(self.show_game_details)
            self.game_widgets.append(widget)

        scroll_area.setWidget(self.games_container)
        grid_page_layout.addWidget(scroll_area)
        grid_page_layout.addLayout(self._create_status_legend())

        self.details_page = GameDetailsWidget(self.asset_manager, self.pixel_font, self.data_manager)
        self.details_page.back_requested.connect(self.show_game_grid)
        self.details_page.refresh_library.connect(self.refresh_game_statuses)
        self.settings_page = SettingsPage(self.pixel_font)
        self.settings_page.back_requested.connect(self.show_game_grid)

        initial_console_text = "".join(self.console_buffer)
        self.settings_page.append_to_console(initial_console_text)
        self.console_stream._text_written.disconnect(self.console_buffer.append)
        self.console_stream._text_written.connect(self.settings_page.append_to_console)

        self.stack.addWidget(grid_page); self.stack.addWidget(self.details_page); self.stack.addWidget(self.settings_page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'reflow_timer'): self.reflow_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'game_widgets') and self.game_widgets: self._reflow_games()

    def show_game_details(self, game_data): self.details_page.set_game_data(game_data); self.stack.setCurrentWidget(self.details_page)
    def show_settings_page(self): self.stack.setCurrentWidget(self.settings_page)
    def show_game_grid(self): self.stack.setCurrentIndex(0)

    def refresh_game_statuses(self):
        """Completely rebuilds the game library view to reflect the latest data."""
        while self.games_layout.count():
            item = self.games_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
        self.game_widgets.clear()

        self.data_manager.local_data = self.data_manager._load_local_data()
        self.data_manager.games = self.data_manager._determine_game_statuses()

        for game_data in self.data_manager.games:
            widget = GameWidget(game_data, self.asset_manager, self.pixel_font)
            widget.clicked.connect(self.show_game_details)
            self.game_widgets.append(widget)

        self._reflow_games()
        print("Game library has been completely refreshed.")

    def _reflow_games(self):
        if not hasattr(self, 'games_layout'): return
        while self.games_layout.count():
            item = self.games_layout.takeAt(0)
            if item.widget(): item.widget().setParent(None)

        card_width = 200 + self.games_layout.spacing()
        num_cols = max(1, self.games_container.width() // card_width)
        widgets_to_show = [w for w in self.game_widgets if self.current_filter is None or w.status == self.current_filter]
        for i, widget in enumerate(widgets_to_show):
            row, col = divmod(i, num_cols)
            self.games_layout.addWidget(widget, row, col)

    def _load_font(self):
        font_path = self.asset_manager.get_asset(FONT_URL)
        if font_path:
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1: self.pixel_font = QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 12); print("Loaded pixelmix font.")

    def _create_status_legend(self):
        legend_layout = QHBoxLayout(); legend_layout.setContentsMargins(10, 10, 10, 10)
        for status_id, info in STATUS_INFO.items():
            button = StatusButton(info['text'], info['color'], status_id, self.pixel_font)
            button.clicked.connect(self._on_filter_changed); legend_layout.addWidget(button); self.status_buttons[status_id] = button
        legend_layout.addStretch()
        settings_button = QPushButton("\u2699")
        font = QFont(self.pixel_font); font.setPointSize(14)
        settings_button.setFont(font)
        settings_button.setFixedSize(38, 38)
        settings_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #5A5A5A; background-color: #404040;
                border-radius: 19px; padding: 0px;
            }
            QPushButton:hover { background-color: #505050; }
        """)
        settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_button.clicked.connect(self.show_settings_page)
        legend_layout.addWidget(settings_button)
        return legend_layout

    def _on_filter_changed(self, status_id):
        if self.current_filter == status_id: self.current_filter = None
        else: self.current_filter = status_id
        for s_id, button in self.status_buttons.items():
            is_active = (self.current_filter is None or s_id == self.current_filter)
            button.set_active(is_active)
        self._reflow_games()

if __name__ == '__main__':
    myappid = 'OFME-DWNLDR'
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except AttributeError:
        pass
    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
        print(f"Successfully loaded icon from: {ICON_PATH}")
    else:
        print(f"ERROR: Icon file not found at the specified path: {ICON_PATH}")
    main_window = GameLauncher()
    main_window.show()
    sys.exit(app.exec())