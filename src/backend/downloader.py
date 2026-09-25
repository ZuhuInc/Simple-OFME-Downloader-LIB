import os
import time
import threading
import requests
from typing import Callable, Optional, Dict, Any, List


class DownloadJob:
    def __init__(self, job_id: int, url: str, dest_file: str, filename: str, meta: Dict[str, Any] = None):
        self.id = job_id
        self.url = url
        self.dest_file = dest_file
        self.filename = filename
        self.meta = meta or {}
        self.status = "queued"  # queued, downloading, paused, cancelled, completed, error
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
    def __init__(self, download_path: Optional[str] = None, max_concurrency: int = 2):
        self.download_path = download_path or os.path.join(os.path.expanduser("~"), "Downloads", "OFME")
        os.makedirs(self.download_path, exist_ok=True)
        self.max_concurrency = max_concurrency
        self.jobs: Dict[int, DownloadJob] = {}
        self._queue: List[int] = []
        self._active_workers: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._callback: Optional[Callable] = None
        self._job_counter = 1

    def set_callback(self, callback: Callable):
        self._callback = callback

    def _notify(self, job: DownloadJob):
        if self._callback:
            try:
                self._callback(job.to_dict())
            except Exception as e:
                print(f"[Downloader] Callback error: {e}")

    def add_job(self, url: str, filename: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> str:
        filename = filename or os.path.basename(url.split("?")[0]) or "download.bin"
        dest_file = os.path.join(self.download_path, filename)
        with self._lock:
            job_id = f"job_{self._job_counter}"
            self._job_counter += 1
            job = DownloadJob(job_id, url, dest_file, filename, meta)
            self.jobs[job_id] = job
            self._queue.append(job_id)

        self._notify(job)
        self._check_queue()
        return job_id

    def get_job(self, job_id: Any) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(str(job_id))
        return job.to_dict() if job else None

    def pause_job(self, job_id: int) -> bool:
        job = self.jobs.get(job_id)
        if job and job.status == "downloading":
            job.status = "paused"
            job._pause_event.clear()
            self._notify(job)
            return True
        return False

    def resume_job(self, job_id: int) -> bool:
        job = self.jobs.get(job_id)
        if job and job.status == "paused":
            job.status = "downloading"
            job._pause_event.set()
            self._notify(job)
            return True
        return False

    def cancel_job(self, job_id: int) -> bool:
        job = self.jobs.get(job_id)
        if job:
            job.status = "cancelled"
            job._cancel_flag = True
            job._pause_event.set()
            self._notify(job)
            return True
        return False

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self.jobs.values()]

    def _check_queue(self):
        with self._lock:
            running_count = sum(1 for j in self.jobs.values() if j.status == "downloading")
            while running_count < self.max_concurrency and self._queue:
                next_id = self._queue.pop(0)
                job = self.jobs.get(next_id)
                if job and job.status == "queued":
                    job.status = "downloading"
                    t = threading.Thread(target=self._download_worker, args=(job,), daemon=True)
                    self._active_workers.append(t)
                    t.start()
                    running_count += 1

    def _download_worker(self, job: DownloadJob):
        part_path = job.dest_file + ".part"
        last_time = time.time()
        last_bytes = 0

        try:
            headers = {}
            if os.path.exists(part_path):
                existing_size = os.path.getsize(part_path)
                if existing_size > 0:
                    headers["Range"] = f"bytes={existing_size}-"
                    job.downloaded_bytes = existing_size

            with requests.get(job.url, headers=headers, stream=True, timeout=20) as resp:
                if resp.status_code in (200, 206):
                    content_length = int(resp.headers.get("content-length", 0))
                    job.total_bytes = job.downloaded_bytes + content_length

                    mode = "ab" if "Range" in headers else "wb"
                    with open(part_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if job._cancel_flag:
                                job.status = "cancelled"
                                self._notify(job)
                                return

                            job._pause_event.wait()

                            if chunk:
                                f.write(chunk)
                                job.downloaded_bytes += len(chunk)
                                if job.total_bytes > 0:
                                    job.progress = (job.downloaded_bytes / job.total_bytes) * 100.0

                                # Calculate speed
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

                                    self._notify(job)

                    if os.path.exists(job.dest_file):
                        try:
                            os.remove(job.dest_file)
                        except Exception:
                            pass
                    os.replace(part_path, job.dest_file)
                    job.status = "completed"
                    job.progress = 100.0
                    job.speed_bytes = 0
                    job.eta = "Done"
                    self._notify(job)
                else:
                    job.status = "error"
                    job.error_msg = f"HTTP {resp.status_code}"
                    self._notify(job)

        except Exception as e:
            job.status = "error"
            job.error_msg = str(e)
            self._notify(job)
        finally:
            self._check_queue()
