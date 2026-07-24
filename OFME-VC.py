from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from seleniumbase import Driver
from selenium import webdriver
from plyer import notification
import requests
import getpass
import time
import json
import sys
import os
import re

options = Options()
options.add_argument("--headless=new") 
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--remote-allow-origins=*")
options.add_argument("--log-level=3")
options.add_argument("--silent")
options.add_experimental_option('excludeSwitches', ['enable-logging'])

brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
if os.path.exists(brave_path):
    options.binary_location = brave_path

driver1 = None
try:
    driver1 = webdriver.Chrome(options=options)
except Exception as e:
    print(f"Brave driver failed: {e}. Trying fallback to standard Chrome...")
    options.binary_location = ""
    try:
        driver1 = webdriver.Chrome(options=options)
    except Exception as e2:
        print(f"Fallback driver failed: {e2}")
        driver1 = None

driver2 = None
driver2_kwargs = {}
if brave_path and os.path.exists(brave_path):
    driver2_kwargs["binary_location"] = brave_path

try:
    driver2 = Driver(browser='chrome', uc=True, **driver2_kwargs)
except Exception as e:
    try:
        driver2 = Driver(browser='chrome', uc=True)
    except Exception as e2:
        print(f"Failed to init Driver 2: {e2}")
        driver2 = None
os.system('cls')
DISCORD_ICON_URL = "https://i.imgur.com/01wdU6Q.png" 
APP_ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-VC-ICO.ico"
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
DATA_FILE = os.path.join(DATA_FOLDER, 'Login.json')
ICO_PATH = os.path.join(DATA_FOLDER, 'cache', 'OFME-VC-ICO.ico') 
CACHE_FOLDER = os.path.join(DATA_FOLDER, 'cache')
os.makedirs(CACHE_FOLDER, exist_ok=True)

if not os.path.exists(ICO_PATH):
    try:
        response = requests.get(APP_ICON_URL, timeout=15)
        response.raise_for_status() 
        with open(ICO_PATH, 'wb') as f:
            f.write(response.content)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not download the app icon. {e}")

WEBHOOK_URL = ""
username = ""
password = ""

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        credentials = json.load(f)
    
    username = credentials.get('username')
    password = credentials.get('password')
    WEBHOOK_URL = credentials.get('webhook_url', "") 
    print(f"Using saved credentials for: {username}")

    if not WEBHOOK_URL:
        print("No Webhook URL found in settings.")
        new_webhook = input("Enter Discord Webhook URL (Press Enter to skip): ").strip()
        if new_webhook:
            WEBHOOK_URL = new_webhook
            credentials['webhook_url'] = WEBHOOK_URL
            with open(DATA_FILE, 'w') as f:
                json.dump(credentials, f, indent=4)
            print(f"Webhook URL added to {DATA_FILE}")

else:
    username = input("Enter your username: ")
    password = getpass.getpass("Enter your password: ")
    WEBHOOK_URL = input("Enter Discord Webhook URL (Press Enter to skip): ").strip()
    save_choice = input("Save login for future use? (Y/N): ")
    if save_choice.lower() in ['y', 'yes']:
        data_to_save = {
            'username': username, 
            'password': password,
            'webhook_url': WEBHOOK_URL
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        print(f"Credentials and Webhook saved to {DATA_FILE}")
    else:
        print("Credentials will not be saved.")

response = requests.get(DB_URL)
lines = response.text.splitlines()
games = []
current_game = {}
opties = ['GoFile', 'DropBox', 'Both', 'BuzzHeavier']
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue

    for optie in opties:
        if line.startswith(optie):
            if current_game:
                games.append(current_game)
                current_game = {}
            name_part = line.split(f"{optie} (")[1].split(")")[0]
            version = line.split("[")[1].split("]")[0]
            current_game["Source"] = optie
            current_game["Name"] = name_part
            current_game["Version"] = version
            break  
    
        elif ":" in line:
            key, value = line.split(":", 1)
            current_game[key.strip()] = value.strip()

if current_game:
    games.append(current_game)
    
counter = 0
game_update = {}
for game in games:
    if 'https://online-fix.me/' in game['Origin']:
        if not driver1: continue
        driver1.get(game['Origin'])
        if counter == 0:
            search = driver1.find_element(By.NAME, 'login_name')
            search.send_keys(username)
            search = driver1.find_element(By.NAME, 'login_password')
            search.send_keys(password)
            time.sleep(0.5)
            search.send_keys(Keys.RETURN)            
            try:
                WebDriverWait(driver1, 5).until(
                    EC.presence_of_element_located((By.XPATH, f"//img[@alt='{username}']"))
                )
                print(f"Successfully logged in as: {username}")
                print("-" * 60)
            except TimeoutException:
                print("Error logging in. Please check your credentials.")
                if os.path.exists(DATA_FILE):
                        try:
                            os.startfile(DATA_FILE)
                            print(f"Opening {DATA_FILE}...")
                        except Exception as error:
                            print(f"Could not open the file. Please navigate to it manually: {DATA_FILE}")
                            print(f"Error: {error}")
                if driver1: driver1.quit()
                if driver2: driver2.quit()
                sys.exit()
            counter += 1
        driver1.get(game['Origin'])
        time.sleep(1) 
        try:
            select_version = WebDriverWait(driver1, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "quote")))
            version = select_version.find_element(By.TAG_NAME, 'b').text.replace('Версия игры: ', '')
        except:
            print(f"Version not found for {game['Name']}")
            continue 
                 
    elif 'https://steamrip.com/' in game['Origin']:
        if not driver2: continue
        Origin_URL = game['Origin']
        try:
            driver2.uc_open_with_reconnect(Origin_URL, 6) 
            driver2.uc_gui_click_captcha()
            try:
                h1_elem = WebDriverWait(driver2, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'h1'))
                )
                h1_text = h1_elem.text.strip()
            except Exception:
                try:
                    h1_elem = driver2.find_element(By.CLASS_NAME, 'entry-title')
                    h1_text = h1_elem.text.strip()
                except Exception:
                    h1_text = ""

            if '(' in h1_text and ')' in h1_text:
                version = h1_text.split('(')[1].split(')')[0].strip()
            else:
                ver_match = re.search(r'(?:v|Build\s*)([\d\.\w\-]+)', h1_text, re.IGNORECASE)
                if ver_match:
                    version = ver_match.group(0).strip()
                else:
                    version = h1_text.replace("Free Download", "").strip()
        except Exception as e:
            print(f"SteamRIP error for {game['Name']}: {e}")
            continue
    else:
        continue
    if "Build" in version:
        version = version.replace("Build ", "")
    if "v" in version:
        version = version.replace("v", "")
    print(f"{game['Name']}: {version} (Current: {game['Version']})")  
    if version != game['Version']:
        game_update[game['Name']] = {
            'new': version, 
            'old': game['Version'],
            'url': game['Origin']
        }

if driver1: driver1.quit()
if driver2: driver2.quit()
print("-" * 60)
num_updates = len(game_update)

if num_updates > 0:
    notif_title = "Game Updates Found!"
    notif_message = f"{num_updates} game(s) need an update. Check Discord/Console."
    print("GAMES THAT NEED AN UPDATE:")
    for name, data in game_update.items():
        print(f" > {name}: {data['new']} (Was: {data['old']})")
    
    if WEBHOOK_URL and "discord" in WEBHOOK_URL:
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
        try:
            requests.post(WEBHOOK_URL, json=payload)
            print("Update Notification sent to Discord.")
        except Exception as e:
            print(f"Failed to send webhook: {e}")

else:
    notif_title = "Update Check Complete"
    notif_message = "All your games are up to date!"
    print(f'There are no games that need a update.')

    if WEBHOOK_URL and "discord" in WEBHOOK_URL:
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
            print("Status Notification sent to Discord.")
        except Exception as e:
            print(f"Failed to send webhook: {e}")

try:
    notification.notify(
        title=notif_title,
        message=notif_message,
        app_name="OFME-VC",
        app_icon=ICO_PATH,
        timeout=15  
    )
except Exception as e:
    print(f"Notification Error: {e}")
    notification.notify(
        title=notif_title,
        message=notif_message,
        app_name="OFME-VC",
        timeout=15  
    )
print("-" * 60)