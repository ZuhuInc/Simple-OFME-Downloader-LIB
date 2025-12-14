"""
Zuhu's OFME GUI Downloader V1.5.5

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
import ctypes
import webbrowser
import traceback
from plyer import notification
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QScrollArea, QGridLayout, QSizePolicy,
                             QGraphicsOpacityEffect, QStackedWidget, QPushButton,
                             QProgressBar, QLineEdit, QFormLayout, QTabWidget,
                             QPlainTextEdit, QFileDialog, QCheckBox, QMessageBox, QFrame)
from PyQt6.QtGui import QPixmap, QFontDatabase, QFont, QTextCursor, QIcon, QPainter, QColor, QBrush, QPen
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject, QThread, QTimer, pyqtSlot, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty

# --- CONFIGURATION ---
CURRENT_VERSION = "V1.5.5"
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
DATA_FILE = os.path.join(DATA_FOLDER, 'Data.json')
SETTINGS_FILE = os.path.join(DATA_FOLDER, 'Settings.json')
ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-DWND-ICO.ico"
SETTINGS_ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-STNG-ICO.ico"
RELOAD_ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-RLD-ICO.ico"
FONT_URL = "https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/raw/main/Assets/pixelmix.ttf"
ICON_PATH = os.path.join(DATA_FOLDER, 'cache', 'OFME-DWND-ICO.ico')
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
DEFAULT_DOWNLOAD_PATH = ""
SHOW_SIZE_IN_GB = True
SHOW_SPEED_IN_MBPS = True
ENABLE_NOTIFICATIONS = True

# --- STYLING ---
STYLESHEET = """
    QWidget { background-color: #1e1e1e; color: #e0e0e0; }
    QScrollArea { border: none; background-color: #1e1e1e; }
    
    QProgressBar {
        border: 1px solid #444; border-radius: 4px; text-align: center;
        background-color: #2d2d2d; height: 14px; color: white; font-size: 10px;
    }
    QProgressBar::chunk { background-color: #00ff7f; border-radius: 3px; }
    
    QLineEdit {
        border: 1px solid #444; background-color: #2d2d2d;
        border-radius: 15px; 
        padding: 5px 12px; 
        color: #e0e0e0;
        min-height: 20px; 
    }
    QLineEdit:focus { border: 1px solid #00ff7f; }
    
    QPushButton#CircleBtn {
        border: 1px solid #444; background-color: #2d2d2d; border-radius: 17px; 
    }
    QPushButton#CircleBtn:hover { border-color: #00ff7f; background-color: #333; }
    
    QPushButton {
        background-color: #2d2d2d; border: 1px solid #444; border-radius: 8px;
        padding: 6px 12px; color: #e0e0e0; 
    }
    QPushButton:hover { border: 1px solid #00ff7f; color: #00ff7f; background-color: #333; }
    QPushButton:disabled { border: 1px solid #333; color: #555; }
    
    QPushButton#TopBackBtn {
        background: transparent; border: none; color: #00ff7f; 
        text-align: left; font-weight: bold; font-size: 14px; padding: 0px;
    }
    QPushButton#TopBackBtn:hover { color: #fff; border: none; background: transparent; }
    
    QTabWidget::pane { border: 1px solid #444; background-color: #1e1e1e; }
    QTabBar::tab {
        background-color: #2d2d2d; color: #aaa; padding: 8px 15px;
        border: 1px solid #444; border-bottom: none;
        border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px;
    }
    QTabBar::tab:selected { background-color: #1e1e1e; color: #00ff7f; border-bottom: 1px solid #1e1e1e; }
    QTabBar::tab:hover { color: #fff; }
    
    QPlainTextEdit { color: #00ff7f; background-color: #151515; border: 1px solid #444; border-radius: 4px; }
    QMessageBox { background-color: #1e1e1e; color: #e0e0e0; }
    QMessageBox QLabel { color: #e0e0e0; }
"""

# --- SETTINGS LOGIC ---
def load_settings():
    global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH, SHOW_SIZE_IN_GB, SHOW_SPEED_IN_MBPS, ENABLE_NOTIFICATIONS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                WINRAR_PATH = settings.get('winrar_path', WINRAR_PATH)
                DEFAULT_DOWNLOAD_PATH = settings.get('default_download_path', DEFAULT_DOWNLOAD_PATH)
                SHOW_SIZE_IN_GB = settings.get('show_size_in_gb', True)
                SHOW_SPEED_IN_MBPS = settings.get('show_speed_in_mbps', False)
                ENABLE_NOTIFICATIONS = settings.get('enable_notifications', True)
        except (json.JSONDecodeError, IOError): pass

def save_settings_to_file():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    settings = {
        'winrar_path': WINRAR_PATH,
        'default_download_path': DEFAULT_DOWNLOAD_PATH,
        'show_size_in_gb': SHOW_SIZE_IN_GB,
        'show_speed_in_mbps': SHOW_SPEED_IN_MBPS,
        'enable_notifications': ENABLE_NOTIFICATIONS
    }
    try:
        with open(SETTINGS_FILE, 'w') as f: json.dump(settings, f, indent=4)
    except IOError as e: print(f"ERROR: Could not save settings to file: {e}")

# --- STATUS DEFINITIONS ---
class GameStatus:
    UP_TO_DATE = 1; UPDATE_AVAILABLE = 2; NOT_DOWNLOADED = 3
STATUS_INFO = {
    GameStatus.UP_TO_DATE: {'color': '#00ff7f', 'text': 'UP-TO-DATE'},
    GameStatus.UPDATE_AVAILABLE: {'color': '#ffd700', 'text': 'UPDATE'},
    GameStatus.NOT_DOWNLOADED: {'color': '#ff4500', 'text': 'MISSING'}
}

# --- CONSOLE REDIRECTION ---
class ConsoleStream(QObject):
    _text_written = pyqtSignal(str)
    
    def __init__(self, original_stream):
        super().__init__()
        self.original_stream = original_stream

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()
        self._text_written.emit(str(text))

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

# --- UPDATE CHECKER ---
class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str)
    def run(self):
        url = f"https://api.github.com/repos/ZuhuInc/Simple-OFME-Downloader-LIB/releases/latest"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get('tag_name', '')
                html_url = data.get('html_url', '')
                if latest_version and self._is_version_higher(latest_version, CURRENT_VERSION):
                    self.update_available.emit(latest_version, html_url)
        except Exception: pass

    def _parse_version(self, v_str):
        clean_v = v_str.lstrip('vV')
        if '-' in clean_v: main_part, pre_part = clean_v.split('-', 1)
        else: main_part, pre_part = clean_v, None
        try: main_nums = [int(x) for x in main_part.split('.')]
        except ValueError: main_nums = [0, 0, 0]
        return main_nums, pre_part

    def _is_version_higher(self, remote_ver, local_ver):
        r_main, r_pre = self._parse_version(remote_ver)
        l_main, l_pre = self._parse_version(local_ver)
        if r_main > l_main: return True
        if r_main < l_main: return False
        if r_pre is None and l_pre is not None: return True 
        if r_pre is not None and l_pre is None: return False     
        return r_pre > l_pre

# --- CUSTOM TOGGLE SWITCH ---
class PyToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_color = "#777"
        self._circle_color = "#DDD"
        self._active_color = "#00ff7f"
        self._circle_position = 3
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(300)
        self.stateChanged.connect(self.start_transition)

    def start_transition(self, state):
        self.animation.stop()
        if state: self.animation.setEndValue(self.width() - 24)
        else: self.animation.setEndValue(3)
        self.animation.start()
        
    def hitButton(self, pos): return self.contentsRect().contains(pos)
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked(): p.setBrush(QColor(self._active_color))
        else: p.setBrush(QColor(self._bg_color))
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        p.drawRoundedRect(0, 0, rect.width(), rect.height(), 14, 14)
        p.setBrush(QColor(self._circle_color))
        p.drawEllipse(int(self._circle_position), 3, 22, 22)
        p.end()

    def get_circle_position(self): return self._circle_position
    def set_circle_position(self, pos): self._circle_position = pos; self.update()
    circle_position = pyqtProperty(float, get_circle_position, set_circle_position)

# --- SETTINGS PAGE ---
class SettingsPage(QWidget):
    back_requested = pyqtSignal()
    def __init__(self, main_font):
        super().__init__()
        
        self.settings_font = QFont(main_font)
        self.settings_font.setPointSize(11)
        self.settings_font.setBold(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(10) 

        header_layout = QHBoxLayout()
        back_button = QPushButton("<< Back to Library")
        back_button.setObjectName("TopBackBtn")
        back_button.setFont(self.settings_font)
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        tabs = QTabWidget()
        tabs.setFont(self.settings_font)
        layout.addWidget(tabs, 1)

        # --- CONSOLE TAB ---
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        
        console_font = QFont(main_font)
        console_font.setPointSize(11)
        self.console_output.setFont(console_font) 
        
        console_layout.addWidget(self.console_output)
        tabs.addTab(console_widget, "Console Output")

        # --- SETTINGS TAB ---
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        lbl_winrar = QLabel("WinRAR Path:")
        lbl_winrar.setFont(self.settings_font)
        self.winrar_path_edit = QLineEdit(WINRAR_PATH)
        self.winrar_path_edit.setFont(self.settings_font)
        form_layout.addRow(lbl_winrar, self.winrar_path_edit)

        lbl_dl = QLabel("Default Path:")
        lbl_dl.setFont(self.settings_font)
        self.download_path_edit = QLineEdit(DEFAULT_DOWNLOAD_PATH)
        self.download_path_edit.setFont(self.settings_font)
        self.download_path_edit.setPlaceholderText("Leave empty to prompt every time...")
        form_layout.addRow(lbl_dl, self.download_path_edit)

        def create_toggle_row(text, toggle, status_lbl):
            container = QWidget()
            h_lay = QHBoxLayout(container)
            h_lay.setContentsMargins(0, 0, 0, 0)
            h_lay.addWidget(toggle)
            h_lay.addWidget(status_lbl)
            h_lay.addStretch()
            lbl = QLabel(text)
            lbl.setFont(self.settings_font)
            return lbl, container

        self.speed_toggle = PyToggle()
        self.speed_toggle.setChecked(SHOW_SPEED_IN_MBPS)
        self.lbl_speed_status = QLabel("Mbps" if SHOW_SPEED_IN_MBPS else "MB/s")
        self.lbl_speed_status.setFont(self.settings_font)
        self.lbl_speed_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.speed_toggle.stateChanged.connect(lambda s: self.lbl_speed_status.setText("Mbps" if s else "MB/s"))
        lbl_sp, cont_sp = create_toggle_row("Show Speed in:", self.speed_toggle, self.lbl_speed_status)
        form_layout.addRow(lbl_sp, cont_sp)

        self.size_toggle = PyToggle()
        self.size_toggle.setChecked(SHOW_SIZE_IN_GB)
        self.lbl_size_status = QLabel("GB" if SHOW_SIZE_IN_GB else "MB")
        self.lbl_size_status.setFont(self.settings_font)
        self.lbl_size_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.size_toggle.stateChanged.connect(lambda s: self.lbl_size_status.setText("GB" if s else "MB"))
        lbl_sz, cont_sz = create_toggle_row("Show Size in:", self.size_toggle, self.lbl_size_status)
        form_layout.addRow(lbl_sz, cont_sz)

        self.notif_toggle = PyToggle()
        self.notif_toggle.setChecked(ENABLE_NOTIFICATIONS)
        self.lbl_notif_status = QLabel("On" if ENABLE_NOTIFICATIONS else "Off")
        self.lbl_notif_status.setFont(self.settings_font)
        self.lbl_notif_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.notif_toggle.stateChanged.connect(lambda s: self.lbl_notif_status.setText("On" if s else "Off"))
        lbl_nf, cont_nf = create_toggle_row("Desktop Notifications:", self.notif_toggle, self.lbl_notif_status)
        form_layout.addRow(lbl_nf, cont_nf)

        settings_layout.addLayout(form_layout)
        settings_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_button = QPushButton("Save Settings")
        self.save_button.setFont(self.settings_font)
        self.save_button.setFixedWidth(200)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_button)
        
        settings_layout.addLayout(btn_layout)
        tabs.addTab(settings_widget, "General Settings")
        
    def append_to_console(self, text):
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertPlainText(text)

    def save_settings(self):
        global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH, SHOW_SIZE_IN_GB, SHOW_SPEED_IN_MBPS, ENABLE_NOTIFICATIONS
        self.save_button.setText("Saved!")
        self.save_button.setStyleSheet("border: 1px solid #00ff7f; color: #00ff7f;")
        QTimer.singleShot(1500, lambda: self._reset_save_btn())

        new_winrar_path = self.winrar_path_edit.text()
        if os.path.exists(new_winrar_path): WINRAR_PATH = new_winrar_path
        
        new_download_path = self.download_path_edit.text()
        DEFAULT_DOWNLOAD_PATH = new_download_path 
        
        SHOW_SPEED_IN_MBPS = self.speed_toggle.isChecked()
        SHOW_SIZE_IN_GB = self.size_toggle.isChecked()
        ENABLE_NOTIFICATIONS = self.notif_toggle.isChecked()
        
        print("Settings saved successfully.")
        save_settings_to_file()

    def _reset_save_btn(self):
        self.save_button.setText("Save Settings")
        self.save_button.setStyleSheet("")

# --- DATA AND ASSET MANAGEMENT ---
class DataManager:
    def __init__(self):
        self.games_db = self._parse_github_db()
        self.local_data = self._load_local_data()
        self.games = self._determine_game_statuses()
    
    def refresh_database(self):
        print("Force reloading database from server...")
        self.games_db = self._parse_github_db()
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
        base_style = f"QLabel {{ background-color: #2d2d2d; border: 2px solid {border_color}; border-radius: 0px; }}"
        
        if thumbnail_path and os.path.exists(thumbnail_path):
            self._pixmap = QPixmap(thumbnail_path); self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_label.setStyleSheet(base_style)
        else:
            self.content_label.setText(game_data.get('name', 'Unknown')); self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f = QFont(pixel_font); f.setPointSize(16); f.setBold(True)
            self.content_label.setFont(f); self.content_label.setWordWrap(True)
            self.content_label.setStyleSheet(base_style + "QLabel { color: #cccccc; padding: 5px; }")
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
        
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        
        self.text_label = QLabel(text)
        f = QFont(pixel_font); f.setPointSize(12); f.setBold(True)
        self.text_label.setFont(f)
        self.text_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        self.line = QWidget(); self.line.setFixedHeight(2)
        self.line.setStyleSheet(f"background-color: {color}; border-radius: 1px;")
        
        layout.addWidget(self.text_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.line)
        self.opacity_effect = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity_effect)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.status_id)
        super().mousePressEvent(event)
    def set_active(self, is_active): self.opacity_effect.setOpacity(1.0 if is_active else 0.3)

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
            
            progress_str = f"({i+1}/{total_downloads})"
            self.status_update.emit(f"Downloading Part {i+1}/{total_downloads}...")
            direct_url, token = url, None
            if "gofile.io" in url:
                direct_url, token = self._resolve_gofile_link(url, progress_str)
                if not direct_url:
                    self.finished.emit(False, "Failed to resolve GoFile link.", {}); return
            elif "buzzheavier.com" in url:
                direct_url = self._resolve_buzzheavier_link(url, progress_str)
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

    def _resolve_buzzheavier_link(self, buzzheavier_url, progress_str=""):
        self.status_update.emit(f"Resolving BuzzHeavier link... {progress_str}")
        try:
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'HX-Request': 'true',
                'Referer': buzzheavier_url.rstrip('/') + '/'
            }
            session.headers.update(headers)
            download_trigger_url = buzzheavier_url.rstrip('/') + "/download"
            self.status_update.emit(f"Downloading From BuzzHeavier... {progress_str}")
            response = session.get(download_trigger_url, allow_redirects=False, timeout=15)

            if response.status_code >= 400: return None

            if 'hx-redirect' in response.headers:
                final_url = response.headers['hx-redirect']
                if "buzzheavier.com" in final_url: return None
                return final_url
            else: return None
        except requests.exceptions.RequestException as e:
            print(f"BuzzHeavier resolution error: {e}")
            return None

    def _resolve_gofile_link(self, gofile_url, progress_str=""):
        self.status_update.emit(f"Downloading From GoFile... {progress_str}")
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
                if 'text/html' in content_type: return None
                local_filename = ""
                if "Content-Disposition" in r.headers:
                    disposition = r.headers['content-disposition']
                    filenames = re.findall('filename="?([^"]+)"?', disposition)
                    if filenames: local_filename = filenames[0]
                if not local_filename: local_filename = r.url.split('/')[-1].split('?')[0]
                if not local_filename: local_filename = "download.tmp"
                local_filepath = os.path.join(dest_folder, local_filename)
                
                total_size = int(r.headers.get('content-length', 0)); bytes_downloaded = 0; start_time = time.time()
                with open(local_filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if not self._is_running: return None
                        f.write(chunk); bytes_downloaded += len(chunk)
                        if total_size > 0:
                            percentage = int(100 * bytes_downloaded / total_size); elapsed_time = time.time() - start_time
                            speed = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
                            if SHOW_SIZE_IN_GB: dl_disp = bytes_downloaded / (1024**3); tot_disp = total_size / (1024**3); size_unit = "GB"
                            else: dl_disp = bytes_downloaded / (1024**2); tot_disp = total_size / (1024**2); size_unit = "MB"
                            if SHOW_SPEED_IN_MBPS: speed_disp = (speed * 8) / (1024**2); speed_unit = "Mbps"
                            else: speed_disp = speed / (1024**2); speed_unit = "MB/s"
                            stats = f"{dl_disp:.2f}{size_unit} / {tot_disp:.2f}{size_unit} | {speed_disp:.2f} {speed_unit}"
                            self.progress.emit(percentage, stats)
                return local_filepath
        except requests.exceptions.RequestException: return None

# --- INSTALL MANAGER ---
class InstallManager(QObject):
    main_extraction_finished = pyqtSignal(bool, str, str)
    fix_extraction_finished = pyqtSignal(bool, str)
    cleanup_finished = pyqtSignal(bool, str)
    status_update = pyqtSignal(str)
    progress = pyqtSignal(int, str)

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
                    if os.path.isdir(full_new_path): final_install_path = full_new_path
            self.main_extraction_finished.emit(True, "Main game extracted.", final_install_path)
        else:
            self.main_extraction_finished.emit(False, "Main game extraction failed!", self.base_install_path)

    @pyqtSlot(str)
    def start_fix_extraction(self, fix_target_path):
        if not self.fix_path:
            self.fix_extraction_finished.emit(True, "No fix to extract.")
            return

        self.status_update.emit(f"Extracting fix...")
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
                if path and os.path.exists(path): os.remove(path)
            temp_folder = "temp_downloads"
            if os.path.exists(temp_folder) and not os.listdir(temp_folder): os.rmdir(temp_folder)
            self.cleanup_finished.emit(True, "Cleanup complete.")
        except OSError as e:
            self.cleanup_finished.emit(False, f"Cleanup failed: {e}")

    def _winrar_extraction(self, rar_path, dest_folder):
        exe_to_use = WINRAR_PATH
        if "WinRAR.exe" in WINRAR_PATH:
            rar_candidate = WINRAR_PATH.replace("WinRAR.exe", "Rar.exe")
            if os.path.exists(rar_candidate): exe_to_use = rar_candidate

        if not os.path.exists(exe_to_use):
            self.status_update.emit("WinRAR/Rar not found!")
            return False

        command = [exe_to_use, "x", f"-p{RAR_PASSWORD}", "-o+", "-idcd", os.path.abspath(rar_path), os.path.abspath(dest_folder) + os.sep]
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, startupinfo=si, bufsize=0)
            num_buffer = ""
            while True:
                char = process.stdout.read(1)
                if not char and process.poll() is not None: break
                if char:
                    if char.isdigit(): num_buffer += char
                    elif char == '%':
                        if num_buffer:
                            try:
                                percent = int(num_buffer)
                                self.progress.emit(percent, f"{percent}%")
                            except ValueError: pass
                        num_buffer = ""
                    elif char in ["\b", "\r", " "]: num_buffer = ""
            return_code = process.wait()
            return return_code == 0 or return_code == 1
        except Exception as e:
            print(f"Extraction Error: {e}")
            return False

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
        self.final_game_path = ""; self.path_manually_changed = False; self.installer = None
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20, 10, 20, 20); main_layout.setSpacing(15)
        
        header_layout = QHBoxLayout()
        back_button = QPushButton("<< Back to Library"); back_button.setObjectName("TopBackBtn")
        back_button.setFont(self.pixel_font) # Use custom font
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft); header_layout.addStretch()
        main_layout.addLayout(header_layout)
        content_layout = QHBoxLayout(); content_layout.setSpacing(20)
        
        self.thumbnail_label = QLabel(); self.thumbnail_label.setFixedSize(300, 450)
        self.thumbnail_label.setStyleSheet("border: 2px solid #444; border-radius: 0px; background-color: #000;")
        content_layout.addWidget(self.thumbnail_label)
        
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel); right_layout.setContentsMargins(0,0,0,0)
        
        info_panel = QWidget(); info_layout = QVBoxLayout(info_panel)
        self.game_name_label = self._create_info_label(size=18, bold=True, color="#00ff7f")
        self.sources_label = self._create_info_label()
        self.size_label = self._create_info_label()
        self.version_label = self._create_info_label()
        
        info_layout.addWidget(self._create_info_row("Game:", self.game_name_label))
        info_layout.addWidget(self._create_info_row("Source:", self.sources_label))
        info_layout.addWidget(self._create_info_row("Size:", self.size_label))
        info_layout.addWidget(self._create_info_row("Version:", self.version_label))
        
        self.description_label = QLabel(); self.description_label.setWordWrap(True); 
        self.description_label.setFont(self.pixel_font)
        self.description_label.setStyleSheet("color: #aaa; margin-top: 10px; font-size: 13px;")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.location_bar = QLineEdit()
        self.location_bar.setFont(self.pixel_font)
        
        self.fix_prompt_widget = QWidget(); fix_layout = QHBoxLayout(self.fix_prompt_widget); fix_layout.setContentsMargins(0,0,0,0)
        self.fix_label = self._create_info_label(text="Fix is available. Apply it?", color="#ffd700")
        yes_button = QPushButton("Yes"); yes_button.setFont(self.pixel_font)
        no_button = QPushButton("No"); no_button.setFont(self.pixel_font)
        self.change_path_button = QPushButton("Change Path"); self.change_path_button.setFont(self.pixel_font)
        yes_button.clicked.connect(self.on_fix_yes); no_button.clicked.connect(self.on_fix_no); self.change_path_button.clicked.connect(self.select_fix_path)
        fix_layout.addWidget(self.fix_label, 1); fix_layout.addWidget(yes_button); fix_layout.addWidget(no_button); fix_layout.addWidget(self.change_path_button)
        
        right_layout.addWidget(info_panel)
        
        desc_title = QLabel("Description:"); desc_title.setFont(self.pixel_font)
        desc_title.setStyleSheet("color:#fff; font-weight:bold; margin-top:10px;")
        right_layout.addWidget(desc_title)
        
        right_layout.addWidget(self.description_label, 1)
        right_layout.addStretch()
        right_layout.addWidget(self.location_bar)
        right_layout.addWidget(self.fix_prompt_widget)
        
        content_layout.addWidget(right_panel, 1)
        main_layout.addLayout(content_layout)

        bottom_controls = QWidget(); bottom_layout = QVBoxLayout(bottom_controls)
        bottom_layout.setContentsMargins(0,0,0,0); bottom_layout.setSpacing(5)
        
        status_line = QHBoxLayout()
        self.status_label = QLabel(""); self.status_label.setStyleSheet("color: #00ff7f;"); self.status_label.setFont(self.pixel_font)
        self.stats_label = QLabel(""); self.stats_label.setStyleSheet("color: #aaa;"); self.stats_label.setFont(self.pixel_font)
        status_line.addWidget(self.status_label); status_line.addStretch(); status_line.addWidget(self.stats_label)

        action_line = QHBoxLayout()
        self.download_progress = QProgressBar()
        self.download_progress.setFont(self.pixel_font)
        self.download_button = QPushButton("DOWNLOAD")
        self.download_button.setFont(self.pixel_font)
        self.download_button.setFixedWidth(200)
        self.download_button.setFixedHeight(35)
        self.download_button.clicked.connect(self.start_or_cancel_download)
        
        action_line.addWidget(self.download_progress, 1); action_line.addWidget(self.download_button)
        
        bottom_layout.addLayout(status_line); bottom_layout.addLayout(action_line)
        main_layout.addWidget(bottom_controls)

    def _create_info_row(self, title, data_label):
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0,0,0,0)
        title_label = QLabel(title); title_label.setStyleSheet("color: #888; font-weight: bold;")
        title_label.setFont(self.pixel_font)
        layout.addWidget(title_label); layout.addStretch(); layout.addWidget(data_label)
        return row
    def _create_info_label(self, text="", size=12, bold=False, color="#e0e0e0"):
        label = QLabel(text)
        f = QFont(self.pixel_font)
        if size > 14: f.setPointSize(14)
        else: f.setPointSize(10)
        f.setBold(bold)
        label.setFont(f)
        label.setStyleSheet(f"color: {color};")
        return label

    def set_game_data(self, game_data):
        self.current_game_data = game_data
        self.final_game_path = ""; self.path_manually_changed = False; self.downloaded_file_paths = {}
        self.download_progress.setValue(0); self.stats_label.setText(""); self.status_label.setText("")
        self.fix_prompt_widget.setVisible(False)
        
        self.game_name_label.setText(game_data.get('name', 'N/A')); self.sources_label.setText(game_data.get('Sources', 'N/A'))
        self.size_label.setText(game_data.get('ApproxSize', 'N/A')); self.version_label.setText(game_data.get('version', 'N/A'))
        self.description_label.setText(game_data.get('Description', 'No description available.'))
        
        status = game_data.get('status', GameStatus.NOT_DOWNLOADED)
        thumbnail_path = self.asset_manager.get_asset(game_data.get('Thumbnail'))
        
        border_color = STATUS_INFO[status]['color']
        self.thumbnail_label.setStyleSheet(f"border: 2px solid {border_color}; border-radius: 0px; background-color: #000;")

        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            scaled_pixmap = pixmap.scaled(self.thumbnail_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled_pixmap)
        else: self.thumbnail_label.clear(); self.thumbnail_label.setText("No Image")

        self.download_button.setEnabled(True)
        if status == GameStatus.NOT_DOWNLOADED:
            self.download_button.setText("DOWNLOAD")
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setPlaceholderText("Select base download folder...")
            self.location_bar.setVisible(True)
        else:
            game_name_key = game_data.get('name', '').upper()
            self.final_game_path = self.data_manager.local_data.get(game_name_key, {}).get('location', '')
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setVisible(True)
            if status == GameStatus.UPDATE_AVAILABLE: self.download_button.setText("UPDATE")
            else: self.download_button.setText("RE-DOWNLOAD")

    def start_or_cancel_download(self):
        if self.worker_thread is not None:
            try:
                if self.worker_thread.isRunning():
                    if hasattr(self, 'worker'): self.worker.stop()
                    self.download_button.setText("DOWNLOAD")
                    return
            except RuntimeError: self.worker_thread = None

        if self.installer_thread and self.installer_thread.isRunning(): return
        is_new_install = self.current_game_data['status'] == GameStatus.NOT_DOWNLOADED    
        path_to_use = self.location_bar.text()

        if not os.path.isdir(path_to_use):
            self.status_label.setText("Invalid location path!"); return
        
        self.download_button.setText("CANCEL")
        self.worker_thread = QThread()
        self.worker = DownloadManager(self.current_game_data)
        self.worker.moveToThread(self.worker_thread)
        
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(lambda s, m, p: self.on_download_complete(s, m, p, path_to_use, is_new_install))
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.progress.connect(self.update_progress)
        self.worker.status_update.connect(self.status_label.setText)
        self.worker_thread.start()

    def on_download_complete(self, success, message, path_dict, base_path, is_new_install):
        self.status_label.setText(message)
        if success:
            self.downloaded_file_paths = path_dict
            self.installer_thread = QThread()
            self.installer = InstallManager(self.downloaded_file_paths.get('main', []), self.downloaded_file_paths.get('fix', ''), base_path, is_new_install)
            self.installer.moveToThread(self.installer_thread)
            self.installer.main_extraction_finished.connect(self.on_main_extraction_complete)
            self.installer.fix_extraction_finished.connect(self.on_fix_extraction_complete)
            self.installer.cleanup_finished.connect(self.on_cleanup_complete)
            self.installer.status_update.connect(self.status_label.setText)
            self.installer.progress.connect(self.update_progress)
            self.installer_thread.started.connect(self.installer.start_main_extraction)
            self.installer_thread.finished.connect(self.installer_thread.deleteLater)
            self.download_button.setText("EXTRACTING.."); self.download_button.setEnabled(False)
            self.download_progress.setValue(0)
            self.installer_thread.start()
        else: self.set_game_data(self.current_game_data)

    def on_main_extraction_complete(self, success, message, detected_path):
        self.status_label.setText(message)
        if success:
            self.download_progress.setValue(100); self.final_game_path = detected_path
            self.data_manager.save_downloaded_game(self.current_game_data['name'], self.current_game_data['version'], self.final_game_path)
            self.refresh_library.emit()
            if self.downloaded_file_paths.get('fix'):
                self.fix_prompt_widget.setVisible(True)
                self.location_bar.setVisible(False)
                self.fix_label.setText(f"Apply fix to: {os.path.basename(self.final_game_path)}?")
                self.download_button.setText("ACTION REQUIRED"); self.download_button.setEnabled(False)
                if ENABLE_NOTIFICATIONS:
                    try: notification.notify(title="Fix Available", message="Game downloaded. Please apply the fix.", app_icon=ICON_PATH, timeout=5)
                    except Exception: pass
            else: self.installer.cleanup_files()
        else: self.installer.cleanup_files()

    def select_fix_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if directory:
            self.final_game_path = directory; self.path_manually_changed = True
            self.fix_label.setText(f"Apply fix to: {os.path.basename(self.final_game_path)}?")

    def on_fix_yes(self): self.fix_prompt_widget.setVisible(False); self.installer.start_fix_extraction(self.final_game_path)
    def on_fix_no(self): self.fix_prompt_widget.setVisible(False); self.installer.cleanup_files()
    def on_fix_extraction_complete(self, success, message): self.status_label.setText(message); self.installer.cleanup_files()

    def on_cleanup_complete(self, success, message):
        self.status_label.setText(message)
        if success:
            self.download_progress.setValue(100); self.stats_label.setText("Done")
            if ENABLE_NOTIFICATIONS:
                try: notification.notify(title="Download Complete", message=f"{self.current_game_data.get('name')} ready!", app_icon=ICON_PATH, timeout=5)
                except Exception: pass
        if self.path_manually_changed:
            self.data_manager.save_downloaded_game(self.current_game_data['name'], self.current_game_data['version'], self.final_game_path)
            self.refresh_library.emit()
        self.download_button.setText("INSTALLED"); self.download_button.setEnabled(False)
        
    def update_progress(self, value, stats_text): self.download_progress.setValue(value); self.stats_label.setText(stats_text)

# --- MAIN LAUNCHER WINDOW ---
class GameLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Zuhu's OFME GUI Downloader {CURRENT_VERSION}")
        if os.path.exists(ICON_PATH): self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(690, 395); self.resize(1120, 710)
        self.setStyleSheet(STYLESHEET)

        self.main_layout = QVBoxLayout(self)
        self.loading_widget = QWidget(); l_lay = QVBoxLayout(self.loading_widget); l_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label = QLabel("Initializing..."); self.loading_label.setFont(QFont("Segoe UI", 16)); self.loading_label.setStyleSheet("color: #00ff7f;")
        self.progress_label = QLabel(""); self.progress_label.setStyleSheet("color: #aaa;")
        l_lay.addWidget(self.loading_label); l_lay.addWidget(self.progress_label)
        self.main_layout.addWidget(self.loading_widget)
        QTimer.singleShot(100, self.perform_initialization)

    def perform_initialization(self):
        try:
            self.console_buffer = []
            self.console_stream = ConsoleStream(sys.__stdout__) 
            self.console_stream._text_written.connect(self.console_buffer.append)
            sys.stdout = self.console_stream
            sys.stderr = self.console_stream
            
            load_settings()
            
            self.asset_manager = AssetManager(); self.data_manager = DataManager()
            if os.path.exists(ICON_PATH): self.setWindowIcon(QIcon(ICON_PATH))

            self.loading_label.setText("Downloading Assets...")
            all_urls = [FONT_URL, SETTINGS_ICON_URL, RELOAD_ICON_URL]
            for game in self.data_manager.games:
                if t := game.get('Thumbnail'): all_urls.append(t)
            
            unique_urls = list(set(all_urls))
            total = len(unique_urls)
            for i, url in enumerate(unique_urls):
                self.progress_label.setText(f"{i+1}/{total}")
                self.asset_manager.get_asset(url)
                QApplication.processEvents()

            self.finish_ui_setup()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Initialization Error", f"An error occurred during startup:\n{str(e)}")

    def finish_ui_setup(self):
        try:
            self.pixel_font = QFont("Segoe UI", 10) 
            if os.path.exists(os.path.join(DATA_FOLDER, 'cache', 'pixelmix.ttf')):
                 fid = QFontDatabase.addApplicationFont(os.path.join(DATA_FOLDER, 'cache', 'pixelmix.ttf'))
                 if fid != -1: self.pixel_font = QFont(QFontDatabase.applicationFontFamilies(fid)[0], 10)
                 
            self.game_widgets = []; self.status_buttons = {}; self.current_filter = None; self.search_text = "" 
            self.initUI()
            self.loading_widget.hide()
            self.main_layout.removeWidget(self.loading_widget)
            self.loading_widget.deleteLater()
            self.main_layout.addWidget(self.stack)
            
            QTimer.singleShot(0, self._reflow_games)
            self.check_for_updates()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "UI Setup Error", f"An error occurred during UI setup:\n{str(e)}")

    def check_for_updates(self):
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self.show_update_dialog)
        self.update_checker.start()

    def show_update_dialog(self, new_version, html_url):
        msg = QMessageBox(self); msg.setWindowTitle("Update Available"); msg.setText(f"Version {new_version} available!")
        view_btn = msg.addButton("View", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.exec(); 
        if msg.clickedButton() == view_btn: webbrowser.open(html_url)

    def initUI(self):
        self.stack = QStackedWidget()
        grid_page = QWidget(); grid_layout = QVBoxLayout(grid_page); grid_layout.setContentsMargins(0,0,0,0)
        grid_layout.addWidget(self._create_top_bar())

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.games_container = QWidget(); self.games_layout = QGridLayout(self.games_container)
        self.games_layout.setSpacing(15); self.games_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        for game_data in self.data_manager.games:
            widget = GameWidget(game_data, self.asset_manager, self.pixel_font)
            widget.clicked.connect(self.show_game_details)
            self.game_widgets.append(widget)

        self.scroll_area.setWidget(self.games_container)
        grid_layout.addWidget(self.scroll_area)

        self.details_page = GameDetailsWidget(self.asset_manager, self.pixel_font, self.data_manager)
        self.details_page.back_requested.connect(self.show_game_grid)
        self.details_page.refresh_library.connect(self.refresh_game_statuses)
        
        self.settings_page = SettingsPage(self.pixel_font)
        self.settings_page.back_requested.connect(self.show_game_grid)
        self.settings_page.append_to_console("".join(self.console_buffer))
        self.console_stream._text_written.disconnect(self.console_buffer.append)
        self.console_stream._text_written.connect(self.settings_page.append_to_console)

        self.stack.addWidget(grid_page); self.stack.addWidget(self.details_page); self.stack.addWidget(self.settings_page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll_area'): 
            self._reflow_games()

    def showEvent(self, event): super().showEvent(event); self._reflow_games()
    def show_game_details(self, game_data): self.details_page.set_game_data(game_data); self.stack.setCurrentWidget(self.details_page)
    def show_settings_page(self): self.stack.setCurrentWidget(self.settings_page)
    def show_game_grid(self): self.stack.setCurrentIndex(0)

    def perform_full_reload(self):
        self.data_manager.refresh_database()
        self.refresh_game_statuses()

    def refresh_game_statuses(self):
        while self.games_layout.count():
            item = self.games_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.game_widgets.clear()
        self.data_manager.local_data = self.data_manager._load_local_data()
        self.data_manager.games = self.data_manager._determine_game_statuses()
        for game_data in self.data_manager.games:
            widget = GameWidget(game_data, self.asset_manager, self.pixel_font)
            widget.clicked.connect(self.show_game_details)
            self.game_widgets.append(widget)
        self._reflow_games()

    def _reflow_games(self):
        if not hasattr(self, 'games_layout'): return
        while self.games_layout.count():
            item = self.games_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        viewport_width = self.scroll_area.viewport().width()
        card_w = 200
        spacing = 15 
        available_space = viewport_width - 20
        
        num_cols = (available_space + spacing) // (card_w + spacing)
        num_cols = max(1, int(num_cols))

        widgets_to_show = []
        for w in self.game_widgets:
            status_match = (self.current_filter is None or w.status == self.current_filter)
            name_match = (self.search_text.lower() in w.game_data.get('name', '').lower())
            if status_match and name_match: widgets_to_show.append(w)

        for i, widget in enumerate(widgets_to_show):
            row, col = divmod(i, num_cols)
            self.games_layout.addWidget(widget, row, col)
            widget.show()

    def _create_top_bar(self):
        bar_widget = QWidget()
        layout = QHBoxLayout(bar_widget)
        layout.setContentsMargins(20, 5, 20, 5)
        
        for status_id, info in STATUS_INFO.items():
            button = StatusButton(info['text'], info['color'], status_id, self.pixel_font)
            button.clicked.connect(self._on_filter_changed)
            layout.addWidget(button)
            self.status_buttons[status_id] = button
        
        layout.addStretch()
        self.search_bar = QLineEdit()
        self.search_bar.setFont(self.pixel_font)
        self.search_bar.setPlaceholderText("Search Game...")
        self.search_bar.setFixedWidth(235)
        self.search_bar.textChanged.connect(lambda t: (setattr(self, 'search_text', t), self._reflow_games()))
        layout.addWidget(self.search_bar)
        layout.addSpacing(1)

        reload_btn = QPushButton()
        reload_btn.setObjectName("CircleBtn"); reload_btn.setFixedSize(35, 35)
        reload_btn.setToolTip("Reload Library")
        r_ico = self.asset_manager.get_asset(RELOAD_ICON_URL)
        if r_ico and os.path.exists(r_ico): reload_btn.setIcon(QIcon(r_ico)); reload_btn.setIconSize(QSize(25, 25))
        else: reload_btn.setText("↻")
        reload_btn.clicked.connect(self.perform_full_reload)
        layout.addWidget(reload_btn)

        settings_btn = QPushButton()
        settings_btn.setObjectName("CircleBtn"); settings_btn.setFixedSize(35, 35)
        settings_btn.setToolTip("Settings")
        s_ico = self.asset_manager.get_asset(SETTINGS_ICON_URL)
        if s_ico and os.path.exists(s_ico): settings_btn.setIcon(QIcon(s_ico)); settings_btn.setIconSize(QSize(25, 25))
        else: settings_btn.setText("⚙")
        settings_btn.clicked.connect(self.show_settings_page)
        layout.addWidget(settings_btn)
        return bar_widget

    def _on_filter_changed(self, status_id):
        if self.current_filter == status_id: self.current_filter = None
        else: self.current_filter = status_id
        for s_id, button in self.status_buttons.items():
            button.set_active(self.current_filter is None or s_id == self.current_filter)
        self._reflow_games()

if __name__ == '__main__':
    myappid = 'OFME-DWNLDR'
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass
    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH): app.setWindowIcon(QIcon(ICON_PATH))
    main_window = GameLauncher()
    main_window.show()
    sys.exit(app.exec())