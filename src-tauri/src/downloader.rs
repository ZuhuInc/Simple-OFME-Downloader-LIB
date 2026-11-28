use crate::backend;
use crate::config::{get_default_games_dir, get_home_dir, ConfigManager};
use crate::database::normalize_key;
use crate::extractor::{parse_multipart_number, ExtractOptions, Extractor, DEFAULT_RAR_PASSWORD};
use crate::resolver::{extract_content_disposition_filename, format_cookie_header, resolve_url, GoFileResolver};
use crate::{find_installed_game_key, AppState};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

pub fn sanitize_filename(filename: &str) -> String {
    if filename.trim().is_empty() {
        return "download.bin".to_string();
    }

    // Replace ':' runs with ' -' preserving readable titles
    let mut after_colon = String::with_capacity(filename.len());
    let mut prev_colon = false;
    for ch in filename.chars() {
        if ch == ':' {
            if !prev_colon {
                after_colon.push_str(" -");
                prev_colon = true;
            }
        } else {
            prev_colon = false;
            let mapped = match ch {
                '<' | '>' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
                _ => ch,
            };
            after_colon.push(mapped);
        }
    }

    let collapsed = after_colon
        .split_whitespace()
        .collect::<Vec<&str>>()
        .join(" ");
    let trimmed = collapsed.trim_matches(|c| c == '.' || c == ' ');
    if trimmed.is_empty() {
        "download.bin".to_string()
    } else {
        trimmed.to_string()
    }
}

pub fn parse_size_str(raw: &Value) -> u64 {
    if let Some(n) = raw.as_u64() {
        return n;
    }
    if let Some(n) = raw.as_i64() {
        return n.max(0) as u64;
    }
    if let Some(f) = raw.as_f64() {
        return f.max(0.0) as u64;
    }
    let s = raw.as_str().unwrap_or("").trim().to_ascii_uppercase();
    let bytes = s.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i].is_ascii_digit() {
            let start = i;
            while i < bytes.len() && (bytes[i].is_ascii_digit() || bytes[i] == b'.') {
                i += 1;
            }
            if let Ok(val) = s[start..i].parse::<f64>() {
                let unit = s[i..].trim_start();
                let mult: f64 = if unit.starts_with('T') {
                    1024_f64.powi(4)
                } else if unit.starts_with('G') {
                    1024_f64.powi(3)
                } else if unit.starts_with('M') {
                    1024_f64.powi(2)
                } else if unit.starts_with('K') {
                    1024.0
                } else {
                    1.0
                };
                return (val * mult) as u64;
            }
        }
        i += 1;
    }
    10 * 1024 * 1024 * 1024 // default 10GB
}

pub fn format_bytes_human(b: u64) -> String {
    const KB: f64 = 1024.0;
    const MB: f64 = KB * 1024.0;
    const GB: f64 = MB * 1024.0;
    const TB: f64 = GB * 1024.0;
    let bf = b as f64;
    if bf >= TB {
        format!("{:.1} TB", bf / TB)
    } else if bf >= GB {
        format!("{:.1} GB", bf / GB)
    } else if bf >= MB {
        format!("{:.1} MB", bf / MB)
    } else if bf >= KB {
        format!("{:.1} KB", bf / KB)
    } else {
        format!("{} B", b)
    }
}

fn existing_ancestor_dir(raw_path: &str) -> PathBuf {
    let mut cur = if raw_path.trim().is_empty() {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    } else {
        PathBuf::from(raw_path.trim())
    };
    while !cur.as_os_str().is_empty() && !cur.exists() {
        let Some(parent) = cur.parent() else {
            break;
        };
        if parent == cur {
            break;
        }
        cur = parent.to_path_buf();
    }
    if cur.exists() {
        cur
    } else {
        let drv = extract_drive_prefix(raw_path);
        PathBuf::from(format!("{}\\", drv))
    }
}

fn extract_drive_prefix(path: &str) -> String {
    let clean = path.trim().replace('/', "\\");
    let b = clean.as_bytes();
    if b.len() >= 2 && b[0].is_ascii_alphabetic() && b[1] == b':' {
        return format!("{}:", (b[0] as char).to_ascii_uppercase());
    }
    "C:".to_string()
}

#[cfg(target_os = "windows")]
fn free_disk_bytes(path: &Path) -> u64 {
    #[link(name = "kernel32")]
    extern "system" {
        fn GetDiskFreeSpaceExW(
            lp_directory_name: *const u16,
            lp_free_bytes_available_to_caller: *mut u64,
            lp_total_number_of_bytes: *mut u64,
            lp_total_number_of_free_bytes: *mut u64,
        ) -> i32;
    }

    let wide: Vec<u16> = path
        .to_string_lossy()
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    let mut free_avail: u64 = 0;
    let mut total: u64 = 0;
    let mut total_free: u64 = 0;
    let ok = unsafe {
        GetDiskFreeSpaceExW(
            wide.as_ptr(),
            &mut free_avail,
            &mut total,
            &mut total_free,
        )
    };
    if ok != 0 {
        free_avail
    } else {
        100 * 1024 * 1024 * 1024
    }
}

#[cfg(not(target_os = "windows"))]
fn free_disk_bytes(_path: &Path) -> u64 {
    100 * 1024 * 1024 * 1024
}

pub fn check_disk_space(install_path: &str, download_path: &str, game_size_raw: &Value) -> Value {
    let dl_path_str = if download_path.trim().is_empty() {
        get_home_dir()
            .join("Downloads")
            .join("OFME")
            .to_string_lossy()
            .to_string()
    } else {
        download_path.trim().to_string()
    };

    let inst_path_input = if install_path.trim().is_empty() {
        dl_path_str.as_str()
    } else {
        install_path.trim()
    };

    let download_bytes = parse_size_str(game_size_raw);
    let extract_bytes = (download_bytes as f64 * 1.08) as u64;

    let dl_check = existing_ancestor_dir(&dl_path_str);
    let inst_check = existing_ancestor_dir(inst_path_input);

    let dl_drive = extract_drive_prefix(&dl_check.to_string_lossy());
    let inst_drive = extract_drive_prefix(&inst_check.to_string_lossy());
    let same_drive = dl_drive == inst_drive;

    let dl_free = free_disk_bytes(&dl_check);
    let inst_free = free_disk_bytes(&inst_check);

    let dl_needed = download_bytes;
    let inst_needed = extract_bytes;
    let (dl_ok, inst_ok, has_sufficient, warning): (bool, bool, bool, Option<String>) = if same_drive {
        let total_needed = download_bytes.saturating_add(extract_bytes);
        let ok = dl_free >= total_needed;
        let warn = if !ok {
            Some(format!(
                "Drive {} has only {} free, but needs at least {} ({} download + {} extraction) for both to co-exist on the same drive.",
                dl_drive,
                format_bytes_human(dl_free),
                format_bytes_human(total_needed),
                format_bytes_human(download_bytes),
                format_bytes_human(extract_bytes)
            ))
        } else {
            None
        };
        (ok, ok, ok, warn)
    } else {
        let dok = dl_free >= dl_needed;
        let iok = inst_free >= inst_needed;
        let ok = dok && iok;
        let warn = if !dok && !iok {
            Some(format!(
                "Both drives are low on space! Download Drive ({}) needs {} (has {}) and Install Drive ({}) needs {} (has {}).",
                dl_drive,
                format_bytes_human(dl_needed),
                format_bytes_human(dl_free),
                inst_drive,
                format_bytes_human(inst_needed),
                format_bytes_human(inst_free)
            ))
        } else if !dok {
            Some(format!(
                "Download Drive ({}) has only {} free, but needs {} for the download archives.",
                dl_drive,
                format_bytes_human(dl_free),
                format_bytes_human(dl_needed)
            ))
        } else if !iok {
            Some(format!(
                "Install Drive ({}) has only {} free, but needs {} to extract the game files.",
                inst_drive,
                format_bytes_human(inst_free),
                format_bytes_human(inst_needed)
            ))
        } else {
            None
        };
        (dok, iok, ok, warn)
    };

    json!({
        "success": true,
        "same_drive": same_drive,
        "has_sufficient_space": has_sufficient,
        "warning": warning,
        "download": {
            "drive": dl_drive,
            "path": dl_path_str,
            "free_bytes": dl_free,
            "free_str": format_bytes_human(dl_free),
            "needed_bytes": dl_needed,
            "needed_str": format_bytes_human(dl_needed),
            "ok": dl_ok,
        },
        "install": {
            "drive": inst_drive,
            "path": install_path,
            "free_bytes": inst_free,
            "free_str": format_bytes_human(inst_free),
            "needed_bytes": inst_needed,
            "needed_str": format_bytes_human(inst_needed),
            "ok": inst_ok,
        },
        "total_needed_str": format_bytes_human(download_bytes.saturating_add(extract_bytes)),
    })
}

pub struct JobControl {
    pub paused: AtomicBool,
    pub cancelled: AtomicBool,
}

impl JobControl {
    pub fn new() -> Self {
        Self {
            paused: AtomicBool::new(false),
            cancelled: AtomicBool::new(false),
        }
    }
}

#[derive(Clone)]
pub struct DownloadJob {
    pub id: String,
    pub url: String,
    pub filename: String,
    pub dest_file: String,
    pub meta: Map<String, Value>,
    pub status: String,
    pub total_bytes: u64,
    pub downloaded_bytes: u64,
    pub speed_bytes: u64,
    pub progress: f64,
    pub eta: String,
    pub error_msg: String,
    pub generation: u64,
    pub control: Arc<JobControl>,
}

impl DownloadJob {
    pub fn new(
        id: String,
        url: String,
        dest_file: String,
        filename: String,
        meta: Map<String, Value>,
        generation: u64,
    ) -> Self {
        Self {
            id,
            url,
            filename,
            dest_file,
            meta,
            status: "queued".to_string(),
            total_bytes: 0,
            downloaded_bytes: 0,
            speed_bytes: 0,
            progress: 0.0,
            eta: String::new(),
            error_msg: String::new(),
            generation,
            control: Arc::new(JobControl::new()),
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
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
            "error_msg": self.error_msg,
        })
    }
}

struct DownloadState {
    jobs: Vec<DownloadJob>,
    queue: Vec<String>,
    job_counter: u64,
    generation_counter: u64,
}

impl Default for DownloadState {
    fn default() -> Self {
        Self {
            jobs: Vec::new(),
            queue: Vec::new(),
            job_counter: 1,
            generation_counter: 1,
        }
    }
}

pub struct DownloadManager {
    inner: Mutex<DownloadState>,
}

impl Default for DownloadManager {
    fn default() -> Self {
        Self {
            inner: Mutex::new(DownloadState::default()),
        }
    }
}

impl DownloadManager {
    pub fn resolve_download_dir(cfg: &ConfigManager) -> PathBuf {
        let configured = cfg.get_str("download_path");
        let default_dl = get_home_dir().join("Downloads").join("OFME");
        let chosen = if !configured.trim().is_empty() {
            PathBuf::from(configured.trim())
        } else {
            default_dl.clone()
        };
        if fs::create_dir_all(&chosen).is_ok() {
            return chosen;
        }
        let _ = fs::create_dir_all(&default_dl);
        default_dl
    }

    fn job_match_key(meta: &Map<String, Value>) -> (String, String, String) {
        let raw_title = meta.get("title").and_then(|v| v.as_str()).unwrap_or("");
        let title = normalize_key(raw_title);
        let part_idx = meta
            .get("part_index")
            .and_then(|v| {
                v.as_u64()
                    .map(|n| n.to_string())
                    .or_else(|| v.as_str().map(str::to_string))
            })
            .unwrap_or_default();
        let job_type = meta
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("main")
            .trim()
            .to_lowercase();
        (title, part_idx, job_type)
    }

    fn is_multipart_job(job: &DownloadJob) -> bool {
        let meta_type = job
            .meta
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if meta_type.starts_with("main_part") {
            return true;
        }
        if job
            .meta
            .get("total_parts")
            .and_then(|v| v.as_u64())
            .is_some_and(|n| n > 1)
        {
            return true;
        }
        parse_multipart_number(&job.filename).is_some()
    }

    fn part_sort_key(sj: &DownloadJob) -> u32 {
        if let Some(p) = sj.meta.get("part_index").and_then(|v| v.as_u64()) {
            return p as u32;
        }
        if let Some(t) = sj.meta.get("type").and_then(|v| v.as_str()) {
            if let Some(after) = t.strip_prefix("main_part_") {
                if let Ok(n) = after.parse::<u32>() {
                    return n;
                }
            }
        }
        if let Some((_, _, n)) = parse_multipart_number(&sj.filename) {
            return n;
        }
        999
    }

    fn get_siblings_snapshot(jobs: &[DownloadJob], anchor: &DownloadJob) -> Vec<DownloadJob> {
        if !Self::is_multipart_job(anchor) {
            return vec![anchor.clone()];
        }
        let norm_title = anchor
            .meta
            .get("title")
            .and_then(|v| v.as_str())
            .map(normalize_key)
            .unwrap_or_default();
        let game_id = anchor
            .meta
            .get("game_id")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        let mut siblings: Vec<DownloadJob> = jobs
            .iter()
            .filter(|j| {
                if j.status == "cancelled" || j.control.cancelled.load(Ordering::Relaxed) {
                    return false;
                }
                if !Self::is_multipart_job(j) {
                    return false;
                }
                if !game_id.is_empty()
                    && j.meta.get("game_id").and_then(|v| v.as_str()) == Some(game_id)
                {
                    return true;
                }
                let j_norm = j
                    .meta
                    .get("title")
                    .and_then(|v| v.as_str())
                    .map(normalize_key)
                    .unwrap_or_default();
                !norm_title.is_empty() && j_norm == norm_title
            })
            .cloned()
            .collect();

        if siblings.is_empty() {
            siblings.push(anchor.clone());
        }
        siblings.sort_by_key(Self::part_sort_key);

        let mut deduped = Vec::new();
        let mut seen: HashSet<(u32, String)> = HashSet::new();
        for sj in siblings {
            let dest_norm = if sj.dest_file.is_empty() {
                sj.filename.to_lowercase()
            } else {
                sj.dest_file.replace('/', "\\").to_lowercase()
            };
            let k = (Self::part_sort_key(&sj), dest_norm);
            if seen.insert(k) {
                deduped.push(sj);
            }
        }
        deduped
    }

    fn emit_progress(app: &AppHandle, job_json: &Value) {
        let _ = app.emit("download-progress", job_json.clone());
    }

    pub fn add_job(
        self: &Arc<Self>,
        app: &AppHandle,
        download_dir: &Path,
        max_concurrency: usize,
        url: String,
        filename_opt: Option<String>,
        meta: Map<String, Value>,
    ) -> String {
        let raw_fn = filename_opt
            .filter(|s| !s.trim().is_empty())
            .unwrap_or_else(|| {
                url.split('?')
                    .next()
                    .unwrap_or("")
                    .rsplit('/')
                    .next()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("download.bin")
                    .to_string()
            });
        let clean_fn = sanitize_filename(&raw_fn);
        let dest_path = download_dir.join(&clean_fn);
        let dest_str = dest_path.to_string_lossy().to_string();
        let norm_dest = dest_str.replace('/', "\\").to_lowercase();
        let new_key = Self::job_match_key(&meta);

        let (job_id, job_json) = {
            let mut st = self.inner.lock().unwrap();
            st.jobs
                .retain(|j| j.status != "cancelled" && !j.control.cancelled.load(Ordering::Relaxed));
            let active_ids: HashSet<String> = st.jobs.iter().map(|j| j.id.clone()).collect();
            st.queue.retain(|qid| active_ids.contains(qid));

            let existing_pos = st.jobs.iter().position(|j| {
                let j_dest = j.dest_file.replace('/', "\\").to_lowercase();
                if j_dest == norm_dest {
                    return true;
                }
                !new_key.0.is_empty() && Self::job_match_key(&j.meta) == new_key
            });

            st.generation_counter += 1;
            let generation = st.generation_counter;

            let (jid, job) = if let Some(pos) = existing_pos {
                let old = &st.jobs[pos];
                let old_id = old.id.clone();
                if old.status != "completed" {
                    old.control.cancelled.store(true, Ordering::Relaxed);
                    old.control.paused.store(false, Ordering::Relaxed);
                    if old.url != url {
                        let old_part = format!("{}.part", old.dest_file);
                        let _ = fs::remove_file(old_part);
                    }
                }
                st.queue.retain(|q| q != &old_id);
                let fresh = DownloadJob::new(
                    old_id.clone(),
                    url.clone(),
                    dest_str,
                    clean_fn.clone(),
                    meta.clone(),
                    generation,
                );
                st.jobs[pos] = fresh.clone();
                (old_id, fresh)
            } else {
                let id = format!("job_{}", st.job_counter);
                st.job_counter += 1;
                let fresh = DownloadJob::new(
                    id.clone(),
                    url.clone(),
                    dest_str,
                    clean_fn.clone(),
                    meta.clone(),
                    generation,
                );
                st.jobs.push(fresh.clone());
                st.queue.push(id.clone());
                (id, fresh)
            };

            if !st.queue.contains(&jid) {
                st.queue.push(jid.clone());
            }

            (jid, job.to_json())
        };

        let title = meta
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or(&clean_fn);
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Queued: '{}' ({}) from {}", job_id, title, clean_fn, url),
            Some("info"),
        );
        Self::emit_progress(app, &job_json);
        self.check_queue(app, max_concurrency);
        job_id
    }

    pub fn get_all_jobs(&self) -> Vec<Value> {
        let st = self.inner.lock().unwrap();
        st.jobs
            .iter()
            .filter(|j| j.status != "cancelled")
            .map(DownloadJob::to_json)
            .collect()
    }

    pub fn pause_job(&self, app: &AppHandle, job_id: &str) -> bool {
        let updated = {
            let mut st = self.inner.lock().unwrap();
            if let Some(job) = st.jobs.iter_mut().find(|j| j.id == job_id) {
                if matches!(job.status.as_str(), "downloading" | "connecting" | "resolving") {
                    job.status = "paused".to_string();
                    job.control.paused.store(true, Ordering::Relaxed);
                    Some(job.to_json())
                } else {
                    None
                }
            } else {
                None
            }
        };
        if let Some(json_val) = updated {
            backend::broadcast_log(app, &format!("[Downloader] [{}] Paused.", job_id), Some("info"));
            Self::emit_progress(app, &json_val);
            return true;
        }
        false
    }

    pub fn resume_job(&self, app: &AppHandle, job_id: &str) -> bool {
        let updated = {
            let mut st = self.inner.lock().unwrap();
            if let Some(job) = st.jobs.iter_mut().find(|j| j.id == job_id) {
                if job.status == "paused" {
                    job.status = "downloading".to_string();
                    job.control.paused.store(false, Ordering::Relaxed);
                    Some(job.to_json())
                } else {
                    None
                }
            } else {
                None
            }
        };
        if let Some(json_val) = updated {
            backend::broadcast_log(app, &format!("[Downloader] [{}] Resumed.", job_id), Some("info"));
            Self::emit_progress(app, &json_val);
            return true;
        }
        false
    }

    pub fn cancel_job(self: &Arc<Self>, app: &AppHandle, max_concurrency: usize, job_id: &str) -> bool {
        let removed = {
            let mut st = self.inner.lock().unwrap();
            st.queue.retain(|q| q != job_id);
            if let Some(pos) = st.jobs.iter().position(|j| j.id == job_id) {
                let mut job = st.jobs.remove(pos);
                job.status = "cancelled".to_string();
                job.control.cancelled.store(true, Ordering::Relaxed);
                job.control.paused.store(false, Ordering::Relaxed);
                Some((job.dest_file.clone(), job.to_json()))
            } else {
                None
            }
        };

        if let Some((dest_file, json_val)) = removed {
            let part = format!("{}.part", dest_file);
            let _ = fs::remove_file(part);
            backend::broadcast_log(
                app,
                &format!("[Downloader] [{}] Cancelled by user.", job_id),
                Some("info"),
            );
            Self::emit_progress(app, &json_val);
            self.check_queue(app, max_concurrency);
            return true;
        }
        false
    }

    pub fn retry_job(
        self: &Arc<Self>,
        app: &AppHandle,
        max_concurrency: usize,
        job_id: &str,
        new_url: Option<String>,
    ) -> bool {
        let updated = {
            let mut st = self.inner.lock().unwrap();
            let gen_next = st.generation_counter + 1;
            let mut result_pair = None;
            if let Some(job) = st.jobs.iter_mut().find(|j| j.id == job_id) {
                if let Some(ref u) = new_url {
                    if u.trim().starts_with("http") {
                        job.url = u.trim().to_string();
                    }
                }
                job.status = "queued".to_string();
                job.error_msg.clear();
                job.control = Arc::new(JobControl::new());
                job.generation = gen_next;
                result_pair = Some((job.url.clone(), job.to_json()));
            }
            if result_pair.is_some() {
                st.generation_counter = gen_next;
                if !st.queue.iter().any(|q| q == job_id) {
                    st.queue.push(job_id.to_string());
                }
            }
            result_pair
        };

        if let Some((url, json_val)) = updated {
            backend::broadcast_log(
                app,
                &format!("[Downloader] [{}] Retrying download from: {}", job_id, url),
                Some("info"),
            );
            Self::emit_progress(app, &json_val);
            self.check_queue(app, max_concurrency);
            return true;
        }
        false
    }

    pub fn switch_job_source(
        self: &Arc<Self>,
        app: &AppHandle,
        max_concurrency: usize,
        job_id: &str,
        new_host: &str,
        part_urls: Option<Vec<String>>,
        fix_url: Option<String>,
        switch_all_parts: bool,
    ) -> Value {
        let mut switched_logs: Vec<(String, String, Value)> = Vec::new();
        {
            let mut st = self.inner.lock().unwrap();
            let Some(target) = st.jobs.iter().find(|j| j.id == job_id).cloned() else {
                return json!({ "success": false, "error": "Download job not found" });
            };

            let jobs_to_switch = if switch_all_parts && Self::is_multipart_job(&target) {
                let sibs: Vec<DownloadJob> = Self::get_siblings_snapshot(&st.jobs, &target)
                    .into_iter()
                    .filter(|sj| sj.status != "completed")
                    .collect();
                if sibs.is_empty() {
                    vec![target]
                } else {
                    sibs
                }
            } else {
                vec![target]
            };

            for sj in jobs_to_switch {
                let meta_type = sj
                    .meta
                    .get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_lowercase();
                let new_url = if meta_type == "fix" {
                    fix_url.clone()
                } else {
                    let idx = Self::part_sort_key(&sj);
                    let idx_usize = if idx >= 1 && idx < 999 { (idx - 1) as usize } else { 0 };
                    if let Some(ref urls) = part_urls {
                        if idx_usize < urls.len() {
                            Some(urls[idx_usize].clone())
                        } else if urls.len() == 1 {
                            Some(urls[0].clone())
                        } else {
                            fix_url.clone()
                        }
                    } else {
                        fix_url.clone()
                    }
                };

                let Some(valid_url) = new_url.filter(|u| u.trim().starts_with("http")) else {
                    continue;
                };

                if let Some(pos) = st.jobs.iter().position(|j| j.id == sj.id) {
                    st.jobs[pos].control.cancelled.store(true, Ordering::Relaxed);
                    st.jobs[pos].control.paused.store(false, Ordering::Relaxed);
                    let old_part = format!("{}.part", st.jobs[pos].dest_file);
                    let _ = fs::remove_file(old_part);

                    st.generation_counter += 1;
                    let gen_next = st.generation_counter;
                    let mut new_meta = st.jobs[pos].meta.clone();
                    new_meta.insert("host".into(), json!(new_host));
                    let mut fresh = DownloadJob::new(
                        sj.id.clone(),
                        valid_url.trim().to_string(),
                        st.jobs[pos].dest_file.clone(),
                        st.jobs[pos].filename.clone(),
                        new_meta,
                        gen_next,
                    );
                    fresh.eta = format!("Switched to {}", new_host);
                    let fresh_json = fresh.to_json();
                    st.jobs[pos] = fresh;
                    if !st.queue.iter().any(|q| q == &sj.id) {
                        st.queue.push(sj.id.clone());
                    }
                    switched_logs.push((sj.id.clone(), valid_url.trim().to_string(), fresh_json));
                }
            }
        }

        if switched_logs.is_empty() {
            return json!({
                "success": false,
                "error": format!("No compatible download URL found on {}", new_host)
            });
        }

        let switched_ids: Vec<String> = switched_logs
            .iter()
            .map(|(id, url, json_val)| {
                backend::broadcast_log(
                    app,
                    &format!("[Downloader] [{}] Switched source -> {} ({})", id, new_host, url),
                    Some("info"),
                );
                Self::emit_progress(app, json_val);
                id.clone()
            })
            .collect();

        self.check_queue(app, max_concurrency);
        json!({
            "success": true,
            "switched_count": switched_ids.len(),
            "job_ids": switched_ids,
            "host": new_host,
        })
    }

    pub fn mark_job_extracting(&self, app: &AppHandle, job_id: Option<&str>, archive_path: &str, title: &str) {
        let updates = {
            let mut st = self.inner.lock().unwrap();
            let norm_arch = archive_path.replace('/', "\\").to_lowercase();
            let mut out = Vec::new();
            for j in &mut st.jobs {
                if j.status == "cancelled" {
                    continue;
                }
                let matches_id = job_id.is_some_and(|jid| j.id == jid);
                let matches_file = !norm_arch.is_empty()
                    && j.dest_file.replace('/', "\\").to_lowercase() == norm_arch;
                let matches_title = !title.trim().is_empty()
                    && j.meta
                        .get("title")
                        .and_then(|v| v.as_str())
                        .is_some_and(|t| t.trim().eq_ignore_ascii_case(title.trim()));
                if matches_id || matches_file || matches_title {
                    j.status = "extracting".to_string();
                    j.eta = format!("Extracting {}...", j.filename);
                    j.error_msg.clear();
                    out.push(j.to_json());
                }
            }
            out
        };
        for j in updates {
            Self::emit_progress(app, &j);
        }
    }

    pub fn mark_job_extracted(
        &self,
        app: &AppHandle,
        job_id: Option<&str>,
        archive_path: &str,
        title: &str,
        game_dir: &str,
        exe_path: Option<&str>,
    ) {
        let updates = {
            let mut st = self.inner.lock().unwrap();
            let norm_arch = archive_path.replace('/', "\\").to_lowercase();
            let mut out = Vec::new();
            for j in &mut st.jobs {
                if j.status == "cancelled" {
                    continue;
                }
                let matches_id = job_id.is_some_and(|jid| j.id == jid);
                let matches_file = !norm_arch.is_empty()
                    && j.dest_file.replace('/', "\\").to_lowercase() == norm_arch;
                let matches_title = !title.trim().is_empty()
                    && j.meta
                        .get("title")
                        .and_then(|v| v.as_str())
                        .is_some_and(|t| t.trim().eq_ignore_ascii_case(title.trim()));
                if matches_id || matches_file || matches_title {
                    j.status = "completed".to_string();
                    j.progress = 100.0;
                    j.speed_bytes = 0;
                    j.eta = "Installed / Ready".to_string();
                    j.error_msg.clear();
                    j.meta.insert("extracted_dir".into(), json!(game_dir));
                    if let Some(exe) = exe_path {
                        j.meta.insert("exe_path".into(), json!(exe));
                    }
                    out.push(j.to_json());
                }
            }
            out
        };
        for j in updates {
            Self::emit_progress(app, &j);
        }
    }

    pub fn mark_job_extract_failed(
        &self,
        app: &AppHandle,
        job_id: Option<&str>,
        archive_path: &str,
        title: &str,
        err_msg: &str,
    ) {
        let updates = {
            let mut st = self.inner.lock().unwrap();
            let norm_arch = archive_path.replace('/', "\\").to_lowercase();
            let mut out = Vec::new();
            for j in &mut st.jobs {
                if j.status == "cancelled" {
                    continue;
                }
                let matches_id = job_id.is_some_and(|jid| j.id == jid);
                let matches_file = !norm_arch.is_empty()
                    && j.dest_file.replace('/', "\\").to_lowercase() == norm_arch;
                let matches_title = !title.trim().is_empty()
                    && j.meta
                        .get("title")
                        .and_then(|v| v.as_str())
                        .is_some_and(|t| t.trim().eq_ignore_ascii_case(title.trim()));
                if matches_id || matches_file || matches_title {
                    j.status = "completed".to_string();
                    j.progress = 100.0;
                    j.speed_bytes = 0;
                    j.eta = "Done (Extraction Failed)".to_string();
                    j.error_msg = format!("Extraction notice: {}", err_msg);
                    out.push(j.to_json());
                }
            }
            out
        };
        for j in updates {
            Self::emit_progress(app, &j);
        }
    }

    fn is_superseded(&self, job_id: &str, gen: u64, control: &JobControl) -> bool {
        if control.cancelled.load(Ordering::Relaxed) {
            return true;
        }
        let st = self.inner.lock().unwrap();
        match st.jobs.iter().find(|j| j.id == job_id) {
            Some(j) => j.generation != gen || j.control.cancelled.load(Ordering::Relaxed),
            None => true,
        }
    }

    pub fn check_queue(self: &Arc<Self>, app: &AppHandle, max_concurrency: usize) {
        let limit = max_concurrency.max(1);
        let to_start: Vec<(String, u64, Arc<JobControl>, Value)> = {
            let mut st = self.inner.lock().unwrap();
            let mut running = st
                .jobs
                .iter()
                .filter(|j| {
                    matches!(
                        j.status.as_str(),
                        "resolving" | "connecting" | "downloading" | "extracting"
                    )
                })
                .count();
            let mut launched = Vec::new();
            while running < limit && !st.queue.is_empty() {
                let next_id = st.queue.remove(0);
                if let Some(job) = st.jobs.iter_mut().find(|j| j.id == next_id) {
                    if job.status == "queued" {
                        job.status = "resolving".to_string();
                        launched.push((
                            job.id.clone(),
                            job.generation,
                            Arc::clone(&job.control),
                            job.to_json(),
                        ));
                        running += 1;
                    }
                }
            }
            launched
        };

        for (job_id, generation, control, job_json) in to_start {
            Self::emit_progress(app, &job_json);
            let mgr = Arc::clone(self);
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                mgr.run_worker(app_clone, job_id, generation, control).await;
            });
        }
    }

    fn read_snapshot(&self, job_id: &str) -> Option<DownloadJob> {
        let st = self.inner.lock().unwrap();
        st.jobs.iter().find(|j| j.id == job_id).cloned()
    }

    fn update_and_emit<F>(&self, app: &AppHandle, job_id: &str, gen: u64, mut f: F)
    where
        F: FnMut(&mut DownloadJob),
    {
        let emitted = {
            let mut st = self.inner.lock().unwrap();
            if let Some(j) = st.jobs.iter_mut().find(|j| j.id == job_id && j.generation == gen) {
                f(j);
                Some(j.to_json())
            } else {
                None
            }
        };
        if let Some(v) = emitted {
            Self::emit_progress(app, &v);
        }
    }

    async fn wait_if_paused(&self, job_id: &str, gen: u64, control: &JobControl) -> bool {
        while control.paused.load(Ordering::Relaxed) {
            if self.is_superseded(job_id, gen, control) {
                return false;
            }
            let _ = tauri::async_runtime::spawn_blocking(|| {
                std::thread::sleep(Duration::from_millis(120));
            })
            .await;
        }
        !self.is_superseded(job_id, gen, control)
    }

    async fn run_worker(self: Arc<Self>, app: AppHandle, job_id: String, gen: u64, control: Arc<JobControl>) {
        self.run_worker_inner(&app, &job_id, gen, &control).await;
        let concurrency = {
            let state = app.state::<AppState>();
            let cfg = state.config.lock().unwrap();
            cfg.settings
                .get("concurrent_downloads")
                .and_then(|v| v.as_u64())
                .unwrap_or(2) as usize
        };
        self.check_queue(&app, concurrency);
    }

    async fn run_worker_inner(&self, app: &AppHandle, job_id: &str, gen: u64, control: &JobControl) {
        if self.is_superseded(job_id, gen, control) {
            return;
        }
        let Some(mut job) = self.read_snapshot(job_id) else {
            return;
        };

        // Read settings needed up-front
        let (download_dir, custom_token, cfg_auto_extract, cfg_auto_delete) = {
            let state = app.state::<AppState>();
            let cfg = state.config.lock().unwrap();
            let dir = Self::resolve_download_dir(&cfg);
            let tok = cfg.get_str("gofile_token");
            let ae = cfg
                .settings
                .get("auto_extract")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let ad = cfg
                .settings
                .get("auto_delete_archive")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            (dir, tok, ae, ad)
        };

        // Step 0: sanitize destination filename
        let clean_fn = sanitize_filename(&job.filename);
        let parent_dir = Path::new(&job.dest_file)
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(&download_dir)
            .to_path_buf();
        let clean_dest = parent_dir.join(&clean_fn).to_string_lossy().to_string();
        if job.dest_file != clean_dest {
            let old_part = format!("{}.part", job.dest_file);
            let new_part = format!("{}.part", clean_dest);
            if Path::new(&old_part).is_file() && old_part != new_part {
                if fs::copy(&old_part, &new_part).is_ok() {
                    let _ = fs::remove_file(&old_part);
                }
            }
            self.update_and_emit(app, job_id, gen, |j| {
                j.filename = clean_fn.clone();
                j.dest_file = clean_dest.clone();
            });
            job.filename = clean_fn;
            job.dest_file = clean_dest;
        }

        let title = job
            .meta
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or(&job.filename)
            .to_string();
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] ==========================================", job_id),
            Some("info"),
        );
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Starting download process for '{}'", job_id, title),
            Some("info"),
        );
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Input URL: {}", job_id, job.url),
            Some("info"),
        );
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Destination: {}", job_id, job.dest_file),
            Some("info"),
        );

        // Step 1: Resolve host link
        self.update_and_emit(app, job_id, gen, |j| j.status = "resolving".to_string());
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Step 1/3: Resolving direct stream URL...", job_id),
            Some("info"),
        );

        let mut download_url = job.url.clone();
        let mut resolved_cookies: HashMap<String, String> = HashMap::new();
        let tok_opt = if custom_token.trim().is_empty() {
            None
        } else {
            Some(custom_token.trim())
        };

        if let Ok(resolved) = resolve_url(&job.url, tok_opt, Some(&title), |msg| {
            backend::broadcast_log(app, &format!("[Downloader] [{}] {}", job_id, msg), Some("info"));
        })
        .await
        {
            if !resolved.direct_url.is_empty() {
                download_url = resolved.direct_url;
                resolved_cookies = resolved.cookies;
                backend::broadcast_log(
                    app,
                    &format!("[Downloader] [{}] Direct CDN stream URL: {}", job_id, download_url),
                    Some("info"),
                );
            }
            if let Some(rname) = resolved.filename {
                let lower_fn = job.filename.to_ascii_lowercase();
                let url_base = job
                    .url
                    .split('?')
                    .next()
                    .unwrap_or("")
                    .rsplit('/')
                    .next()
                    .unwrap_or("");
                let is_archive_ext = [".rar", ".zip", ".7z", ".iso", ".tar", ".gz", ".exe"]
                    .iter()
                    .any(|ext| lower_fn.ends_with(ext));
                if lower_fn.ends_with(".bin") || !is_archive_ext || job.filename == url_base {
                    let sname = sanitize_filename(&rname);
                    let new_dest = download_dir.join(&sname).to_string_lossy().to_string();
                    self.update_and_emit(app, job_id, gen, |j| {
                        j.filename = sname.clone();
                        j.dest_file = new_dest.clone();
                    });
                    job.filename = sname;
                    job.dest_file = new_dest;
                }
            }
        }

        if download_url.contains("gofile.io/d/") {
            if !self.is_superseded(job_id, gen, control) {
                let msg = "GoFile connection timed out (server unreachable or blocked by ISP/VPN). Try 'Open Mirror'.".to_string();
                backend::broadcast_log(app, &format!("[Downloader] [{}] ERROR: {}", job_id, msg), Some("danger"));
                self.update_and_emit(app, job_id, gen, |j| {
                    j.status = "error".to_string();
                    j.error_msg = msg.clone();
                });
            }
            return;
        }

        if self.is_superseded(job_id, gen, control) {
            return;
        }

        self.update_and_emit(app, job_id, gen, |j| j.status = "connecting".to_string());
        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Step 2/3: Connecting to CDN stream...", job_id),
            Some("info"),
        );

        let part_path = format!("{}.part", job.dest_file);

        // Fast skip if destination archive already exists and is complete (> 1 MiB)
        let mut already_complete = false;
        if let Ok(meta_dest) = fs::metadata(&job.dest_file) {
            let dest_sz = meta_dest.len();
            if dest_sz > 1024 * 1024 {
                let part_sz = fs::metadata(&part_path).map(|m| m.len()).unwrap_or(0);
                if dest_sz > part_sz {
                    let _ = fs::remove_file(&part_path);
                    self.update_and_emit(app, job_id, gen, |j| {
                        j.downloaded_bytes = dest_sz;
                        j.total_bytes = dest_sz;
                        j.progress = 100.0;
                        j.speed_bytes = 0;
                        j.status = "completed".to_string();
                        j.eta = "Done".to_string();
                    });
                    backend::broadcast_log(
                        app,
                        &format!(
                            "[Downloader] [{}] Finalized archive already present ({:.2} MB), skipping re-download.",
                            job_id,
                            dest_sz as f64 / (1024.0 * 1024.0)
                        ),
                        Some("success"),
                    );
                    already_complete = true;
                }
            }
        }

        if !already_complete {
            let client = match reqwest::Client::builder()
                .connect_timeout(Duration::from_secs(30))
                .build()
            {
                Ok(c) => c,
                Err(e) => {
                    self.update_and_emit(app, job_id, gen, |j| {
                        j.status = "error".to_string();
                        j.error_msg = e.to_string();
                    });
                    return;
                }
            };

            let mut req = client
                .get(&download_url)
                .header(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                )
                .header("Accept", "*/*");

            if download_url.contains("gofile.io") {
                req = req.header("Referer", "https://gofile.io/");
                let tok = if let Some(t) = resolved_cookies.get("accountToken") {
                    t.clone()
                } else if !custom_token.trim().is_empty() {
                    custom_token.trim().to_string()
                } else {
                    GoFileResolver::get_token(None).await
                };
                if !tok.is_empty() {
                    req = req.header("Authorization", format!("Bearer {}", tok));
                    resolved_cookies.insert("accountToken".to_string(), tok);
                }
            }

            if !resolved_cookies.is_empty() {
                req = req.header("Cookie", format_cookie_header(&resolved_cookies));
            }

            let mut existing_size = fs::metadata(&part_path).map(|m| m.len()).unwrap_or(0);
            if existing_size > 0 {
                req = req.header("Range", format!("bytes={}-", existing_size));
                self.update_and_emit(app, job_id, gen, |j| j.downloaded_bytes = existing_size);
                backend::broadcast_log(
                    app,
                    &format!(
                        "[Downloader] [{}] Resuming from existing partial file: {} bytes ({:.2} MB)",
                        job_id,
                        existing_size,
                        existing_size as f64 / (1024.0 * 1024.0)
                    ),
                    Some("info"),
                );
            }

            let mut resp = match req.send().await {
                Ok(r) => r,
                Err(e) => {
                    if !self.is_superseded(job_id, gen, control) {
                        let msg = e.to_string();
                        backend::broadcast_log(
                            app,
                            &format!("[Downloader] [{}] ERROR: {}", job_id, msg),
                            Some("danger"),
                        );
                        self.update_and_emit(app, job_id, gen, |j| {
                            j.status = "error".to_string();
                            j.error_msg = msg.clone();
                        });
                    }
                    return;
                }
            };

            let status_code = resp.status().as_u16();
            if status_code != 200 && status_code != 206 {
                let server_hdr = resp
                    .headers()
                    .get("server")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("")
                    .to_ascii_lowercase();
                let cf_mit = resp
                    .headers()
                    .get("cf-mitigated")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("");
                let msg = if status_code == 403
                    && (server_hdr.contains("cloudflare")
                        || cf_mit == "challenge"
                        || download_url.to_ascii_lowercase().contains("fileditch"))
                {
                    "Host blocked direct download (Cloudflare Challenge 403). Try PixelDrain or GoFile, or click 'Open Link'.".to_string()
                } else {
                    format!("Server returned HTTP {}", status_code)
                };
                backend::broadcast_log(app, &format!("[Downloader] [{}] ERROR: {}", job_id, msg), Some("danger"));
                self.update_and_emit(app, job_id, gen, |j| {
                    j.status = "error".to_string();
                    j.error_msg = msg.clone();
                });
                return;
            }

            // Update filename from Content-Disposition if needed
            if let Some(cd) = resp.headers().get("content-disposition").and_then(|v| v.to_str().ok()) {
                if let Some(raw_cd_fn) = extract_content_disposition_filename(cd) {
                    let cd_fn = sanitize_filename(&raw_cd_fn);
                    let cur_lower = job.filename.to_ascii_lowercase();
                    if !cd_fn.is_empty()
                        && !(cur_lower.ends_with(".rar")
                            || cur_lower.ends_with(".zip")
                            || cur_lower.ends_with(".7z")
                            || cur_lower.ends_with(".iso"))
                    {
                        let new_dest = download_dir.join(&cd_fn).to_string_lossy().to_string();
                        self.update_and_emit(app, job_id, gen, |j| {
                            j.filename = cd_fn.clone();
                            j.dest_file = new_dest.clone();
                        });
                        job.filename = cd_fn;
                        job.dest_file = new_dest;
                    }
                }
            }

            let active_part_path = format!("{}.part", job.dest_file);
            if active_part_path != part_path && Path::new(&part_path).is_file() {
                let _ = fs::rename(&part_path, &active_part_path);
            }

            let content_type = resp
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_ascii_lowercase();
            let content_length = resp.content_length().unwrap_or(0);
            if status_code == 200 {
                existing_size = 0;
            }
            let total_expected = existing_size.saturating_add(content_length);

            if content_type.starts_with("text/html") && (total_expected < 100_000 || content_length == 0) {
                let _ = fs::remove_file(&active_part_path);
                let msg = "Download link resolved to an HTML webpage rather than a direct archive stream. Check hoster link or token.".to_string();
                backend::broadcast_log(app, &format!("[Downloader] [{}] ERROR: {}", job_id, msg), Some("danger"));
                self.update_and_emit(app, job_id, gen, |j| {
                    j.status = "error".to_string();
                    j.error_msg = msg.clone();
                });
                return;
            }

            let total_mb = total_expected as f64 / (1024.0 * 1024.0);
            backend::broadcast_log(
                app,
                &format!(
                    "[Downloader] [{}] Connected! HTTP {} | Total Size: {:.2} MB | Content-Type: {}",
                    job_id, status_code, total_mb, content_type
                ),
                Some("info"),
            );

            self.update_and_emit(app, job_id, gen, |j| {
                j.total_bytes = total_expected;
                j.downloaded_bytes = existing_size;
                j.status = "downloading".to_string();
            });
            backend::broadcast_log(
                app,
                &format!("[Downloader] [{}] Step 3/3: Downloading data stream...", job_id),
                Some("info"),
            );

            if self.is_superseded(job_id, gen, control) {
                return;
            }

            let file_res = if status_code == 206 {
                OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&active_part_path)
            } else {
                File::create(&active_part_path)
            };
            let mut out_file = match file_res {
                Ok(f) => f,
                Err(e) => {
                    let msg = format!("Failed to open output file: {}", e);
                    self.update_and_emit(app, job_id, gen, |j| {
                        j.status = "error".to_string();
                        j.error_msg = msg.clone();
                    });
                    return;
                }
            };

            let mut downloaded = existing_size;
            let mut last_time = Instant::now();
            let mut last_bytes = downloaded;
            let mut last_milestone = 0u32;

            loop {
                if self.is_superseded(job_id, gen, control) {
                    return;
                }
                if !self.wait_if_paused(job_id, gen, control).await {
                    return;
                }

                match resp.chunk().await {
                    Ok(Some(chunk)) => {
                        if self.is_superseded(job_id, gen, control) {
                            return;
                        }
                        if let Err(werr) = out_file.write_all(&chunk) {
                            let msg = format!("Disk write error: {}", werr);
                            self.update_and_emit(app, job_id, gen, |j| {
                                j.status = "error".to_string();
                                j.error_msg = msg.clone();
                            });
                            return;
                        }
                        downloaded = downloaded.saturating_add(chunk.len() as u64);
                        let progress = if total_expected > 0 {
                            (downloaded as f64 / total_expected as f64) * 100.0
                        } else {
                            0.0
                        };

                        let elapsed = last_time.elapsed().as_secs_f64();
                        if elapsed >= 0.5 {
                            let delta = downloaded.saturating_sub(last_bytes);
                            let speed = (delta as f64 / elapsed) as u64;
                            last_bytes = downloaded;
                            last_time = Instant::now();

                            let eta = if speed > 0 && total_expected > downloaded {
                                let rem_secs = (total_expected - downloaded) / speed;
                                format!("{}m {}s", rem_secs / 60, rem_secs % 60)
                            } else {
                                String::new()
                            };

                            let milestone = ((progress as u32) / 25) * 25;
                            if milestone > last_milestone && milestone < 100 {
                                last_milestone = milestone;
                                let dl_mb = downloaded as f64 / (1024.0 * 1024.0);
                                let sp_mb = speed as f64 / (1024.0 * 1024.0);
                                backend::broadcast_log(
                                    app,
                                    &format!(
                                        "[Downloader] [{}] Progress: {}% ({:.1} MB / {:.1} MB) @ {:.2} MB/s | ETA: {}",
                                        job_id, milestone, dl_mb, total_mb, sp_mb, eta
                                    ),
                                    Some("info"),
                                );
                            }

                            self.update_and_emit(app, job_id, gen, |j| {
                                j.downloaded_bytes = downloaded;
                                j.progress = progress;
                                j.speed_bytes = speed;
                                if !eta.is_empty() {
                                    j.eta = eta.clone();
                                }
                            });
                        }
                    }
                    Ok(None) => break,
                    Err(e) => {
                        if !self.is_superseded(job_id, gen, control) {
                            let msg = format!("Download stream interrupted: {}", e);
                            backend::broadcast_log(
                                app,
                                &format!("[Downloader] [{}] ERROR: {}", job_id, msg),
                                Some("danger"),
                            );
                            self.update_and_emit(app, job_id, gen, |j| {
                                j.status = "error".to_string();
                                j.error_msg = msg.clone();
                            });
                        }
                        return;
                    }
                }
            }

            let _ = out_file.flush();
            drop(out_file);

            if self.is_superseded(job_id, gen, control) {
                return;
            }

            if Path::new(&job.dest_file).exists() {
                let _ = fs::remove_file(&job.dest_file);
            }
            if let Err(_) = fs::rename(&active_part_path, &job.dest_file) {
                if fs::copy(&active_part_path, &job.dest_file).is_ok() {
                    let _ = fs::remove_file(&active_part_path);
                }
            }

            backend::broadcast_log(
                app,
                &format!("[Downloader] [{}] Download SUCCESS: {} (100%)", job_id, job.dest_file),
                Some("success"),
            );
        }

        // Step 4: Native Rust Auto-Extraction
        let auto_extract = job
            .meta
            .get("auto_extract")
            .and_then(|v| v.as_bool())
            .unwrap_or(cfg_auto_extract);
        let dest_lower = job.dest_file.to_ascii_lowercase();
        let is_archive = dest_lower.ends_with(".rar")
            || dest_lower.ends_with(".zip")
            || dest_lower.ends_with(".7z");

        if !(auto_extract && is_archive) {
            self.update_and_emit(app, job_id, gen, |j| {
                j.status = "completed".to_string();
                j.progress = 100.0;
                j.speed_bytes = 0;
                j.eta = "Done".to_string();
            });
            return;
        }

        let Some(latest_job) = self.read_snapshot(job_id) else {
            return;
        };
        let is_multipart = Self::is_multipart_job(&latest_job);
        let sibling_ids: Vec<String>;

        if is_multipart {
            let mut st = self.inner.lock().unwrap();
            let siblings = Self::get_siblings_snapshot(&st.jobs, &latest_job);
            if siblings.len() > 1 {
                if siblings.iter().any(|sj| sj.status == "extracting") {
                    return;
                }
                let has_failed = siblings
                    .iter()
                    .any(|sj| sj.id != job_id && matches!(sj.status.as_str(), "error" | "cancelled"));
                if has_failed {
                    if let Some(j) = st.jobs.iter_mut().find(|j| j.id == job_id && j.generation == gen) {
                        j.status = "completed".to_string();
                        j.progress = 100.0;
                        j.speed_bytes = 0;
                        j.eta = "Downloaded (Sibling part failed)".to_string();
                        j.error_msg = "Cannot extract: one or more parts failed to download.".to_string();
                        Self::emit_progress(app, &j.to_json());
                    }
                    return;
                }

                let pending_count = siblings
                    .iter()
                    .filter(|sj| {
                        sj.id != job_id
                            && ((matches!(
                                sj.status.as_str(),
                                "queued" | "resolving" | "connecting" | "downloading" | "paused"
                            ) && sj.progress < 100.0)
                                || !Path::new(&sj.dest_file).is_file())
                    })
                    .count();
                if pending_count > 0 {
                    if let Some(j) = st.jobs.iter_mut().find(|j| j.id == job_id && j.generation == gen) {
                        j.status = "completed".to_string();
                        j.progress = 100.0;
                        j.speed_bytes = 0;
                        j.eta = format!("Downloaded (Waiting for {} part(s))", pending_count);
                        Self::emit_progress(app, &j.to_json());
                    }
                    backend::broadcast_log(
                        app,
                        &format!(
                            "[Downloader] [{}] Part downloaded. Waiting for {} other part(s) before extraction...",
                            job_id, pending_count
                        ),
                        Some("info"),
                    );
                    return;
                }

                sibling_ids = siblings.iter().map(|s| s.id.clone()).collect();
                for sj_id in &sibling_ids {
                    if let Some(sj) = st.jobs.iter_mut().find(|j| &j.id == sj_id) {
                        sj.status = "extracting".to_string();
                        sj.progress = 100.0;
                        sj.speed_bytes = 0;
                        sj.eta = "Extracting multi-part archive...".to_string();
                        Self::emit_progress(app, &sj.to_json());
                    }
                }
            } else {
                sibling_ids = vec![job_id.to_string()];
                if let Some(j) = st.jobs.iter_mut().find(|j| j.id == job_id) {
                    j.status = "extracting".to_string();
                    j.progress = 100.0;
                    j.speed_bytes = 0;
                    j.eta = "Extracting...".to_string();
                    Self::emit_progress(app, &j.to_json());
                }
            }
        } else {
            sibling_ids = vec![job_id.to_string()];
            self.update_and_emit(app, job_id, gen, |j| {
                j.status = "extracting".to_string();
                j.progress = 100.0;
                j.speed_bytes = 0;
                j.eta = "Extracting...".to_string();
            });
        }

        backend::broadcast_log(
            app,
            &format!("[Downloader] [{}] Starting native Rust extraction for '{}'...", job_id, title),
            Some("info"),
        );

        let siblings_for_extract: Vec<DownloadJob> = {
            let st = self.inner.lock().unwrap();
            sibling_ids
                .iter()
                .filter_map(|sid| st.jobs.iter().find(|j| &j.id == sid).cloned())
                .collect()
        };

        let job_type = latest_job
            .meta
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("main");
        let is_fix = job_type == "fix"
            || latest_job.filename.to_ascii_lowercase().contains("fix")
            || latest_job.dest_file.to_ascii_lowercase().contains("_fix.");
        let custom_extract_dir = latest_job
            .meta
            .get("extract_dir")
            .or_else(|| latest_job.meta.get("custom_location"))
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);

        let (extractor_inst, mut extract_dir, rar_pwd, cg_pwd) = {
            let state = app.state::<AppState>();
            let mut cfg = state.config.lock().unwrap();
            cfg.reload_if_changed();
            let ext = Extractor::from_config(&cfg);
            let existing_loc = find_installed_game_key(&cfg.installed_games, &title, "")
                .and_then(|fk| {
                    cfg.installed_games
                        .get(&fk)
                        .and_then(|v| v.get("location"))
                        .and_then(|l| l.as_str())
                        .map(str::to_string)
                })
                .or_else(|| {
                    latest_job
                        .meta
                        .get("location")
                        .and_then(|v| v.as_str())
                        .map(str::to_string)
                });

            let default_base = {
                let def_dl = cfg.get_str("default_download_path");
                let ext_p = cfg.get_str("extract_path");
                if !def_dl.trim().is_empty() {
                    PathBuf::from(def_dl.trim())
                } else if !ext_p.trim().is_empty() {
                    PathBuf::from(ext_p.trim())
                } else {
                    get_default_games_dir()
                }
            };

            let resolved_dir = if let Some(custom) = custom_extract_dir {
                PathBuf::from(custom)
            } else if is_fix {
                if let Some(ref loc) = existing_loc {
                    let lp = PathBuf::from(loc);
                    if lp.is_dir() { lp } else { default_base.join(&title) }
                } else {
                    default_base.join(&title)
                }
            } else if let Some(ref loc) = existing_loc {
                let lp = PathBuf::from(loc);
                if lp.is_dir() {
                    match lp.parent() {
                        Some(p) if p.exists() || p.to_string_lossy().len() <= 3 => p.to_path_buf(),
                        _ => lp,
                    }
                } else {
                    default_base
                }
            } else {
                default_base
            };

            let rar_p = cfg.get_str("rar_password");
            let cg_p = cfg.get_str("cg_password");
            (ext, resolved_dir, rar_p, cg_p)
        };

        let title_lower = title.to_ascii_lowercase();
        let is_forza_azimuth =
            title_lower.contains("forza horizon 2") || title_lower.contains("azimuth");
        if is_forza_azimuth {
            let norm_ed = extract_dir.to_string_lossy().to_ascii_lowercase();
            if !(norm_ed.ends_with("forza horizon 2") || norm_ed.ends_with("forzahorizon2")) {
                extract_dir = extract_dir.join(&title);
            }
        }

        let origin_lower = latest_job
            .meta
            .get("origin_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let archive_pwd = latest_job
            .meta
            .get("archive_password")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                if origin_lower.contains("cracked-games.org") {
                    "cracked-games.org".to_string()
                } else if origin_lower.contains("steamrip.com")
                    || origin_lower.contains("archive.org")
                    || latest_job.url.to_ascii_lowercase().contains("archive.org")
                    || origin_lower.contains("dropbox")
                    || latest_job.url.to_ascii_lowercase().contains("dropbox")
                    || origin_lower.contains("fileditch")
                    || latest_job.url.to_ascii_lowercase().contains("fileditch")
                {
                    String::new()
                } else if !rar_pwd.is_empty() {
                    rar_pwd
                } else {
                    DEFAULT_RAR_PASSWORD.to_string()
                }
            });

        let title_clone = title.clone();
        let job_dest_clone = latest_job.dest_file.clone();
        let extract_dir_for_blocking = extract_dir.clone();
        let extract_res = tauri::async_runtime::spawn_blocking(move || {
            if siblings_for_extract.len() > 1 && is_forza_azimuth {
                let mut last = extractor_inst.extract_archive(
                    ExtractOptions {
                        archive_path: PathBuf::from(&siblings_for_extract[0].dest_file),
                        extract_dir: extract_dir_for_blocking.clone(),
                        password: archive_pwd.clone(),
                        cg_password: cg_pwd.clone(),
                        delete_after: cfg_auto_delete,
                        game_title: Some(title_clone.clone()),
                        is_fix: false,
                    },
                    |_| {},
                );
                if last.success {
                    for sj in siblings_for_extract.iter().skip(1) {
                        last = extractor_inst.extract_archive(
                            ExtractOptions {
                                archive_path: PathBuf::from(&sj.dest_file),
                                extract_dir: extract_dir_for_blocking.clone(),
                                password: archive_pwd.clone(),
                                cg_password: cg_pwd.clone(),
                                delete_after: cfg_auto_delete,
                                game_title: Some(title_clone.clone()),
                                is_fix: false,
                            },
                            |_| {},
                        );
                        if !last.success {
                            break;
                        }
                    }
                }
                last
            } else {
                let primary_path = siblings_for_extract
                    .first()
                    .map(|s| s.dest_file.as_str())
                    .unwrap_or(&job_dest_clone);
                let res = extractor_inst.extract_archive(
                    ExtractOptions {
                        archive_path: PathBuf::from(primary_path),
                        extract_dir: extract_dir_for_blocking,
                        password: archive_pwd,
                        cg_password: cg_pwd,
                        delete_after: cfg_auto_delete,
                        game_title: Some(title_clone),
                        is_fix,
                    },
                    |_| {},
                );
                if res.success && cfg_auto_delete {
                    for sj in &siblings_for_extract {
                        if Path::new(&sj.dest_file).is_file() {
                            let _ = fs::remove_file(&sj.dest_file);
                        }
                    }
                }
                res
            }
        })
        .await;

        match extract_res {
            Ok(res) if res.success => {
                let target_game_dir = res.game_dir.unwrap_or_else(|| res.extract_dir.clone());
                let exe_path = res.exe_path;

                if !res.skipped && !title.trim().is_empty() {
                    let state = app.state::<AppState>();
                    let mut cfg = state.config.lock().unwrap();
                    cfg.reload_if_changed();
                    let mut db = state.database.lock().unwrap();
                    if db.games.is_empty() {
                        db.load_local_or_cached(&cfg, false);
                    }

                    let norm_title = normalize_key(&title);
                    let resolved_version = latest_job
                        .meta
                        .get("version")
                        .and_then(|v| v.as_str())
                        .filter(|s| !s.trim().is_empty())
                        .map(str::to_string)
                        .or_else(|| {
                            db.games
                                .iter()
                                .find(|g| {
                                    g.title.eq_ignore_ascii_case(&title)
                                        || (!norm_title.is_empty()
                                            && normalize_key(&g.title) == norm_title)
                                })
                                .map(|g| g.version.clone())
                                .filter(|v| !v.trim().is_empty())
                        });

                    let key = find_installed_game_key(&cfg.installed_games, &title, "")
                        .unwrap_or_else(|| title.to_uppercase());
                    let mut record = cfg
                        .installed_games
                        .get(&key)
                        .and_then(|v| v.as_object())
                        .cloned()
                        .unwrap_or_default();
                    record.insert("downloaded".into(), json!(true));
                    record.insert("location".into(), json!(target_game_dir));
                    if let Some(ref ver) = resolved_version {
                        record.insert("version".into(), json!(ver));
                    }
                    if let Some(ref exe) = exe_path {
                        record.insert("exe_path".into(), json!(exe));
                    }
                    cfg.installed_games.insert(key, Value::Object(record));
                    cfg.save_installed_games();
                    db.update_installed_states(&cfg);
                }

                {
                    let mut st = self.inner.lock().unwrap();
                    for sj_id in &sibling_ids {
                        if let Some(sj) = st.jobs.iter_mut().find(|j| &j.id == sj_id) {
                            sj.status = "completed".to_string();
                            sj.progress = 100.0;
                            sj.speed_bytes = 0;
                            sj.eta = "Installed / Ready".to_string();
                            sj.error_msg.clear();
                            sj.meta.insert("extracted_dir".into(), json!(target_game_dir));
                            if let Some(ref exe) = exe_path {
                                sj.meta.insert("exe_path".into(), json!(exe));
                            }
                            Self::emit_progress(app, &sj.to_json());
                        }
                    }
                }

                backend::broadcast_log(
                    app,
                    &format!("[Downloader] [{}] Extraction SUCCESS: {}", job_id, target_game_dir),
                    Some("success"),
                );

                let mut done_ev = Map::new();
                done_ev.insert("status".into(), json!("success"));
                done_ev.insert("title".into(), json!(title));
                done_ev.insert("file".into(), json!(latest_job.dest_file));
                done_ev.insert("dest".into(), json!(target_game_dir));
                done_ev.insert("game_dir".into(), json!(target_game_dir));
                if let Some(ref exe) = exe_path {
                    done_ev.insert("exe_path".into(), json!(exe));
                }
                done_ev.insert("job_id".into(), json!(job_id));
                let _ = app.emit("extraction-status", Value::Object(done_ev));
            }
            Ok(res) => {
                let err_msg = res.error.unwrap_or_else(|| "Unknown extraction error".to_string());
                {
                    let mut st = self.inner.lock().unwrap();
                    for sj_id in &sibling_ids {
                        if let Some(sj) = st.jobs.iter_mut().find(|j| &j.id == sj_id) {
                            sj.status = "completed".to_string();
                            sj.progress = 100.0;
                            sj.speed_bytes = 0;
                            sj.eta = "Done (Extraction Failed)".to_string();
                            sj.error_msg = format!("Extraction notice: {}", err_msg);
                            Self::emit_progress(app, &sj.to_json());
                        }
                    }
                }
                backend::broadcast_log(
                    app,
                    &format!("[Downloader] [{}] Extraction error: {}", job_id, err_msg),
                    Some("danger"),
                );
                let _ = app.emit(
                    "extraction-status",
                    json!({
                        "status": "error",
                        "title": title,
                        "file": latest_job.dest_file,
                        "error": err_msg,
                        "job_id": job_id,
                    }),
                );
            }
            Err(join_err) => {
                let err_msg = join_err.to_string();
                self.update_and_emit(app, job_id, gen, |j| {
                    j.status = "completed".to_string();
                    j.eta = "Done (Extraction Failed)".to_string();
                    j.error_msg = format!("Extraction notice: {}", err_msg);
                });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_filename() {
        assert_eq!(
            sanitize_filename("Zelda: Ocarina of Time <v1.0>.zip"),
            "Zelda - Ocarina of Time _v1.0_.zip"
        );
        assert_eq!(sanitize_filename("   ...  "), "download.bin");
        assert_eq!(sanitize_filename("Cool  Game/Part*1?.rar"), "Cool Game_Part_1_.rar");
    }

    #[test]
    fn test_disk_space_size_parsing_and_formatting() {
        assert_eq!(parse_size_str(&json!("2.5 GB")), (2.5 * 1024f64.powi(3)) as u64);
        assert_eq!(parse_size_str(&json!("512MB")), 512 * 1024 * 1024);
        assert_eq!(format_bytes_human(1536 * 1024 * 1024), "1.5 GB");
        assert_eq!(format_bytes_human(512 * 1024), "512.0 KB");

        let res = check_disk_space(r"C:\Games", r"C:\Downloads", &json!("10MB"));
        assert_eq!(res["success"], true);
        assert_eq!(res["same_drive"], true);
        assert!(res["download"]["free_bytes"].as_u64().unwrap_or(0) > 0);
    }

    #[test]
    fn test_multipart_siblings_and_source_switch() {
        let mut meta1 = Map::new();
        meta1.insert("title".into(), json!("Peak"));
        meta1.insert("type".into(), json!("main_part_1"));
        meta1.insert("part_index".into(), json!(1));
        meta1.insert("total_parts".into(), json!(2));

        let mut meta2 = Map::new();
        meta2.insert("title".into(), json!("Peak"));
        meta2.insert("type".into(), json!("main_part_2"));
        meta2.insert("part_index".into(), json!(2));
        meta2.insert("total_parts".into(), json!(2));

        let mut j1 = DownloadJob::new(
            "job_1".into(),
            "https://gofile.io/d/1".into(),
            r"D:\Cache\Peak.part1.rar".into(),
            "Peak.part1.rar".into(),
            meta1,
            1,
        );
        j1.status = "paused".into();
        let j2 = DownloadJob::new(
            "job_2".into(),
            "https://gofile.io/d/2".into(),
            r"D:\Cache\Peak.part2.rar".into(),
            "Peak.part2.rar".into(),
            meta2,
            2,
        );

        let jobs = vec![j2.clone(), j1.clone()];
        let siblings = DownloadManager::get_siblings_snapshot(&jobs, &j1);
        assert_eq!(siblings.len(), 2);
        assert_eq!(siblings[0].id, "job_1");
        assert_eq!(siblings[1].id, "job_2");
    }
}
