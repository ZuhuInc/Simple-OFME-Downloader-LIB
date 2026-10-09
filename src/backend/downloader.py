"""
Fanta OFME Downloader - Core Download Manager & Worker Queue
Handles multi-threaded file downloads, resume support, dynamic stream resolution, automated archive extraction,
and real-time event broadcasting.
"""

import os
import re
import time
import threading
import requests
from typing import Callable, Optional, Dict, Any, List


class DownloadJob:
    def __init__(self, job_id: str, url: str, dest_file: str, filename: str, meta: Dict[str, Any] = None):
        self.id = job_id
        self.url = url
        self.dest_file = dest_file
        self.filename = filename
        self.meta = meta or {}
        self.status = "queued"  # queued, resolving, connecting, downloading, extracting, paused, cancelled, completed, error
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.speed_bytes = 0
        self.progress = 0.0
        self.eta = ""
        self.error_msg = ""
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_flag = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "dest_file": self.dest_file,
            "meta": self.meta,
            "status": self.status,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "speed_bytes": self.speed_bytes,
            "progress": self.progress,
            "eta": self.eta,
            "error_msg": self.error_msg
        }


class Downloader:
    def __init__(
        self,
        download_path: Optional[str] = None,
        max_concurrency: int = 2,
        config: Optional[Any] = None,
        extractor: Optional[Any] = None
    ):
        self.config = config
        self.extractor = extractor
        self.download_path = download_path or os.path.join(os.path.expanduser("~"), "Downloads", "OFME")
        os.makedirs(self.download_path, exist_ok=True)
        self.max_concurrency = max_concurrency
        self.jobs: Dict[str, DownloadJob] = {}
        self._queue: List[str] = []
        self._active_workers: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._callback: Optional[Callable] = None
        self._job_counter = 1

    def set_callback(self, callback: Callable):
        self._callback = callback

    def _notify(self, job_data: Any):
        if self._callback:
            try:
                if isinstance(job_data, DownloadJob):
                    self._callback(job_data.to_dict())
                elif isinstance(job_data, dict):
                    self._callback(job_data)
            except Exception as e:
                print(f"[Downloader] Callback error: {e}", flush=True)

    def add_job(self, url: str, filename: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> str:
        filename = filename or os.path.basename(url.split("?")[0]) or "download.bin"
        dest_file = os.path.join(self.download_path, filename)
        with self._lock:
            job_id = f"job_{self._job_counter}"
            self._job_counter += 1
            job = DownloadJob(job_id, url, dest_file, filename, meta)
            self.jobs[job_id] = job
            self._queue.append(job_id)

        title = (meta or {}).get("title", filename)
        print(f"[Downloader] [{job_id}] Queued: '{title}' ({filename}) from {url}", flush=True)

        self._notify(job)
        self._check_queue()
        return job_id

    def get_job(self, job_id: Any) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(str(job_id))
        return job.to_dict() if job else None

    def pause_job(self, job_id: Any) -> bool:
        job = self.jobs.get(str(job_id))
        if job and job.status in ("downloading", "connecting", "resolving"):
            job.status = "paused"
            job._pause_event.clear()
            print(f"[Downloader] [{job_id}] Paused.", flush=True)
            self._notify(job)
            return True
        return False

    def resume_job(self, job_id: Any) -> bool:
        job = self.jobs.get(str(job_id))
        if job and job.status == "paused":
            job.status = "downloading"
            job._pause_event.set()
            print(f"[Downloader] [{job_id}] Resumed.", flush=True)
            self._notify(job)
            return True
        return False

    def cancel_job(self, job_id: Any) -> bool:
        job = self.jobs.get(str(job_id))
        if job:
            job.status = "cancelled"
            job._cancel_flag = True
            job._pause_event.set()
            print(f"[Downloader] [{job_id}] Cancelled by user.", flush=True)
            self._notify(job)
            return True
        return False

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self.jobs.values()]

    def _check_queue(self):
        with self._lock:
            running_count = sum(1 for j in self.jobs.values() if j.status in ("resolving", "connecting", "downloading", "extracting"))
            while running_count < self.max_concurrency and self._queue:
                next_id = self._queue.pop(0)
                job = self.jobs.get(next_id)
                if job and job.status == "queued":
                    job.status = "resolving"
                    self._notify(job)
                    t = threading.Thread(target=self._download_worker, args=(job,), daemon=True)
                    self._active_workers.append(t)
                    t.start()
                    running_count += 1

    def _download_worker(self, job: DownloadJob):
        title = job.meta.get("title", job.filename)
        print(f"\n[Downloader] [{job.id}] ==========================================", flush=True)
        print(f"[Downloader] [{job.id}] Starting download process for '{title}'", flush=True)
        print(f"[Downloader] [{job.id}] Input URL: {job.url}", flush=True)
        print(f"[Downloader] [{job.id}] Destination: {job.dest_file}", flush=True)

        # 1. Resolve host link to direct CDN download stream
        download_url = job.url
        resolved_cookies = None
        custom_token = self.config.get("gofile_token") if self.config else None

        job.status = "resolving"
        self._notify(job)

        try:
            from .resolver import LinkResolver, GoFileResolver
            resolver_cls = LinkResolver
        except Exception:
            try:
                from resolver import LinkResolver, GoFileResolver
                resolver_cls = LinkResolver
            except Exception:
                resolver_cls = None

        if resolver_cls:
            try:
                print(f"[Downloader] [{job.id}] Step 1/3: Resolving direct stream URL...", flush=True)
                resolved_url, resolved_name, cookies = resolver_cls.resolve_url(
                    job.url,
                    custom_gofile_token=custom_token,
                    game_name=title,
                    progress_callback=lambda msg: print(f"[Downloader] [{job.id}] {msg}", flush=True)
                )
                if resolved_url:
                    download_url = resolved_url
                    resolved_cookies = cookies
                    print(f"[Downloader] [{job.id}] Direct CDN stream URL: {download_url}", flush=True)
                if resolved_name and job.filename.endswith(".bin"):
                    job.filename = resolved_name
                    job.dest_file = os.path.join(self.download_path, resolved_name)
            except Exception as res_err:
                print(f"[Downloader] [{job.id}] Link resolution notice: {res_err}", flush=True)

        if "gofile.io/d/" in download_url:
            job.status = "error"
            job.error_msg = "GoFile connection timed out (server unreachable or blocked by ISP/VPN). Try 'Open Mirror'."
            print(f"[Downloader] [{job.id}] ERROR: {job.error_msg}", flush=True)
            self._notify(job)
            return

        job.status = "connecting"
        self._notify(job)
        print(f"[Downloader] [{job.id}] Step 2/3: Connecting to CDN stream...", flush=True)

        part_path = job.dest_file + ".part"
        last_time = time.time()
        last_bytes = 0
        last_milestone = 0

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }

            # If downloading from GoFile CDN, ensure authentication headers and cookies are attached
            if "gofile.io" in download_url:
                headers["Referer"] = "https://gofile.io/"
                token = None
                if resolved_cookies and "accountToken" in resolved_cookies:
                    token = resolved_cookies["accountToken"]
                elif custom_token:
                    token = custom_token
                else:
                    try:
                        from .resolver import GoFileResolver
                        token = GoFileResolver.get_token()
                    except Exception:
                        try:
                            from resolver import GoFileResolver
                            token = GoFileResolver.get_token()
                        except Exception:
                            pass
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    if not resolved_cookies:
                        resolved_cookies = {}
                    resolved_cookies["accountToken"] = token

            if os.path.exists(part_path):
                existing_size = os.path.getsize(part_path)
                if existing_size > 0:
                    headers["Range"] = f"bytes={existing_size}-"
                    job.downloaded_bytes = existing_size
                    print(f"[Downloader] [{job.id}] Resuming from existing partial file: {existing_size} bytes ({existing_size / (1024*1024):.2f} MB)", flush=True)

            with requests.get(download_url, headers=headers, cookies=resolved_cookies, stream=True, timeout=30) as resp:
                if resp.status_code in (200, 206):
                    content_type = resp.headers.get("content-type", "").lower()
                    content_length = int(resp.headers.get("content-length", 0))
                    total_expected = job.downloaded_bytes + content_length

                    # Safety check: if server returned an HTML landing page instead of a game stream
                    if content_type.startswith("text/html") and (total_expected < 100000 or content_length == 0):
                        if os.path.exists(part_path):
                            try: os.remove(part_path)
                            except Exception: pass
                        job.status = "error"
                        job.error_msg = "Download link resolved to an HTML webpage rather than a direct archive stream. Check hoster link or token."
                        print(f"[Downloader] [{job.id}] ERROR: {job.error_msg}", flush=True)
                        self._notify(job)
                        return

                    job.total_bytes = total_expected
                    total_mb = job.total_bytes / (1024 * 1024)
                    print(f"[Downloader] [{job.id}] Connected! HTTP {resp.status_code} | Total Size: {total_mb:.2f} MB | Content-Type: {content_type}", flush=True)

                    job.status = "downloading"
                    self._notify(job)
                    print(f"[Downloader] [{job.id}] Step 3/3: Downloading data stream...", flush=True)

                    mode = "ab" if "Range" in headers else "wb"
                    with open(part_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if job._cancel_flag:
                                job.status = "cancelled"
                                print(f"[Downloader] [{job.id}] Download cancelled.", flush=True)
                                self._notify(job)
                                return

                            job._pause_event.wait()

                            if chunk:
                                f.write(chunk)
                                job.downloaded_bytes += len(chunk)
                                if job.total_bytes > 0:
                                    job.progress = (job.downloaded_bytes / job.total_bytes) * 100.0

                                # Calculate speed and ETA
                                now = time.time()
                                if now - last_time >= 0.5:
                                    delta_bytes = job.downloaded_bytes - last_bytes
                                    job.speed_bytes = int(delta_bytes / (now - last_time))
                                    last_bytes = job.downloaded_bytes
                                    last_time = now

                                    if job.speed_bytes > 0 and job.total_bytes > 0:
                                        remaining = max(0, job.total_bytes - job.downloaded_bytes)
                                        eta_secs = int(remaining / job.speed_bytes)
                                        mins, secs = divmod(eta_secs, 60)
                                        job.eta = f"{mins}m {secs}s"

                                    # Log milestone progress every 25%
                                    current_milestone = int(job.progress // 25) * 25
                                    if current_milestone > last_milestone and current_milestone < 100:
                                        last_milestone = current_milestone
                                        dl_mb = job.downloaded_bytes / (1024 * 1024)
                                        sp_mb = job.speed_bytes / (1024 * 1024)
                                        print(f"[Downloader] [{job.id}] Progress: {current_milestone}% ({dl_mb:.1f} MB / {total_mb:.1f} MB) @ {sp_mb:.2f} MB/s | ETA: {job.eta}", flush=True)

                                    self._notify(job)

                    if os.path.exists(job.dest_file):
                        try: os.remove(job.dest_file)
                        except Exception: pass
                    os.replace(part_path, job.dest_file)
                    print(f"[Downloader] [{job.id}] Download SUCCESS: {job.dest_file} (100%)", flush=True)

                    # Automated Extraction Workflow
                    auto_extract = job.meta.get("auto_extract")
                    if auto_extract is None:
                        auto_extract = self.config.get("auto_extract", True) if self.config else True
                    is_archive = job.dest_file.lower().endswith((".rar", ".zip", ".7z"))

                    if auto_extract and self.extractor and is_archive:
                        job.status = "extracting"
                        job.progress = 100.0
                        job.speed_bytes = 0
                        job.eta = "Extracting..."
                        print(f"[Downloader] [{job.id}] Starting automated archive extraction for '{title}'...", flush=True)
                        self._notify(job)

                        # Determine if this is a fix or main game
                        job_type = job.meta.get("type", "main")
                        is_fix = (job_type == "fix") or ("fix" in job.filename.lower()) or ("_fix." in job.dest_file.lower())

                        custom_extract_dir = job.meta.get("extract_dir") or job.meta.get("custom_location")

                        # Check existing game install location from Data.json
                        existing_location = None
                        if self.config and hasattr(self.config, "data") and title:
                            norm_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
                            for k, v in self.config.data.items():
                                k_norm = re.sub(r'[^a-zA-Z0-9]', '', k).lower()
                                if k.upper() == title.upper() or k_norm == norm_title:
                                    existing_location = v.get("location")
                                    break

                        if not existing_location:
                            existing_location = job.meta.get("location")

                        default_base = (
                            self.config.get("default_download_path") or
                            self.config.get("extract_path") or
                            r"D:\GAMES2"
                        ) if self.config else r"D:\GAMES2"

                        if custom_extract_dir:
                            extract_dir = custom_extract_dir
                        elif is_fix:
                            # Patch must unpack directly inside the existing game directory
                            if existing_location and os.path.isdir(existing_location):
                                extract_dir = existing_location
                            else:
                                extract_dir = os.path.join(default_base, title)
                        else:
                            # Main game / update:
                            if existing_location and os.path.isdir(existing_location):
                                parent_dir = os.path.dirname(os.path.normpath(existing_location))
                                extract_dir = parent_dir if (parent_dir and (os.path.exists(parent_dir) or len(parent_dir) <= 3)) else existing_location
                            else:
                                extract_dir = default_base

                        rar_password = self.config.get("rar_password", "online-fix.me") if self.config else "online-fix.me"
                        delete_after = job.meta.get("auto_delete_archive")
                        if delete_after is None:
                            delete_after = self.config.get("auto_delete_archive", True) if self.config else True

                        print(f"[Downloader] [{job.id}] Destination folder: {extract_dir} (is_fix={is_fix}, delete_after={delete_after})", flush=True)

                        def on_extract_progress(info):
                            pass

                        extract_res = self.extractor.extract_archive(
                            archive_path=job.dest_file,
                            extract_dir=extract_dir,
                            password=rar_password,
                            delete_after=delete_after,
                            game_title=title,
                            is_fix=is_fix,
                            progress_cb=on_extract_progress
                        )

                        if extract_res.get("success"):
                            job.status = "completed"
                            job.eta = "Installed / Ready"
                            target_game_dir = extract_res.get("game_dir") or extract_res.get("extract_dir")
                            job.meta["extracted_dir"] = target_game_dir
                            job.meta["exe_path"] = extract_res.get("exe_path")

                            # Automatically record in installed games catalog
                            if self.config and hasattr(self.config, "data") and title:
                                key = title.upper()
                                existing_record = self.config.data.get(key, {})
                                existing_record["downloaded"] = True
                                existing_record["location"] = target_game_dir
                                if job.meta.get("version"):
                                    existing_record["version"] = job.meta.get("version")
                                self.config.data[key] = existing_record
                                self.config.save()
                                print(f"[Downloader] [{job.id}] Game '{title}' marked as installed at: {target_game_dir}", flush=True)

                            print(f"[Downloader] [{job.id}] Extraction SUCCESS: {target_game_dir}", flush=True)
                            print(f"[Downloader] [{job.id}] ==========================================\n", flush=True)
                            self._notify(job)
                        else:
                            job.status = "completed"
                            job.eta = "Done (Extraction Failed)"
                            job.error_msg = f"Extraction notice: {extract_res.get('error')}"
                            print(f"[Downloader] [{job.id}] Extraction error: {extract_res.get('error')}", flush=True)
                            print(f"[Downloader] [{job.id}] ==========================================\n", flush=True)
                            self._notify(job)
                    else:
                        job.status = "completed"
                        job.progress = 100.0
                        job.speed_bytes = 0
                        job.eta = "Done"
                        print(f"[Downloader] [{job.id}] ==========================================\n", flush=True)
                        self._notify(job)

                else:
                    job.status = "error"
                    job.error_msg = f"Server returned HTTP {resp.status_code}"
                    print(f"[Downloader] [{job.id}] ERROR: {job.error_msg}", flush=True)
                    self._notify(job)

        except Exception as e:
            job.status = "error"
            job.error_msg = str(e)
            print(f"[Downloader] [{job.id}] EXCEPTION: {job.error_msg}", flush=True)
            self._notify(job)
        finally:
            self._check_queue()
