"""
Simple Zuhu Downloader V1.3.5

By Zuhu | DC: ZuhuInc | DCS: https://discord.gg/Wr3wexQcD3
"""

import requests
import os
import tqdm
import sys
import subprocess
import shutil
import re
import hashlib

# --- Configuration --- #
GITHUB_LINKS_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Download-DB.txt"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
CLEANUP_RAR_FILE = True
# --- End of Configuration --- #

# --- UI Helper Functions --- #
def clear_screen():
    """Clears the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_status_header(game_name, source_name=None, game_status=None, fix_status=None):
    """Clears the screen and prints a status checklist header."""
    clear_screen()
    print("--- Zuhu's Downloader Status ---")
    print(f"Game:       {game_name}")
    if source_name:
        print(f"Source:     {source_name}")
    if game_status:
        print(f"Game File:  {game_status}")
    if fix_status:
        print(f"Fix File:   {fix_status}")
    print("-" * 34 + "\n")


def resolve_gofile_link(gofile_url):
    """
    Resolves a GoFile.io URL using the correct API interaction method.
    Returns a tuple: (direct_link, account_token)
    """
    print(f"[*] Resolving GoFile link using direct API calls: {gofile_url}")
    try:
        print("[*] Step 1: Requesting a guest account token...")
        headers = {"User-Agent": "Mozilla/5.0"}
        token_response = requests.post("https://api.gofile.io/accounts", headers=headers).json()
        if token_response.get("status") != "ok":
            print("[X] ERROR: Could not create a guest account to get a token.")
            return None, None
        account_token = token_response["data"]["token"]
        print("[V] Successfully obtained guest token.")

        content_id = gofile_url.split("/")[-1]
        hashed_password = hashlib.sha256(RAR_PASSWORD.encode()).hexdigest()
        api_url = f"https://api.gofile.io/contents/{content_id}"
        params = {'wt': '4fd6sg89d7s6', 'password': hashed_password}
        auth_headers = {"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {account_token}"}

        print("[*] Step 2: Calling API with token and hashed password...")
        content_response = requests.get(api_url, params=params, headers=auth_headers).json()

        if content_response.get("status") != "ok":
            error_msg = content_response.get("status", "Unknown Error")
            print(f"[X] ERROR: API call failed. Server responded: {error_msg}")
            return None, None
        print("[V] API call successful. Parsing response...")

        data = content_response.get("data", {})
        if data.get("type") == "folder":
            print("[*] Folder content detected, searching for first file...")
            for child_id, child_data in data.get("children", {}).items():
                if child_data.get("type") == "file":
                    direct_link = child_data.get("link")
                    filename = child_data.get("name", "Unknown")
                    print(f"[V] Found file '{filename}' in folder. Link acquired!")
                    return direct_link, account_token
            print("[X] ERROR: Folder found, but it contains no files.")
            return None, None
        elif data.get("type") == "file":
            print("[*] Direct file content detected. Link acquired!")
            return data.get("link"), account_token
        else:
            print("[X] ERROR: Could not determine content type (file or folder).")
            return None, None
    except Exception as e:
        print(f"[X] FATAL ERROR: An unexpected error occurred: {e}")
        return None, None

def fetch_links_from_github(github_raw_url):
    """
    Fetches games and their download sources from a structured text file on GitHub.
    Parses "SourceName (Game Name) [Version]" format.
    """
    clear_screen()
    print("--- Zuhu's Smart Downloader and Extractor ---")
    print(f"[*] Fetching latest game list from GitHub...")
    try:
        response = requests.get(github_raw_url)
        response.raise_for_status()
        
        games = {}
        current_display_name = None
        current_source_name = None

        for line in response.text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            
            # --- THIS IS THE NEW REGEX FOR VERSION PARSING --- #
            match = re.match(r'(.+?)\s*\((.+?)\)\s*\[(.+?)\]', line)
            if match:
                source_name = match.group(1).strip()
                base_name = match.group(2).strip()
                version = match.group(3).strip()
                
                current_display_name = f"{base_name} {version}"
                current_source_name = source_name
                
                games.setdefault(current_display_name, {'base_name': base_name, 'sources': {}})
                games[current_display_name]['sources'][current_source_name] = {}
            elif ':' in line and current_display_name and current_source_name:
                key, value = [s.strip() for s in line.split(':', 1)]
                standard_key = "MainGame" if "maingame" in key.lower() else "Fix" if "fix" in key.lower() else key
                games[current_display_name]['sources'][current_source_name][standard_key] = value
        
        if not games:
            print("[X] ERROR: No valid games found. Check format: 'Source (Game) [Version]'.")
            return None
            
        print(f"[V] Successfully fetched {len(games)} game(s) from GitHub.")
        return games
    except Exception as e:
        print(f"[X] ERROR: Could not fetch link file from GitHub: {e}")
        return None

def download_file(url, destination_folder, token=None):
    print(f"\n[*] Preparing to download from: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    if token:
        print("[*] Using account token as cookie for authorization.")
        headers['Cookie'] = f'accountToken={token}'
    try:
        os.makedirs(destination_folder, exist_ok=True)
        local_filename = url.split('/')[-1].split('?')[0] or "downloaded_file"
        local_filepath = os.path.join(destination_folder, local_filename)
        print(f"[*] Starting download: {local_filename}")
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            progress_bar = tqdm.tqdm(total=total_size, unit='iB', unit_scale=True, desc="Downloading")
            with open(local_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    progress_bar.update(len(chunk))
                    f.write(chunk)
            progress_bar.close()
        if total_size != 0 and progress_bar.n != total_size:
            print("[X] ERROR: Downloaded size does not match expected size.")
            return None
        print(f"[V] Download complete: {local_filepath}")
        return local_filepath
    except Exception as e:
        print(f"[X] ERROR: An unexpected error occurred during download: {e}")
        return None

def winrar_extraction(winrar_path, rar_path, destination_folder, password):
    print("\n--- Starting WinRAR Extraction ---")
    if not os.path.exists(winrar_path):
        print(f"[X] CRITICAL ERROR: WinRAR.exe not found at '{winrar_path}'.")
        return False
    os.makedirs(destination_folder, exist_ok=True)
    command = [winrar_path, "x", f"-p{password}", "-ibck", "-o+", os.path.abspath(rar_path), os.path.abspath(destination_folder) + os.sep]
    print(f"[*] Extracting '{os.path.basename(rar_path)}' to '{destination_folder}'...")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print("[V] WinRAR extraction successful.")
        return True
    except subprocess.CalledProcessError as e:
        print("[X] An error occurred during WinRAR execution.")
        print("[!] HINT: The error might be related to an incorrect password." if "password" in e.stderr.lower() else f"[!] Details: {e.stderr}")
        return False
    except Exception as e:
        print(f"[X] An unexpected error occurred during WinRAR execution: {e}")
        return False

# --- MAIN SCRIPT LOGIC --- #
def main():
    games = fetch_links_from_github(GITHUB_LINKS_URL)
    if not games: sys.exit(1)
    
    # --- Status Tracking Variables --- #
    game_file_status = "Not Started"
    fix_file_status = "Not Started"

    # --- Phase 1: User Selection --- #
    game_display_names = list(games.keys())
    selected_display_name = game_display_names[0] if len(game_display_names) == 1 else None
    if selected_display_name:
        print(f"\n[*] Only one game found: '{selected_display_name}'. Selecting it automatically.")
    else:
        print("\n[?] Please choose which game to download:")
        for i, name in enumerate(game_display_names): print(f"  [{i+1}] {name}")
        while not selected_display_name:
            try:
                choice = int(input(f"> Enter your choice (1-{len(game_display_names)}): ").strip())
                if 1 <= choice <= len(game_display_names): selected_display_name = game_display_names[choice - 1]
                else: print(f"[!] Invalid choice.")
            except ValueError: print("[!] Invalid input.")
    
    # --- Get Base Name and Sources using the selected Display Name --- #
    base_game_name = games[selected_display_name]['base_name']
    sources_for_game = games[selected_display_name]['sources']
    
    source_names = list(sources_for_game.keys())
    selected_source_name = source_names[0] if len(source_names) == 1 else None
    if selected_source_name:
        print(f"\n[*] Only one download source for '{base_game_name}' found: '{selected_source_name}'. Using it automatically.")
    else:
        print(f"\n[?] Choose a download source for '{base_game_name}':")
        for i, name in enumerate(source_names): print(f"  [{i+1}] {name}")
        while not selected_source_name:
            try:
                choice = int(input(f"> Enter your choice (1-{len(source_names)}): ").strip())
                if 1 <= choice <= len(source_names): selected_source_name = source_names[choice - 1]
                else: print(f"[!] Invalid choice.")
            except ValueError: print("[!] Invalid input.")
    
    # --- Phase 2: Main Game Download --- #
    print_status_header(selected_display_name, selected_source_name)
    
    selected_links = sources_for_game[selected_source_name]
    game_url, fix_url = selected_links.get('MainGame'), selected_links.get('Fix')

    if not game_url:
        print("[X] ERROR: Main game URL ('MainGame') not found. Check your DWNLD.txt file.")
        sys.exit(1)

    temp_download_folder, main_game_folder_path = "temp_downloads", None

    print("--- Processing Main Game File ---")
    user_base_path = os.path.abspath(input("> Enter the BASE path for game extraction. (e.g., I:\\Games): ").strip())
    if not os.path.isdir(user_base_path):
        print(f"[X] Invalid path: '{user_base_path}' does not exist. Exiting.")
        sys.exit(1)

    direct_game_url, game_token = game_url, None
    if "gofile.io" in game_url:
        direct_game_url, game_token = resolve_gofile_link(game_url)
        if not direct_game_url:
            print("[X] Failed to get direct download link from GoFile. Aborting.")
            sys.exit(1)

    downloaded_rar_path = download_file(direct_game_url, temp_download_folder, token=game_token)
    if downloaded_rar_path:
        dirs_before = set(os.listdir(user_base_path))
        if winrar_extraction(WINRAR_PATH, downloaded_rar_path, user_base_path, RAR_PASSWORD):
            game_file_status = "Completed"
            dirs_after = set(os.listdir(user_base_path))
            new_dirs = [d for d in (dirs_after - dirs_before) if os.path.isdir(os.path.join(user_base_path, d))]
            if len(new_dirs) == 1:
                main_game_folder_path = os.path.join(user_base_path, new_dirs[0])
                print(f"\n[*] Main game folder auto-detected: '{main_game_folder_path}'")
            else:
                print("\n[!] Warning: Could not auto-detect the new game folder.")
            if CLEANUP_RAR_FILE:
                print(f"[*] Cleaning up '{os.path.basename(downloaded_rar_path)}'...")
                os.remove(downloaded_rar_path)
    else:
        game_file_status = "Failed"
        print("[X] Main game download failed. Aborting.")
        sys.exit(1)
    
    # --- Phase 3: Fix Download --- #
    if fix_url:
        fix_choice = input("\n" + "="*50 + "\n[?] A fix/update is available. Download and apply it? (y/n): ").lower().strip()
        
        if fix_choice in ['y', 'yes']:
            print_status_header(selected_display_name, selected_source_name, game_file_status)
            prompt_message = ""
            if main_game_folder_path:
                prompt_message = (f"> Enter the path for the fix extraction.\n  (Press Enter to use auto-detected path: {main_game_folder_path}): ")
            else:
                invalid_chars = r'[:*?"<>|]'
                clean_game_name = re.sub(invalid_chars, '', base_game_name)
                example_path = os.path.join(user_base_path, clean_game_name)
                prompt_message = (f"> [!] Could not auto-detect game folder.\n  Enter the FULL path for the fix extraction (e.g., {example_path}): ")
            
            user_input_path = input(prompt_message).strip()
            fix_extraction_path = os.path.abspath(user_input_path) if user_input_path else main_game_folder_path
            
            if not fix_extraction_path or not os.path.isdir(fix_extraction_path):
                print(f"[X] ERROR: Invalid path '{fix_extraction_path}'. Aborting fix.")
                fix_file_status = "Failed"
            else:
                print(f"[*] The fix will be extracted to: '{fix_extraction_path}'")
                direct_fix_url, fix_token = fix_url, None
                if "gofile.io" in fix_url:
                    direct_fix_url, fix_token = resolve_gofile_link(fix_url)
                if direct_fix_url:
                    downloaded_fix_path = download_file(direct_fix_url, temp_download_folder, token=fix_token)
                    if downloaded_fix_path and winrar_extraction(WINRAR_PATH, downloaded_fix_path, fix_extraction_path, RAR_PASSWORD):
                        fix_file_status = "Completed"
                        if CLEANUP_RAR_FILE:
                            print(f"[*] Cleaning up '{os.path.basename(downloaded_fix_path)}'...")
                            os.remove(downloaded_fix_path)
                    else:
                        fix_file_status = "Failed"
                else:
                    print("[X] Failed to get direct download link for the fix. Skipping fix.")
                    fix_file_status = "Failed"
            
            input("\nPress Enter to continue...")
        else:
            fix_file_status = "Skipped"
    else:
        fix_file_status = "Not Available"

    # --- Phase 4: Final Summary --- #
    print_status_header(selected_display_name, selected_source_name, game_file_status, fix_file_status)

    try:
        if os.path.exists(temp_download_folder) and not os.listdir(temp_download_folder):
            print("[*] Cleaning up temporary download directory...")
            os.rmdir(temp_download_folder)
    except Exception as e:
        print(f"[!] Could not remove temporary directory '{temp_download_folder}': {e}")

if __name__ == "__main__":
    main()
    print("\n--- ALL TASKS COMPLETED ---")
    input("Press Enter to exit.")