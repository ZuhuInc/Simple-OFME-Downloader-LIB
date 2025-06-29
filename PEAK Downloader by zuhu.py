"""
Simple Zuhu Peak Downloader V1.2.1 | converted using (python -m auto_py_to_exe)

By Zuhu | DC: ZuhuInc | DCS: https://discord.gg/Wr3wexQcD3

Exe 1.3.1 download link:
https://mega.nz/file/sOdz3bAK#PpQ7Zv9YrLLt9T4v79hLXAjYvffUEIf4Oxvj1sNrjsY
"""

import requests
import os
import tqdm
import sys
import subprocess
import shutil
import re

# --- Configuration ---
GITHUB_LINKS_URL = "https://raw.githubusercontent.com/ZuhuInc/TESTS/refs/heads/main/DWNLD.txt"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
CLEANUP_RAR_FILE = True
# --- End of Configuration ---

# --- Helper Functions ---

def fetch_links_from_github(github_raw_url):
    """
    Fetches games and their download sources from a structured text file on GitHub.
    Parses "SourceName (Game Name)" format.
    """
    print(f"[*] Fetching latest game list from GitHub...")
    try:
        response = requests.get(github_raw_url)
        response.raise_for_status()
        
        games = {}
        current_game_name = None
        current_source_name = None

        for line in response.text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = re.match(r'(.+?)\s*\((.+?)\)', line)
            if match:
                current_source_name = match.group(1).strip()
                current_game_name = match.group(2).strip()
                games.setdefault(current_game_name, {})[current_source_name] = {}
            elif ':' in line and current_game_name and current_source_name:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if "maingame" in key.lower(): standard_key = "MainGame"
                elif "fix" in key.lower(): standard_key = "Fix"
                else: standard_key = key
                
                games[current_game_name][current_source_name][standard_key] = value

        if not games:
            print("[X] ERROR: No valid games or sources were found in the GitHub file.")
            print("[!] Ensure the format is 'SourceName (Game Name)'.")
            return None
            
        print(f"[V] Successfully fetched {len(games)} game(s) from GitHub.")
        return games
        
    except Exception as e:
        print(f"[X] ERROR: Could not fetch link file from GitHub: {e}")
        return None

def download_file(url, destination_folder):
    """Downloads a single direct-link file with a progress bar."""
    print(f"[*] Preparing to download from: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        os.makedirs(destination_folder, exist_ok=True)
        local_filename = url.split('/')[-1].split('?')[0]
        if not local_filename: local_filename = "downloaded_file"
        local_filepath = os.path.join(destination_folder, local_filename)
        print(f"[*] Starting download: {local_filename}")
        
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size_in_bytes = int(r.headers.get('content-length', 0))
            progress_bar = tqdm.tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True, desc="Downloading")
            with open(local_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    progress_bar.update(len(chunk))
                    f.write(chunk)
            progress_bar.close()
            
        if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
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
        print(f"[X] An error occurred during WinRAR execution.")
        if "password" in e.stderr.lower(): print("[!] HINT: The error might be related to an incorrect password.")
        else: print(f"[!] Details: {e.stderr}")
        return False
    except Exception as e:
        print(f"[X] An unexpected error occurred during WinRAR execution: {e}")
        return False

# --- MAIN SCRIPT LOGIC ---
def main():
    print("--- Zuhu's Smart Downloader and Extractor ---")
    games = fetch_links_from_github(GITHUB_LINKS_URL)
    if not games:
        sys.exit(1)

    # --- 1. Choose the Game ---
    game_names = list(games.keys())
    selected_game_name = None
    if len(game_names) == 1:
        selected_game_name = game_names[0]
        print(f"\n[*] Only one game found: '{selected_game_name}'. Selecting it automatically.")
    else:
        print("\n[?] Please choose which game to download:")
        for i, name in enumerate(game_names):
            print(f"  [{i+1}] {name}")
        while True:
            try:
                choice = int(input(f"> Enter your choice (1-{len(game_names)}): ").strip())
                if 1 <= choice <= len(game_names):
                    selected_game_name = game_names[choice - 1]
                    break
                else:
                    print(f"[!] Invalid choice. Please enter a number between 1 and {len(game_names)}.")
            except ValueError:
                print("[!] Invalid input. Please enter a number.")
    
    # --- 2. Choose the Source for the selected game ---
    sources_for_game = games[selected_game_name]
    source_names = list(sources_for_game.keys())
    selected_links = None
    if len(source_names) == 1:
        selected_source_name = source_names[0]
        selected_links = sources_for_game[selected_source_name]
        print(f"[*] Only one download source for '{selected_game_name}' found: '{selected_source_name}'. Using it automatically.")
    else:
        print(f"\n[?] Choose a download source for '{selected_game_name}':")
        for i, name in enumerate(source_names):
            print(f"  [{i+1}] {name}")
        while True:
            try:
                choice = int(input(f"> Enter your choice (1-{len(source_names)}): ").strip())
                if 1 <= choice <= len(source_names):
                    selected_source_name = source_names[choice - 1]
                    selected_links = sources_for_game[selected_source_name]
                    print(f"[*] You selected source: '{selected_source_name}'")
                    break
                else:
                    print(f"[!] Invalid choice. Please enter a number between 1 and {len(source_names)}.")
            except ValueError:
                print("[!] Invalid input. Please enter a number.")
    
    game_url = selected_links.get('MainGame')
    fix_url = selected_links.get('Fix')

    if not game_url:
        print("[X] ERROR: Main game URL ('MainGame') not found in the selected source. Check your DWNLD.txt file.")
        sys.exit(1)

    temp_download_folder = "temp_downloads"
    main_game_folder_path = None

    # --- Process Main Game File ---
    print("\n--- Processing Main Game File ---")
    user_base_path = input("\n> " + r"Enter the BASE path for game extraction. (Like, I:\Games) and press Enter: ").strip()
    user_base_path = os.path.abspath(user_base_path)
    if not os.path.isdir(user_base_path):
        print(f"[X] Invalid path: The directory '{user_base_path}' does not exist. Exiting.")
        sys.exit(1)

    downloaded_rar_path = download_file(game_url, temp_download_folder)
    if downloaded_rar_path:
        dirs_before = set(f for f in os.listdir(user_base_path) if os.path.isdir(os.path.join(user_base_path, f)))
        success = winrar_extraction(WINRAR_PATH, downloaded_rar_path, user_base_path, RAR_PASSWORD)

        if success:
            dirs_after = set(f for f in os.listdir(user_base_path) if os.path.isdir(os.path.join(user_base_path, f)))
            new_dirs = dirs_after - dirs_before
            if len(new_dirs) == 1:
                new_folder_name = new_dirs.pop()
                main_game_folder_path = os.path.join(user_base_path, new_folder_name)
                print(f"[*] Main game folder auto-detected: '{main_game_folder_path}'")
            else:
                print("[!] Warning: Could not auto-detect the new game folder. Please specify the path for the fix manually.")
            
            if CLEANUP_RAR_FILE:
                print(f"[*] Cleaning up '{os.path.basename(downloaded_rar_path)}'...")
                os.remove(downloaded_rar_path)
                print("[V] Cleanup complete.")
    else:
        print("[X] Main game download failed. Aborting.")
        sys.exit(1)

    # --- Process the fix file (if it exists) ---
    if fix_url:
        print("\n" + "="*50)
        download_fix_choice = input("[?] A fix/update is available. Do you want to download and apply it? (y/n): ").lower().strip()

        if download_fix_choice in ['y', 'yes']:
            # <<< THIS IS THE CORRECTED BLOCK >>>
            prompt_message = "\n" + r"> Enter the path for the fix extraction. (e.g., I:\Games\(Game-Name)"
            # Check if we successfully auto-detected the game folder earlier
            if main_game_folder_path:
                prompt_message += f"\n (auto-detected path: {main_game_folder_path}): "
            else:
                prompt_message += " and press Enter: "

            user_input_path = input(prompt_message).strip()
            fix_extraction_path = os.path.abspath(user_input_path) if user_input_path else main_game_folder_path
            
            if not fix_extraction_path or not os.path.isdir(fix_extraction_path):
                print(f"[X] ERROR: The specified path does not exist or is not a directory: '{fix_extraction_path}'")
                print("[!] Aborting fix installation.")
            else:
                print(f"[*] The fix will be extracted to: '{fix_extraction_path}'")
                downloaded_fix_path = download_file(fix_url, temp_download_folder)
                if downloaded_fix_path:
                    success = winrar_extraction(WINRAR_PATH, downloaded_fix_path, fix_extraction_path, RAR_PASSWORD)
                    if success and CLEANUP_RAR_FILE:
                        print(f"[*] Cleaning up '{os.path.basename(downloaded_fix_path)}'...")
                        os.remove(downloaded_fix_path)
                        print("[V] Cleanup complete.")
        else:
            print("[*] Skipping fix download and installation as requested.")

    # --- Final Cleanup ---
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
