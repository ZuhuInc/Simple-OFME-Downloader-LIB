"""
Zuhu's OFME GUI Downloader V1.5-Beta.7

By Zuhu | DC: ZuhuInc | DCS: https://discord.gg/Wr3wexQcD3
"""

import sys
import os
import requests
import json
import re
import time
import subprocess
import hashlib
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QScrollArea, QGridLayout, QSizePolicy,
                             QGraphicsOpacityEffect, QStackedWidget, QPushButton,
                             QProgressBar, QLineEdit, QFormLayout)
from PyQt6.QtGui import QPixmap, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject, QThread, QTimer

# --- CONFIGURATION ---
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
DATA_FILE = os.path.join(DATA_FOLDER, 'Data.json')
FONT_URL = "https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/raw/main/Assets/pixelmix.ttf"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"

# --- STYLING ---
STYLESHEET = """
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
"""

# --- STATUS DEFINITIONS ---
class GameStatus:
    UP_TO_DATE = 1; UPDATE_AVAILABLE = 2; NOT_DOWNLOADED = 3
STATUS_INFO = {
    GameStatus.UP_TO_DATE: {'color': '#00ff7f', 'text': 'UP-TO-DATE'},
    GameStatus.UPDATE_AVAILABLE: {'color': '#ffd700', 'text': 'UPDATE AVAILABLE'},
    GameStatus.NOT_DOWNLOADED: {'color': '#ff4500', 'text': 'NOT DOWNLOADED'}
}

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
            self.content_label.setStyleSheet(f"QLabel {{ background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 10px; }}")
        else:
            self.content_label.setText(game_data.get('name', 'Unknown')); self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_label.setFont(QFont(pixel_font.family(), 20, QFont.Weight.Bold)); self.content_label.setWordWrap(True)
            self.content_label.setStyleSheet(f"QLabel {{ color: #cccccc; background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 10px; padding: 5px; }}")
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

# --- REAL DOWNLOAD MANAGER ---
class DownloadManager(QObject):
    progress = pyqtSignal(int, str); status_update = pyqtSignal(str); finished = pyqtSignal(bool, str, str)
    def __init__(self, game_data, base_path, apply_fix=False):
        super().__init__()
        self.game_data = game_data; self.base_path = base_path; self.apply_fix = apply_fix; self._is_running = True
    def stop(self): self._is_running = False
    def run(self):
        temp_download_folder = "temp_downloads"; os.makedirs(temp_download_folder, exist_ok=True)
        urls_to_download = []
        if self.apply_fix:
            if self.game_data.get('Fix'): urls_to_download.append(self.game_data['Fix'])
        else:
            main_parts = {};
            for key, value in self.game_data.items():
                if key == 'MainGame': main_parts[0] = value
                elif key.startswith('MainPart'):
                    try: part_num = int(key.replace('MainPart', '')); main_parts[part_num] = value
                    except ValueError: pass
            sorted_keys = sorted(main_parts.keys()); urls_to_download = [main_parts[key] for key in sorted_keys]
        if not urls_to_download: self.finished.emit(False, "No valid download links found.", ""); return
        downloaded_paths = []
        for i, url in enumerate(urls_to_download):
            if not self._is_running: self.finished.emit(False, "Download cancelled.", ""); return
            self.status_update.emit(f"Downloading Part {i+1}/{len(urls_to_download)}...")
            direct_url, token = url, None
            if "gofile.io" in url:
                direct_url, token = self._resolve_gofile_link(url)
                if not direct_url: self.finished.emit(False, "Failed to resolve GoFile link.", ""); return
            downloaded_path = self._download_file(direct_url, temp_download_folder, token)
            if not downloaded_path: self.finished.emit(False, "Download failed.", ""); return
            downloaded_paths.append(downloaded_path)
        if not self._is_running: self.finished.emit(False, "Download cancelled.", ""); return
        self.status_update.emit("Extracting files..."); dirs_before = set(os.listdir(self.base_path))
        if self._winrar_extraction(downloaded_paths[0], self.base_path):
            self.status_update.emit("Cleaning up...")
            for path in downloaded_paths:
                try: os.remove(path)
                except OSError as e: print(f"Could not remove {path}: {e}")
            dirs_after = set(os.listdir(self.base_path))
            new_dirs = [d for d in (dirs_after - dirs_before) if os.path.isdir(os.path.join(self.base_path, d))]
            new_game_path = os.path.join(self.base_path, new_dirs[0]) if len(new_dirs) == 1 else self.base_path
            self.finished.emit(True, "Completed!", new_game_path)
        else: self.finished.emit(False, "Extraction Failed!", "")
    def _resolve_gofile_link(self, gofile_url):
        self.status_update.emit("Resolving GoFile link...")
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
        local_filename = url.split('/')[-1].split('?')[0] or "download.tmp"; local_filepath = os.path.join(dest_folder, local_filename)
        try:
            with requests.get(url, stream=True, headers=headers) as r:
                r.raise_for_status()
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
        except Exception as e: print(f"Download error: {e}"); return None
    def _winrar_extraction(self, rar_path, dest_folder):
        self.status_update.emit("Extracting with WinRAR...")
        if not os.path.exists(WINRAR_PATH): self.status_update.emit("WinRAR not found!"); return False
        command = [WINRAR_PATH, "x", f"-p{RAR_PASSWORD}", "-ibck", "-o+", os.path.abspath(rar_path), os.path.abspath(dest_folder) + os.sep]
        try: subprocess.run(command, check=True, capture_output=True, text=True); return True
        except subprocess.CalledProcessError as e: print(f"WinRAR Error: {e.stderr}"); return False

# --- GAME DETAILS WIDGET ---
class GameDetailsWidget(QWidget):
    back_requested = pyqtSignal(); refresh_library = pyqtSignal()
    def __init__(self, asset_manager, pixel_font, data_manager):
        super().__init__()
        self.asset_manager = asset_manager; self.pixel_font = pixel_font
        self.data_manager = data_manager; self.worker_thread = None; self.current_game_data = {}
        self._is_fix_download = False
        self.initUI()
    def initUI(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20, 20, 20, 20); main_layout.setSpacing(15)
        top_panel_layout = QHBoxLayout(); top_panel_layout.setSpacing(20)
        self.thumbnail_label = QLabel(); self.thumbnail_label.setFixedSize(400, 600)
        top_panel_layout.addWidget(self.thumbnail_label)
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        top_panel_layout.addWidget(right_panel, 1)
        back_button = QPushButton("« Back to Library"); back_button.setFont(self.pixel_font)
        back_button.setCursor(Qt.CursorShape.PointingHandCursor); back_button.clicked.connect(self.back_requested.emit)
        info_panel = QWidget(); info_layout = QVBoxLayout(info_panel)
        self.game_name_label = self._create_info_label(); self.sources_label = self._create_info_label()
        self.size_label = self._create_info_label(); self.version_label = self._create_info_label()
        info_layout.addWidget(self._create_info_row("GameName:", self.game_name_label)); info_layout.addWidget(self._create_info_row("Sources:", self.sources_label))
        info_layout.addWidget(self._create_info_row("AproxSize:", self.size_label)); info_layout.addWidget(self._create_info_row("Version:", self.version_label))
        self.description_label = self._create_info_label(); self.description_label.setWordWrap(True); self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.location_bar = QLineEdit(); self.location_bar.setFont(self.pixel_font)
        self.fix_prompt_widget = QWidget(); fix_layout = QHBoxLayout(self.fix_prompt_widget); fix_layout.setContentsMargins(0,0,0,0)
        self.fix_label = self._create_info_label("Fix is available. Apply it?"); yes_button = QPushButton("Yes"); yes_button.setFont(self.pixel_font)
        no_button = QPushButton("No"); no_button.setFont(self.pixel_font); yes_button.clicked.connect(self.on_fix_yes); no_button.clicked.connect(self.on_fix_no)
        fix_layout.addWidget(self.fix_label, 1); fix_layout.addWidget(yes_button); fix_layout.addWidget(no_button)
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
        self.download_progress.setValue(0); self.stats_label.setText(""); self.status_label.setText("")
        self.download_button.setEnabled(True); self.download_button.setText("DOWNLOAD")
        self.location_bar.setVisible(True); self.fix_prompt_widget.setVisible(False)
        self.game_name_label.setText(game_data.get('name', 'N/A')); self.sources_label.setText(game_data.get('Sources', 'N/A'))
        self.size_label.setText(game_data.get('ApproxSize', 'N/A')); self.version_label.setText(game_data.get('version', 'N/A'))
        self.description_label.setText(game_data.get('Description', 'No description available.'))
        status = game_data.get('status', GameStatus.NOT_DOWNLOADED); border_color = STATUS_INFO[status]['color']
        self.thumbnail_label.setStyleSheet(f"background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 10px;")
        thumbnail_path = self.asset_manager.get_asset(game_data.get('Thumbnail'))
        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            scaled_pixmap = pixmap.scaled(self.thumbnail_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled_pixmap)
        else: self.thumbnail_label.clear(); self.thumbnail_label.setText("No Image")
        self.location_bar.clear(); self.location_bar.setPlaceholderText("Select a base download folder...")
    def start_or_cancel_download(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker.stop(); self.download_button.setText("DOWNLOAD"); return
        
        base_path = self.location_bar.text()
        if self._is_fix_download: base_path = self.fix_path
            
        if not os.path.isdir(base_path): self.status_label.setText("Invalid location path!"); return
        
        self.download_button.setText("CANCEL")
        self.worker_thread = QThread()
        self.worker = DownloadManager(self.current_game_data, base_path, self._is_fix_download)
        self.worker.moveToThread(self.worker_thread); self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_download_finished); self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater); self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.progress.connect(self.update_progress); self.worker.status_update.connect(self.status_label.setText)
        self.worker_thread.start()
    def on_download_finished(self, success, message, new_game_path):
        self.status_label.setText(message); self.download_button.setText("DOWNLOAD"); self.download_button.setEnabled(True)
        if success:
            self.download_button.setText("FINISHED"); self.download_button.setEnabled(False)
            if not self._is_fix_download:
                self.data_manager.save_downloaded_game(self.current_game_data['name'], self.current_game_data['version'], new_game_path)
                self.refresh_library.emit()
                if self.current_game_data.get('Fix'):
                    self.location_bar.setVisible(False); self.fix_prompt_widget.setVisible(True)
                    self.fix_path = new_game_path # Store the correct game folder path
                    self.fix_label.setText(f"Apply fix to: {self.fix_path}?")
    def on_fix_yes(self):
        self.fix_prompt_widget.setVisible(False)
        self.download_button.setText("APPLY FIX"); self.download_button.setEnabled(True)
        self._is_fix_download = True
    def on_fix_no(self): 
        self.fix_prompt_widget.setVisible(False)
        self.download_button.setText("FINISHED"); self.download_button.setEnabled(False)
    def update_progress(self, value, stats_text): self.download_progress.setValue(value); self.stats_label.setText(stats_text)

# --- MAIN LAUNCHER WINDOW ---
class GameLauncher(QWidget):
    def __init__(self, data_manager, asset_manager):
        super().__init__()
        self.data_manager = data_manager; self.asset_manager = asset_manager
        self.pixel_font = QFont("Arial", 12); self.game_widgets = []; self.status_buttons = {}
        self.current_filter = None
        self.initUI()
    def initUI(self):
        self.setWindowTitle("Zuhu's OFME Download GUI 1.5-Beta.7"); self.setMinimumSize(640, 480)
        self.resize(1155, 710); self.setStyleSheet(STYLESHEET + "QWidget { background-color: #2c2c2c; }")
        self._load_font()
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(10, 10, 10, 10)
        self.reflow_timer = QTimer(self); self.reflow_timer.setSingleShot(True)
        self.reflow_timer.setInterval(50); self.reflow_timer.timeout.connect(self._reflow_games)
        self.stack = QStackedWidget(); main_layout.addWidget(self.stack)
        grid_page = QWidget(); grid_page_layout = QVBoxLayout(grid_page)
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setStyleSheet("QScrollArea { border: none; }")
        self.games_container = QWidget(); self.games_layout = QGridLayout(self.games_container)
        self.games_layout.setSpacing(15); self.games_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        for game_data in self.data_manager.games:
            widget = GameWidget(game_data, self.asset_manager, self.pixel_font)
            widget.clicked.connect(self.show_game_details); self.game_widgets.append(widget)
        scroll_area.setWidget(self.games_container); grid_page_layout.addWidget(scroll_area)
        grid_page_layout.addLayout(self._create_status_legend())
        self.details_page = GameDetailsWidget(self.asset_manager, self.pixel_font, self.data_manager)
        self.details_page.back_requested.connect(self.show_game_grid)
        self.details_page.refresh_library.connect(self.refresh_game_statuses)
        self.stack.addWidget(grid_page); self.stack.addWidget(self.details_page)
    def resizeEvent(self, event): super().resizeEvent(event); self.reflow_timer.start()
    def showEvent(self, event): super().showEvent(event); self._reflow_games()
    def show_game_details(self, game_data):
        self.details_page.set_game_data(game_data); self.stack.setCurrentWidget(self.details_page)
    def show_game_grid(self): self.stack.setCurrentIndex(0)
    def refresh_game_statuses(self):
        self.data_manager.games = self.data_manager._determine_game_statuses()
        for widget in self.game_widgets:
            for game in self.data_manager.games:
                if widget.game_data['name'] == game['name']:
                    widget.status = game['status']
                    status_info = STATUS_INFO[widget.status]; border_color = status_info['color']
                    if not widget._pixmap:
                         widget.content_label.setStyleSheet(f"QLabel {{ color: #cccccc; background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 10px; padding: 5px; }}")
                    else:
                         widget.content_label.setStyleSheet(f"QLabel {{ background-color: #3c3c3c; border: 3px solid {border_color}; border-radius: 10px; }}")
                    break
        print("Game statuses refreshed.")
    def _reflow_games(self):
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
        legend_layout.addStretch(); return legend_layout
    def _on_filter_changed(self, status_id):
        if self.current_filter == status_id: self.current_filter = None
        else: self.current_filter = status_id
        for s_id, button in self.status_buttons.items():
            is_active = (self.current_filter is None or s_id == self.current_filter)
            button.set_active(is_active)
        self._reflow_games()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    data_manager = DataManager(); asset_manager = AssetManager()
    main_window = GameLauncher(data_manager, asset_manager); main_window.show()
    sys.exit(app.exec())