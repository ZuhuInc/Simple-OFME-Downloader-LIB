import os
import sys
try:
    import winreg
except Exception:
    winreg = None


def normalize_browser_name(raw_name: str) -> str:
    raw = raw_name.lower()
    if 'brave' in raw: return 'Brave'
    if 'opera gx' in raw or 'operagx' in raw: return 'Opera GX'
    if 'chrome' in raw and 'google' in raw: return 'Google Chrome'
    if 'firefox' in raw: return 'Firefox'
    if 'opera' in raw and 'gx' not in raw: return 'Opera'
    if 'vivaldi' in raw: return 'Vivaldi'
    if 'edge' in raw: return 'Microsoft Edge'
    return raw_name


def get_installed_browsers() -> dict:
    found = {}
    prog_files = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    prog_files_x86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
    local_appdata = os.environ.get('LOCALAPPDATA', r'C:\Users\Default\AppData\Local')

    potential = {
        'Google Chrome': [os.path.join(prog_files, 'Google', 'Chrome', 'Application', 'chrome.exe')],
        'Brave': [os.path.join(prog_files, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe')],
        'Firefox': [os.path.join(prog_files, 'Mozilla Firefox', 'firefox.exe')],
    }

    for name, paths in potential.items():
        for p in paths:
            if os.path.exists(p):
                found[name] = p
                break

    # try registry if available
    if winreg:
        for hive, reg_path in [(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Clients\StartMenuInternet"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Clients\StartMenuInternet")]:
            try:
                with winreg.OpenKey(hive, reg_path) as key:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, i); i += 1
                            name = normalize_browser_name(sub)
                            if name in found: continue
                            cmd_path = reg_path + '\\' + sub + '\\shell\\open\\command'
                            try:
                                with winreg.OpenKey(hive, cmd_path) as cmdk:
                                    val, _ = winreg.QueryValueEx(cmdk, '')
                                    val = val.strip('"')
                                    if os.path.exists(val): found[name] = val
                            except Exception:
                                pass
                        except OSError:
                            break
            except Exception:
                pass

    return found
