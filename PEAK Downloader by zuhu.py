import requests
import os
import tqdm
import sys
import subprocess
import shutil

# --- Configuration ---
GITHUB_LINKS_URL = "https://raw.githubusercontent.com/ZuhuInc/TESTS/refs/heads/main/DWNLD.txt"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
CLEANUP_RAR_FILE = True
# --- End of Configuration ---

# --- Helper Functions (No changes needed) ---

def fetch_links_from_github(github_raw_url):
    print(f"[*] Fetching latest download links from GitHub...")
    try:
        response = requests.get(github_raw_url)
        response.raise_for_status()
        urls = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            if ':' in line: urls.append(line.split(':', 1)[1].strip())
        if not urls:
            print("[X] ERROR: No valid URLs were found in the GitHub file.")
            return None
        print(f"[V] Successfully fetched {len(urls)} link(s) from GitHub.")
        return urls
    except Exception as e:
        print(f"[X] ERROR: Could not fetch link file from GitHub: {e}")
        return None

def download_file(url, destination_folder):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        os.makedirs(destination_folder, exist_ok=True)
        local_filename = url.split('/')[-1].split('?')[0]
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
        subprocess.run(command, check=True)
        print("[V] WinRAR extraction successful.")
        return True
    except Exception as e:
        print(f"[X] An error occurred during WinRAR execution: {e}")
        return False

# --- MAIN FUNCTION WITH NEW LOGIC ---

def main():
    print("--- Zuhu's Smart PEAK Downloader and Extractor ---")
    urls_to_download = fetch_links_from_github(GITHUB_LINKS_URL)
    if not urls_to_download:
        sys.exit(1)

    # --- THIS LINE IS THE FIX ---
    # Using a raw string (r"...") to prevent backslash issues with PyInstaller.
    user_base_path = input("\n> " + r"Enter the BASE path for extraction (e.g., I:\Games or C:\Users\(username)\Documents) and press Enter: ")
    user_base_path = os.path.abspath(user_base_path)
    if not os.path.isdir(user_base_path):
        print(f"[X] Invalid path: The directory '{user_base_path}' does not seem to exist. Exiting.")
        sys.exit(1)
    
    temp_download_folder = "temp_downloads"
    main_game_folder_path = None

    for i, url in enumerate(urls_to_download):
        print("\n" + "="*50)
        print(f"--- Processing file {i+1} of {len(urls_to_download)} ---")
        
        downloaded_rar_path = download_file(url, temp_download_folder)
        if not downloaded_rar_path:
            print("!! Skipping extraction due to download failure.")
            continue

        if main_game_folder_path:
            current_extraction_path = main_game_folder_path
        else:
            current_extraction_path = user_base_path

        dirs_before = set(f for f in os.listdir(current_extraction_path) if os.path.isdir(os.path.join(current_extraction_path, f)))
        
        success = winrar_extraction(WINRAR_PATH, downloaded_rar_path, current_extraction_path, RAR_PASSWORD)
        
        if success:
            if not main_game_folder_path:
                dirs_after = set(f for f in os.listdir(current_extraction_path) if os.path.isdir(os.path.join(current_extraction_path, f)))
                new_dirs = dirs_after - dirs_before
                if len(new_dirs) == 1:
                    new_folder_name = new_dirs.pop()
                    main_game_folder_path = os.path.join(current_extraction_path, new_folder_name)
                    print(f"[*] Main game folder auto-detected: '{main_game_folder_path}'")
                    print("[*] All subsequent files will be extracted here.")
            
            if CLEANUP_RAR_FILE:
                print(f"[*] Cleaning up '{os.path.basename(downloaded_rar_path)}'...")
                os.remove(downloaded_rar_path)
                print("[V] Cleanup complete.")

    try:
        if os.path.exists(temp_download_folder) and not os.listdir(temp_download_folder):
            os.rmdir(temp_download_folder)
    except Exception:
        pass

if __name__ == "__main__":
    main()
    print("\n--- ALL TASKS COMPLETED ---")
