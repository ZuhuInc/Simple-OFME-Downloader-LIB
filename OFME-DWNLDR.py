"""
Zuhu's OFME GUI Downloader V1.5.8-Beta6

By Zuhu | DC: ZuhuInc | DCS: https://discord.gg/Wr3wexQcD3
"""
import sys
import os
import shutil
import requests
import json
import zlib
import re
import time
import subprocess
import ctypes
import webbrowser
import traceback
import urllib.parse
import vdf
import psutil
import winreg
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from seleniumbase import Driver
from plyer import notification
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QScrollArea, QGridLayout, QSizePolicy,
                             QGraphicsOpacityEffect, QStackedWidget, QPushButton,
                             QProgressBar, QLineEdit, QFormLayout, QTabWidget,
                             QPlainTextEdit, QFileDialog, QCheckBox, QMessageBox, 
                             QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                             QDialog, QComboBox, QMenu)
from PyQt6.QtGui import (QPixmap, QFontDatabase, QFont, QTextCursor, QIcon, 
                         QPainter, QColor, QDesktopServices, QPen)
from PyQt6.QtCore import (Qt, QSize, pyqtSignal, QObject, QThread, QTimer, 
                          pyqtSlot, QRect, QPropertyAnimation, QEasingCurve, 
                          pyqtProperty, QUrl, QStandardPaths)
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading

# --- CONFIGURATION ---
CURRENT_VERSION = "V1.5.8-Beta6"
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DOCUMENTS_DIR = os.path.join(os.path.expanduser('~'), 'Documents')
PROJECTS_DIR = os.path.join(DOCUMENTS_DIR, 'ZuhuProjects')
OLD_DATA_FOLDER = os.path.join(DOCUMENTS_DIR, 'ZuhuOFME')
NEW_DATA_FOLDER = os.path.join(PROJECTS_DIR, 'ZuhuOFME')

if os.path.exists(OLD_DATA_FOLDER) and not os.path.exists(NEW_DATA_FOLDER):
    try:
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        shutil.move(OLD_DATA_FOLDER, NEW_DATA_FOLDER)
        print(f"Successfully migrated data folder to: {NEW_DATA_FOLDER}")
    except Exception as e:
        print(f"Error migrating folder: {e}")

DATA_FOLDER = NEW_DATA_FOLDER
DATA_FILE = os.path.join(DATA_FOLDER, 'Data.json')
SETTINGS_FILE = os.path.join(DATA_FOLDER, 'Settings.json')
ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-DWND-ICO.ico"
SETTINGS_ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-STNG-ICO.ico"
RELOAD_ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-RLD-ICO.ico"
WEB_TEMPLATE_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/index.html"
DISCORD_ICON_URL = "https://i.imgur.com/01wdU6Q.png"
FONT_URL = "https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/raw/main/Assets/pixelmix.ttf"
ICON_PATH = os.path.join(DATA_FOLDER, 'cache', 'OFME-DWND-ICO.ico')
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
STEAM_PATH = r"C:\Program Files (x86)\Steam"
STEAM_USER_ID = ""
DEFAULT_DOWNLOAD_PATH = ""
SHOW_SIZE_IN_GB = True
SHOW_SPEED_IN_MBPS = True
ENABLE_NOTIFICATIONS = True
ENABLE_WEBHOOK = False
WEBHOOK_URL = ""
OFME_USERNAME = ""
OFME_PASSWORD = ""
VERSION_CHECK_BYPASS_LIST = []
SELECTED_BROWSER_PATH = ""
WEB_MODE = False
SYNC_PATH = ""

# --- BROWSER DETECTION ---
def normalize_browser_name(raw_name):
    raw = raw_name.lower()
    if "brave" in raw: return "Brave"
    if "opera gx" in raw or "operagx" in raw: return "Opera GX"
    if "chrome" in raw and "google" in raw: return "Google Chrome"
    if "firefox" in raw: return "Firefox"
    if "opera" in raw and "gx" not in raw: return "Opera"
    if "vivaldi" in raw: return "Vivaldi"
    if "edge" in raw: return "Microsoft Edge"
    return raw_name

def get_installed_browsers():
    found_browsers = {}
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")
    
    potential_paths = {
        "Opera GX": [os.path.join(local_appdata, "Programs", "Opera GX", "launcher.exe"), os.path.join(local_appdata, "Programs", "Opera GX", "opera.exe")],
        "Google Chrome": [os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"), os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"), os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe")],
        "Brave": [os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"), os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")],
        "Firefox": [os.path.join(prog_files, "Mozilla Firefox", "firefox.exe"), os.path.join(local_appdata, "Mozilla Firefox", "firefox.exe")],
        "Opera": [os.path.join(local_appdata, "Programs", "Opera", "launcher.exe"), os.path.join(prog_files, "Opera", "launcher.exe")],
        "Vivaldi": [os.path.join(local_appdata, "Vivaldi", "Application", "vivaldi.exe"), os.path.join(prog_files, "Vivaldi", "Application", "vivaldi.exe")],
        "Microsoft Edge": [os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"), os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe")]
    }

    for name, paths in potential_paths.items():
        for path in paths:
            if os.path.exists(path):
                found_browsers[name] = path
                break 

    registry_locations = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Clients\StartMenuInternet"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Clients\StartMenuInternet"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet")
    ]
    for hive, reg_path in registry_locations:
        try:
            with winreg.OpenKey(hive, reg_path) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i); i += 1
                        if "iexplore" in subkey_name.lower(): continue
                        name = normalize_browser_name(subkey_name)
                        if name in found_browsers: continue 
                        cmd_path = f"{reg_path}\\{subkey_name}\\shell\\open\\command"
                        with winreg.OpenKey(hive, cmd_path) as cmd_key:
                            val, _ = winreg.QueryValueEx(cmd_key, "")
                            val = val.strip('"')
                            if os.path.exists(val): found_browsers[name] = val
                    except OSError: break
        except OSError: continue

    priority = ["Brave", "Opera GX", "Google Chrome", "Firefox", "Opera", "Vivaldi", "Microsoft Edge"]
    sorted_browsers = {}
    for p in priority:
        if p in found_browsers: sorted_browsers[p] = found_browsers[p]
    for k, v in found_browsers.items():
        if k not in sorted_browsers: sorted_browsers[k] = v
    return sorted_browsers

# --- WEB TEMPLATE MANAGEMENT ---
def ensure_web_template():
    template_dir = os.path.join(DATA_FOLDER, 'Templates')
    template_path = os.path.join(template_dir, 'index.html')
    dev_lock_path = os.path.join(template_dir, '.dev') 
    
    os.makedirs(template_dir, exist_ok=True)
    
    if os.path.exists(dev_lock_path):
        print("Developer Mode: .dev lock found. Skipping index.html update.")
        return

    url = WEB_TEMPLATE_URL 
    
    try:
        local_exists = os.path.exists(template_path)
        response = requests.head(url, timeout=5)
        remote_size = int(response.headers.get('content-length', 0))
        
        should_download = False
        if not local_exists:
            print("Web template missing. Downloading...")
            should_download = True
        else:
            local_size = os.path.getsize(template_path)
            if local_size != remote_size and remote_size > 0:
                print(f"Update found for web template. Downloading...")
                should_download = True

        if should_download:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(template_path, 'wb') as f:
                    f.write(r.content)
                print("Web template saved successfully.")
    except Exception as e:
        print(f"Web template check skipped: {e}")

# --- CUSTOM WIDGETS ---
class CustomComboBox(QComboBox):
    """
    A custom ComboBox that draws a text-based arrow ( > or v ) 
    instead of using an image file. Matches the green pixel theme.
    """
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_open = self.view().isVisible()
        arrow_char = "v" if is_open else ">"
        painter.setPen(QColor("#00ff7f"))
        f = self.font()
        f.setBold(True)
        painter.setFont(f)
        rect = self.rect()
        arrow_area = QRect(rect.width() - 30, 0, 30, rect.height())
        painter.drawText(arrow_area, Qt.AlignmentFlag.AlignCenter, arrow_char)

# --- STYLING ---
STYLESHEET = """
    QWidget { background-color: #1e1e1e; color: #e0e0e0; }
    QScrollArea { border: none; background-color: #1e1e1e; }
    
    QProgressBar {
        border: 1px solid #444; border-radius: 13px; text-align: center;
        background-color: #2d2d2d; height: 26px; color: white; font-size: 10px;
    }
    QProgressBar::chunk { background-color: #00ff7f; border-radius: 13px; }
    
    QLineEdit {
        border: 1px solid #444; background-color: #2d2d2d;
        border-radius: 15px; padding: 5px 12px; color: #e0e0e0; min-height: 20px; 
    }
    QLineEdit:focus { border: 1px solid #00ff7f; }
    
    QPushButton#CircleBtn {
        border: 1px solid #444; background-color: #2d2d2d; border-radius: 17px; 
    }
    QPushButton#CircleBtn:hover { border-color: #00ff7f; background-color: #333; }
    
    QPushButton {
        background-color: #2d2d2d; border: 1px solid #444; 
        border-radius: 15px; padding: 6px 12px; color: #e0e0e0; 
    }
    QPushButton:hover { border: 1px solid #00ff7f; color: #00ff7f; background-color: #333; }
    QPushButton:disabled { border: 1px solid #333; color: #555; }
    
    QPushButton#TopBackBtn {
        background: transparent; border: none; color: #00ff7f; 
        text-align: left; font-weight: bold; font-size: 14px; padding: 0px;
    }
    QPushButton#TopBackBtn:hover { color: #fff; border: none; background: transparent; }

    QPushButton#SteamBtn {
        background-color: #171a21; border: 1px solid #66c0f4; color: #66c0f4; font-weight: bold;
        border-radius: 15px;
    }
    QPushButton#SteamBtn:hover { background-color: #2a475e; color: #ffffff; }
    
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

    QTableWidget { gridline-color: #444; background-color: #1e1e1e; border: 1px solid #444; }
    QHeaderView::section { background-color: #2d2d2d; padding: 4px; border: 1px solid #444; color: #00ff7f; }
    QTableWidget::item { padding: 5px; }

    /* --- CUSTOM COMBOBOX STYLING --- */
    QComboBox {
        background-color: #2d2d2d;
        border: 1px solid #444;
        border-radius: 0px; /* Square */
        padding: 5px 10px;
        color: #00ff7f;
        min-width: 140px;
        font-weight: bold;
    }
    QComboBox:hover { border: 1px solid #00ff7f; }
    
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border-left-width: 1px;
        border-left-color: #444;
        border-left-style: solid;
        border-top-right-radius: 0px;
        border-bottom-right-radius: 0px;
    }
    
    /* HIDE DEFAULT ARROW (We draw it manually in Python) */
    QComboBox::down-arrow {
        image: none;
        border: none;
    }

    QComboBox QAbstractItemView {
        background-color: #2d2d2d;
        color: #e0e0e0;
        selection-background-color: #00ff7f;
        selection-color: #000000;
        border: 1px solid #444;
        outline: none;
    }
"""

# --- SETTINGS LOGIC ---
def load_settings():
    global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH, SHOW_SIZE_IN_GB, SHOW_SPEED_IN_MBPS, ENABLE_NOTIFICATIONS
    global ENABLE_WEBHOOK, WEBHOOK_URL, OFME_USERNAME, OFME_PASSWORD, VERSION_CHECK_BYPASS_LIST
    global STEAM_PATH, STEAM_USER_ID, SELECTED_BROWSER_PATH, WEB_MODE, SYNC_PATH
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                WINRAR_PATH = settings.get('winrar_path', WINRAR_PATH)
                DEFAULT_DOWNLOAD_PATH = settings.get('default_download_path', DEFAULT_DOWNLOAD_PATH)
                STEAM_PATH = settings.get('steam_path', STEAM_PATH)
                STEAM_USER_ID = settings.get('steam_user_id', "")
                SHOW_SIZE_IN_GB = settings.get('show_size_in_gb', True)
                SHOW_SPEED_IN_MBPS = settings.get('show_speed_in_mbps', False)
                ENABLE_NOTIFICATIONS = settings.get('enable_notifications', True)
                ENABLE_WEBHOOK = settings.get('enable_webhook', False)
                WEBHOOK_URL = settings.get('webhook_url', "")
                OFME_USERNAME = settings.get('ofme_username', "")
                OFME_PASSWORD = settings.get('ofme_password', "")
                VERSION_CHECK_BYPASS_LIST = settings.get('version_check_bypass_list', [])
                SELECTED_BROWSER_PATH = settings.get('selected_browser_path', "")
                WEB_MODE = settings.get('web_mode', False)
                SYNC_PATH = settings.get('sync_path', "")

        except (json.JSONDecodeError, IOError): pass
    if not OFME_USERNAME or not OFME_PASSWORD:
        old_login_file = os.path.join(DATA_FOLDER, 'Login.json')
        if os.path.exists(old_login_file):
            try:
                with open(old_login_file, 'r') as f:
                    creds = json.load(f)
                    if not OFME_USERNAME: OFME_USERNAME = creds.get('username', '')
                    if not OFME_PASSWORD: OFME_PASSWORD = creds.get('password', '')
                    if not WEBHOOK_URL: WEBHOOK_URL = creds.get('webhook_url', '')
                save_settings_to_file()
                print("Migrated credentials from Login.json to Settings.json")
            except: pass

def save_settings_to_file():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    settings = {
        'winrar_path': WINRAR_PATH,
        'default_download_path': DEFAULT_DOWNLOAD_PATH,
        'steam_path': STEAM_PATH,
        'steam_user_id': STEAM_USER_ID,
        'show_size_in_gb': SHOW_SIZE_IN_GB,
        'show_speed_in_mbps': SHOW_SPEED_IN_MBPS,
        'enable_notifications': ENABLE_NOTIFICATIONS,
        'enable_webhook': ENABLE_WEBHOOK,
        'webhook_url': WEBHOOK_URL,
        'ofme_username': OFME_USERNAME,
        'ofme_password': OFME_PASSWORD,
        'version_check_bypass_list': VERSION_CHECK_BYPASS_LIST,
        'selected_browser_path': SELECTED_BROWSER_PATH,
        'web_mode': WEB_MODE,
        'sync_path': SYNC_PATH
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
        self.history = []

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()
        self.history.append(text)
        self._text_written.emit(str(text))

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

# ---  STEAM SCRAPER WORKER ---
class SteamScraperWorker(QThread):
    account_found = pyqtSignal(str, str, str)
    finished = pyqtSignal()

    def run(self):
        userdata_path = os.path.join(STEAM_PATH, "userdata")
        if not os.path.exists(userdata_path): return
        headers = {'User-Agent': 'Mozilla/5.0'}
        for entry in os.listdir(userdata_path):
            if entry.isdigit():
                try:
                    url = f"https://steamid.xyz/{entry}"
                    resp = requests.get(url, headers=headers, timeout=5)
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    
                    user_tag = soup.find('h1', class_='value')
                    username = user_tag.text.strip() if user_tag else f"User {entry}"
                    
                    ava_tag = soup.find('img', class_='avatar')
                    avatar_url = ava_tag['src'] if ava_tag and 'src' in ava_tag.attrs else ""
                    
                    self.account_found.emit(entry, username, avatar_url)
                    time.sleep(1.0)
                except:
                    self.account_found.emit(entry, "N/A", "")
        self.finished.emit()

# --- STEAM ACCOUNT PICKER DIALOG ---
class SteamAccountPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Steam Account")
        self.setFixedSize(450, 480)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")
        self.selected_id = None
        
        layout = QVBoxLayout(self)
        title = QLabel("Select your Steam Profile:"); 
        title.setStyleSheet("font-weight: bold; color: #00ff7f; font-size: 14px; border:none;")
        layout.addWidget(title)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedHeight(350)
        self.container = QWidget()
        self.accounts_layout = QVBoxLayout(self.container)
        self.accounts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        
        self.loading_lbl = QLabel("Scanning Steam accounts..."); 
        self.loading_lbl.setStyleSheet("color: #888; border: none;")
        layout.addWidget(self.loading_lbl)
        
        self.worker = SteamScraperWorker()
        self.worker.account_found.connect(self.add_account_row)
        self.worker.finished.connect(lambda: self.loading_lbl.setText("Scan complete."))
        self.worker.start()

    def add_account_row(self, sid, name, avatar_url):
        row = QFrame()
        row.setFixedHeight(100)
        row.setStyleSheet("background-color: #252525; border-radius: 8px;")
        h_lay = QHBoxLayout(row)
        
        img_lbl = QLabel()
        img_lbl.setFixedSize(65, 65)
        img_lbl.setStyleSheet("background-color: #000; border: 1px solid #444;")
        if avatar_url:
            try:
                data = requests.get(avatar_url, timeout=5).content
                pix = QPixmap()
                pix.loadFromData(data)
                img_lbl.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio))
            except: pass
        
        v_lay = QVBoxLayout()
        name_lbl = QLabel(name); 
        name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0; border:none;")
        id_lbl = QLabel(f"ID: {sid}"); 
        id_lbl.setStyleSheet("font-size: 11px; color: #888; border:none;")
        v_lay.addWidget(name_lbl); v_lay.addWidget(id_lbl)
        h_lay.addWidget(img_lbl); h_lay.addLayout(v_lay, 1)
        
        sel_btn = QPushButton("Select")
        sel_btn.setFixedWidth(80)
        sel_btn.clicked.connect(lambda: self.confirm_selection(sid))
        h_lay.addWidget(sel_btn)
        self.accounts_layout.addWidget(row)

    def confirm_selection(self, sid):
        self.selected_id = sid
        self.accept()

# ---  VERSION CHECKER ---
class VersionCheckWorker(QThread):
    status_update = pyqtSignal(str, str, str)
    log_message = pyqtSignal(str)
    check_finished = pyqtSignal(list, str)
    login_failed = pyqtSignal()
    
    def run(self):
        self.log_message.emit("Starting Version Check...")
        start_time = time.time()
        
        if not OFME_USERNAME or not OFME_PASSWORD:
            self.log_message.emit("Error: Missing credentials.")
            self.login_failed.emit()
            return

        options = Options()
        options.add_argument("--headless=new") 
        browser_exe = SELECTED_BROWSER_PATH
        if not browser_exe or not os.path.exists(browser_exe):
            self.log_message.emit("Selected browser not found or unset, fallback to default...")
            if os.path.exists(BRAVE_PATH):
                browser_exe = BRAVE_PATH
            else:
                self.log_message.emit("Brave default not found. Attempting system Chrome...")
                browser_exe = ""
        self.log_message.emit(f"Using Browser Path: {browser_exe if browser_exe else 'System Default'}")
        if browser_exe:
            options.binary_location = browser_exe
        
        driver1 = None
        driver2 = None
        
        try:
            self.log_message.emit("Initializing Driver 1 (OFME - Headless)...")
            try:
                driver1 = webdriver.Chrome(options=options)
            except Exception as e:
                self.log_message.emit(f"Failed to init standard driver: {e}")
                if "binary is not a Chrome" in str(e) or "binary" in str(e).lower():
                    self.log_message.emit("Binary error. Trying default system Chrome...")
                    options.binary_location = "" 
                    driver1 = webdriver.Chrome(options=options)

            self.log_message.emit("Initializing Driver 2 (SteamRIP - VISIBLE)...")
            try:
                sb_browser = "chrome"
                if browser_exe:
                    lower_path = browser_exe.lower()
                    if "brave" in lower_path: sb_browser = "brave"
                    elif "firefox" in lower_path: sb_browser = "firefox"
                    elif "edge" in lower_path: sb_browser = "edge"
                    elif "opera" in lower_path: sb_browser = "opera"
                
                driver2 = Driver(browser=sb_browser, uc=True, headless=False)
            except Exception as e:
                self.log_message.emit(f"Failed to init UC driver: {e}")

            self.log_message.emit("Fetching latest database...")
            response = requests.get(DB_URL)
            lines = response.text.splitlines()
            games = []
            current_game = {}
            opties = ['GoFile', 'DropBox', 'Both', 'BuzzHeavier']
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"): continue
                for optie in opties:
                    if line.startswith(optie):
                        if current_game:
                            games.append(current_game); current_game = {}
                        name_part = line.split(f"{optie} (")[1].split(")")[0]
                        version = line.split("[")[1].split("]")[0]
                        current_game["Source"] = optie; current_game["Name"] = name_part; current_game["Version"] = version
                        break  
                    elif ":" in line:
                        key, value = line.split(":", 1)
                        current_game[key.strip()] = value.strip()
            if current_game: games.append(current_game)

            total_games = len(games)
            game_update = {}
            counter = 0
            
            for idx, game in enumerate(games):
                if game['Name'] in VERSION_CHECK_BYPASS_LIST:
                    self.log_message.emit(f"Skipping {game['Name']} (Bypass enabled)")
                    continue
                
                progress_str = f"{idx + 1}/{total_games}"
                local_ver_display = f"Local: {game.get('Version', '?')}"
                self.status_update.emit(game['Name'], f"Checking... ({local_ver_display})", progress_str)
                
                version = ""
                
                if 'https://online-fix.me/' in game.get('Origin', ''):
                    if not driver1: continue
                    driver1.get(game['Origin'])
                    if counter == 0:
                        try:
                            search = driver1.find_element(By.NAME, 'login_name')
                            search.send_keys(OFME_USERNAME)
                            search = driver1.find_element(By.NAME, 'login_password')
                            search.send_keys(OFME_PASSWORD)
                            time.sleep(0.5)
                            search.send_keys(Keys.RETURN)            
                            try:
                                WebDriverWait(driver1, 5).until(
                                    EC.presence_of_element_located((By.XPATH, f"//img[@alt='{OFME_USERNAME}']"))
                                )
                                self.log_message.emit(f"Successfully logged in as: {OFME_USERNAME}")
                                counter += 1
                            except TimeoutException:
                                self.log_message.emit("Login failed on website.")
                                self.login_failed.emit()
                                driver1.quit(); 
                                if driver2: driver2.quit()
                                return
                        except Exception as e:
                            self.log_message.emit(f"Login element error: {e}")
                            continue
                            
                        driver1.get(game['Origin'])

                    time.sleep(1) 
                    try:
                        select_version = WebDriverWait(driver1, 15).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "quote")))
                        version = select_version.find_element(By.TAG_NAME, 'b').text.replace('Версия игры: ', '')
                    except:
                        self.log_message.emit(f"Version tag not found for {game['Name']}")
                        continue 
                             
                elif 'https://steamrip.com/' in game.get('Origin', ''):
                    if not driver2: continue
                    Origin_URL = game['Origin']
                    try:
                        driver2.uc_open_with_reconnect(Origin_URL, 6) 
                        driver2.uc_gui_click_captcha()
                        
                        version = driver2.find_element(By.TAG_NAME, 'h1').text.split('(')[1].replace(')','')
                    except Exception as e:
                        self.log_message.emit(f"SteamRIP error for {game['Name']}: {e}")
                        continue
                else:
                    continue
                
                if "Build" in version: version = version.replace("Build ", "")
                if "v" in version: version = version.replace("v", "")
                
                self.status_update.emit(game['Name'], f"Found: {version}", progress_str)
                if version != game['Version']:
                    game_update[game['Name']] = {
                        'new': version, 
                        'old': game['Version'],
                        'url': game['Origin']
                    }
            if driver1: driver1.quit()
            if driver2: driver2.quit()

            end_time = time.time()
            elapsed = end_time - start_time
            
            if elapsed < 60:
                time_str = f"{int(elapsed)} sec"
            else:
                mins, secs = divmod(elapsed, 60)
                time_str = f"{int(mins)}min {int(secs)}sec"
            if ENABLE_WEBHOOK and WEBHOOK_URL and "discord" in WEBHOOK_URL:
                self.send_discord_webhook(game_update, len(game_update))

            results_list = []
            for name, data in game_update.items():
                results_list.append({
                    'name': name,
                    'old': data['old'],
                    'new': data['new'],
                    'url': data['url']
                })
                
            self.check_finished.emit(results_list, time_str)

        except Exception as e:
            self.log_message.emit(f"Critical Worker Error: {e}")
            self.check_finished.emit([], "Error")
            if driver1: driver1.quit()
            if driver2: driver2.quit()

    def send_discord_webhook(self, game_update, num_updates):
        if num_updates > 0:
            embed_fields = []
            for name, info in game_update.items():
                embed_fields.append({
                    "name": f"🎮 {name}",
                    "value": f"**New:** {info['new']}\n**Old:** {info['old']}\n[Download Page]({info['url']})",
                    "inline": False 
                })
            payload = {
                "username": "OFME Version Checker",
                "avatar_url": DISCORD_ICON_URL,
                "embeds": [{
                    "title": f"🚨 {num_updates} Game Updates Available!",
                    "description": "The following games have new versions detected:",
                    "color": 16711680,
                    "fields": embed_fields,
                    "thumbnail": { "url": DISCORD_ICON_URL },
                    "footer": {"text": "ZuhuOFME Checker"}
                }]
            }
        else:
            payload = {
                "username": "OFME Version Checker",
                "avatar_url": DISCORD_ICON_URL,
                "embeds": [{
                    "title": "✅ All Games Up To Date",
                    "description": "We checked your library and everything is on the latest version.",
                    "color": 3066993,
                    "thumbnail": { "url": DISCORD_ICON_URL },
                    "footer": {"text": "ZuhuOFME Checker"}
                }]
            }
        
        try:
            requests.post(WEBHOOK_URL, json=payload)
            self.log_message.emit("Discord Webhook sent.")
        except Exception as e:
            self.log_message.emit(f"Failed to send webhook: {e}")

# --- CUSTOM TOGGLE SWITCH ---
class PyToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 32) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_color = "#777"
        self._circle_color = "#DDD"
        self._active_color = "#00ff7f"
        self._margin = 4
        self._circle_size = self.height() - (self._margin * 2)
        self._circle_position = self._margin
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(300)
        self.stateChanged.connect(self.start_transition)

    def start_transition(self, state):
        self.animation.stop()
        if state: 
            self.animation.setEndValue(self.width() - self._circle_size - self._margin)
        else: 
            self.animation.setEndValue(self._margin)
        self.animation.start()

    def set_state_immediate(self, state):
        self.blockSignals(True)
        self.setChecked(state)
        if state:
            self._circle_position = self.width() - self._circle_size - self._margin
        else:
            self._circle_position = self._margin
        self.blockSignals(False)
        self.update()
        
    def hitButton(self, pos): return self.contentsRect().contains(pos)
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked(): p.setBrush(QColor(self._active_color))
        else: p.setBrush(QColor(self._bg_color))
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        radius = self.height() / 2
        p.drawRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
        p.setBrush(QColor(self._circle_color))
        p.drawEllipse(int(self._circle_position), self._margin, self._circle_size, self._circle_size)
        p.end()

    def get_circle_position(self): return self._circle_position
    def set_circle_position(self, pos): self._circle_position = pos; self.update()
    circle_position = pyqtProperty(float, get_circle_position, set_circle_position)

# --- SYNC WORKER ---
class SyncWorker(QThread):
    finished = pyqtSignal(bool, str)
    def __init__(self, local_path, cloud_path, mode="sync"):
        super().__init__()
        self.local = local_path; self.cloud = cloud_path; self.mode = mode
        
    def run(self):
        try:
            import datetime
            if not os.path.exists(self.cloud): os.makedirs(self.cloud, exist_ok=True)
            
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            silent_flags = ['/E', '/FFT', '/DST', '/R:1', '/W:1', '/XO', '/NJH', '/NJS', '/NDL', '/NFL', '/NC', '/NS', '/NP']

            # --- CUSTOM HEADER ---
            start_dt = datetime.datetime.now().strftime("%d %B %Y %H:%M:%S")
            print(f"\n  Started : {start_dt}")
            
            if self.mode == "push":
                print(f"   Source = {self.local}")
                print(f"     Dest : {self.cloud}")
                subprocess.run(['robocopy', self.local, self.cloud] + silent_flags, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = "Force Upload Complete!"
            elif self.mode == "pull":
                print(f"   Source = {self.cloud}")
                print(f"     Dest : {self.local}")
                subprocess.run(['robocopy', self.cloud, self.local] + silent_flags, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = "Force Download Complete!"
            else:
                print(f"   Source = {self.cloud} <-> {self.local}")
                print(f"     Dest : Bidirectional Sync")
                subprocess.run(['robocopy', self.cloud, self.local] + silent_flags, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['robocopy', self.local, self.cloud] + silent_flags, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = "Sync Complete!"

            # --- CUSTOM FOOTER ---
            end_dt = datetime.datetime.now().strftime("%d %B %Y %H:%M:%S")
            print(f"   Ended : {end_dt}")
            print("Files synced successfully.\n")
                
            self.finished.emit(True, msg)
        except Exception as e: 
            self.finished.emit(False, str(e))

# --- SETTINGS PAGE ---
class SettingsPage(QWidget):
    back_requested = pyqtSignal()
    def __init__(self, main_font):
        super().__init__()
        
        self.settings_font = QFont(main_font)
        self.settings_font.setPointSize(13)
        self.settings_font.setBold(False)
        self.checker_thread = None
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live_time)
        self.start_timestamp = 0

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

        self.tabs = QTabWidget()
        self.tabs.setFont(self.settings_font)
        layout.addWidget(self.tabs, 1)

        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        console_font = QFont(main_font); console_font.setPointSize(11)
        self.console_output.setFont(console_font) 
        console_layout.addWidget(self.console_output)
        self.tabs.addTab(console_widget, "Console Output")
        self.create_general_settings_tab()
        self.create_version_checker_tab()
        
        bottom_container = QWidget()
        self.bottom_layout = QHBoxLayout(bottom_container)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.addStretch()

        self.save_button = QPushButton("Save Settings")
        self.save_button.setFont(self.settings_font)
        self.save_button.setFixedWidth(200)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_settings)
        self.bottom_layout.addWidget(self.save_button)

        self.vc_toggle_container = QWidget()
        vc_toggle_layout = QHBoxLayout(self.vc_toggle_container)
        vc_toggle_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_browser = QLabel("Browser:")
        lbl_browser.setFont(self.settings_font)
        lbl_browser.setStyleSheet("color: #e0e0e0; margin-right: 5px;")
        
        self.browser_combo = CustomComboBox()
        self.browser_combo.setFont(self.settings_font)
        self.browser_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browser_combo.setToolTip("Select the browser used for verification")
        self.browser_combo.setEnabled(False)
        self.detected_browsers = get_installed_browsers()
        for name, path in self.detected_browsers.items():
            self.browser_combo.addItem(name, path)
            
        idx = self.browser_combo.findData(SELECTED_BROWSER_PATH)
        if idx >= 0: self.browser_combo.setCurrentIndex(idx)
        elif self.browser_combo.count() > 0: self.browser_combo.setCurrentIndex(0) 
        self.browser_combo.currentIndexChanged.connect(self.save_browser_selection)

        vc_toggle_layout.addWidget(lbl_browser)
        vc_toggle_layout.addWidget(self.browser_combo)
        vc_toggle_layout.addSpacing(20)
        
        vc_lbl = QLabel("Discord Webhook:")
        vc_lbl.setFont(self.settings_font)
        vc_lbl.setStyleSheet("color: #e0e0e0; margin-right: 10px;")
        
        self.vc_wh_toggle = PyToggle()
        self.vc_wh_toggle.setFixedSize(60, 32)
        self.vc_wh_toggle.stateChanged.connect(self.on_vc_webhook_toggled)
        vc_toggle_layout.addWidget(vc_lbl)
        vc_toggle_layout.addWidget(self.vc_wh_toggle)
        
        self.bottom_layout.addWidget(self.vc_toggle_container)
        self.vc_toggle_container.hide()
        layout.addWidget(bottom_container)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.on_tab_changed(self.tabs.currentIndex())

    def save_browser_selection(self):
        global SELECTED_BROWSER_PATH
        SELECTED_BROWSER_PATH = self.browser_combo.currentData()
        print(f"Browser selection changed to: {self.browser_combo.currentText()}")
        save_settings_to_file()

    def on_tab_changed(self, index):
        self.save_button.hide()
        self.vc_toggle_container.hide()
        if index == 1:
            self.save_button.show()
        elif index == 2:
            self.vc_toggle_container.show()
            self.vc_wh_toggle.set_state_immediate(ENABLE_WEBHOOK)

    def on_vc_webhook_toggled(self, state):
        global ENABLE_WEBHOOK
        is_checked = (state != 0)
        ENABLE_WEBHOOK = is_checked
        
        self.wh_toggle.set_state_immediate(is_checked)
        self.lbl_wh_status.setText("On" if is_checked else "Off")
        self.wh_input.setEnabled(is_checked)
        save_settings_to_file()
        print(f"Webhook toggled to {'ON' if is_checked else 'OFF'}")
        
    def append_stream_output(self, text):
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertPlainText(text)
    def append_log_line(self, text):
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertPlainText(text + "\n")
    def create_general_settings_tab(self):
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

        lbl_sync = QLabel("Cloud Save Folder:")
        lbl_sync.setFont(self.settings_font)
        sync_cont = QWidget(); sync_lay = QHBoxLayout(sync_cont); sync_lay.setContentsMargins(0,0,0,0)
        self.sync_path_edit = QLineEdit(SYNC_PATH)
        self.sync_path_edit.setFont(self.settings_font)
        self.sync_path_edit.setPlaceholderText("Folder to sync saves to (e.g. OneDrive)")
        btn_browse_sync = QPushButton("...")
        btn_browse_sync.setFixedWidth(40)
        btn_browse_sync.clicked.connect(self.browse_sync_path)
        sync_lay.addWidget(self.sync_path_edit); sync_lay.addWidget(btn_browse_sync)
        form_layout.addRow(lbl_sync, sync_cont)

        # --- STEAM SETTINGS ---
        lbl_steam_p = QLabel("Steam Path:")
        lbl_steam_p.setFont(self.settings_font)
        self.steam_path_edit = QLineEdit(STEAM_PATH)
        self.steam_path_edit.setFont(self.settings_font)
        form_layout.addRow(lbl_steam_p, self.steam_path_edit)

        lbl_steam_id = QLabel("Steam User ID:")
        lbl_steam_id.setFont(self.settings_font)
        self.steam_id_edit = QLineEdit(STEAM_USER_ID)
        self.steam_id_edit.setFont(self.settings_font)
        self.steam_id_edit.setPlaceholderText("Select in Game Tab or enter ID here")
        form_layout.addRow(lbl_steam_id, self.steam_id_edit)
        lbl_web = QLabel("Enable Web Interface (Restart required):")
        lbl_web.setFont(self.settings_font)
        
        self.web_mode_toggle = PyToggle()
        self.web_mode_toggle.set_state_immediate(WEB_MODE)
        form_layout.addRow(lbl_web, self.web_mode_toggle)

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
        self.speed_toggle.set_state_immediate(SHOW_SPEED_IN_MBPS)
        self.lbl_speed_status = QLabel("Mbps" if SHOW_SPEED_IN_MBPS else "MB/s")
        self.lbl_speed_status.setFont(self.settings_font)
        self.lbl_speed_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.speed_toggle.stateChanged.connect(lambda s: self.lbl_speed_status.setText("Mbps" if s else "MB/s"))
        lbl_sp, cont_sp = create_toggle_row("Show Speed in:", self.speed_toggle, self.lbl_speed_status)
        form_layout.addRow(lbl_sp, cont_sp)

        self.size_toggle = PyToggle()
        self.size_toggle.set_state_immediate(SHOW_SIZE_IN_GB)
        self.lbl_size_status = QLabel("GB" if SHOW_SIZE_IN_GB else "MB")
        self.lbl_size_status.setFont(self.settings_font)
        self.lbl_size_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.size_toggle.stateChanged.connect(lambda s: self.lbl_size_status.setText("GB" if s else "MB"))
        lbl_sz, cont_sz = create_toggle_row("Show Size in:", self.size_toggle, self.lbl_size_status)
        form_layout.addRow(lbl_sz, cont_sz)

        self.notif_toggle = PyToggle()
        self.notif_toggle.set_state_immediate(ENABLE_NOTIFICATIONS)
        self.lbl_notif_status = QLabel("On" if ENABLE_NOTIFICATIONS else "Off")
        self.lbl_notif_status.setFont(self.settings_font)
        self.lbl_notif_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.notif_toggle.stateChanged.connect(lambda s: self.lbl_notif_status.setText("On" if s else "Off"))
        lbl_nf, cont_nf = create_toggle_row("Desktop Notifications:", self.notif_toggle, self.lbl_notif_status)
        form_layout.addRow(lbl_nf, cont_nf)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #444; margin-top: 10px; margin-bottom: 10px;")
        form_layout.addRow(line)

        # --- DISCORD WEBHOOK SETTINGS ---
        self.wh_toggle = PyToggle()
        self.wh_toggle.set_state_immediate(ENABLE_WEBHOOK)
        self.lbl_wh_status = QLabel("On" if ENABLE_WEBHOOK else "Off")
        self.lbl_wh_status.setFont(self.settings_font)
        self.lbl_wh_status.setStyleSheet("color: #aaa; margin-left: 10px;")
        self.wh_toggle.stateChanged.connect(lambda s: self.lbl_wh_status.setText("On" if s else "Off"))
        
        lbl_wh, cont_wh = create_toggle_row("Discord Webhook (Toggle):", self.wh_toggle, self.lbl_wh_status)
        form_layout.addRow(lbl_wh, cont_wh)
        lbl_wh_link = QLabel("Webhook Link:")
        lbl_wh_link.setFont(self.settings_font)
        
        self.wh_input = QLineEdit(WEBHOOK_URL)
        self.wh_input.setFont(self.settings_font)
        self.wh_input.setPlaceholderText("Paste Discord Webhook URL here...")
        self.wh_input.setEnabled(ENABLE_WEBHOOK)
        
        self.wh_toggle.stateChanged.connect(self.wh_input.setEnabled)
        
        form_layout.addRow(lbl_wh_link, self.wh_input)

        settings_layout.addLayout(form_layout)
        settings_layout.addStretch()
        self.tabs.addTab(settings_widget, "General Settings")

    def create_version_checker_tab(self):
        vc_widget = QWidget()
        vc_layout = QVBoxLayout(vc_widget)
        
        config_group = QFrame()
        config_group.setStyleSheet("background-color: #252525; border-radius: 8px;")
        config_layout = QVBoxLayout(config_group)
        
        self.creds_container = QWidget()
        c_lay = QFormLayout(self.creds_container)
        self.user_input = QLineEdit(OFME_USERNAME); self.user_input.setPlaceholderText("Online-Fix Username")
        self.pass_input = QLineEdit(OFME_PASSWORD); self.pass_input.setEchoMode(QLineEdit.EchoMode.Password); self.pass_input.setPlaceholderText("Online-Fix Password")
        c_lay.addRow("Username:", self.user_input)
        c_lay.addRow("Password:", self.pass_input)
        
        if OFME_USERNAME and OFME_PASSWORD:
            self.creds_expand_btn = QPushButton("Show/Edit Login Credentials ▼")
            self.creds_expand_btn.setCheckable(True)
            self.creds_expand_btn.clicked.connect(lambda c: self.creds_container.setVisible(c))
            self.creds_container.setVisible(False)
            config_layout.addWidget(self.creds_expand_btn)
        else:
             lbl = QLabel("Login Credentials Required for Checker:"); lbl.setStyleSheet("color: #ff4500;")
             config_layout.addWidget(lbl)
        
        config_layout.addWidget(self.creds_container)
        vc_layout.addWidget(config_group)
        
        self.start_check_btn = QPushButton("Start Version Check")
        self.start_check_btn.setFont(self.settings_font)
        self.start_check_btn.setStyleSheet("background-color: #006400; color: white; padding: 10px;")
        self.start_check_btn.clicked.connect(self.start_version_check)
        vc_layout.addWidget(self.start_check_btn)
        
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 5px; padding: 5px;")
        s_lay = QGridLayout(status_frame)
        
        self.lbl_game_checking = QLabel("Game Checking: Idle"); self.lbl_game_checking.setFont(self.settings_font)
        self.lbl_game_version = QLabel("Version: -"); self.lbl_game_version.setFont(self.settings_font)
        self.lbl_check_progress = QLabel("Progress: 0/0"); self.lbl_check_progress.setFont(self.settings_font)
        self.lbl_time_taken = QLabel("Time Taken: 0 sec"); self.lbl_time_taken.setFont(self.settings_font)
        
        s_lay.addWidget(self.lbl_game_checking, 0, 0)
        s_lay.addWidget(self.lbl_game_version, 0, 1)
        s_lay.addWidget(self.lbl_check_progress, 1, 0)
        s_lay.addWidget(self.lbl_time_taken, 1, 1)
        vc_layout.addWidget(status_frame)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Game Name", "Old Ver", "New Ver", "Action"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.verticalHeader().setVisible(False)
        vc_layout.addWidget(self.results_table)
        
        self.tabs.addTab(vc_widget, "Version Checker")

    def start_version_check(self):
        global OFME_USERNAME, OFME_PASSWORD, WEBHOOK_URL, ENABLE_WEBHOOK
        OFME_USERNAME = self.user_input.text()
        OFME_PASSWORD = self.pass_input.text()
        
        WEBHOOK_URL = self.wh_input.text()
        ENABLE_WEBHOOK = self.wh_toggle.isChecked()
        
        self.start_check_btn.setEnabled(False)
        self.start_check_btn.setText("Checking... (Please Wait)")
        self.results_table.setRowCount(0)
        self.lbl_game_checking.setText("Game Checking: Initializing...")
        
        self.start_timestamp = time.time()
        self.timer.start(1000)
        self.lbl_time_taken.setText("Time Taken: 0 sec")
        
        self.checker_thread = VersionCheckWorker()
        self.checker_thread.log_message.connect(self.append_log_line)
        self.checker_thread.status_update.connect(self.update_check_status)
        self.checker_thread.check_finished.connect(self.on_check_finished)
        self.checker_thread.login_failed.connect(self.on_login_failed)
        self.checker_thread.start()

    def update_live_time(self):
        elapsed = time.time() - self.start_timestamp
        if elapsed < 60:
            time_str = f"{int(elapsed)} sec"
        else:
            mins, secs = divmod(elapsed, 60)
            time_str = f"{int(mins)}min {int(secs)}sec"
        self.lbl_time_taken.setText(f"Time Taken: {time_str}")

    def update_check_status(self, name, ver, prog):
        self.lbl_game_checking.setText(f"Game Checking: {name}")
        self.lbl_game_version.setText(f"Version: {ver}")
        self.lbl_check_progress.setText(f"Progress: {prog}")
        
    def on_check_finished(self, results, time_str):
        self.timer.stop()
        self.start_check_btn.setEnabled(True)
        self.start_check_btn.setText("Start Version Check")
        self.lbl_time_taken.setText(f"Time Taken: {time_str}")
        self.lbl_game_checking.setText("Overview:")
        self.lbl_game_version.setText("")
        self.lbl_check_progress.setText(f"{len(results)} Update(s) Found")
        
        self.results_table.setRowCount(len(results))
        
        if not results:
             self.results_table.setRowCount(1)
             item = QTableWidgetItem("All games are up to date!")
             item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
             self.results_table.setItem(0, 0, item)
             self.results_table.setSpan(0, 0, 1, 4)
             
             if ENABLE_NOTIFICATIONS:
                 safe_icon = ICON_PATH if os.path.exists(ICON_PATH) else None
                 notification.notify(title="OFME Checker", message="All games up to date!", app_icon=safe_icon, timeout=10)
        else:
            if ENABLE_NOTIFICATIONS:
                 safe_icon = ICON_PATH if os.path.exists(ICON_PATH) else None
                 notification.notify(title="OFME Checker", message=f"{len(results)} Games need updates!", app_icon=safe_icon, timeout=10)
                 
            for row, data in enumerate(results):
                self.results_table.setItem(row, 0, QTableWidgetItem(data['name']))
                self.results_table.setItem(row, 1, QTableWidgetItem(data['old']))
                self.results_table.setItem(row, 2, QTableWidgetItem(data['new']))
                
                btn = QPushButton("Open Site")
                btn.setStyleSheet("background-color: #007acc; border-radius: 4px; padding: 2px;")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked, url=data['url']: QDesktopServices.openUrl(QUrl(url)))
                self.results_table.setCellWidget(row, 3, btn)

    def on_login_failed(self):
        self.timer.stop()
        self.start_check_btn.setEnabled(True)
        self.start_check_btn.setText("Start Version Check")
        QMessageBox.warning(self, "Login Error", "Could not log in to Online-Fix.me.\nPlease check your username and password in the fields above.")
        self.creds_container.setVisible(True)

    def browse_sync_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Cloud Sync Folder")
        if path: self.sync_path_edit.setText(path)

    def save_settings(self):
        global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH, SHOW_SIZE_IN_GB, SHOW_SPEED_IN_MBPS, ENABLE_NOTIFICATIONS
        global ENABLE_WEBHOOK, WEBHOOK_URL, OFME_USERNAME, OFME_PASSWORD, VERSION_CHECK_BYPASS_LIST
        global STEAM_PATH, STEAM_USER_ID
        
        self.save_button.setText("Saved!")
        self.save_button.setStyleSheet("border: 1px solid #00ff7f; color: #00ff7f;")
        QTimer.singleShot(1500, lambda: self._reset_save_btn())

        new_winrar_path = self.winrar_path_edit.text()
        if os.path.exists(new_winrar_path): WINRAR_PATH = new_winrar_path
        
        new_download_path = self.download_path_edit.text()
        global SYNC_PATH; SYNC_PATH = self.sync_path_edit.text()
        
        DEFAULT_DOWNLOAD_PATH = new_download_path 
        STEAM_PATH = self.steam_path_edit.text()
        STEAM_USER_ID = self.steam_id_edit.text()
        SHOW_SPEED_IN_MBPS = self.speed_toggle.isChecked()
        SHOW_SIZE_IN_GB = self.size_toggle.isChecked()
        ENABLE_NOTIFICATIONS = self.notif_toggle.isChecked()
        ENABLE_WEBHOOK = self.wh_toggle.isChecked()
        WEBHOOK_URL = self.wh_input.text()
        OFME_USERNAME = self.user_input.text()
        OFME_PASSWORD = self.pass_input.text()
        
        global WEB_MODE
        old_web_mode = WEB_MODE
        WEB_MODE = self.web_mode_toggle.isChecked()
        
        if WEB_MODE and not old_web_mode:
            ensure_web_template()
            
        print("Settings saved successfully.")
        save_settings_to_file()
        
    def _reset_save_btn(self):
        self.save_button.setText("Save Settings")
        self.save_button.setStyleSheet("")

# --- DATA AND ASSET MANAGEMENT ---
class DataManager(QObject):
    def __init__(self):
        super().__init__()
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
                with open(DATA_FILE, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        return {}
                    return {k.upper(): v for k, v in json.loads(content).items()}
            except json.JSONDecodeError as e:
                print(f"CRITICAL ERROR: Data.json is corrupted! Line {e.lineno}: {e.msg}")
                return {}
            except IOError as e:
                print(f"ERROR: Could not read Data.json: {e}")
        return {}
    
    def save_downloaded_game(self, game_name, version, location):
        data = self._load_local_data()
        name_key = game_name.upper()
        
        if name_key not in data:
            data[name_key] = {}
            
        data[name_key].update({
            'version': version,
            'location': location
        })
        
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Saved game data for {name_key} at location {location}")

    def update_save_path(self, game_name, path):
        data = self._load_local_data()
        name_key = game_name.upper()
        if name_key not in data: data[name_key] = {}
        data[name_key]['save_path'] = path
        with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
        self.local_data = data

    def _determine_game_statuses(self):
        processed_games = []
        for game_key, db_info in self.games_db.items():
            game_data = db_info.copy()
            game_data['newest_version'] = db_info.get('version', '0.0')
            if game_key in self.local_data:
                game_data.update(self.local_data[game_key]) 
                local_version = self.local_data[game_key].get('version', '0.0')
                game_data['status'] = GameStatus.UP_TO_DATE if local_version == game_data['newest_version'] else GameStatus.UPDATE_AVAILABLE
            else:
                game_data['status'] = GameStatus.NOT_DOWNLOADED
                game_data['version'] = "N/A"
            processed_games.append(game_data)
        return processed_games

    def save_downloaded_game(self, game_name, version, location):
        data = self._load_local_data()
        name_key = game_name.upper()
        if name_key not in data:
            data[name_key] = {}
            
        data[name_key].update({
            'version': version,
            'location': location
        })
        
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Saved game data for {name_key}")
        
    def save_steam_url(self, game_name, steam_url):
        data = self._load_local_data()
        if game_name.upper() in data:
            data[game_name.upper()]['steam_url'] = steam_url
            try:
                with open(DATA_FILE, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"Saved Steam URL for {game_name}: {steam_url}")
                self.local_data = data 
            except Exception as e:
                print(f"Error saving Steam URL: {e}")

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
            safe_name = re.sub(r'[\\/*?:"<>|]', "", self.game_data.get('name', 'Game'))
            safe_name = safe_name.replace(" ", "_")
            
            target_name = ""
            if url == fix_url:
                target_name = f"{safe_name}_Fix.rar"
            else:
                if len(main_urls) == 1 and not fix_url:
                     target_name = f"{safe_name}.rar"
                else:
                     target_name = f"{safe_name}_Part{i+1}.rar"

            direct_url, cookies = url, None            
            if "gofile.io" in url:
                direct_url, cookies = self._resolve_gofile_link(url, progress_str)
                if not direct_url:
                    self.finished.emit(False, "Failed to resolve GoFile link.", {}); return
            elif "buzzheavier.com" in url:
                direct_url, cookies = self._resolve_buzzheavier_link(url, progress_str)
                if not direct_url:
                    self.finished.emit(False, "Failed to resolve BuzzHeavier link.", {}); return
                    
            downloaded_path = self._download_file(direct_url, temp_download_folder, cookies, target_name)
            if not downloaded_path:
                self.finished.emit(False, "Download failed (File not found or access denied).", {}); return
            self.status_update.emit("Finalizing file...")
            time.sleep(1) 
            try:
                if not os.path.exists(downloaded_path) or os.path.getsize(downloaded_path) < 10 * 1024: # 10KB
                    self.status_update.emit("Download invalid (too small/missing).")
                    if os.path.exists(downloaded_path):
                        os.remove(downloaded_path) 
                    self.finished.emit(False, "Download failed: File invalid or blocked by host.", {}); return
            except OSError: pass

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

            if response.status_code >= 400: return None, None

            if 'hx-redirect' in response.headers:
                final_url = response.headers['hx-redirect']
                if "buzzheavier.com" in final_url: return None, None
                return final_url, session.cookies.get_dict()
            else: return None, None
        except requests.exceptions.RequestException as e:
            print(f"BuzzHeavier resolution error: {e}")
            return None, None

    def _resolve_gofile_link(self, gofile_url, progress_str=""):
        self.status_update.emit(f"Resolving GoFile Link... {progress_str}")
        driver = None
        try:
            options = Options()
            options.add_argument("--headless=new") 
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
            options.binary_location = BRAVE_PATH 
            try:
                driver = webdriver.Chrome(options=options)
            except Exception:
                options.binary_location = ""
                driver = webdriver.Chrome(options=options)

            driver.get(gofile_url)
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "item_open"))
                )
            except TimeoutException:
                print("GoFile: List didn't load.")
                return None, None

            file_links = driver.find_elements(By.CLASS_NAME, "item_open")
            target_link = None
            target_name = self.game_data.get('name', '').lower()
            for link in file_links:
                text = link.text.lower()
                if ".rar" in text:
                    if target_name in text:
                        target_link = link
                        break
                    if target_link is None:
                        target_link = link

            if not target_link:
                print("GoFile: No suitable .rar file found in the list.")
                return None, None
            try:
                row_ancestor = target_link.find_element(By.XPATH, "./ancestor::div[.//button[contains(@class, 'item_download')]][1]")
                download_btn = row_ancestor.find_element(By.CSS_SELECTOR, ".item_download")
            except NoSuchElementException:
                print("GoFile: Structure fallback used.")
                download_btn = driver.find_element(By.CSS_SELECTOR, ".item_download")
            driver.execute_script("arguments[0].click();", download_btn)
            start_time = time.time()
            direct_url = None

            while time.time() - start_time < 5:
                logs = driver.get_log("performance")
                for entry in logs:
                    try:
                        message = json.loads(entry["message"])["message"]
                        if message["method"] == "Network.requestWillBeSent":
                            request_url = message["params"]["request"]["url"]
                            if ".rar" in request_url and "gofile.io" in request_url and "/d/" not in request_url:
                                direct_url = request_url
                                break
                    except: continue
                if direct_url: break

            cookies = driver.get_cookies()
            account_token = None
            for cookie in cookies:
                if cookie['name'] == 'accountToken':
                    account_token = cookie['value']
                    break
            if direct_url:
                print(f"GoFile Resolved via Network Tab: {direct_url}")
                return direct_url, account_token
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                return driver.current_url, account_token

            return None, None

        except Exception as e:
            print(f"GoFile Resolution Error: {e}")
            return None, None
        finally:
            if driver:
                driver.quit()

    def _download_file(self, url, dest_folder, cookies=None, forced_name=""):
        headers = {'User-Agent': 'Mozilla/5.0'}
        req_cookies = None
        if cookies:
            if isinstance(cookies, dict): req_cookies = cookies
            elif isinstance(cookies, str): headers['Cookie'] = f'accountToken={cookies}'
        
        if "buzzheavier" in url: headers['Referer'] = "https://buzzheavier.com/"

        try:
            with requests.get(url, stream=True, headers=headers, cookies=req_cookies, timeout=(10, 30)) as r:
                r.raise_for_status()
                content_type = r.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type: return None
                local_filename = ""
                if "Content-Disposition" in r.headers:
                    disposition = r.headers['content-disposition']
                    filenames = re.findall('filename="?([^"]+)"?', disposition)
                    if filenames: local_filename = filenames[0]
                if not local_filename and 'filename=' in r.url:
                    try:
                        parsed_url = urllib.parse.urlparse(r.url)
                        params = urllib.parse.parse_qs(parsed_url.query)
                        if 'filename' in params: local_filename = params['filename'][0]
                    except: pass
                if not local_filename: local_filename = r.url.split('/')[-1].split('?')[0]
                has_ext = "." in local_filename and len(local_filename.split('.')[-1]) < 5
                
                if not has_ext or (len(local_filename) > 30 and not " " in local_filename):
                    if forced_name:
                        print(f"Renaming bad filename '{local_filename}' to '{forced_name}'")
                        local_filename = forced_name
                    elif not has_ext:
                        local_filename += ".rar"
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

    def _winrar_extraction(self, rar_path, LazyExtraction):
        dest_folder = LazyExtraction
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
        self.selected_exe = ""
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20, 10, 20, 20); main_layout.setSpacing(15)
        
        header_layout = QHBoxLayout()
        back_button = QPushButton("<< Back to Library"); back_button.setObjectName("TopBackBtn")
        back_button.setFont(self.pixel_font) 
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
        
        right_layout.addWidget(info_panel)
        
        desc_title = QLabel("Description:"); desc_title.setFont(self.pixel_font)
        desc_title.setStyleSheet("color:#fff; font-weight:bold; margin-top:10px;")
        right_layout.addWidget(desc_title)
        
        right_layout.addWidget(self.description_label, 1)
        right_layout.addStretch()

        self.bypass_container = QWidget()
        bypass_layout = QHBoxLayout(self.bypass_container)
        bypass_layout.setContentsMargins(0, 5, 0, 5)
        self.bypass_toggle = PyToggle()
        self.bypass_toggle.stateChanged.connect(self.on_bypass_toggled)
        bypass_lbl = QLabel("Version Check Bypass")
        bypass_lbl.setFont(self.pixel_font)
        bypass_lbl.setStyleSheet("color: #aaa; margin-right: 10px;")
        bypass_layout.addStretch()
        bypass_layout.addWidget(bypass_lbl)
        bypass_layout.addWidget(self.bypass_toggle)
        right_layout.addWidget(self.bypass_container)
        buttons_container = QWidget()
        buttons_layout = QVBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.setSpacing(10)
        bottom_buttons_layout = QHBoxLayout()
        bottom_buttons_layout.setSpacing(10)
        buttons_layout.addLayout(top_buttons_layout)
        buttons_layout.addLayout(bottom_buttons_layout)
        
        self.launch_button = QPushButton("LAUNCH GAME")
        self.launch_button.setFont(self.pixel_font)
        self.launch_button.setFixedHeight(32)
        self.launch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_button.clicked.connect(self.launch_steam_game)
        self.launch_button.hide() 
        self.steam_button = QPushButton("ADD TO STEAM")
        self.steam_button.setObjectName("SteamBtn")
        self.steam_button.setFont(self.pixel_font)
        self.steam_button.setFixedHeight(32)
        self.steam_button.clicked.connect(self.handle_steam_click)
        top_buttons_layout.addWidget(self.launch_button, 1) 
        top_buttons_layout.addWidget(self.steam_button, 1)
        
        self.locate_path_button = QPushButton("LOCATE GAME EXE")
        self.locate_path_button.hide() 
        
        self.locate_save_button = QPushButton("LINK SAVE FOLDER")
        self.locate_save_button.setFont(self.pixel_font); self.locate_save_button.setFixedHeight(32)
        self.locate_save_button.clicked.connect(self.manually_select_save_folder)
        self.sync_button = QPushButton("SYNC PROGRESS")
        self.sync_button.setFont(self.pixel_font); self.sync_button.setFixedHeight(32)
        self.sync_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sync_button.customContextMenuRequested.connect(self.show_sync_menu)
        self.sync_button.setToolTip("Right-click for Force Upload/Download options")
        self.sync_button.clicked.connect(lambda: self.handle_sync_click(mode="sync")); self.sync_button.hide()
        
        bottom_buttons_layout.addWidget(self.locate_path_button, 1)
        bottom_buttons_layout.addWidget(self.locate_save_button, 1)
        bottom_buttons_layout.addWidget(self.sync_button, 1)
        right_layout.addWidget(buttons_container)
        self.location_bar = QLineEdit()
        self.location_bar.setFont(self.pixel_font)
        right_layout.addWidget(self.location_bar)
        
        self.fix_prompt_widget = QWidget(); fix_layout = QHBoxLayout(self.fix_prompt_widget); fix_layout.setContentsMargins(0,0,0,0)
        self.fix_label = self._create_info_label(text="Fix is available. Apply it?", color="#ffd700")
        yes_button = QPushButton("Yes"); yes_button.setFont(self.pixel_font)
        no_button = QPushButton("No"); no_button.setFont(self.pixel_font)
        self.change_path_button = QPushButton("Change Path"); self.change_path_button.setFont(self.pixel_font)
        yes_button.clicked.connect(self.on_fix_yes); no_button.clicked.connect(self.on_fix_no); self.change_path_button.clicked.connect(self.select_fix_path)
        fix_layout.addWidget(self.fix_label, 1); fix_layout.addWidget(yes_button); fix_layout.addWidget(no_button); fix_layout.addWidget(self.change_path_button)
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
        
        font_family = self.pixel_font.family()
        large_font = QFont(font_family, 12, QFont.Weight.Bold) 

        self.download_progress = QProgressBar()
        self.download_progress.setFont(self.pixel_font)
        
        self.download_button = QPushButton("DOWNLOAD")
        self.download_button.setFont(large_font) 
        self.download_button.setFixedWidth(200)
        self.download_button.setFixedHeight(30)
        self.download_button.clicked.connect(self.start_or_cancel_download)
        
        action_line.addWidget(self.download_progress, 1); action_line.addWidget(self.download_button)
        bottom_layout.addLayout(status_line); bottom_layout.addLayout(action_line)
        main_layout.addWidget(bottom_controls)

    def get_actual_path(self, path):
            try:
                path = os.path.abspath(path)
                if os.name == 'nt':
                    buf = ctypes.create_unicode_buffer(500)
                    GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
                    GetLongPathNameW(path, buf, 500)
                    path = buf.value
                    if len(path) > 1 and path[1] == ':':
                        path = path[0].upper() + path[1:]
                return path
            except:
                return path

    def handle_steam_click(self):
        global STEAM_USER_ID, STEAM_PATH
        current_text = self.steam_button.text()
        if not STEAM_USER_ID:
            picker = SteamAccountPicker(self)
            if picker.exec():
                STEAM_USER_ID = picker.selected_id
                save_settings_to_file()
                self.steam_button.setText("SELECT GAME EXE")
                self.status_label.setText(f"Steam Account {STEAM_USER_ID} selected.")
            return
        if current_text == "ADD TO STEAM" or current_text == "SELECT GAME EXE":
            game_folder = self.final_game_path if os.path.exists(self.final_game_path) else DEFAULT_DOWNLOAD_PATH
            if not game_folder:
                 game_folder = "C:\\"
            
            exe_path, _ = QFileDialog.getOpenFileName(self, "Select the game executable", game_folder, "Executables (*.exe)")
            if exe_path:
                self.selected_exe = exe_path
                self.steam_button.setText("CONFIRM STEAM SHORTCUT")
                self.steam_button.setStyleSheet("background-color: #00ff7f; color: black; font-weight: bold;")
                self.status_label.setText(f"Target selected: {os.path.basename(exe_path)}")
            return
        if current_text == "CONFIRM STEAM SHORTCUT":
            self.finalize_steam_shortcut()

    def finalize_steam_shortcut(self):
        global STEAM_PATH

        steam_running = any(p.name().lower() == "steam.exe" for p in psutil.process_iter())
        if steam_running:
            res = QMessageBox.warning(self, "Steam is Running", 
                "Steam must be closed to add the game to the library.\n\nClick YES to close Steam automatically.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            if res == QMessageBox.StandardButton.Yes:
                os.system("taskkill /f /im steam.exe")
                timeout = 0
                while any(p.name().lower() == "steam.exe" for p in psutil.process_iter()) and timeout < 10:
                    time.sleep(0.5)
                    timeout += 1
            else:
                return

        try:
            vdf_path = os.path.join(STEAM_PATH, "userdata", STEAM_USER_ID, "config", "shortcuts.vdf")
            if os.path.exists(vdf_path):
                with open(vdf_path, 'rb') as f: data = vdf.binary_load(f)
            else:
                data = {'shortcuts': {}}

            app_name = self.current_game_data['name']
            real_exe_path = self.get_actual_path(self.selected_exe)
            real_dir_path = os.path.dirname(real_exe_path)
            exe_string = f'"{real_exe_path}"'
            start_dir = f'"{real_dir_path}"'

            already_exists = False
            for k, v in data['shortcuts'].items():
                if v.get('AppName') == app_name:
                    already_exists = True
                    break

            if not already_exists:
                index = str(len(data['shortcuts']))
                new_shortcut = {
                    'appid': -1,
                    'AppName': app_name,
                    'exe': exe_string,
                    'StartDir': start_dir,
                    'icon': "", 'ShortcutPath': "", 'LaunchOptions': "",
                    'IsHidden': 0, 'AllowDesktopConfig': 1, 'AllowOverlay': 1, 'OpenVR': 0,
                    'Devkit': 0, 'DevkitGameID': "", 'LastPlayTime': 0, 'tags': {}
                }
                data['shortcuts'][index] = new_shortcut
                with open(vdf_path, 'wb') as f: vdf.binary_dump(data, f)
                print("Written shortcut to VDF.")

            print("Restarting Steam...")
            steam_exe = os.path.join(STEAM_PATH, "steam.exe")
            if os.path.exists(steam_exe):
                subprocess.Popen([steam_exe])

            reply = QMessageBox.question(self, "Sync Steam ID?", 
                f"{app_name} has been added to Steam!\n\n"
                "Do you want to import the Steam Launch URL to this launcher?\n"
                "This requires you to manually create a desktop shortcut in Steam right now.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                self.initiate_shortcut_watch(app_name)
            else:
                self.status_label.setText(f"Added to Steam (No ID Sync).")
                self.set_game_data(self.current_game_data)

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save shortcut: {e}")
            self.set_game_data(self.current_game_data)

    def initiate_shortcut_watch(self, app_name):
        self.download_button.setText("WAITING FOR SHORTCUT...")
        self.download_button.setEnabled(False)
        self.status_label.setText("Waiting for Desktop Shortcut...")
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Action Required")
        msg.setText(f"Steam is restarting...\n\nTo grab the ID for {app_name}:\n\n"
                    "1. Go to your Steam Library.\n"
                    f"2. Right-Click '{app_name}' > Manage > Add desktop shortcut.\n"
                    "3. Wait a moment, and this app will auto-detect it!")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(lambda: self.check_for_shortcut(app_name))
        self.watch_timer.start(1000)
        self.watch_start_time = time.time()

    def check_for_shortcut(self, app_name):
        desktop_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        safe_name = re.sub(r'[\\/*?:"<>|]', "", app_name)
        shortcut_path = os.path.join(desktop_path, f"{safe_name}.url")
        if os.path.exists(shortcut_path):
            self.watch_timer.stop()
            try:
                with open(shortcut_path, 'r') as f:
                    content = f.read()
                match = re.search(r'steam://rungameid/(\d+)', content)
                if match:
                    steam_id = match.group(1)
                    steam_url = f"steam://rungameid/{steam_id}"
                    self.data_manager.save_steam_url(app_name, steam_url)
                    try:
                        os.remove(shortcut_path)
                    except: pass 
                    
                    self.status_label.setText(f"Success! ID: {steam_id}")
                    QMessageBox.information(self, "Integration Complete", f"Successfully grabbed Steam ID!\n\nURL: {steam_url}")
                else:
                    self.status_label.setText("Error: ID not found in shortcut.")
            
            except Exception as e:
                print(f"Error reading shortcut: {e}")
            
            self.set_game_data(self.current_game_data)
            return

        if time.time() - self.watch_start_time > 120:
            self.watch_timer.stop()
            self.download_button.setText("TIMED OUT")
            self.status_label.setText("Shortcut detection timed out.")
            QMessageBox.warning(self, "Timeout", "Could not find the desktop shortcut in time.\nPlease try again.")
            self.set_game_data(self.current_game_data)
            
    def launch_steam_game(self):
        steam_url = self.current_game_data.get('steam_url')
        if steam_url:
            print(f"Launching: {steam_url}")
            QDesktopServices.openUrl(QUrl(steam_url))
            
            if ENABLE_NOTIFICATIONS:
                safe_icon = ICON_PATH if os.path.exists(ICON_PATH) else None
                notification.notify(title="Launching", message=f"Starting {self.current_game_data['name']} via Steam...", app_icon=safe_icon, timeout=3)
        else:
            QMessageBox.warning(self, "Error", "No Steam URL found for this game.")

    def on_bypass_toggled(self, state):
        game_name = self.current_game_data.get('name')
        if not game_name: return
        is_checked = (state != 0)
        if is_checked:
            if game_name not in VERSION_CHECK_BYPASS_LIST:
                VERSION_CHECK_BYPASS_LIST.append(game_name)
                print(f"[{game_name}] added to Version Check bypass.")
        else:
            if game_name in VERSION_CHECK_BYPASS_LIST:
                VERSION_CHECK_BYPASS_LIST.remove(game_name)
                print(f"[{game_name}] removed from Version Check bypass.")
        save_settings_to_file()

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
        self.final_game_path = ""
        self.path_manually_changed = False
        self.downloaded_file_paths = {}
        self.download_progress.setValue(0)
        self.stats_label.setText("")
        self.status_label.setText("")
        self.fix_prompt_widget.setVisible(False) 
        self.selected_exe = ""
        local_ver = game_data.get('version', 'N/A')
        newest_ver = game_data.get('newest_version', 'N/A')
        status = game_data.get('status', GameStatus.NOT_DOWNLOADED)
        self.version_label.setStyleSheet("color: #e0e0e0;")

        if status == GameStatus.UPDATE_AVAILABLE:
            self.version_label.setText(f"{local_ver} > {newest_ver}")
        else:
            self.version_label.setText(newest_ver)

        self.game_name_label.setText(game_data.get('name', 'N/A'))
        self.sources_label.setText(game_data.get('Sources', 'N/A'))
        self.size_label.setText(game_data.get('ApproxSize', 'N/A'))
        self.description_label.setText(game_data.get('Description', 'No description available.'))
        status_color = STATUS_INFO[status]['color']
        self.game_name_label.setStyleSheet(f"color: {status_color};")
        
        thumbnail_path = self.asset_manager.get_asset(game_data.get('Thumbnail'))
        self.thumbnail_label.setStyleSheet(f"border: 2px solid {status_color}; background-color: #000;")

        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            scaled_pixmap = pixmap.scaled(self.thumbnail_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled_pixmap)
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.setText("No Image")

        game_key = game_data.get('name', '').upper()
        local_info = self.data_manager.local_data.get(game_key, {})
        
        if status == GameStatus.NOT_DOWNLOADED:
            self.sync_button.hide()
            self.locate_save_button.hide()
        else:
            self.locate_save_button.show()
            if local_info.get('save_path'):
                self.sync_button.show()
                self.locate_save_button.setText("CHANGE SAVE FOLDER")
            else:
                self.sync_button.hide()
                self.locate_save_button.setText("LINK SAVE FOLDER")

        game_name = game_data.get('name')
        if game_name in VERSION_CHECK_BYPASS_LIST:
            self.bypass_toggle.set_state_immediate(True)
        else:
            self.bypass_toggle.set_state_immediate(False)

        self.download_button.setEnabled(True)
        self.steam_button.setText("ADD TO STEAM")
        self.launch_button.hide()
        
        if status == GameStatus.NOT_DOWNLOADED:
            self.download_button.setText("DOWNLOAD")
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setPlaceholderText("Select base download folder...")
            self.location_bar.setVisible(True)
            self.bypass_container.setVisible(True)
            self.steam_button.setVisible(False)
        else:
            game_name_key = game_data.get('name', '').upper()
            self.final_game_path = self.data_manager.local_data.get(game_name_key, {}).get('location', '')
            self.location_bar.setText(DEFAULT_DOWNLOAD_PATH)
            self.location_bar.setVisible(True)
            self.bypass_container.setVisible(True)
            self.steam_button.setVisible(True)
            
            if status == GameStatus.UPDATE_AVAILABLE: 
                self.download_button.setText("UPDATE")
            else: 
                self.download_button.setText("RE-DOWNLOAD")

            steam_url = game_data.get('steam_url')
            if steam_url:
                self.steam_button.setText("RE-ADD TO STEAM")
                self.launch_button.setVisible(True)
                self.launch_button.setText("LAUNCH (STEAM)")
                if status == GameStatus.UP_TO_DATE:
                    self.launch_button.setStyleSheet("background-color: #00ff7f; color: black; font-weight: bold; border-radius: 15px;")
                elif status == GameStatus.UPDATE_AVAILABLE:
                    self.launch_button.setStyleSheet("background-color: #ffd700; color: black; font-weight: bold; border-radius: 15px;")
                else:
                    self.launch_button.setStyleSheet("border-radius: 15px; border: 1px solid #444;")

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
            self.download_progress.setValue(100)
            self.final_game_path = detected_path
            
            new_version_to_save = self.current_game_data.get('newest_version')
            if not new_version_to_save or new_version_to_save == "N/A":
                new_version_to_save = self.current_game_data.get('version')
                
            self.data_manager.save_downloaded_game(
                self.current_game_data['name'], 
                new_version_to_save, 
                self.final_game_path
            )
            self.current_game_data['version'] = new_version_to_save
            self.refresh_library.emit()
            if self.downloaded_file_paths.get('fix'):
                self.fix_prompt_widget.setVisible(True)
                if hasattr(self, 'location_bar'): self.location_bar.setVisible(False)
                if hasattr(self, 'bypass_container'): self.bypass_container.setVisible(False)
                
                self.fix_label.setText(f"Apply fix to: {os.path.basename(self.final_game_path)}?")
                self.download_button.setText("ACTION REQUIRED")
                self.download_button.setEnabled(False)
                
                if ENABLE_NOTIFICATIONS:
                    try: 
                        safe_icon = ICON_PATH if os.path.exists(ICON_PATH) else None
                        notification.notify(title="Fix Available", message="Game updated. Please apply the fix.", app_icon=safe_icon, timeout=5)
                    except Exception: pass
            else: 
                self.installer.cleanup_files()
        else: 
            self.installer.cleanup_files()
            
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
                try: 
                    safe_icon = ICON_PATH if os.path.exists(ICON_PATH) else None
                    notification.notify(title="Download Complete", message=f"{self.current_game_data.get('name')} ready!", app_icon=safe_icon, timeout=5)
                except Exception: pass
        if self.path_manually_changed:
            self.data_manager.save_downloaded_game(self.current_game_data['name'], self.current_game_data['version'], self.final_game_path)
            self.refresh_library.emit()
        self.download_button.setText("INSTALLED"); self.download_button.setEnabled(False)
        
    def update_progress(self, value, stats_text): self.download_progress.setValue(value); self.stats_label.setText(stats_text)

    def manually_select_save_folder(self):
        game_name = self.current_game_data.get('name')
        start_dir = os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, f"Select the folder where {game_name} stores SAVES/PROGRESS", start_dir)
        
        if folder:
            self.data_manager.update_save_path(game_name, folder)
            QMessageBox.information(self, "Saves Linked", f"Progress for {game_name} is now ready to sync!")
            self.set_game_data(self.current_game_data)

    def show_sync_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2d2d2d; color: #e0e0e0; border: 1px solid #444; } QMenu::item:selected { background-color: #00ff7f; color: #000; }")
        
        action_sync = menu.addAction("🔄 Standard Sync (Merge)")
        action_push = menu.addAction("⬆️ Force Upload (Local -> Cloud)")
        action_pull = menu.addAction("⬇️ Force Download (Cloud -> Local)")
        
        action = menu.exec(self.sync_button.mapToGlobal(pos))
        
        if action == action_sync: self.handle_sync_click(mode="sync")
        elif action == action_push: self.handle_sync_click(mode="push")
        elif action == action_pull: self.handle_sync_click(mode="pull")

    def handle_sync_click(self, mode="sync"):
        if isinstance(mode, bool): mode = "sync"
        global SYNC_PATH
        game_name = self.current_game_data.get('name')
        game_key = game_name.upper()
        
        if not SYNC_PATH or not os.path.exists(SYNC_PATH):
            QMessageBox.warning(self, "Cloud Not Set", "Please set your OneDrive/Cloud folder in Settings first.")
            return

        local_info = self.data_manager.local_data.get(game_key, {})
        save_path = local_info.get('save_path')

        if not save_path or not os.path.exists(save_path):
            QMessageBox.warning(self, "No Save Folder", "Please click 'LINK SAVE FOLDER' first so I know what to sync!")
            return

        safe_game_name = re.sub(r'[\\/*?:"<>|]', "", game_name).strip()
        target_cloud_dir = os.path.join(SYNC_PATH, "ZuhuOFME_Saves", safe_game_name)

        self.sync_button.setEnabled(False)
        self.sync_button.setText("SYNCING..." if mode == "sync" else mode.upper() + "ING...")
        
        self.sync_thread_obj = SyncWorker(save_path, target_cloud_dir, mode=mode)
        self.sync_thread_obj.finished.connect(self.on_sync_finished)
        self.sync_thread_obj.start()

    def on_sync_finished(self, success, message):
        self.sync_button.setEnabled(True)
        self.sync_button.setText("SYNC PROGRESS")
        if success:
            QMessageBox.information(self, "Sync Complete", "Your saves are now synced with the cloud!")
        else:
            QMessageBox.warning(self, "Sync Failed", f"Error: {message}")

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
            self.pixel_font = QFont("Segoe UI", 11)
            if os.path.exists(os.path.join(DATA_FOLDER, 'cache', 'pixelmix.ttf')):
                 fid = QFontDatabase.addApplicationFont(os.path.join(DATA_FOLDER, 'cache', 'pixelmix.ttf'))
                 if fid != -1: self.pixel_font = QFont(QFontDatabase.applicationFontFamilies(fid)[0], 11)
                 
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
        
        self.console_stream._text_written.disconnect(self.console_buffer.append)
        self.console_stream._text_written.connect(self.settings_page.append_stream_output)
        self.settings_page.append_stream_output("".join(self.console_buffer))
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


class OFMEWebServer:
    def __init__(self, data_manager, asset_manager, console_stream=None):
        template_dir = os.path.join(DATA_FOLDER, 'Templates')
        self.app = Flask(__name__, 
                        template_folder=template_dir,
                        static_folder=os.path.join(DATA_FOLDER, 'cache'),
                        static_url_path='/cache')
        
        self.socketio = SocketIO(self.app)
        self.data_manager = data_manager
        self.asset_manager = asset_manager
        self.client_count = 0
        self.temp_selected_exe = None
        self.last_finalizing_game = None
        self.detection_mode = False
        
        if console_stream:
            self.log_buffer = list(console_stream.history) 
            console_stream._text_written.connect(self.handle_new_log)
        else:
            self.log_buffer = []
            
        self.setup_routes()

    def handle_new_log(self, text):
        """Pushes logs directly to the web UI console."""
        if not text.endswith('\n'):
            text += '\n'
        self.log_buffer.append(text)
        self.socketio.emit('console_log', {'message': text})

    def setup_routes(self):
        @self.app.route('/')
        def index():
            initial_logs = "".join(self.log_buffer)
            global SYNC_PATH
            return render_template('index.html', 
                                 games=self.data_manager.games, 
                                 version=CURRENT_VERSION,
                                 winrar=WINRAR_PATH,
                                 default_path=DEFAULT_DOWNLOAD_PATH,
                                 steam_path=STEAM_PATH,
                                 steam_id=STEAM_USER_ID,
                                 sync_path=SYNC_PATH,
                                 web_mode=WEB_MODE,
                                 mbps=SHOW_SPEED_IN_MBPS,
                                 size_gb=SHOW_SIZE_IN_GB,
                                 notifs=ENABLE_NOTIFICATIONS,
                                 webhook_on=ENABLE_WEBHOOK,
                                 webhook_url=WEBHOOK_URL,
                                 initial_logs=initial_logs)

        @self.socketio.on('save_settings')
        def handle_save_settings(data):
            global WINRAR_PATH, DEFAULT_DOWNLOAD_PATH, STEAM_PATH, STEAM_USER_ID
            global SHOW_SPEED_IN_MBPS, SHOW_SIZE_IN_GB, ENABLE_NOTIFICATIONS, ENABLE_WEBHOOK, WEBHOOK_URL
            global WEB_MODE, SYNC_PATH
            
            WINRAR_PATH = data.get('winrar')
            DEFAULT_DOWNLOAD_PATH = data.get('path')
            STEAM_PATH = data.get('steam_path')
            STEAM_USER_ID = data.get('steam_id')
            SYNC_PATH = data.get('sync_path')
            SHOW_SPEED_IN_MBPS = data.get('mbps')
            SHOW_SIZE_IN_GB = data.get('size_gb')
            ENABLE_NOTIFICATIONS = data.get('notifs')
            ENABLE_WEBHOOK = data.get('webhook_on')
            WEBHOOK_URL = data.get('webhook_url')
            WEB_MODE = data.get('web_mode')
            
            save_settings_to_file()
            self.handle_new_log("Web UI: Settings successfully saved.\n")
            self.socketio.emit('settings_saved', {'status': 'success'})

        @self.socketio.on('pick_sync_path')
        def handle_pick_sync():
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="Select Cloud Sync Folder")
            root.destroy()
            if path:
                self.socketio.emit('sync_path_picked', {'path': path})

        @self.socketio.on('pick_game_save_path')
        def handle_pick_save(data):
            game_name = data.get('game_name')
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            path = filedialog.askdirectory(title=f"Select Save Folder for {game_name}")
            root.destroy()
            if path:
                self.data_manager.update_save_path(game_name, path)
                self.handle_new_log(f"Web UI: Linked save path for {game_name}\n")
                self.socketio.emit('save_path_linked', {'game_name': game_name, 'path': path})

        @self.socketio.on('trigger_sync')
        def handle_sync(data):
            game_name = data.get('name')
            mode = data.get('mode', 'sync')
            
            def run_sync_thread():
                import datetime
                game_key = game_name.upper()
                local_info = self.data_manager.local_data.get(game_key, {})
                save_path = local_info.get('save_path')

                if not SYNC_PATH or not save_path:
                    self.handle_new_log("Error: Cloud Path or Game Save Path not set!\n")
                    self.socketio.emit('sync_finished', {'status': 'error'})
                    return

                # Create the cloud folder
                safe_game_name = re.sub(r'[\\/*?:"<>|]', "", game_name).strip()
                target_cloud_dir = os.path.join(SYNC_PATH, "ZuhuOFME_Saves", safe_game_name)
                os.makedirs(target_cloud_dir, exist_ok=True)
                
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                # Silencing Robocopy table
                flags = ['/E', '/FFT', '/DST', '/R:1', '/W:1', '/XO', '/NJH', '/NJS', '/NDL', '/NFL', '/NC', '/NS', '/NP']

                # --- CLEAN LOG START ---
                start_dt = datetime.datetime.now().strftime("%d %B %Y %H:%M:%S")
                self.handle_new_log(f"\n  Started : {start_dt}")
                
                if mode == "push":
                    self.handle_new_log(f"   Source = {save_path}")
                    self.handle_new_log(f"     Dest : {target_cloud_dir}")
                    subprocess.run(['robocopy', save_path, target_cloud_dir] + flags, startupinfo=si, stdout=subprocess.DEVNULL)
                elif mode == "pull":
                    self.handle_new_log(f"   Source = {target_cloud_dir}")
                    self.handle_new_log(f"     Dest : {save_path}")
                    subprocess.run(['robocopy', target_cloud_dir, save_path] + flags, startupinfo=si, stdout=subprocess.DEVNULL)
                else: # Bidirectional Sync
                    self.handle_new_log(f"   Source = {target_cloud_dir} <-> {save_path}")
                    self.handle_new_log(f"     Dest : Bidirectional Sync")
                    subprocess.run(['robocopy', target_cloud_dir, save_path] + flags, startupinfo=si, stdout=subprocess.DEVNULL)
                    subprocess.run(['robocopy', save_path, target_cloud_dir] + flags, startupinfo=si, stdout=subprocess.DEVNULL)

                # --- CLEAN LOG END ---
                end_dt = datetime.datetime.now().strftime("%d %B %Y %H:%M:%S")
                self.handle_new_log(f"   Ended : {end_dt}")
                self.handle_new_log(f"Files synced successfully for {game_name}.\n")
                self.socketio.emit('sync_finished', {'status': 'success'})

            threading.Thread(target=run_sync_thread, daemon=True).start()

        @self.socketio.on('connect')
        def handle_connect():
            self.client_count += 1
            print(f"Web UI: Connected. Active tabs: {self.client_count}")

        @self.socketio.on('disconnect')
        def handle_disconnect():
            self.client_count -= 1
            print(f"Web UI: Disconnected. Active tabs: {self.client_count}")
            if self.client_count <= 0:
                timeout = 180.0 if self.detection_mode else 15.0
                if self.detection_mode:
                    self.handle_new_log(f"Detection mode active: Postponing shutdown for {timeout} seconds...\n")
                threading.Timer(timeout, self.shutdown_check).start()

        @self.socketio.on('start_download')
        def handle_download(data):
            game_name = data.get('name')
            custom_path = data.get('path')
            self.handle_new_log(f"Web UI: Requesting download for {game_name}...\n")
            # Logic for trigger_download_from_main_app could be placed here or signaled
            
        @self.socketio.on('launch_game')
        def handle_launch(data):
            steam_url = data.get('url')
            if steam_url:
                self.handle_new_log(f"Web UI: Launching {steam_url}\n")
                webbrowser.open(steam_url)
                
        @self.socketio.on('request_steam_accounts')
        def handle_steam_request():
            def run_scraper():
                userdata_path = os.path.join(STEAM_PATH, "userdata")
                if not os.path.exists(userdata_path): return
                headers = {'User-Agent': 'Mozilla/5.0'}
                for entry in os.listdir(userdata_path):
                    if entry.isdigit():
                        try:
                            url = f"https://steamid.xyz/{entry}"
                            resp = requests.get(url, headers=headers, timeout=5)
                            soup = BeautifulSoup(resp.content, 'html.parser')
                            user_tag = soup.find('h1', class_='value')
                            username = user_tag.text.strip() if user_tag else f"User {entry}"
                            ava_tag = soup.find('img', class_='avatar')
                            avatar_url = ava_tag['src'] if ava_tag and 'src' in ava_tag.attrs else ""
                            self.socketio.emit('steam_account_found', {'id': entry, 'name': username, 'avatar': avatar_url})
                        except:
                            self.socketio.emit('steam_account_found', {'id': entry, 'name': "N/A", 'avatar': ""})
                self.socketio.emit('steam_scan_finished')
            threading.Thread(target=run_scraper, daemon=True).start()

        @self.socketio.on('set_steam_account')
        def handle_set_steam(data):
            global STEAM_USER_ID
            STEAM_USER_ID = data.get('id')
            save_settings_to_file()
            self.handle_new_log(f"Web UI: Steam ID set to {STEAM_USER_ID}\n")

        @self.socketio.on('pick_steam_exe')
        def handle_pick_exe(data):
            game_name = data.get('game_name')
            game_key = game_name.upper()
            game_folder = self.data_manager.local_data.get(game_key, {}).get('location', DEFAULT_DOWNLOAD_PATH)
            
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            exe_path = filedialog.askopenfilename(title="Select Game EXE", initialdir=game_folder, filetypes=[("Executable", "*.exe")])
            root.destroy()
            if exe_path:
                self.temp_selected_exe = exe_path 
                self.socketio.emit('steam_exe_picked', {'filename': os.path.basename(exe_path)})

        @self.socketio.on('finalize_steam')
        def handle_finalize(data):
            game_name = data.get('game_name')
            self.last_finalizing_game = game_name 
            steam_running = any(p.name().lower() == "steam.exe" for p in psutil.process_iter())
            if steam_running:
                self.socketio.emit('steam_require_close')
            else:
                self.process_vdf_write(game_name)

        @self.socketio.on('close_steam_and_continue')
        def handle_close_and_cont():
            os.system("taskkill /f /im steam.exe")
            self.handle_new_log("Web UI: steam.exe has been successfully terminated.\n")
            time.sleep(2)
            if self.last_finalizing_game:
                self.process_vdf_write(self.last_finalizing_game)

        @self.socketio.on('start_shortcut_watch')
        def handle_watch(data):
            game_name = data.get('name')
            self.detection_mode = True 
            watch_start_time = time.time() 
            def watch():
                desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
                safe_name = re.sub(r'[\\/*?:"<>|]', "", game_name)
                path = os.path.join(desktop, f"{safe_name}.url")
                self.handle_new_log(f"Watch started for: {safe_name} on Desktop\n")
                start_loop = time.time()
                while time.time() - start_loop < 120:
                    if os.path.exists(path):
                        if os.path.getmtime(path) >= watch_start_time:
                            time.sleep(1.5)
                            try:
                                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                m = re.search(r'steam://rungameid/(\d+)', content)
                                if m:
                                    steam_url = f"steam://rungameid/{m.group(1)}"
                                    self.data_manager.save_steam_url(game_name, steam_url)
                                    self.handle_new_log(f"Web UI: Saved Steam URL for {game_name}: {steam_url}\n")
                                    try: os.remove(path)
                                    except: pass
                                    self.socketio.emit('steam_integration_success', {'url': steam_url})
                                    self.detection_mode = False 
                                    return
                            except Exception as e:
                                self.handle_new_log(f"Error reading shortcut: {e}\n")
                    time.sleep(1)
                self.detection_mode = False 
                self.socketio.emit('steam_error', {'message': "Timeout: No new shortcut detected."})
            threading.Thread(target=watch, daemon=True).start()

    def process_vdf_write(self, game_name):
        try:
            vdf_path = os.path.join(STEAM_PATH, "userdata", STEAM_USER_ID, "config", "shortcuts.vdf")
            if os.path.exists(vdf_path):
                with open(vdf_path, 'rb') as f: data = vdf.binary_load(f)
            else:
                data = {'shortcuts': {}}
            
            exe_path = self.temp_selected_exe
            real_exe = os.path.abspath(exe_path)
            real_dir = os.path.dirname(real_exe)
            exists = any(v.get('AppName') == game_name for k, v in data['shortcuts'].items())
            if not exists:
                idx = str(len(data['shortcuts']))
                data['shortcuts'][idx] = {
                    'AppName': game_name, 'exe': f'"{real_exe}"', 'StartDir': f'"{real_dir}"',
                    'icon': "", 'ShortcutPath': "", 'LaunchOptions': "", 'IsHidden': 0, 
                    'AllowDesktopConfig': 1, 'AllowOverlay': 1, 'OpenVR': 0, 'Devkit': 0, 
                    'DevkitGameID': "", 'LastPlayTime': 0, 'tags': {}
                }
                with open(vdf_path, 'wb') as f: vdf.binary_dump(data, f)
                self.handle_new_log(f"Web UI: {game_name} written to Steam VDF.\n")
            
            steam_exe = os.path.join(STEAM_PATH, "steam.exe")
            if os.path.exists(steam_exe):
                subprocess.Popen([steam_exe])
            self.socketio.emit('steam_sync_prompt', {'name': game_name})
        except Exception as e:
            self.handle_new_log(f"VDF Error: {str(e)}\n")
            self.socketio.emit('steam_error', {'message': f"VDF Error: {str(e)}"})                    

    def shutdown_check(self):
        if self.client_count <= 0 and not self.detection_mode:
            print("No active web sessions. Closing ZuhuOFME...")
            os._exit(0)

    def run(self):
        print(f"Starting Web Mode on http://127.0.0.1:5000")
        webbrowser.open("http://127.0.0.1:5000")
        self.socketio.run(self.app, port=5000, debug=False, use_reloader=False)
        
if __name__ == '__main__':
    myappid = 'OFME-DWNLDR'
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass
    load_settings()

    console_stream = ConsoleStream(sys.__stdout__)
    sys.stdout = console_stream
    sys.stderr = console_stream
    
    if WEB_MODE:
        ensure_web_template() 
        dm = DataManager()
        am = AssetManager()
        server = OFMEWebServer(dm, am, console_stream) 
        server.run()
    else:
        app = QApplication(sys.argv)
        if os.path.exists(ICON_PATH): 
            app.setWindowIcon(QIcon(ICON_PATH))
        main_window = GameLauncher()
        main_window.show()
        sys.exit(app.exec())