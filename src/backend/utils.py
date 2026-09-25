import re
from typing import List, Dict


def parse_db(text: str) -> List[Dict[str, str]]:
    """Parse a Download-DB.txt style text into list of game dicts.

    This reproduces the simple parsing used in existing scripts: top-level
    lines starting with a source token (GoFile, DropBox, Both, BuzzHeavier)
    start a new game entry and subsequent `Key: value` lines are added.
    """
    lines = text.splitlines()
    games = []
    current = {}
    source_tokens = ['GoFile', 'DropBox', 'Both', 'BuzzHeavier']

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        matched = False
        for token in source_tokens:
            if line.startswith(token):
                if current:
                    games.append(current)
                    current = {}
                # extract name and version if present
                name_part = re.sub(r'^' + re.escape(token) + r'\s*\(', '', line)
                name_part = name_part.split(')')[0] if ')' in name_part else name_part
                current['Source'] = token
                current['Name'] = name_part.strip()
                # try to capture [version]
                if '[' in line and ']' in line:
                    try:
                        current['Version'] = line.split('[')[1].split(']')[0]
                    except Exception:
                        pass
                matched = True
                break
        if matched:
            continue
        if ':' in line:
            k, v = line.split(':', 1)
            current[k.strip()] = v.strip()

    if current:
        games.append(current)
    return games


def safe_request(session, url: str, timeout: int = 10):
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception:
        return None
