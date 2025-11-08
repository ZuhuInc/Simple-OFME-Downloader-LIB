from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import time
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests

brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
username = input("Enter your username: ")
password = input("Enter your password: ")
options = Options()
options.binary_location = brave_path
driver = webdriver.Chrome(options = options)

url = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/main/Download-DB.txt"
response = requests.get(url)
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
    time.sleep(1)
    if 'https://online-fix.me/' in game['Origin']:
        pass
    else:
        continue
    
    driver.get(game['Origin'])
    if counter == 0:
        search = driver.find_element(By.NAME, 'login_name')
        search.send_keys(username)
        search = driver.find_element(By.NAME, 'login_password')
        search.send_keys(password)
        time.sleep(1)
        search.send_keys(Keys.RETURN)
        counter += 1
        pass
    time.sleep(1)
    try:
        select_version = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "quote")))
        version = select_version.find_element(By.TAG_NAME, 'b').text.replace('Версия игры: ', '')
    except:
        print("Version not found")

    if "Build" in version:
        version = version.replace("Build ", "")

    print(f"{game['Name']}: {version} (Current: {game['Version']})")  

    if version != game['Version']:
        game_update[game['Name']] = version, game['Version']

driver.quit()
print(game_update)
