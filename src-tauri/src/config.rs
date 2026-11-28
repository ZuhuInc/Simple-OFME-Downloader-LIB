use serde_json::{json, Map, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;
use tauri::{AppHandle, Manager};

pub const DEFAULT_DB_URL: &str =
    "https://raw.githubusercontent.com/ZuhuInc/Simple-OFME-Downloader-LIB/refs/heads/main/src/backend/data/Data.json";

pub fn get_home_dir() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn get_default_data_folder() -> PathBuf {
    let zuhu_dir = get_home_dir()
        .join("Documents")
        .join("ZuhuProjects")
        .join("ZuhuOFME");
    if zuhu_dir.exists() {
        return zuhu_dir;
    }
    get_home_dir().join(".fanta_ofme")
}

pub fn get_default_download_dir() -> PathBuf {
    let zuhu_dl = get_home_dir()
        .join("Documents")
        .join("ZuhuProjects")
        .join("ZuhuOFME")
        .join("downloads");
    if zuhu_dl.exists() {
        return zuhu_dl;
    }
    get_home_dir().join("Downloads").join("OFME")
}

pub fn get_default_games_dir() -> PathBuf {
    if Path::new(r"D:\").exists() {
        return PathBuf::from(r"D:\Games");
    }
    get_home_dir().join("Games")
}

pub fn resolve_bundled_data_path(app: Option<&AppHandle>, filename: &str) -> Option<PathBuf> {
    if cfg!(debug_assertions) {
        if let Ok(cwd) = std::env::current_dir() {
            for ancestor in cwd.ancestors() {
                let candidate = ancestor.join("src").join("backend").join("data").join(filename);
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
        }
    }

    if let Some(app_handle) = app {
        if let Ok(res_dir) = app_handle.path().resource_dir() {
            let p1 = res_dir.join("data").join(filename);
            if p1.is_file() {
                return Some(p1);
            }
            let p2 = res_dir.join(filename);
            if p2.is_file() {
                return Some(p2);
            }
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            for candidate in [
                exe_dir.join("data").join(filename),
                exe_dir.join("_internal").join("data").join(filename),
                exe_dir.join("resources").join("data").join(filename),
            ] {
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        for ancestor in cwd.ancestors() {
            let candidate = ancestor.join("src").join("backend").join("data").join(filename);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }

    None
}

fn default_settings_map(bundled_json_path: Option<&Path>) -> Map<String, Value> {
    let dl_path = get_default_download_dir().to_string_lossy().to_string();
    let extract_path = get_default_games_dir().to_string_lossy().to_string();

    let mut m = Map::new();
    m.insert("winrar_path".into(), json!(r"C:\Program Files\WinRAR\WinRAR.exe"));
    m.insert("download_path".into(), json!(dl_path));
    m.insert("extract_path".into(), json!(extract_path));
    m.insert("default_download_path".into(), json!(extract_path));
    m.insert("steam_path".into(), json!(r"C:\Program Files (x86)\Steam"));
    m.insert("steam_user_id".into(), json!(""));
    m.insert("steam_id".into(), json!(""));
    m.insert("rar_password".into(), json!("online-fix.me"));
    m.insert("cg_password".into(), json!("cracked-games.org"));
    m.insert("concurrent_downloads".into(), json!(2));
    m.insert("speed_unit".into(), json!("MB/s"));
    m.insert("size_unit".into(), json!("GB"));
    m.insert("preferred_host".into(), json!("GoFile"));
    m.insert("show_size_in_gb".into(), json!(true));
    m.insert("show_download_speed".into(), json!(true));
    m.insert("show_download_percent".into(), json!(true));
    m.insert("show_download_total".into(), json!(true));
    m.insert("enable_notifications".into(), json!(true));
    m.insert("enable_webhook".into(), json!(true));
    m.insert("webhook_url".into(), json!(""));
    m.insert("ofme_username".into(), json!(""));
    m.insert("ofme_password".into(), json!(""));
    m.insert("browser_path".into(), json!(""));
    m.insert("db_url".into(), json!(DEFAULT_DB_URL));
    m.insert("use_local_db".into(), json!(false));
    m.insert("sevenzip_path".into(), json!(r"C:\Program Files\7-Zip\7z.exe"));
    m.insert("auto_extract".into(), json!(true));
    m.insert("auto_delete_archive".into(), json!(true));
    m.insert("gofile_token".into(), json!(""));
    m.insert("multi_threaded_scan".into(), json!(false));
    m.insert("scan_workers".into(), json!(6));
    m.insert("enable_scrape_cache".into(), json!(false));
    m.insert("scrape_cache_ttl_minutes".into(), json!(15));
    m.insert("game_edit_mode".into(), json!(false));
    m.insert("ach_overlay_enabled".into(), json!(true));
    m.insert("ach_sound_enabled".into(), json!(true));
    m.insert("ach_volume".into(), json!(80));
    m.insert("ach_duration".into(), json!(4500));
    m.insert("beta_updates".into(), json!(false));

    if let Some(p) = bundled_json_path {
        if p.exists() {
            m.insert("local_db_path".into(), json!(p.to_string_lossy().to_string()));
        }
    }
    m
}

pub struct ConfigManager {
    pub data_folder: PathBuf,
    pub cache_folder: PathBuf,
    pub settings_path: PathBuf,
    pub data_json_path: PathBuf,
    pub data_bak_path: PathBuf,
    pub data_old_path: PathBuf,
    pub login_json_path: PathBuf,
    pub bundled_data_path: Option<PathBuf>,
    pub settings: Map<String, Value>,
    pub installed_games: Map<String, Value>,
    settings_mtime: Option<SystemTime>,
    installed_mtime: Option<SystemTime>,
}

impl Default for ConfigManager {
    fn default() -> Self {
        Self::new(None)
    }
}

impl ConfigManager {
    pub fn new(app: Option<&AppHandle>) -> Self {
        let data_folder = get_default_data_folder();
        let cache_folder = data_folder.join("cache");
        let _ = fs::create_dir_all(&data_folder);
        let _ = fs::create_dir_all(&cache_folder);

        let bundled = resolve_bundled_data_path(app, "Data.json");
        let defaults = default_settings_map(bundled.as_deref());

        let mut mgr = Self {
            settings_path: data_folder.join("Settings.json"),
            data_json_path: data_folder.join("Data.json"),
            data_bak_path: data_folder.join("Data.json.bak"),
            data_old_path: data_folder.join("old.Data.json"),
            login_json_path: data_folder.join("Login.json"),
            data_folder,
            cache_folder,
            bundled_data_path: bundled,
            settings: defaults,
            installed_games: Map::new(),
            settings_mtime: None,
            installed_mtime: None,
        };
        mgr.load();
        mgr
    }

    pub fn bind_app(&mut self, app: &AppHandle) {
        if self.bundled_data_path.is_none() {
            self.bundled_data_path = resolve_bundled_data_path(Some(app), "Data.json");
            if !self.settings.contains_key("local_db_path") {
                if let Some(p) = &self.bundled_data_path {
                    self.settings.insert(
                        "local_db_path".into(),
                        json!(p.to_string_lossy().to_string()),
                    );
                }
            }
        }
    }

    pub fn load(&mut self) {
        self.load_settings();
        self.load_installed_games();
    }

    pub fn reload_if_changed(&mut self) {
        if let Ok(meta) = fs::metadata(&self.settings_path) {
            if let Ok(mtime) = meta.modified() {
                if self.settings_mtime != Some(mtime) {
                    self.load_settings();
                }
            }
        }
        if let Ok(meta) = fs::metadata(&self.data_json_path) {
            if let Ok(mtime) = meta.modified() {
                if self.installed_mtime != Some(mtime) {
                    self.load_installed_games();
                }
            }
        } else if !self.installed_games.is_empty() {
            self.installed_games.clear();
            self.installed_mtime = None;
        }
    }

    fn load_settings(&mut self) {
        let mut merged = default_settings_map(self.bundled_data_path.as_deref());
        let mut has_saved_favorites = false;

        if self.settings_path.is_file() {
            if let Ok(raw) = fs::read_to_string(&self.settings_path) {
                if let Ok(Value::Object(saved)) = serde_json::from_str::<Value>(&raw) {
                    has_saved_favorites = saved.contains_key("favorite_games");
                    for (k, v) in saved {
                        merged.insert(k, v);
                    }
                }
            }
            self.settings_mtime = fs::metadata(&self.settings_path)
                .ok()
                .and_then(|m| m.modified().ok());
        }

        // Auto-migrate legacy Download-DB.txt or BetaRework db_url
        let db_url_str = merged
            .get("db_url")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if db_url_str.is_empty()
            || db_url_str.contains("Download-DB.txt")
            || db_url_str.contains("BetaRework")
        {
            merged.insert("db_url".into(), json!(DEFAULT_DB_URL));
        }

        // Auto-migrate invalid hardcoded ZUHU download path if not on ZUHU machine
        let dl_path = merged
            .get("download_path")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if dl_path.contains("ZUHU") && !Path::new(dl_path).exists() {
            merged.insert(
                "download_path".into(),
                json!(get_home_dir().join("Downloads").join("OFME").to_string_lossy().to_string()),
            );
        }

        // Auto-fallback extract_path if drive/GAMES2 folder does not exist on this PC
        let cur_extract = merged
            .get("extract_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if !cur_extract.is_empty() && !Path::new(&cur_extract).exists() {
            let drive_missing = cur_extract
                .get(0..2)
                .filter(|p| p.ends_with(':'))
                .map(|p| !Path::new(&format!("{}\\", p)).exists())
                .unwrap_or(false);
            if drive_missing || cur_extract.to_lowercase().contains("games2") {
                merged.insert(
                    "extract_path".into(),
                    json!(get_default_games_dir().to_string_lossy().to_string()),
                );
            }
        }
        if let Some(ext) = merged.get("extract_path").cloned() {
            if ext.as_str().is_some_and(|s| !s.is_empty()) {
                merged.insert("default_download_path".into(), ext);
            }
        }

        // Clear legacy hardcoded Steam ID
        if merged.get("steam_id").and_then(|v| v.as_str()) == Some("1004235037") {
            merged.insert("steam_id".into(), json!(""));
        }
        if merged.get("steam_user_id").and_then(|v| v.as_str()) == Some("1004235037") {
            merged.insert("steam_user_id".into(), json!(""));
        }

        // Load Login.json credentials & webhook if present
        if self.login_json_path.is_file() {
            if let Ok(raw) = fs::read_to_string(&self.login_json_path) {
                if let Ok(Value::Object(login_data)) = serde_json::from_str::<Value>(&raw) {
                    if let Some(u) = login_data.get("username").and_then(|v| v.as_str()) {
                        if !u.is_empty() {
                            merged.insert("ofme_username".into(), json!(u));
                        }
                    }
                    if let Some(p) = login_data.get("password").and_then(|v| v.as_str()) {
                        if !p.is_empty() {
                            merged.insert("ofme_password".into(), json!(p));
                        }
                    }
                    if let Some(w) = login_data.get("webhook_url").and_then(|v| v.as_str()) {
                        if !w.is_empty() {
                            merged.insert("webhook_url".into(), json!(w));
                        }
                    }
                }
            }
        }

        self.settings = merged;

        if !has_saved_favorites {
            if let Some(favs) = import_electron_favorites_from_appdata() {
                if !favs.is_empty() {
                    let count = favs.len();
                    self.settings.insert("favorite_games".into(), json!(favs));
                    self.save_settings();
                    self.settings_mtime = fs::metadata(&self.settings_path)
                        .ok()
                        .and_then(|m| m.modified().ok());
                    println!(
                        "[Rust Backend] [Config] Migrated {} favorite game(s) from Electron Local Storage to Settings.json",
                        count
                    );
                }
            }
        }
    }

    fn load_installed_games(&mut self) {
        if !self.data_json_path.is_file() {
            self.installed_games.clear();
            self.installed_mtime = None;
            return;
        }

        if let Ok(raw) = fs::read_to_string(&self.data_json_path) {
            if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&raw) {
                self.installed_games = map;
                self.installed_mtime = fs::metadata(&self.data_json_path)
                    .ok()
                    .and_then(|m| m.modified().ok());
                return;
            }
        }

        // Corruption protection: preserve copy and recover from .bak
        let _ = fs::copy(&self.data_json_path, &self.data_old_path);
        if self.data_bak_path.is_file() {
            if let Ok(raw_bak) = fs::read_to_string(&self.data_bak_path) {
                if let Ok(Value::Object(recovered)) = serde_json::from_str::<Value>(&raw_bak) {
                    if !recovered.is_empty() {
                        self.installed_games = recovered;
                    }
                }
            }
        }
    }

    pub fn save_settings(&self) {
        if let Ok(pretty) = serialize_pretty_4(&Value::Object(self.settings.clone())) {
            let _ = fs::write(&self.settings_path, pretty);
        }

        let user = self.get_str("ofme_username");
        let webhook = self.get_str("webhook_url");
        if !user.is_empty() || !webhook.is_empty() {
            let login_payload = json!({
                "username": user,
                "password": self.get_str("ofme_password"),
                "webhook_url": webhook,
            });
            if let Ok(pretty) = serialize_pretty_4(&login_payload) {
                let _ = fs::write(&self.login_json_path, pretty);
            }
        }
    }

    pub fn save_installed_games(&mut self) {
        if self.installed_games.is_empty() {
            if let Ok(meta) = fs::metadata(&self.data_json_path) {
                if meta.len() > 100 {
                    println!("[Rust Backend] [Config] Prevented saving empty installed games dictionary over existing Data.json");
                    return;
                }
            }
        }

        if let Ok(meta) = fs::metadata(&self.data_json_path) {
            if meta.len() > 20 {
                let _ = fs::copy(&self.data_json_path, &self.data_bak_path);
                let _ = fs::copy(&self.data_json_path, &self.data_old_path);
            }
        }

        if let Ok(pretty) = serialize_pretty_4(&Value::Object(self.installed_games.clone())) {
            let tmp_path = self.data_json_path.with_extension("json.tmp");
            if fs::write(&tmp_path, pretty).is_ok() {
                let _ = fs::remove_file(&self.data_json_path);
                if fs::rename(&tmp_path, &self.data_json_path).is_ok() {
                    self.installed_mtime = fs::metadata(&self.data_json_path)
                        .ok()
                        .and_then(|m| m.modified().ok());
                }
            }
        }
    }

    pub fn update_settings(&mut self, incoming: Map<String, Value>) {
        if let Some(ext) = incoming.get("extract_path").and_then(|v| v.as_str()) {
            let trimmed = ext.trim();
            if !trimmed.is_empty() {
                self.settings.insert("default_download_path".into(), json!(trimmed));
            }
        }
        for (k, v) in incoming {
            self.settings.insert(k, v);
        }
        self.save_settings();
        self.settings_mtime = fs::metadata(&self.settings_path)
            .ok()
            .and_then(|m| m.modified().ok());
    }

    pub fn get_str(&self, key: &str) -> String {
        self.settings
            .get(key)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    }

    pub fn get_bool(&self, key: &str) -> bool {
        self.settings
            .get(key)
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }

    pub fn get_active_db_path(&self) -> Option<PathBuf> {
        let custom = self.get_str("local_db_path");
        if !custom.trim().is_empty() {
            return Some(PathBuf::from(custom.trim()));
        }
        if let Some(p) = &self.bundled_data_path {
            if p.exists() {
                return Some(p.clone());
            }
        }
        Some(self.cache_folder.join("Data.json"))
    }
}

fn serialize_pretty_4(value: &Value) -> Result<String, serde_json::Error> {
    let mut buf = Vec::new();
    let formatter = serde_json::ser::PrettyFormatter::with_indent(b"    ");
    let mut ser = serde_json::Serializer::with_formatter(&mut buf, formatter);
    serde::Serialize::serialize(value, &mut ser)?;
    Ok(String::from_utf8_lossy(&buf).to_string())
}

fn import_electron_favorites_from_appdata() -> Option<Vec<String>> {
    let appdata = std::env::var_os("APPDATA")?;
    let base = PathBuf::from(appdata);
    for folder_name in ["Fanta OFME Downloader", "fanta-ofme-dwnld"] {
        let leveldb_dir = base.join(folder_name).join("Local Storage").join("leveldb");
        if leveldb_dir.is_dir() {
            if let Some(favs) = read_favorites_from_leveldb_dir(&leveldb_dir) {
                if !favs.is_empty() {
                    return Some(favs);
                }
            }
        }
    }
    None
}

fn read_favorites_from_leveldb_dir(dir: &Path) -> Option<Vec<String>> {
    let entries = fs::read_dir(dir).ok()?;
    let mut files: Vec<(u64, bool, PathBuf)> = Vec::new();

    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_ascii_lowercase())
            .unwrap_or_default();
        let is_log = match ext.as_str() {
            "log" => true,
            "ldb" | "sst" => false,
            _ => continue,
        };
        let file_num = path
            .file_stem()
            .and_then(|s| s.to_str())
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(0);
        files.push((file_num, is_log, path));
    }

    // Newest file number first; .log before .ldb/.sst on equal file number.
    files.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| b.1.cmp(&a.1)));

    for (_num, is_log, path) in files {
        let Ok(bytes) = fs::read(&path) else {
            continue;
        };
        let found = if is_log {
            extract_favorites_from_bytes(&bytes, true)
        } else {
            extract_favorites_from_ldb(&bytes)
        };
        if let Some(favs) = found {
            return Some(favs);
        }
    }

    None
}

fn read_varint_u64(data: &[u8], pos: &mut usize) -> Option<u64> {
    let mut result: u64 = 0;
    let mut shift = 0u32;
    while *pos < data.len() && shift < 64 {
        let byte = data[*pos];
        *pos += 1;
        result |= ((byte & 0x7f) as u64) << shift;
        if (byte & 0x80) == 0 {
            return Some(result);
        }
        shift += 7;
    }
    None
}

fn decompress_snappy(input: &[u8]) -> Option<Vec<u8>> {
    const MAX_UNCOMPRESSED: usize = 16 * 1024 * 1024;
    let mut pos = 0usize;
    let expected_len = read_varint_u64(input, &mut pos)? as usize;
    if expected_len > MAX_UNCOMPRESSED {
        return None;
    }

    let mut out = Vec::with_capacity(expected_len);
    while pos < input.len() {
        let tag = input[pos];
        pos += 1;
        match tag & 0x03 {
            0x00 => {
                // Literal bytes
                let len_minus_1 = (tag >> 2) as usize;
                let lit_len = if len_minus_1 < 60 {
                    len_minus_1 + 1
                } else {
                    let extra_bytes = len_minus_1 - 59;
                    if pos + extra_bytes > input.len() {
                        return None;
                    }
                    let mut n = 0usize;
                    for i in 0..extra_bytes {
                        n |= (input[pos + i] as usize) << (8 * i);
                    }
                    pos += extra_bytes;
                    n + 1
                };
                if pos + lit_len > input.len() || out.len() + lit_len > MAX_UNCOMPRESSED {
                    return None;
                }
                out.extend_from_slice(&input[pos..pos + lit_len]);
                pos += lit_len;
            }
            0x01 => {
                // Copy with 1-byte offset
                if pos >= input.len() {
                    return None;
                }
                let copy_len = (((tag >> 2) & 0x07) as usize) + 4;
                let offset = (((tag & 0xe0) as usize) << 3) | (input[pos] as usize);
                pos += 1;
                if offset == 0 || offset > out.len() || out.len() + copy_len > MAX_UNCOMPRESSED {
                    return None;
                }
                for _ in 0..copy_len {
                    let b = out[out.len() - offset];
                    out.push(b);
                }
            }
            0x02 => {
                // Copy with 2-byte offset
                if pos + 2 > input.len() {
                    return None;
                }
                let copy_len = ((tag >> 2) as usize) + 1;
                let offset = u16::from_le_bytes([input[pos], input[pos + 1]]) as usize;
                pos += 2;
                if offset == 0 || offset > out.len() || out.len() + copy_len > MAX_UNCOMPRESSED {
                    return None;
                }
                for _ in 0..copy_len {
                    let b = out[out.len() - offset];
                    out.push(b);
                }
            }
            _ => {
                // Copy with 4-byte offset
                if pos + 4 > input.len() {
                    return None;
                }
                let copy_len = ((tag >> 2) as usize) + 1;
                let offset = u32::from_le_bytes([
                    input[pos],
                    input[pos + 1],
                    input[pos + 2],
                    input[pos + 3],
                ]) as usize;
                pos += 4;
                if offset == 0 || offset > out.len() || out.len() + copy_len > MAX_UNCOMPRESSED {
                    return None;
                }
                for _ in 0..copy_len {
                    let b = out[out.len() - offset];
                    out.push(b);
                }
            }
        }
    }

    if out.len() != expected_len {
        return None;
    }
    Some(out)
}

fn read_sstable_block(file: &[u8], offset: usize, size: usize) -> Option<Vec<u8>> {
    let end = offset.checked_add(size)?;
    if end >= file.len() {
        return None;
    }
    let raw = &file[offset..end];
    match file[end] {
        0 => Some(raw.to_vec()),
        1 => decompress_snappy(raw),
        _ => None,
    }
}

fn parse_sstable_data_handles(file: &[u8]) -> Option<Vec<(usize, usize)>> {
    const LEVELDB_MAGIC: [u8; 8] = 0xdb4775248b80fb57u64.to_le_bytes();
    if file.len() < 48 || file[file.len() - 8..] != LEVELDB_MAGIC {
        return None;
    }

    let footer = &file[file.len() - 48..file.len() - 8];
    let mut fpos = 0usize;
    let _meta_off = read_varint_u64(footer, &mut fpos)?;
    let _meta_size = read_varint_u64(footer, &mut fpos)?;
    let idx_off = read_varint_u64(footer, &mut fpos)? as usize;
    let idx_size = read_varint_u64(footer, &mut fpos)? as usize;

    let index_block = read_sstable_block(file, idx_off, idx_size)?;
    if index_block.len() < 4 {
        return None;
    }

    let n_off = index_block.len() - 4;
    let num_restarts = u32::from_le_bytes([
        index_block[n_off],
        index_block[n_off + 1],
        index_block[n_off + 2],
        index_block[n_off + 3],
    ]) as usize;
    let restarts_bytes = num_restarts.checked_mul(4)?;
    let entries_end = n_off.checked_sub(restarts_bytes)?;

    let mut handles = Vec::new();
    let mut bpos = 0usize;
    while bpos < entries_end {
        let _shared = read_varint_u64(&index_block[..entries_end], &mut bpos)?;
        let non_shared = read_varint_u64(&index_block[..entries_end], &mut bpos)? as usize;
        let value_len = read_varint_u64(&index_block[..entries_end], &mut bpos)? as usize;
        let key_end = bpos.checked_add(non_shared)?;
        let val_end = key_end.checked_add(value_len)?;
        if val_end > entries_end {
            return None;
        }
        let val_slice = &index_block[key_end..val_end];
        let mut vpos = 0usize;
        let data_off = read_varint_u64(val_slice, &mut vpos)? as usize;
        let data_size = read_varint_u64(val_slice, &mut vpos)? as usize;
        handles.push((data_off, data_size));
        bpos = val_end;
    }

    Some(handles)
}

fn extract_favorites_from_ldb(file: &[u8]) -> Option<Vec<String>> {
    if let Some(handles) = parse_sstable_data_handles(file) {
        for (off, size) in handles {
            if let Some(block_bytes) = read_sstable_block(file, off, size) {
                if let Some(favs) = extract_favorites_from_bytes(&block_bytes, false) {
                    return Some(favs);
                }
            }
        }
    }

    extract_favorites_from_bytes(file, false)
}

fn normalize_favorite_list(raw: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    for item in raw {
        let norm = item.trim().to_lowercase();
        if !norm.is_empty() && !out.contains(&norm) {
            out.push(norm);
        }
    }
    out
}

fn parse_leading_json_string_array(text: &str) -> Option<Vec<String>> {
    let mut stream = serde_json::Deserializer::from_str(text).into_iter::<Vec<String>>();
    match stream.next() {
        Some(Ok(arr)) => Some(normalize_favorite_list(arr)),
        _ => None,
    }
}

fn decode_valid_utf8_prefix(bytes: &[u8]) -> &str {
    match std::str::from_utf8(bytes) {
        Ok(s) => s,
        Err(e) => std::str::from_utf8(&bytes[..e.valid_up_to()]).unwrap_or(""),
    }
}

fn decode_utf16le_slice(bytes: &[u8]) -> String {
    let units: Vec<u16> = bytes
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    String::from_utf16_lossy(&units)
}

fn extract_favorites_from_bytes(data: &[u8], take_last: bool) -> Option<Vec<String>> {
    const KEY: &[u8] = b"fanta_favorite_games";
    const MAX_JSON_BYTES: usize = 256 * 1024;
    if data.len() < KEY.len() {
        return None;
    }

    let mut result: Option<Vec<String>> = None;
    let mut search_from = 0usize;

    while search_from + KEY.len() <= data.len() {
        let rel = data[search_from..]
            .windows(KEY.len())
            .position(|w| w == KEY);
        let Some(offset) = rel else {
            break;
        };
        let after_key = search_from + offset + KEY.len();
        search_from = after_key;

        let inspect_end = (after_key + 20).min(data.len());
        let mut parsed_here: Option<Vec<String>> = None;

        for idx in after_key..inspect_end {
            if data[idx] == 0x01 && idx + 1 < data.len() && data[idx + 1] == b'[' {
                let json_start = idx + 1;
                let json_end = (json_start + MAX_JSON_BYTES).min(data.len());
                let slice_str = decode_valid_utf8_prefix(&data[json_start..json_end]);
                if let Some(arr) = parse_leading_json_string_array(slice_str) {
                    parsed_here = Some(arr);
                    break;
                }
            } else if data[idx] == 0x00
                && idx + 2 < data.len()
                && data[idx + 1] == b'['
                && data[idx + 2] == 0x00
            {
                let json_start = idx + 1;
                let json_end = (json_start + MAX_JSON_BYTES).min(data.len());
                let decoded = decode_utf16le_slice(&data[json_start..json_end]);
                if let Some(arr) = parse_leading_json_string_array(&decoded) {
                    parsed_here = Some(arr);
                    break;
                }
            }
        }

        if let Some(favs) = parsed_here {
            if !take_last {
                return Some(favs);
            }
            result = Some(favs);
        }
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn encode_snappy_uncompressed_literal(payload: &[u8]) -> Vec<u8> {
        // Test helper: write varint length + a single Snappy literal chunk.
        let mut out = Vec::new();
        let mut n = payload.len();
        while n >= 0x80 {
            out.push(((n as u8) & 0x7f) | 0x80);
            n >>= 7;
        }
        out.push(n as u8);

        let len_m1 = payload.len() - 1;
        if len_m1 < 60 {
            out.push((len_m1 as u8) << 2);
        } else {
            out.push(60 << 2);
            out.push(len_m1 as u8);
        }
        out.extend_from_slice(payload);
        out
    }

    #[test]
    fn test_extract_favorites_utf8_log_takes_latest() {
        let mut log_bytes = Vec::new();
        log_bytes.extend_from_slice(b"_file://\x00\x01fanta_favorite_games\x0f\x01[\"Halo\", \"Portal\"]");
        log_bytes.extend_from_slice(b"_file://\x00\x01fanta_favorite_games\x03\x01[]");
        assert_eq!(extract_favorites_from_bytes(&log_bytes, true), Some(vec![]));

        log_bytes.extend_from_slice(b"_file://\x00\x01fanta_favorite_games\x18\x01[\"Elden Ring\", \"halo\"]");
        assert_eq!(
            extract_favorites_from_bytes(&log_bytes, true),
            Some(vec!["elden ring".to_string(), "halo".to_string()])
        );
    }

    #[test]
    fn test_extract_favorites_utf16le() {
        let mut raw = Vec::new();
        raw.extend_from_slice(b"_file://\x00\x01fanta_favorite_games\x10\x00");
        let utf16: Vec<u16> = "[\"Cyberpunk 2077\",\"Hades\"]".encode_utf16().collect();
        for unit in utf16 {
            raw.extend_from_slice(&unit.to_le_bytes());
        }
        assert_eq!(
            extract_favorites_from_bytes(&raw, false),
            Some(vec!["cyberpunk 2077".to_string(), "hades".to_string()])
        );
    }

    #[test]
    fn test_snappy_decompress_and_extract() {
        // Test literal + 1-byte offset copy backreference in Snappy:
        // Target decoded bytes: "abcabcabc" followed by "_file://\x00\x01fanta_favorite_games\x01[\"peak\"]"
        let prefix_part = b"abc";
        let tail_part = b"_file://\x00\x01fanta_favorite_games\x0c\x01[\"Peak\"]";
        let total_len = 9 + tail_part.len();

        let mut compressed = Vec::new();
        compressed.push(total_len as u8); // varint uncompressed len (< 128)
        // Literal "abc" (len 3 -> tag ((3-1)<<2) = 8)
        compressed.push((2 << 2) | 0x00);
        compressed.extend_from_slice(prefix_part);
        // Copy 6 bytes from offset 3 -> copy_len = 6 => (6-4) = 2 in bits 2..4, tag type 0x01
        compressed.push((2 << 2) | 0x01);
        compressed.push(3);
        // Literal tail_part
        compressed.push(((tail_part.len() - 1) as u8) << 2);
        compressed.extend_from_slice(tail_part);

        let decompressed = decompress_snappy(&compressed).expect("snappy decompress");
        assert!(decompressed.starts_with(b"abcabcabc"));
        assert_eq!(
            extract_favorites_from_bytes(&decompressed, false),
            Some(vec!["peak".to_string()])
        );

        // Also test multi-byte literal helper roundtrip
        let big_payload = b"_file://\x00\x01fanta_favorite_games\x12\x01[\"Game One\",\"Game Two\"]padding_bytes_past_60_bytes_to_hit_extra_len_byte";
        let big_compressed = encode_snappy_uncompressed_literal(big_payload);
        let big_decompressed = decompress_snappy(&big_compressed).expect("big snappy decompress");
        assert_eq!(big_decompressed, big_payload);
        assert_eq!(
            extract_favorites_from_bytes(&big_decompressed, false),
            Some(vec!["game one".to_string(), "game two".to_string()])
        );
    }
}
