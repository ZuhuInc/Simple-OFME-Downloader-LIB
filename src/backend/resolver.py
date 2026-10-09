"""
Fanta OFME Downloader - Browser Detection & Dynamic Link Resolvers
Resolves complex hosters (GoFile, BuzzHeavier, PixelDrain, etc.) to direct downloadable stream URLs
using the proven browser scraper driver architecture with Brave priority.
"""

import os
import re
import json
import time
import shutil
import hashlib
import tempfile
import requests
from typing import Dict, Optional, Tuple, Any, Callable

try:
    import winreg
except ImportError:
    winreg = None

# --- BROWSER DETECTION ---

def normalize_browser_name(raw_name: str) -> str:
    raw = raw_name.lower()
    if "brave" in raw:
        return "Brave"
    if "opera gx" in raw or "operagx" in raw:
        return "Opera GX"
    if "chrome" in raw and "google" in raw:
        return "Google Chrome"
    if "firefox" in raw:
        return "Firefox"
    if "opera" in raw and "gx" not in raw:
        return "Opera"
    if "vivaldi" in raw:
        return "Vivaldi"
    if "edge" in raw:
        return "Microsoft Edge"
    return raw_name


def get_installed_browsers() -> Dict[str, str]:
    found_browsers = {}
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")

    potential_paths = {
        "Brave": [
            os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(prog_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
        ],
        "Opera GX": [
            os.path.join(local_appdata, "Programs", "Opera GX", "launcher.exe"),
            os.path.join(local_appdata, "Programs", "Opera GX", "opera.exe")
        ],
        "Google Chrome": [
            os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe")
        ],
        "Firefox": [
            os.path.join(prog_files, "Mozilla Firefox", "firefox.exe"),
            os.path.join(local_appdata, "Mozilla Firefox", "firefox.exe")
        ],
        "Opera": [
            os.path.join(local_appdata, "Programs", "Opera", "launcher.exe"),
            os.path.join(prog_files, "Opera", "launcher.exe")
        ],
        "Vivaldi": [
            os.path.join(local_appdata, "Vivaldi", "Application", "vivaldi.exe"),
            os.path.join(prog_files, "Vivaldi", "Application", "vivaldi.exe")
        ],
        "Microsoft Edge": [
            os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe")
        ]
    }

    for name, paths in potential_paths.items():
        for path in paths:
            if os.path.exists(path):
                found_browsers[name] = path
                break

    if winreg:
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
                            subkey_name = winreg.EnumKey(key, i)
                            i += 1
                            if "iexplore" in subkey_name.lower():
                                continue
                            name = normalize_browser_name(subkey_name)
                            if name in found_browsers:
                                continue
                            cmd_path = f"{reg_path}\\{subkey_name}\\shell\\open\\command"
                            with winreg.OpenKey(hive, cmd_path) as cmd_key:
                                val, _ = winreg.QueryValueEx(cmd_key, "")
                                val = val.strip('"')
                                if os.path.exists(val):
                                    found_browsers[name] = val
                        except OSError:
                            break
            except OSError:
                continue

    priority = ["Brave", "Opera GX", "Google Chrome", "Firefox", "Opera", "Vivaldi", "Microsoft Edge"]
    sorted_browsers = {}
    for p in priority:
        if p in found_browsers:
            sorted_browsers[p] = found_browsers[p]
    for k, v in found_browsers.items():
        if k not in sorted_browsers:
            sorted_browsers[k] = v

    return sorted_browsers


# --- DRIVER & RESOLVER CONSTANTS ---

DOWNLOAD_HOOK_JS = """
window.__ofmeHits = [];
const rec = (u) => {
    try {
        if (typeof u !== 'string' && u) u = u.url || String(u);
        if (u && (u.indexOf('/download/') !== -1 || u.indexOf('.gofile.io/download') !== -1 || u.indexOf('download') !== -1)) {
            if (u.indexOf('/d/') === -1) {
                window.__ofmeHits.push(u);
            }
        }
    } catch (e) {}
};
document.addEventListener('click', (e) => {
    const a = e.target && e.target.closest && e.target.closest('a');
    if (a && a.href) rec(a.href);
}, true);
const _click = HTMLElement.prototype.click;
HTMLElement.prototype.click = function () {
    if (this.href) rec(this.href);
    return _click.call(this);
};
const _open = window.open;
window.open = function (u, ...rest) {
    rec(u);
    return null;
};
const _fetch = window.fetch;
window.fetch = function (u, ...rest) { rec(u); return _fetch.call(window, u, ...rest); };
const _xhr = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (m, u, ...rest) { rec(u); return _xhr.call(this, m, u, ...rest); };
"""

prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")

CHROMIUM_BROWSERS = [
    ("Brave", os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")),
    ("Brave (x86)", os.path.join(prog_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")),
    ("Brave (Local)", os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")),
    ("Opera GX", os.path.join(local_appdata, "Programs", "Opera GX", "launcher.exe")),
    ("Opera GX (alt)", os.path.join(local_appdata, "Programs", "Opera GX", "opera.exe")),
    ("Chrome", None),
    ("Edge", os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe")),
    ("Edge (64)", os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe")),
    ("Opera", os.path.join(local_appdata, "Programs", "Opera", "launcher.exe")),
    ("Vivaldi", os.path.join(local_appdata, "Vivaldi", "Application", "vivaldi.exe")),
    ("Chromium", os.path.join(prog_files, "Chromium", "Application", "chrome.exe")),
]

FIREFOX_PATHS = [
    os.path.join(prog_files, "Mozilla Firefox", "firefox.exe"),
    os.path.join(prog_files_x86, "Mozilla Firefox", "firefox.exe"),
    os.path.join(local_appdata, "Mozilla Firefox", "firefox.exe")
]


def _build_chromium_options(binary: Optional[str] = None, user_data_dir: Optional[str] = None):
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    if binary:
        options.binary_location = binary
    return options


def _build_firefox_options(binary: Optional[str] = None):
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    options = FirefoxOptions()
    options.add_argument("-headless")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    options.set_preference("privacy.trackingprotection.enabled", True)
    options.set_preference("dom.disable_open_during_load", True)
    options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0")
    if binary:
        options.binary_location = binary
    return options


class ScraperSession:
    def __init__(self, driver, is_chromium: bool, temp_dir: Optional[str] = None):
        self.driver = driver
        self.is_chromium = is_chromium
        self.temp_dir = temp_dir

    def quit(self):
        try:
            self.driver.quit()
        except Exception:
            pass
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass


def create_scraper_driver() -> Tuple[ScraperSession, bool]:
    """
    Start a browser for link scraping, prioritizing Brave.
    """
    from selenium import webdriver
    original_path = os.environ.get("PATH", "")
    filtered = [p for p in original_path.split(os.pathsep) if "seleniumbase" not in p.lower()]
    os.environ["PATH"] = os.pathsep.join(filtered)
    try:
        last_error = None
        for name, binary in CHROMIUM_BROWSERS:
            if binary is not None and not os.path.exists(binary):
                continue
            try:
                temp_profile = tempfile.mkdtemp(prefix="fanta_scrap_")
                options = _build_chromium_options(binary, user_data_dir=temp_profile)
                driver = webdriver.Chrome(options=options)
                print(f"[Resolver] Browser automation active using {name}", flush=True)
                return ScraperSession(driver, True, temp_profile), True
            except Exception as e:
                last_error = e
                continue

        for binary in FIREFOX_PATHS:
            if not os.path.exists(binary):
                continue
            try:
                options = _build_firefox_options(binary)
                driver = webdriver.Firefox(options=options)
                print("[Resolver] Browser automation active using Firefox", flush=True)
                return ScraperSession(driver, False, None), False
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"No supported browser driver could be started. Last error: {last_error}"
        )
    finally:
        os.environ["PATH"] = original_path


class GoFileResolver:
    """
    Direct REST API fallback for GoFile when browser driver is not required.
    """
    _token = None
    _token_time = 0
    _salt = "12af056dacea0b"
    _user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    _lang = "en-US"

    @classmethod
    def get_token(cls, custom_token: Optional[str] = None) -> str:
        if custom_token:
            return custom_token
        now = time.time()
        if cls._token and (now - cls._token_time < 86400):
            return cls._token
        try:
            resp = requests.post(
                "https://api.gofile.io/accounts",
                headers={"User-Agent": cls._user_agent, "Accept-Language": cls._lang},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    cls._token = data.get("data", {}).get("token")
                    cls._token_time = now
                    return cls._token
        except Exception as e:
            print(f"[GoFileResolver] Direct API account notice: {e}", flush=True)
        return cls._token or ""

    @classmethod
    def resolve(cls, folder_id: str, custom_token: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        token = cls.get_token(custom_token)
        time_window = str(int(time.time() // 14400))
        raw = f"{cls._user_agent}::{cls._lang}::{token}::{time_window}::{cls._salt}"
        wt = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        headers = {
            "User-Agent": cls._user_agent,
            "Accept-Language": f"{cls._lang},en;q=0.9",
            "Authorization": f"Bearer {token}" if token else "",
            "X-Website-Token": wt,
            "X-BL": cls._lang
        }

        url = f"https://api.gofile.io/contents/{folder_id}?page=1&pageSize=100&sortField=name&sortDirection=1"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    children = data.get("data", {}).get("children", {})
                    for cid, cinfo in children.items():
                        direct_link = cinfo.get("link")
                        name = cinfo.get("name")
                        if direct_link:
                            return direct_link, name, token
        except Exception as e:
            print(f"[GoFileResolver] Direct API resolution error for {folder_id}: {e}", flush=True)

        return None, None, token


class LinkResolver:
    @staticmethod
    def resolve_url(
        url: str,
        custom_gofile_token: Optional[str] = None,
        game_name: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[str, Optional[str], Optional[Dict[str, str]]]:
        """
        Resolves input URL to a direct downloadable stream URL, suggested filename, and cookies.
        Returns: (direct_url, filename, cookies)
        """
        if not url:
            raise ValueError("Empty URL provided")

        url = url.strip()

        def log(msg: str):
            print(f"[Resolver] {msg}", flush=True)
            if progress_callback:
                try: progress_callback(msg)
                except Exception: pass

        # 1. PixelDrain resolver
        if "pixeldrain.com/u/" in url:
            file_id = url.split("/u/")[-1].split("?")[0].split("/")[0]
            direct_url = f"https://pixeldrain.com/api/file/{file_id}?download"
            log(f"PixelDrain link resolved to direct stream: {direct_url}")
            return direct_url, f"pixeldrain_{file_id}.zip", None

        # 2. BuzzHeavier & bzzhr.to resolver
        if "buzzheavier.com/" in url or "bzzhr.to/" in url:
            log(f"Resolving BuzzHeavier / bzzhr.to link: {url}")
            file_id = url.split("buzzheavier.com/")[-1].split("bzzhr.to/")[-1].split("?")[0].strip("/").replace("f/", "")
            target_url = f"https://bzzhr.to/{file_id}"
            
            # Step 2a: High-speed TLS impersonation using curl_cffi (bypasses Cloudflare JA3 bot verification)
            try:
                from curl_cffi import requests as cffi_requests
                from bs4 import BeautifulSoup

                s = cffi_requests.Session(impersonate="chrome124")
                headers = {
                    'Referer': 'https://steamrip.com/',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                r = s.get(target_url, headers=headers, timeout=12)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    file_name = None
                    name_tag = soup.find('p', class_='file-name')
                    if name_tag:
                        file_name = name_tag.text.strip()

                    dl_btn = soup.find('a', class_='download-btn')
                    if dl_btn:
                        hx_get = dl_btn.get('hx-get')
                        if hx_get:
                            trigger_url = f"https://bzzhr.to{hx_get}"
                            headers_dl = {
                                'HX-Request': 'true',
                                'HX-Current-URL': target_url,
                                'Referer': target_url,
                            }
                            r_dl = s.get(trigger_url, headers=headers_dl, allow_redirects=False, timeout=12)
                            direct_url = r_dl.headers.get('hx-redirect') or r_dl.headers.get('location')
                            if direct_url:
                                log(f"BuzzHeavier direct stream resolved: {direct_url[:80]}... Filename: '{file_name}'")
                                return direct_url, file_name or f"buzzheavier_{file_id}.zip", s.cookies.get_dict()
            except Exception as cffi_err:
                log(f"BuzzHeavier fast resolver notice: {cffi_err}")

            # Step 2b: Browser Scraper Fallback (Brave priority)
            session = None
            try:
                from selenium.webdriver.common.by import By
                log("Launching background browser (Brave priority) for BuzzHeavier fallback...")
                session, is_chromium = create_scraper_driver()
                driver = session.driver
                driver.get("https://steamrip.com/")
                time.sleep(1.5)
                driver.execute_script(f"window.location.href = '{target_url}';")
                time.sleep(3)
                
                dl_btn = driver.find_element(By.CSS_SELECTOR, "a.download-btn, [hx-get*='download']")
                hx_get = dl_btn.get_attribute("hx-get")
                if hx_get:
                    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
                    direct_url = f"https://bzzhr.to{hx_get}"
                    log(f"Browser captured BuzzHeavier stream endpoint: {direct_url}")
                    return direct_url, f"buzzheavier_{file_id}.zip", cookies
            except Exception as browser_err:
                log(f"BuzzHeavier browser scraper notice: {browser_err}")
            finally:
                if session:
                    session.quit()

            # Fallback for BuzzHeavier direct download endpoint
            if file_id and not file_id.endswith("/download"):
                direct_url = f"https://bzzhr.to/{file_id}/download"
                return direct_url, f"buzzheavier_{file_id}.zip", None


        # 3. GoFile resolver (Fast REST API + Browser Scraper Driver Fallback)
        if "gofile.io/d/" in url:
            log(f"Resolving GoFile URL: {url}...")
            folder_id = url.split("/d/")[-1].split("?")[0].split("/")[0]

            # Step 3a: High-speed Direct REST API resolver (~0.5s)
            try:
                direct_link, name, token = GoFileResolver.resolve(folder_id, custom_token=custom_gofile_token)
                if direct_link:
                    log(f"GoFile API resolved direct stream: {direct_link}")
                    cookies = {"accountToken": token} if token else None
                    return direct_link, name, cookies
            except Exception as api_err:
                log(f"GoFile fast API notice: {api_err}")

            # Step 3b: Browser Scraper Driver Fallback (Brave priority from Simple-OFME-Downloader-LIB)
            session = None
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.common.exceptions import TimeoutException, WebDriverException

                log("Launching background browser (Brave priority) to solve GoFile stream link...")
                session, is_chromium = create_scraper_driver()
                driver = session.driver

                if is_chromium:
                    try:
                        driver.execute_cdp_cmd("Network.enable", {})
                        driver.execute_cdp_cmd("Network.setBlockedURLs", {
                            "urls": [
                                "*adexchangerapid*", "*adsterra*", "*popcash*", "*popads*",
                                "*exoclick*", "*juicyads*", "*adservice*", "*doubleclick*",
                                "*googlesyndication*", "*onclickads*", "*propellerads*"
                            ]
                        })
                    except Exception:
                        pass

                try:
                    driver.get(url)
                except Exception as get_err:
                    err_str = str(get_err)
                    if "ERR_CONNECTION_TIMED_OUT" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str or "ERR_CONNECTION_REFUSED" in err_str or "ERR_TIMED_OUT" in err_str:
                        log(f"GoFile network error: net::ERR_CONNECTION_TIMED_OUT. Host unreachable.")
                        raise ConnectionError("GoFile connection timed out (server unreachable or blocked by ISP/VPN).")
                    log(f"Page load notice: {get_err}")

                row_selector = ".fm-row, .item_open, tr, [data-action='download']"
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, row_selector))
                    )
                except TimeoutException:
                    log("GoFile elements did not appear within timeout.")
                    raise TimeoutError("Folder elements did not load")

                rows = driver.find_elements(By.CSS_SELECTOR, row_selector)
                target_row = None
                clean_name = re.sub(r'[^a-z0-9]', '', (game_name or '').lower())

                for r in rows:
                    text = r.text.lower()
                    if ".rar" in text or ".zip" in text:
                        if clean_name and clean_name in re.sub(r'[^a-z0-9]', '', text):
                            target_row = r
                            break
                        if target_row is None:
                            target_row = r

                btn_selector = '[data-action="download"], .item_download, button, a'
                download_btn = None
                if target_row:
                    for candidate in target_row.find_elements(By.CSS_SELECTOR, btn_selector):
                        download_btn = candidate
                        break

                if not download_btn:
                    buttons = driver.find_elements(By.CSS_SELECTOR, '[data-action="download"], .item_download')
                    if buttons:
                        download_btn = buttons[0]

                if download_btn:
                    driver.execute_script(DOWNLOAD_HOOK_JS)
                    driver.execute_script("arguments[0].click();", download_btn)
                    
                    start_time = time.time()
                    direct_url = None
                    while time.time() - start_time < 12:
                        try:
                            hits = driver.execute_script("return window.__ofmeHits || [];")
                        except Exception:
                            hits = []
                        for hit in hits:
                            if "/d/" not in hit:
                                direct_url = hit
                                break
                        if direct_url:
                            break

                        if is_chromium:
                            try:
                                logs = driver.get_log("performance")
                                for entry in logs:
                                    msg = json.loads(entry["message"])["message"]
                                    if msg["method"] == "Network.requestWillBeSent":
                                        req_url = msg["params"]["request"]["url"]
                                        if "gofile.io" in req_url and "/download/" in req_url and "/d/" not in req_url:
                                            direct_url = req_url
                                            break
                            except Exception:
                                pass
                        if direct_url:
                            break
                        time.sleep(0.5)

                    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
                    if direct_url:
                        log(f"Browser successfully captured GoFile direct stream: {direct_url}")
                        return direct_url, None, cookies
            except Exception as browser_err:
                log(f"Browser resolver notice: {browser_err}")
            finally:
                if session:
                    session.quit()

        # 4. Direct URLs or fallback with HEAD request
        try:
            head_resp = requests.head(url, allow_redirects=True, timeout=6)
            cd = head_resp.headers.get("content-disposition", "")
            filename = None
            if "filename=" in cd:
                filename_match = re.search(r'filename=["\']?([^"\';]+)["\']?', cd)
                if filename_match:
                    filename = filename_match.group(1)
            return head_resp.url, filename, None
        except Exception:
            pass

        return url, None, None
