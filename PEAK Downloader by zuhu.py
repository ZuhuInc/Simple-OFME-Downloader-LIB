"""
Simple Zuhu Downloader V1.4.7

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
import questionary
from rich.console import Console
from rich.table import Table

# --- Configuration --- #
GITHUB_LINKS_URL = "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/Download-DB.txt"
RAR_PASSWORD = "online-fix.me"
WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
CLEANUP_RAR_FILE = True
# --- End of Configuration --- #

console = Console()

# --- UI Helper Functions --- #
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_status_header(game_name, source_name=None, game_status=None, fix_status=None):
    clear_screen()
    console.print("--- [bold yellow]Zuhu's Downloader Status[/bold yellow] ---")
    console.print(f"[bold]Game:[/]       [cyan]{game_name}[/cyan]", highlight=False)
    if source_name:
        console.print(f"[bold]Source:[/]     [green]{source_name}[/green]", highlight=False)
    if game_status:
        console.print(f"[bold]Game File:[/]  {game_status}")
    if fix_status:
        console.print(f"[bold]Fix File:[/]   {fix_status}")
    console.print("-" * 34 + "\n")

# --- Core Logic Functions --- #
def resolve_gofile_link(gofile_url):
    console.print(f"[*] Resolving GoFile link using direct API calls: {gofile_url}", highlight=False)
    try:
        console.print("[*] Step 1: Requesting a guest account token...")
        headers = {"User-Agent": "Mozilla/5.0"}
        token_response = requests.post("https://api.gofile.io/accounts", headers=headers).json()
        if token_response.get("status") != "ok":
            console.print("[bold red][X] ERROR: Could not create a guest account.[/bold red]"); return None, None
        account_token = token_response["data"]["token"]
        console.print("[green][V] Successfully obtained guest token.[/green]")
        content_id = gofile_url.split("/")[-1]
        hashed_password = hashlib.sha256(RAR_PASSWORD.encode()).hexdigest()
        api_url = f"https://api.gofile.io/contents/{content_id}"
        params = {'wt': '4fd6sg89d7s6', 'password': hashed_password}
        auth_headers = {"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {account_token}"}
        console.print("[*] Step 2: Calling API...")
        content_response = requests.get(api_url, params=params, headers=auth_headers).json()
        if content_response.get("status") != "ok":
            console.print(f"[bold red][X] ERROR: API call failed: {content_response.get('status', 'Unknown')}[/bold red]"); return None, None
        console.print("[green][V] API call successful.[/green]")
        data = content_response.get("data", {})
        if data.get("type") == "folder":
            for child_id, child_data in data.get("children", {}).items():
                if child_data.get("type") == "file":
                    console.print(f"[green][V] Found file '{child_data.get('name', 'Unknown')}' in folder.[/green]", highlight=False); return child_data.get("link"), account_token
            console.print("[bold red][X] ERROR: Folder found, but no files within.[/bold red]"); return None, None
        elif data.get("type") == "file":
            console.print("[green][V] Direct file content detected.[/green]"); return data.get("link"), account_token
        else:
            console.print("[bold red][X] ERROR: Could not determine content type.[/bold red]"); return None, None
    except Exception as e:
        console.print(f"[bold red][X] FATAL ERROR during GoFile resolution: {e}[/bold red]"); return None, None

def fetch_links_from_github(github_raw_url):
    clear_screen()
    console.print("[bold cyan]Fetching latest game list from GitHub...[/bold cyan]")
    try:
        response = requests.get(github_raw_url); response.raise_for_status()
        games = {}
        current_display_name, current_source_name = None, None
        for line in response.text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            match = re.match(r'(.+?)\s*\((.+?)\)\s*\[(.+?)\]', line)
            if match:
                source_name, base_name, version = [s.strip() for s in match.groups()]
                current_display_name = f"{base_name} {version}"; current_source_name = source_name
                games.setdefault(current_display_name, {'base_name': base_name, 'version': version, 'sources': {}})
                games[current_display_name]['sources'][current_source_name] = {'MainParts': [], 'Description': 'N/A', 'ApproxSize': 'N/A'}
            elif ':' in line and current_display_name and current_source_name:
                key, value = [s.strip() for s in line.split(':', 1)]; key_lower = key.lower()
                target_dict = games[current_display_name]['sources'][current_source_name]
                if key_lower.startswith('maingame') or key_lower.startswith('mainpart'): target_dict['MainParts'].append(value)
                elif key_lower == 'fix': target_dict['Fix'] = value
                elif key_lower == 'description': target_dict['Description'] = value
                elif key_lower == 'approxsize': target_dict['ApproxSize'] = value
        if not games: console.print("[bold red][X] ERROR: No valid games found.[/bold red]"); return None
        console.print(f"[bold green][V] Successfully fetched {len(games)} game(s).[/bold green]\n"); return games
    except Exception as e:
        console.print(f"[bold red][X] ERROR: Could not fetch link file: {e}[/bold red]"); return None

def download_file(url, destination_folder, token=None):
    console.print(f"\n[*] Preparing to download from: {url}", highlight=False)
    headers = {'User-Agent': 'Mozilla/5.0'}
    if token: console.print("[*] Using account token for authorization."); headers['Cookie'] = f'accountToken={token}'
    try:
        os.makedirs(destination_folder, exist_ok=True)
        local_filename = url.split('/')[-1].split('?')[0] or "downloaded_file"
        local_filepath = os.path.join(destination_folder, local_filename)
        console.print(f"[*] Starting download: [cyan]{local_filename}[/cyan]", highlight=False)
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            # CHANGED: Readded download rate
            with tqdm.tqdm(total=total_size, unit='iB', unit_scale=True, desc="Downloading", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}, {rate_fmt}]") as progress_bar:
                with open(local_filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): progress_bar.update(len(chunk)); f.write(chunk)
        if total_size != 0 and os.path.getsize(local_filepath) != total_size:
            console.print("[bold red][X] ERROR: Downloaded size mismatch.[/bold red]"); return None
        console.print(f"[green][V] Download complete:[/] {local_filepath}", highlight=False); return local_filepath
    except Exception as e:
        console.print(f"[bold red][X] ERROR during download: {e}[/bold red]"); return None

def winrar_extraction(winrar_path, rar_path, destination_folder, password):
    console.print("\n--- [bold]Starting WinRAR Extraction[/bold] ---")
    if not os.path.exists(winrar_path):
        console.print(f"[bold red][X] CRITICAL ERROR: WinRAR.exe not found at '{winrar_path}'.[/bold red]"); return False
    os.makedirs(destination_folder, exist_ok=True)
    command = [winrar_path, "x", f"-p{password}", "-ibck", "-o+", os.path.abspath(rar_path), os.path.abspath(destination_folder) + os.sep]
    console.print(f"[*] Extracting '[cyan]{os.path.basename(rar_path)}[/cyan]' to '[green]{destination_folder}[/green]'...", highlight=False)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        console.print("[green][V] WinRAR extraction successful.[/green]"); return True
    except subprocess.CalledProcessError as e:
        console.print("[bold red][X] An error occurred during WinRAR execution.[/bold red]")
        error_details = e.stderr.lower()
        if "crc failed" in error_details or "checksum error" in error_details: console.print("[!] [yellow]HINT: CRC error. A downloaded part might be corrupt.[/yellow]")
        elif "password" in error_details: console.print("[!] [yellow]HINT: The password may be incorrect.[/yellow]")
        else: console.print(f"[!] Details: {e.stderr}")
        return False
    except Exception as e:
        console.print(f"[bold red][X] An unexpected error during extraction: {e}[/bold red]"); return False

def display_game_table(games):
    table = Table(title="[bold yellow]Zuhu's Game Downloader[/bold yellow]", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Game Name", min_width=20, style="cyan")
    table.add_column("Version", style="yellow")
    table.add_column("Description", max_width=50)
    table.add_column("Size", justify="right")
    table.add_column("Sources", style="green")
    game_display_names = list(games.keys())
    for i, name in enumerate(game_display_names):
        game_data = games[name]
        sources_list = ", ".join(game_data['sources'].keys())
        first_source_data = list(game_data['sources'].values())[0]
        table.add_row(str(i + 1), game_data['base_name'], game_data['version'], first_source_data.get('Description', 'N/A'), first_source_data.get('ApproxSize', 'N/A'), sources_list)
    console.print(table)

def main():
    games = fetch_links_from_github(GITHUB_LINKS_URL)
    if not games: return
    
    display_game_table(games)
    
    game_display_names = list(games.keys())
    choice_str = questionary.text("Enter the ID of the game you want to download:", validate=lambda text: True if text.isdigit() and 1 <= int(text) <= len(game_display_names) else f"Please enter a number between 1 and {len(game_display_names)}.").ask()
    if not choice_str: return
        
    selected_display_name = game_display_names[int(choice_str) - 1]
    base_game_name = games[selected_display_name]['base_name']
    console.print(f"\n[bold]You selected:[/] [bright_cyan]{selected_display_name}[/bright_cyan]", highlight=False)

    sources_for_game = games[selected_display_name]['sources']
    source_names = list(sources_for_game.keys())
    selected_source_name = source_names[0] if len(source_names) == 1 else questionary.select(f"Choose a download source for '{selected_display_name}':", choices=source_names, use_indicator=True).ask()
    if len(source_names) == 1: console.print(f"[bold]Auto-selected source:[/] [green]{selected_source_name}[/green]")
    if not selected_source_name: return

    user_base_path = ""
    while True:
        prompt = "\n> Enter the BASE path for game extraction (e.g., I:\\Games): "
        user_base_path = input(prompt).strip()
        if os.path.isdir(user_base_path): break
        else: console.print("[bold red]  [X] Invalid path. Please enter an existing directory.[/bold red]")
    user_base_path = os.path.abspath(user_base_path)

    game_file_status, fix_file_status = "Pending...", "Pending..."
    print_status_header(selected_display_name, selected_source_name, game_file_status, fix_file_status)
    
    selected_links = sources_for_game[selected_source_name]
    main_part_urls, fix_url = selected_links.get('MainParts', []), selected_links.get('Fix')
    if not main_part_urls: console.print("[bold red][X] ERROR: Main game URL(s) not found.[/bold red]"); return

    console.print(f"--- Processing {len(main_part_urls)} Main Game File(s) ---")
    temp_download_folder = "temp_downloads"
    main_game_folder_path = None
    downloaded_rar_paths, all_downloads_successful = [], True
    for i, game_url in enumerate(main_part_urls):
        console.print(f"\n--- [bold]Downloading Part {i+1}/{len(main_part_urls)}[/bold] ---")
        direct_game_url, game_token = game_url, None
        if "gofile.io" in game_url:
            direct_game_url, game_token = resolve_gofile_link(game_url)
            if not direct_game_url: all_downloads_successful = False; break
        downloaded_path = download_file(direct_game_url, temp_download_folder, token=game_token)
        if downloaded_path: downloaded_rar_paths.append(downloaded_path)
        else: all_downloads_successful = False; break

    if all_downloads_successful:
        dirs_before = set(os.listdir(user_base_path))
        if winrar_extraction(WINRAR_PATH, downloaded_rar_paths[0], user_base_path, RAR_PASSWORD):
            game_file_status = "[green]Completed[/green]"
            dirs_after = set(os.listdir(user_base_path))
            new_dirs = [d for d in (dirs_after - dirs_before) if os.path.isdir(os.path.join(user_base_path, d))]
            if len(new_dirs) == 1:
                main_game_folder_path = os.path.join(user_base_path, new_dirs[0])
                console.print(f"\n[*] Main game folder auto-detected: '[cyan]{main_game_folder_path}[/cyan]'", highlight=False)
            else: console.print("\n[!] [yellow]Warning: Could not auto-detect new game folder.[/yellow]")
            if CLEANUP_RAR_FILE:
                console.print(f"[*] Cleaning up downloaded part(s)...")
                for rar_path in downloaded_rar_paths:
                    try: os.remove(rar_path); console.print(f"  - Removed '[dim]{os.path.basename(rar_path)}[/dim]'", highlight=False)
                    except Exception as e: console.print(f"  - [!] [red]Failed to remove '{os.path.basename(rar_path)}': {e}[/red]", highlight=False)
        else: game_file_status = "[red]Extraction Failed[/red]"; return
    else: game_file_status = "[red]Download Failed[/red]"; return
    
    if fix_url:
        fix_choice = questionary.confirm("\nA fix/update is available. Download and apply it?", default=True).ask()
        if fix_choice:
            print_status_header(selected_display_name, selected_source_name, game_file_status, "Pending...")
            fix_extraction_path = main_game_folder_path
            if not main_game_folder_path:
                invalid_chars = r'[:*?"<>|]'; clean_game_name = re.sub(invalid_chars, '', base_game_name)
                example_path = os.path.join(user_base_path, clean_game_name)
                while True:
                    console.print("\n[!] [yellow]Could not auto-detect game folder.[/yellow]")
                    prompt = f"> Enter the FULL path for the fix extraction (e.g., {example_path}): "
                    fix_extraction_path = input(prompt).strip()
                    if not fix_extraction_path: console.print("[bold red]  [X] No path provided. Aborting fix.[/bold red]"); fix_extraction_path = None; break
                    if os.path.isdir(fix_extraction_path): break
                    else: console.print("[bold red]  [X] Invalid path. Please enter an existing directory.[/bold red]")
            if not fix_extraction_path: fix_file_status = "[red]Cancelled[/red]"
            else:
                console.print(f"[*] The fix will be extracted to: '[cyan]{fix_extraction_path}[/cyan]'", highlight=False)
                direct_fix_url, fix_token = fix_url, None
                if "gofile.io" in fix_url: direct_fix_url, fix_token = resolve_gofile_link(fix_url)
                if direct_fix_url:
                    downloaded_fix_path = download_file(direct_fix_url, temp_download_folder, token=fix_token)
                    if downloaded_fix_path and winrar_extraction(WINRAR_PATH, downloaded_fix_path, fix_extraction_path, RAR_PASSWORD):
                        fix_file_status = "[green]Completed[/green]"
                        if CLEANUP_RAR_FILE:
                            try: os.remove(downloaded_fix_path); console.print(f"[*] Cleaning up '[dim]{os.path.basename(downloaded_fix_path)}[/dim]'...", highlight=False)
                            except Exception as e: console.print(f"  - [!] [red]Failed to remove '{os.path.basename(downloaded_fix_path)}': {e}[/red]", highlight=False)
                    else: fix_file_status = "[red]Failed[/red]"
                else: fix_file_status = "[red]Failed[/red]"; console.print("[bold red][X] Failed to get direct download link for the fix.[/bold red]")
            if fix_file_status != "[red]Cancelled[/red]":
                console.print("\n[dim]Press Enter to view the final summary...[/dim]")
                input()
        else: fix_file_status = "[yellow]Skipped[/yellow]"
    else: fix_file_status = "[dim]Not Available[/dim]"

    print_status_header(selected_display_name, selected_source_name, game_file_status, fix_file_status)

    try:
        if os.path.exists(temp_download_folder) and not os.listdir(temp_download_folder):
            console.print("[*] Cleaning up empty temporary download directory...")
            os.rmdir(temp_download_folder)
    except Exception as e: console.print(f"[!] [yellow]Could not remove temp directory: {e}[/yellow]")

if __name__ == "__main__":
    try:
        main()
        console.print("\n--- [bold green]ALL TASKS COMPLETED[/bold green] ---")
    except (KeyboardInterrupt, TypeError, EOFError):
        console.print("\n\n[bold yellow]Operation cancelled by user. Exiting.[/bold yellow]")
    except Exception as e:
        console.print(f"\n\n[bold red]An unexpected fatal error occurred:[/bold red]"); console.print_exception(show_locals=True)
    finally:
        if sys.exc_info()[0] in [None, KeyboardInterrupt, TypeError, EOFError]:
            input("\nPress Enter to exit.")
