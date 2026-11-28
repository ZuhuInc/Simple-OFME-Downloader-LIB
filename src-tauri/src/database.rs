use crate::config::ConfigManager;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

#[derive(Clone, Debug)]
pub struct GameEntry {
    pub id: String,
    pub index: usize,
    pub title: String,
    pub version: String,
    pub host: String,
    pub approx_size: String,
    pub size_bytes: u64,
    pub description: String,
    pub thumbnail: String,
    pub origin_url: String,
    pub main_game_url: String,
    pub parts: Vec<String>,
    pub fix_url: String,
    pub category: String,
    pub installed_version: Option<String>,
    pub is_downloaded: bool,
    pub location: Option<String>,
    pub steam_url: Option<String>,
    pub steam_appid: Option<String>,
    pub exe_path: Option<String>,
    pub preferred_runner: Option<String>,
    pub runner_exes: Map<String, Value>,
    pub runner_steam_urls: Map<String, Value>,
    pub source: String,
    pub mirrors: Map<String, Value>,
    pub runners: Vec<Value>,
}

impl GameEntry {
    pub fn determine_source(origin_url: &str, host: &str, raw_source: Option<&str>) -> String {
        if let Some(s) = raw_source {
            let trimmed = s.trim();
            if !trimmed.is_empty() {
                let s_up = trimmed.to_uppercase();
                return match s_up.as_str() {
                    "OFME" | "ONLINE-FIX" | "ONLINEFIX" => "OFME".to_string(),
                    "SR" | "STEAMRIP" => "SR".to_string(),
                    "CG" | "CRACKED-GAMES" | "CRACKEDGAMES" => "CG".to_string(),
                    _ => trimmed.to_string(),
                };
            }
        }

        let u = origin_url.to_lowercase();
        if u.contains("online-fix.me") {
            return "OFME".to_string();
        }
        if u.contains("steamrip.com") {
            return "SR".to_string();
        }
        if u.contains("cracked-games.org") {
            return "CG".to_string();
        }

        let h = host.to_uppercase();
        match h.as_str() {
            "OFME" | "ONLINE-FIX" | "ONLINEFIX" => "OFME".to_string(),
            "SR" | "STEAMRIP" => "SR".to_string(),
            "CG" | "CRACKED-GAMES" | "CRACKEDGAMES" => "CG".to_string(),
            _ => String::new(),
        }
    }

    pub fn parse_size_bytes(size_str: &str) -> u64 {
        let lower = size_str.trim().to_ascii_lowercase();
        if lower.is_empty() {
            return 0;
        }
        let bytes = lower.as_bytes();
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i].is_ascii_digit() {
                let num_start = i;
                while i < bytes.len() && (bytes[i].is_ascii_digit() || bytes[i] == b'.') {
                    i += 1;
                }
                let num_str = &lower[num_start..i];
                let rest = lower[i..].trim_start();
                let unit = if rest.starts_with("tb") {
                    Some("TB")
                } else if rest.starts_with("gb") {
                    Some("GB")
                } else if rest.starts_with("mb") {
                    Some("MB")
                } else if rest.starts_with("kb") {
                    Some("KB")
                } else if rest.starts_with('b') {
                    Some("B")
                } else {
                    None
                };

                if let (Ok(val), Some(u)) = (num_str.parse::<f64>(), unit) {
                    let mult: f64 = match u {
                        "TB" => 1024_f64.powi(4),
                        "GB" => 1024_f64.powi(3),
                        "MB" => 1024_f64.powi(2),
                        "KB" => 1024_f64,
                        _ => 1.0,
                    };
                    return (val * mult) as u64;
                }
            }
            i += 1;
        }
        0
    }

    pub fn normalize_version_str(v: &str) -> String {
        let trimmed = v.trim().to_lowercase();
        trimmed.strip_prefix('v').unwrap_or(&trimmed).to_string()
    }

    /// Mirrors `re.sub(r"\.0(\d)\b", r".0.\1", norm)` for 1.03 vs 1.0.3 equivalence.
    pub fn normalize_zero_padded_minor(v: &str) -> String {
        let chars: Vec<char> = v.chars().collect();
        let mut out = String::with_capacity(v.len() + 2);
        let mut i = 0;
        while i < chars.len() {
            if i + 2 < chars.len()
                && chars[i] == '.'
                && chars[i + 1] == '0'
                && chars[i + 2].is_ascii_digit()
                && !chars
                    .get(i + 3)
                    .is_some_and(|c| c.is_ascii_alphanumeric() || *c == '_')
            {
                out.push('.');
                out.push('0');
                out.push('.');
                out.push(chars[i + 2]);
                i += 3;
                continue;
            }
            out.push(chars[i]);
            i += 1;
        }
        out
    }

    pub fn status_code(&self) -> u8 {
        if !self.is_downloaded && self.installed_version.is_none() {
            return 0;
        }
        if let Some(ref inst) = self.installed_version {
            let norm_inst = Self::normalize_version_str(inst);
            let norm_cat = Self::normalize_version_str(&self.version);
            if norm_inst != norm_cat && !norm_inst.is_empty() {
                if Self::normalize_zero_padded_minor(&norm_inst)
                    == Self::normalize_zero_padded_minor(&norm_cat)
                {
                    return 1;
                }
                return 2;
            }
            return 1;
        }
        1
    }

    pub fn status_text(&self) -> &'static str {
        if !self.is_downloaded && self.installed_version.is_none() {
            return "not_downloaded";
        }
        if let Some(ref inst) = self.installed_version {
            let norm_inst = Self::normalize_version_str(inst);
            let norm_cat = Self::normalize_version_str(&self.version);
            if norm_inst != norm_cat && !norm_inst.is_empty() {
                if Self::normalize_zero_padded_minor(&norm_inst)
                    == Self::normalize_zero_padded_minor(&norm_cat)
                {
                    return "up_to_date";
                }
                return "needs_update";
            }
            return "up_to_date";
        }
        "downloaded"
    }

    pub fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "index": self.index,
            "title": self.title,
            "version": self.version,
            "host": self.host,
            "approx_size": self.approx_size,
            "size_bytes": self.size_bytes,
            "description": self.description,
            "thumbnail": self.thumbnail,
            "origin_url": self.origin_url,
            "main_game_url": self.main_game_url,
            "parts": self.parts,
            "fix_url": self.fix_url,
            "category": self.category,
            "status": self.status_code(),
            "status_text": self.status_text(),
            "installed_version": self.installed_version,
            "is_downloaded": self.is_downloaded || self.installed_version.is_some(),
            "location": self.location,
            "steam_url": self.steam_url,
            "steam_appid": self.steam_appid,
            "exe_path": self.exe_path,
            "preferred_runner": self.preferred_runner,
            "runner_exes": self.runner_exes,
            "runner_steam_urls": self.runner_steam_urls,
            "source": self.source,
            "mirrors": self.mirrors,
            "runners": self.runners,
        })
    }
}

pub fn normalize_key(s: &str) -> String {
    s.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .flat_map(|c| c.to_lowercase())
        .collect()
}

fn sanitize_raw_id(title: &str, host: &str) -> String {
    let t: String = title
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
        .collect();
    format!("{}_{}", t, host.to_lowercase())
}

fn get_str_field(obj: &Map<String, Value>, keys: &[&str], default: &str) -> String {
    for &k in keys {
        if let Some(v) = obj.get(k) {
            if let Some(s) = v.as_str() {
                if !s.is_empty() {
                    return s.to_string();
                }
            } else if !v.is_null() {
                let s = v.to_string().trim_matches('"').to_string();
                if !s.is_empty() {
                    return s;
                }
            }
        }
    }
    default.to_string()
}

fn get_opt_str_field(obj: &Map<String, Value>, keys: &[&str]) -> Option<String> {
    for &k in keys {
        if let Some(v) = obj.get(k) {
            if let Some(s) = v.as_str() {
                if !s.is_empty() {
                    return Some(s.to_string());
                }
            } else if !v.is_null() {
                let s = v.to_string().trim_matches('"').to_string();
                if !s.is_empty() && s != "null" {
                    return Some(s);
                }
            }
        }
    }
    None
}

fn resolve_valid_location(title: &str, raw_loc: Option<&str>, config: &ConfigManager) -> Option<String> {
    let raw_loc = raw_loc?.trim();
    if raw_loc.is_empty() {
        return None;
    }

    let norm_title = normalize_key(title);
    let norm_no_the = norm_title.strip_prefix("the").unwrap_or(&norm_title).to_string();

    let find_title_subdir = |base_dir: &Path| -> Option<String> {
        if !base_dir.is_dir() {
            return None;
        }
        let entries = fs::read_dir(base_dir).ok()?;
        for entry in entries.flatten() {
            let full = entry.path();
            if full.is_dir() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with('_') {
                    continue;
                }
                let ekey = normalize_key(&name);
                let eno_the = ekey.strip_prefix("the").unwrap_or(&ekey);
                if (!norm_title.is_empty() && ekey == norm_title)
                    || (!norm_no_the.is_empty() && eno_the == norm_no_the)
                {
                    return Some(full.to_string_lossy().to_string());
                }
            }
        }
        None
    };

    let raw_path = Path::new(raw_loc);
    if raw_path.is_dir() {
        let base_lower = raw_path
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        if base_lower == "games2" || base_lower == "games" {
            if let Some(sub) = find_title_subdir(raw_path) {
                return Some(sub);
            }
        }
        let games2_sub = raw_path.join("GAMES2");
        if games2_sub.is_dir() {
            if let Some(sub) = find_title_subdir(&games2_sub) {
                return Some(sub);
            }
        }
        return Some(raw_loc.to_string());
    }

    for key in ["extract_path", "default_download_path", "download_path"] {
        let base_str = config.get_str(key);
        if !base_str.is_empty() {
            let base = Path::new(&base_str);
            if base.is_dir() {
                if let Some(sub) = find_title_subdir(base) {
                    return Some(sub);
                }
                let games2_base = base.join("GAMES2");
                if games2_base.is_dir() {
                    if let Some(sub) = find_title_subdir(&games2_base) {
                        return Some(sub);
                    }
                }
            }
        }
    }

    None
}

#[derive(Default)]
pub struct DatabaseManager {
    pub games: Vec<GameEntry>,
    pub hosts: Vec<String>,
    pub loaded_source_mtime: Option<SystemTime>,
    pub loaded_use_local: Option<bool>,
    pub loaded_local_path: Option<PathBuf>,
}

impl DatabaseManager {
    fn update_hosts_list(&mut self) {
        let mut found_sources = Vec::new();
        let mut found_hosts = Vec::new();
        for g in &self.games {
            if !g.source.is_empty() && !found_sources.contains(&g.source) {
                found_sources.push(g.source.clone());
            }
            if !g.host.is_empty() {
                let hu = g.host.to_uppercase();
                if hu != "OFME" && hu != "SR" && hu != "CG" && !found_hosts.contains(&g.host) {
                    found_hosts.push(g.host.clone());
                }
            }
        }
        let _ = found_sources;
        found_hosts.sort();
        let mut hosts = vec!["OFME".to_string(), "SR".to_string(), "CG".to_string()];
        for h in found_hosts {
            if !hosts.contains(&h) {
                hosts.push(h);
            }
        }
        self.hosts = hosts;
    }

    pub fn is_catalog_only_entry(obj: &Map<String, Value>) -> bool {
        let has_downloaded_flag = obj
            .get("downloaded")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let has_install_fields = get_opt_str_field(
            obj,
            &[
                "location",
                "exe_path",
                "steam_url",
                "installed_version",
                "preferred_runner",
            ],
        )
        .is_some();
        let has_runner_exes = obj
            .get("runner_exes")
            .and_then(|v| v.as_object())
            .is_some_and(|m| !m.is_empty());

        if has_downloaded_flag || has_install_fields || has_runner_exes {
            return false;
        }

        const CATALOG_MARKERS: [&str; 9] = [
            "parts",
            "origin_url",
            "Origin",
            "main_game_url",
            "MainGame",
            "thumbnail",
            "Thumbnail",
            "approx_size",
            "ApproxSize",
        ];
        CATALOG_MARKERS.iter().any(|k| obj.contains_key(*k))
    }

    pub fn installed_entry_score(key: &str, obj: &Map<String, Value>) -> u8 {
        let mut score = 0u8;
        if get_opt_str_field(obj, &["location"]).is_some() {
            score += 4;
        }
        if obj
            .get("downloaded")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
        {
            score += 2;
        }
        if get_opt_str_field(obj, &["exe_path", "steam_url"]).is_some() {
            score += 1;
        }
        if key == key.to_uppercase() {
            score += 1;
        }
        score
    }

    fn build_installed_lookup<'a>(
        installed: &'a Map<String, Value>,
    ) -> HashMap<String, &'a Map<String, Value>> {
        let mut lookup: HashMap<String, (u8, &'a Map<String, Value>)> = HashMap::new();
        for (k, v) in installed {
            if let Some(obj) = v.as_object() {
                if Self::is_catalog_only_entry(obj) {
                    continue;
                }
                let norm = normalize_key(k);
                let score = Self::installed_entry_score(k, obj);
                match lookup.get(&norm) {
                    Some(&(prev_score, _)) if score < prev_score => {}
                    _ => {
                        lookup.insert(norm, (score, obj));
                    }
                }
            }
        }
        lookup.into_iter().map(|(k, (_s, v))| (k, v)).collect()
    }

    fn make_entry(
        idx: usize,
        title: String,
        info: &Map<String, Value>,
        raw_id_override: Option<String>,
        lookup: &HashMap<String, &Map<String, Value>>,
        config: &ConfigManager,
    ) -> GameEntry {
        let host = get_str_field(info, &["host", "Host"], "GoFile");
        let raw_id = raw_id_override.unwrap_or_else(|| sanitize_raw_id(&title, &host));
        let norm_title = normalize_key(&title);
        let norm_id = normalize_key(&raw_id);
        let game_state = lookup
            .get(&norm_id)
            .or_else(|| lookup.get(&norm_title))
            .copied();

        let inst_ver = game_state.and_then(|gs| get_opt_str_field(gs, &["version", "installed_version"]));
        let raw_loc = game_state.and_then(|gs| get_opt_str_field(gs, &["location"]));
        let loc = resolve_valid_location(&title, raw_loc.as_deref(), config);
        let is_downloaded = if raw_loc.is_some() && loc.is_none() {
            false
        } else {
            loc.is_some()
                || game_state
                    .and_then(|gs| gs.get("downloaded").and_then(|v| v.as_bool()))
                    .unwrap_or(false)
                || inst_ver.is_some()
        };

        let parts: Vec<String> = info
            .get("parts")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|p| p.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();

        let main_game_url = {
            let explicit = get_str_field(info, &["main_game_url", "MainGame"], "");
            if !explicit.is_empty() {
                explicit
            } else {
                parts.first().cloned().unwrap_or_default()
            }
        };

        let final_parts = if parts.is_empty() && !main_game_url.is_empty() {
            vec![main_game_url.clone()]
        } else {
            parts
        };

        let approx_size = get_str_field(info, &["approx_size", "ApproxSize"], "Unknown");
        let origin_url = get_str_field(info, &["origin_url", "Origin"], "");
        let raw_source = get_opt_str_field(info, &["source"]);
        let source = GameEntry::determine_source(&origin_url, &host, raw_source.as_deref());

        let mirrors = info
            .get("mirrors")
            .and_then(|v| v.as_object())
            .cloned()
            .unwrap_or_default();

        let runners = info
            .get("runners")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();

        let steam_appid = get_opt_str_field(info, &["steam_appid"])
            .or_else(|| game_state.and_then(|gs| get_opt_str_field(gs, &["steam_appid"])));

        GameEntry {
            id: raw_id,
            index: idx,
            title,
            version: get_str_field(info, &["version"], "1.0"),
            size_bytes: GameEntry::parse_size_bytes(&approx_size),
            host,
            approx_size,
            description: get_str_field(
                info,
                &["description", "Description"],
                "No description available.",
            ),
            thumbnail: get_str_field(info, &["thumbnail", "Thumbnail"], ""),
            origin_url,
            main_game_url,
            parts: final_parts,
            fix_url: get_str_field(info, &["fix_url", "Fix"], ""),
            category: get_str_field(info, &["category"], "General"),
            installed_version: inst_ver,
            is_downloaded,
            location: loc,
            steam_url: game_state.and_then(|gs| get_opt_str_field(gs, &["steam_url"])),
            steam_appid,
            exe_path: game_state.and_then(|gs| get_opt_str_field(gs, &["exe_path"])),
            preferred_runner: game_state.and_then(|gs| get_opt_str_field(gs, &["preferred_runner"])),
            runner_exes: game_state
                .and_then(|gs| gs.get("runner_exes").and_then(|v| v.as_object()).cloned())
                .unwrap_or_default(),
            runner_steam_urls: game_state
                .and_then(|gs| {
                    gs.get("runner_steam_urls")
                        .and_then(|v| v.as_object())
                        .cloned()
                })
                .unwrap_or_default(),
            source,
            mirrors,
            runners,
        }
    }

    pub fn parse_database(&self, raw_json: &str, config: &ConfigManager) -> Vec<GameEntry> {
        let Ok(parsed) = serde_json::from_str::<Value>(raw_json) else {
            return Vec::new();
        };
        let lookup = Self::build_installed_lookup(&config.installed_games);
        let mut entries = Vec::new();

        match parsed {
            Value::Object(map) => {
                for (idx, (title, val)) in map.into_iter().enumerate() {
                    if let Some(info) = val.as_object() {
                        entries.push(Self::make_entry(idx, title, info, None, &lookup, config));
                    }
                }
            }
            Value::Array(items) => {
                for (idx, val) in items.into_iter().enumerate() {
                    if let Some(item) = val.as_object() {
                        let title = get_str_field(item, &["title", "name"], "Unknown");
                        let raw_id = get_opt_str_field(item, &["id"]);
                        entries.push(Self::make_entry(idx, title, item, raw_id, &lookup, config));
                    }
                }
            }
            _ => {}
        }

        entries
    }

    pub fn update_installed_states(&mut self, config: &ConfigManager) {
        let lookup = Self::build_installed_lookup(&config.installed_games);
        for g in &mut self.games {
            let norm_title = normalize_key(&g.title);
            let norm_id = normalize_key(&g.id);
            let game_state = lookup
                .get(&norm_id)
                .or_else(|| lookup.get(&norm_title))
                .copied();

            let inst_ver =
                game_state.and_then(|gs| get_opt_str_field(gs, &["version", "installed_version"]));
            let raw_loc = game_state.and_then(|gs| get_opt_str_field(gs, &["location"]));
            let loc = resolve_valid_location(&g.title, raw_loc.as_deref(), config);
            let is_dl = if raw_loc.is_some() && loc.is_none() {
                false
            } else {
                loc.is_some()
                    || game_state
                        .and_then(|gs| gs.get("downloaded").and_then(|v| v.as_bool()))
                        .unwrap_or(false)
                    || inst_ver.is_some()
            };

            g.is_downloaded = is_dl;
            g.installed_version = inst_ver;
            g.location = loc;
            g.steam_url = game_state.and_then(|gs| get_opt_str_field(gs, &["steam_url"]));
            if let Some(appid) = game_state.and_then(|gs| get_opt_str_field(gs, &["steam_appid"])) {
                g.steam_appid = Some(appid);
            }
            g.exe_path = game_state.and_then(|gs| get_opt_str_field(gs, &["exe_path"]));
            g.preferred_runner =
                game_state.and_then(|gs| get_opt_str_field(gs, &["preferred_runner"]));
            g.runner_exes = game_state
                .and_then(|gs| gs.get("runner_exes").and_then(|v| v.as_object()).cloned())
                .unwrap_or_default();
            g.runner_steam_urls = game_state
                .and_then(|gs| {
                    gs.get("runner_steam_urls")
                        .and_then(|v| v.as_object())
                        .cloned()
                })
                .unwrap_or_default();
        }
    }

    pub fn load_local_or_cached(
        &mut self,
        config: &ConfigManager,
        force_reload: bool,
    ) -> bool {
        let use_local = config.get_bool("use_local_db");
        let active_local_path = config.get_active_db_path();
        let cache_json_path = config.cache_folder.join("Data.json");

        if use_local {
            if let Some(ref p) = active_local_path {
                let cur_mtime = fs::metadata(p).ok().and_then(|m| m.modified().ok());
                if !force_reload
                    && !self.games.is_empty()
                    && self.loaded_use_local == Some(true)
                    && self.loaded_local_path.as_ref() == Some(p)
                    && self.loaded_source_mtime == cur_mtime
                {
                    return true;
                }
                if p.is_file() {
                    if let Ok(raw) = fs::read_to_string(p) {
                        self.games = self.parse_database(&raw, config);
                        self.update_hosts_list();
                        self.loaded_source_mtime = cur_mtime;
                        self.loaded_use_local = Some(true);
                        self.loaded_local_path = Some(p.clone());
                        return !self.games.is_empty();
                    }
                }
            }
            return false;
        }

        // Non-local mode: check cache/Data.json first, then bundled Data.json
        if !force_reload && !self.games.is_empty() && self.loaded_use_local == Some(false) {
            return true;
        }

        if cache_json_path.is_file() {
            if let Ok(raw) = fs::read_to_string(&cache_json_path) {
                let parsed = self.parse_database(&raw, config);
                if !parsed.is_empty() {
                    self.games = parsed;
                    self.update_hosts_list();
                    self.loaded_source_mtime = fs::metadata(&cache_json_path)
                        .ok()
                        .and_then(|m| m.modified().ok());
                    self.loaded_use_local = Some(false);
                    self.loaded_local_path = Some(cache_json_path);
                    return true;
                }
            }
        }

        if let Some(ref bundled) = config.bundled_data_path {
            if bundled.is_file() {
                if let Ok(raw) = fs::read_to_string(bundled) {
                    let parsed = self.parse_database(&raw, config);
                    if !parsed.is_empty() {
                        self.games = parsed;
                        self.update_hosts_list();
                        self.loaded_source_mtime =
                            fs::metadata(bundled).ok().and_then(|m| m.modified().ok());
                        self.loaded_use_local = Some(false);
                        self.loaded_local_path = Some(bundled.clone());
                        return true;
                    }
                }
            }
        }

        false
    }

    pub async fn fetch_remote_raw(db_url: &str, cache_path: &Path) -> Result<String, String> {
        let client = reqwest::Client::builder()
            .user_agent("Fanta-OFME-Downloader")
            .timeout(Duration::from_secs(7))
            .build()
            .map_err(|e| e.to_string())?;

        let resp = client.get(db_url).send().await.map_err(|e| e.to_string())?;
        if !resp.status().is_success() {
            return Err(format!("HTTP {}", resp.status()));
        }
        let text = resp.text().await.map_err(|e| e.to_string())?;
        if let Some(parent) = cache_path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let _ = fs::write(cache_path, &text);
        Ok(text)
    }

    pub fn apply_raw_catalog(&mut self, raw_json: &str, config: &ConfigManager, source_path: PathBuf) {
        let parsed = self.parse_database(raw_json, config);
        if !parsed.is_empty() {
            self.games = parsed;
            self.update_hosts_list();
            self.loaded_source_mtime = fs::metadata(&source_path)
                .ok()
                .and_then(|m| m.modified().ok());
            self.loaded_use_local = Some(false);
            self.loaded_local_path = Some(source_path);
        }
    }

    pub fn search_and_filter(
        &self,
        query: &str,
        host: &str,
        status_filter: &str,
        sort_by: &str,
        sort_order: &str,
    ) -> Vec<Value> {
        let mut results: Vec<&GameEntry> = self.games.iter().collect();

        let q = query.trim().to_lowercase();
        if !q.is_empty() {
            results.retain(|g| {
                g.title.to_lowercase().contains(&q) || g.description.to_lowercase().contains(&q)
            });
        }

        let h_lower = host.trim().to_lowercase();
        if !h_lower.is_empty() && h_lower != "all" {
            results.retain(|g| {
                g.host.to_lowercase() == h_lower || g.source.to_lowercase() == h_lower
            });
        }

        let sf = status_filter.trim().to_lowercase();
        if !sf.is_empty() && sf != "all" {
            match sf.as_str() {
                "downloaded" => {
                    results.retain(|g| g.is_downloaded || g.installed_version.is_some())
                }
                "needs_update" => results.retain(|g| g.status_text() == "needs_update"),
                "up_to_date" => results.retain(|g| g.status_text() == "up_to_date"),
                _ => {}
            }
        }

        let desc = sort_order.eq_ignore_ascii_case("desc");
        match sort_by {
            "title" => results.sort_by(|a, b| a.title.to_lowercase().cmp(&b.title.to_lowercase())),
            "size" => results.sort_by(|a, b| a.size_bytes.cmp(&b.size_bytes)),
            "host" => results.sort_by(|a, b| a.host.to_lowercase().cmp(&b.host.to_lowercase())),
            _ => results.sort_by(|a, b| a.index.cmp(&b.index)),
        }
        if desc {
            results.reverse();
        }

        results.into_iter().map(|g| g.to_json()).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_size_bytes() {
        assert_eq!(GameEntry::parse_size_bytes("8.3GB"), (8.3 * 1024f64.powi(3)) as u64);
        assert_eq!(GameEntry::parse_size_bytes("512 MB"), 512 * 1024 * 1024);
        assert_eq!(GameEntry::parse_size_bytes("Unknown"), 0);
    }

    #[test]
    fn test_determine_source() {
        assert_eq!(
            GameEntry::determine_source("https://online-fix.me/games/123", "GoFile", None),
            "OFME"
        );
        assert_eq!(
            GameEntry::determine_source("https://steamrip.com/game/", "BuzzHeavier", None),
            "SR"
        );
        assert_eq!(
            GameEntry::determine_source("", "GoFile", Some("cracked-games")),
            "CG"
        );
    }

    #[test]
    fn test_zero_padded_minor_version_equivalence() {
        assert_eq!(GameEntry::normalize_zero_padded_minor("1.03"), "1.0.3");
        assert_eq!(GameEntry::normalize_zero_padded_minor("1.0.3"), "1.0.3");
    }

    #[test]
    fn test_preserve_order_and_search_filter() {
        let mut cfg = ConfigManager::default();
        cfg.installed_games.clear();

        let raw = r#"{
            "Zeta Game": { "version": "1.0", "host": "GoFile", "approx_size": "2 GB", "origin_url": "https://steamrip.com/z" },
            "Alpha Game": { "version": "1.0.3", "host": "PixelDrain", "approx_size": "500 MB", "origin_url": "https://online-fix.me/a" }
        }"#;
        let mut db = DatabaseManager::default();
        db.games = db.parse_database(raw, &cfg);
        db.update_hosts_list();

        let default_order = db.search_and_filter("", "", "all", "default", "asc");
        assert_eq!(default_order.len(), 2);
        assert_eq!(default_order[0]["title"], "Zeta Game");
        assert_eq!(default_order[1]["title"], "Alpha Game");

        let by_title = db.search_and_filter("", "", "all", "title", "asc");
        assert_eq!(by_title[0]["title"], "Alpha Game");

        let by_source = db.search_and_filter("", "OFME", "all", "default", "asc");
        assert_eq!(by_source.len(), 1);
        assert_eq!(by_source[0]["title"], "Alpha Game");
    }

    #[test]
    fn test_installed_lookup_ignores_catalog_only_duplicates() {
        let mut cfg = ConfigManager::default();
        cfg.installed_games.clear();

        // Insert real installed record first, then a trailing legacy catalog-only duplicate
        cfg.installed_games.insert(
            "MEGABONK".into(),
            json!({
                "location": "D:\\GAMES2\\Megabonk",
                "downloaded": true,
                "version": "21750826",
                "exe_path": "D:\\GAMES2\\Megabonk\\Megabonk.exe"
            }),
        );
        cfg.installed_games.insert(
            "Megabonk".into(),
            json!({
                "version": "21750826Pre-Installed GameMegaDB",
                "host": "BuzzHeavier",
                "parts": ["https://bzzhr.to/jacb00xgmt7c"],
                "origin_url": "https://steamrip.com/megabonk-free-download",
                "thumbnail": "https://steamrip.com/wp-content/uploads/2025/09/megabonk.jpg"
            }),
        );
        cfg.installed_games.insert(
            "Hades 2".into(),
            json!({
                "version": "1.143476",
                "host": "GoFile",
                "parts": ["https://gofile.io/d/45J1cq5n"]
            }),
        );

        let raw_catalog = r#"{
            "Megabonk": { "version": "21750826", "host": "BuzzHeavier", "parts": ["https://bzzhr.to/jacb00xgmt7c"] },
            "Hades 2": { "version": "1.143476", "host": "GoFile", "parts": ["https://gofile.io/d/45J1cq5n"] }
        }"#;
        let mut db = DatabaseManager::default();
        db.games = db.parse_database(raw_catalog, &cfg);

        assert_eq!(db.games.len(), 2);
        let megabonk = &db.games[0];
        assert_eq!(megabonk.status_code(), 1);
        assert_eq!(megabonk.status_text(), "up_to_date");
        assert_eq!(megabonk.installed_version.as_deref(), Some("21750826"));
        assert_eq!(
            megabonk.exe_path.as_deref(),
            Some("D:\\GAMES2\\Megabonk\\Megabonk.exe")
        );

        let hades = &db.games[1];
        assert_eq!(hades.status_code(), 0);
        assert_eq!(hades.status_text(), "not_downloaded");
        assert!(!hades.is_downloaded);
    }
}
