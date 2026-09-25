import os
import requests


def ensure_web_template(data_folder: str, template_url: str, timeout: int = 10) -> str:
    """Ensure index.html template exists under data_folder/Templates and return its path.

    If a remote version differs (by content-length) we download it.
    """
    template_dir = os.path.join(data_folder, 'Templates')
    os.makedirs(template_dir, exist_ok=True)
    template_path = os.path.join(template_dir, 'index.html')

    try:
        head = requests.head(template_url, timeout=5)
        remote_size = int(head.headers.get('content-length', 0))
    except Exception:
        remote_size = 0

    if os.path.exists(template_path):
        try:
            local_size = os.path.getsize(template_path)
            if remote_size and local_size == remote_size:
                return template_path
        except Exception:
            pass

    try:
        r = requests.get(template_url, timeout=timeout)
        r.raise_for_status()
        with open(template_path, 'wb') as f:
            f.write(r.content)
        return template_path
    except Exception:
        # if download fails but local exists, return local
        if os.path.exists(template_path):
            return template_path
        raise
