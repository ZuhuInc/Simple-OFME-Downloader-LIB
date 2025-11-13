from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
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
import os

options = Options()
brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
options.binary_location = brave_path
driver1 = webdriver.Chrome(options = options)
driver2 = Driver(browser='brave', uc = True)
os.system('cls')

ICON_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Assets/OFME-VC-ICO.ico"
DB_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
DATA_FOLDER = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuOFME')
DATA_FILE = os.path.join(DATA_FOLDER, 'Login.json')
ICO_PATH = os.path.join(DATA_FOLDER, 'cache', 'OFME-VC-ICO.ico')
CACHE_FOLDER = os.path.join(DATA_FOLDER, 'cache')
os.makedirs(CACHE_FOLDER, exist_ok=True)

if not os.path.exists(ICO_PATH):
    try:
        response = requests.get(ICON_URL, timeout=15)
        response.raise_for_status() 
        with open(ICO_PATH, 'wb') as f:
            f.write(response.content)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not download the icon. {e}")
        
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        credentials = json.load(f)
    username = credentials.get('username')
    password = credentials.get('password')
    print(f"Logged in as: {username}")
    print("-" * 60)
else:
    username = input("Enter your username: ")
    password = getpass.getpass("Enter your password: ")
    save_choice = input("Save login for future use? (Y/N): ")
    if save_choice.lower() in ['y', 'yes']:
        with open(DATA_FILE, 'w') as f:
            json.dump({'username': username, 'password': password}, f, indent=4)
        print(f"Credentials saved to {DATA_FILE}")
    else:
        print("Credentials will not be saved.")

response = requests.get(DB_URL)
lines = response.text.splitlines()

games = []
current_game = {}
opties = ['GoFile', 'DropBox', 'Both']
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
        driver1.get(game['Origin'])
        if counter == 0:
            search = driver1.find_element(By.NAME, 'login_name')
            search.send_keys(username)
            search = driver1.find_element(By.NAME, 'login_password')
            search.send_keys(password)
            time.sleep(0.5)
            search.send_keys(Keys.RETURN)
            counter += 1
            pass
        time.sleep(0.5)
        try:
            select_version = WebDriverWait(driver1, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "quote")))
            version = select_version.find_element(By.TAG_NAME, 'b').text.replace('Версия игры: ', '')
        except:
            print("Version not found")
    elif 'https://steamrip.com/' in game['Origin']:
        Origin_URL = game['Origin']
        driver2.uc_open_with_reconnect(Origin_URL,4)
        driver2.uc_gui_click_captcha()
        version = driver2.find_element(By.TAG_NAME, 'h1').text.split('(')[1].replace(')','')
        pass
    else:
        continue

    if "Build" in version:
        version = version.replace("Build ", "")
    
    if "v" in version:
        version = version.replace("v", "")

    print(f"{game['Name']}: {version} (Current: {game['Version']})")  

    if version != game['Version']:
        game_update[game['Name']] = version, game['Version']

driver1.quit()
driver2.quit()
print("-" * 60)

num_updates = len(game_update)

if num_updates > 0:
    notif_title = "Game Updates Found!"
    notif_message = f"{num_updates} game(s) need an update. Check the console for details."
    print(f'Games That need a update: {game_update}')
else:
    notif_title = "Update Check Complete"
    notif_message = "All your games are up to date!"
    print(f'There are no games that need a update.')

notification.notify(
    title=notif_title,
    message=notif_message,
    app_name="OFME-VC",
    app_icon=ICO_PATH,
    timeout=15  
)