use crate::config::{get_home_dir, ConfigManager};
use crate::database::{normalize_key, DatabaseManager, GameEntry};
use crate::extractor::is_process_running;
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
#[cfg(target_os = "windows")]
const DETACHED_PROCESS: u32 = 0x0000_0008;

static AVATAR_CACHE: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();

pub const DEFAULT_STEAM_PATHS: [&str; 6] = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Steam",
    r"E:\Steam",
    r"D:\SteamLibrary",
    r"E:\SteamLibrary",
];

const STEAM_CDN_BASE: &str = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps";

pub fn crc32_ieee(data: &[u8]) -> u32 {
    let mut crc: u32 = 0xFFFF_FFFF;
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    !crc
}

pub fn calculate_appid(exe_path: &str, app_name: &str) -> u32 {
    let key = format!("{}{}", exe_path, app_name);
    crc32_ieee(key.as_bytes()) | 0x8000_0000
}

pub fn calculate_shortcut_id(appid: u32) -> u64 {
    ((appid as u64) << 32) | 0x0200_0000
}

#[derive(Clone, Debug, PartialEq)]
pub enum VdfValue {
    Map(Vec<(String, VdfValue)>),
    Str(String),
    U32(u32),
    U64(u64),
}

impl VdfValue {
    pub fn empty_map() -> Self {
        Self::Map(Vec::new())
    }

    pub fn as_map(&self) -> Option<&Vec<(String, VdfValue)>> {
        if let Self::Map(m) = self {
            Some(m)
        } else {
            None
        }
    }

    pub fn as_map_mut(&mut self) -> Option<&mut Vec<(String, VdfValue)>> {
        if let Self::Map(m) = self {
            Some(m)
        } else {
            None
        }
    }

    pub fn get_ci(&self, key: &str) -> Option<&VdfValue> {
        let map = self.as_map()?;
        map.iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(key))
            .map(|(_, v)| v)
    }

    pub fn get_str_ci(&self, key: &str) -> Option<&str> {
        match self.get_ci(key)? {
            VdfValue::Str(s) => Some(s.as_str()),
            _ => None,
        }
    }

    pub fn get_u32_ci(&self, key: &str) -> Option<u32> {
        match self.get_ci(key)? {
            VdfValue::U32(n) => Some(*n),
            _ => None,
        }
    }

    pub fn set_entry(&mut self, key: String, val: VdfValue) {
        if let Self::Map(map) = self {
            if let Some((_, existing)) = map.iter_mut().find(|(k, _)| k == &key) {
                *existing = val;
            } else {
                map.push((key, val));
            }
        }
    }

    pub fn get_or_insert_empty_map(&mut self, key: &str) -> Option<&mut Vec<(String, VdfValue)>> {
        if let Self::Map(map) = self {
            if let Some(pos) = map.iter().position(|(k, _)| k.eq_ignore_ascii_case(key)) {
                if !matches!(map[pos].1, VdfValue::Map(_)) {
                    map[pos].1 = VdfValue::empty_map();
                }
                return map[pos].1.as_map_mut();
            }
            map.push((key.to_string(), VdfValue::empty_map()));
            let last = map.len() - 1;
            return map[last].1.as_map_mut();
        }
        None
    }
}

pub struct BinaryVDF;

impl BinaryVDF {
    pub fn parse(data: &[u8]) -> VdfValue {
        let mut pos = 0usize;
        Self::parse_map(data, &mut pos, 0)
    }

    fn read_cstr(data: &[u8], pos: &mut usize) -> String {
        if *pos >= data.len() {
            return String::new();
        }
        let rel_end = data[*pos..].iter().position(|&b| b == 0);
        match rel_end {
            Some(len) => {
                let s = String::from_utf8_lossy(&data[*pos..*pos + len]).to_string();
                *pos += len + 1;
                s
            }
            None => {
                let s = String::from_utf8_lossy(&data[*pos..]).to_string();
                *pos = data.len();
                s
            }
        }
    }

    fn parse_map(data: &[u8], pos: &mut usize, depth: usize) -> VdfValue {
        let mut entries = Vec::new();
        if depth > 32 {
            return VdfValue::Map(entries);
        }
        while *pos < data.len() {
            let type_byte = data[*pos];
            *pos += 1;
            if type_byte == 8 {
                break;
            }
            let key = Self::read_cstr(data, pos);
            match type_byte {
                0 => {
                    let sub = Self::parse_map(data, pos, depth + 1);
                    entries.push((key, sub));
                }
                1 => {
                    let s = Self::read_cstr(data, pos);
                    entries.push((key, VdfValue::Str(s)));
                }
                2 => {
                    if *pos + 4 > data.len() {
                        break;
                    }
                    let val = u32::from_le_bytes([
                        data[*pos],
                        data[*pos + 1],
                        data[*pos + 2],
                        data[*pos + 3],
                    ]);
                    *pos += 4;
                    entries.push((key, VdfValue::U32(val)));
                }
                7 => {
                    if *pos + 8 > data.len() {
                        break;
                    }
                    let val = u64::from_le_bytes([
                        data[*pos],
                        data[*pos + 1],
                        data[*pos + 2],
                        data[*pos + 3],
                        data[*pos + 4],
                        data[*pos + 5],
                        data[*pos + 6],
                        data[*pos + 7],
                    ]);
                    *pos += 8;
                    entries.push((key, VdfValue::U64(val)));
                }
                _ => break,
            }
        }
        VdfValue::Map(entries)
    }

    pub fn serialize(val: &VdfValue) -> Vec<u8> {
        let mut out = Vec::new();
        if let VdfValue::Map(entries) = val {
            Self::write_entries(entries, &mut out);
        } else {
            out.push(8);
        }
        out
    }

    fn write_cstr(s: &str, out: &mut Vec<u8>) {
        out.extend_from_slice(s.as_bytes());
        out.push(0);
    }

    fn write_entries(entries: &[(String, VdfValue)], out: &mut Vec<u8>) {
        for (k, v) in entries {
            match v {
                VdfValue::Map(sub) => {
                    out.push(0);
                    Self::write_cstr(k, out);
                    Self::write_entries(sub, out);
                }
                VdfValue::Str(s) => {
                    out.push(1);
                    Self::write_cstr(k, out);
                    Self::write_cstr(s, out);
                }
                VdfValue::U32(n) => {
                    out.push(2);
                    Self::write_cstr(k, out);
                    out.extend_from_slice(&n.to_le_bytes());
                }
                VdfValue::U64(n) => {
                    out.push(7);
                    Self::write_cstr(k, out);
                    out.extend_from_slice(&n.to_le_bytes());
                }
            }
        }
        out.push(8);
    }
}

#[derive(Clone, Debug, Default)]
pub struct AddShortcutRequest {
    pub name: String,
    pub exe_path: String,
    pub start_dir: String,
    pub icon_path: String,
    pub launch_options: String,
    pub tags: Vec<String>,
    pub account_id: Option<String>,
    pub auto_artwork: bool,
    pub steam_appid: Option<String>,
}

#[derive(Clone, Debug)]
pub struct SteamManager {
    pub steam_path: Option<PathBuf>,
    pub libraries: Vec<String>,
}

impl SteamManager {
    pub fn new(custom_path: Option<&str>) -> Self {
        let steam_path = Self::detect_steam_path(custom_path);
        let mut mgr = Self {
            steam_path,
            libraries: Vec::new(),
        };
        mgr.libraries = mgr.detect_libraries();
        mgr
    }

    pub fn from_config(cfg: &ConfigManager) -> Self {
        let configured = cfg.get_str("steam_path");
        let opt = if configured.trim().is_empty() {
            None
        } else {
            Some(configured.trim())
        };
        Self::new(opt)
    }

    pub fn detect_steam_path(custom_path: Option<&str>) -> Option<PathBuf> {
        if let Some(cp) = custom_path {
            let trimmed = cp.trim();
            if !trimmed.is_empty() {
                let p = PathBuf::from(trimmed);
                if p.exists() {
                    return Some(normalize_win_path(&p));
                }
            }
        }

        if let Some(reg_path) = read_steam_path_from_registry() {
            if reg_path.exists() {
                return Some(normalize_win_path(&reg_path));
            }
        }

        for cand in DEFAULT_STEAM_PATHS {
            let p = PathBuf::from(cand);
            if p.exists() {
                return Some(normalize_win_path(&p));
            }
        }
        None
    }

    pub fn detect_libraries(&self) -> Vec<String> {
        let mut libs: Vec<String> = Vec::new();
        let Some(ref steam_root) = self.steam_path else {
            return libs;
        };
        if !steam_root.exists() {
            return libs;
        }
        libs.push(steam_root.to_string_lossy().to_string());

        let vdf_path = steam_root.join("steamapps").join("libraryfolders.vdf");
        if vdf_path.is_file() {
            if let Ok(raw) = fs::read_to_string(&vdf_path) {
                for raw_path in extract_vdf_key_values(&raw, "path") {
                    let unescaped = raw_path.replace("\\\\", "\\");
                    let p = normalize_win_path(Path::new(&unescaped));
                    if p.exists() {
                        let s = p.to_string_lossy().to_string();
                        if !libs.iter().any(|x| x.eq_ignore_ascii_case(&s)) {
                            libs.push(s);
                        }
                    }
                }
            }
        }
        libs
    }

    pub fn get_installed_games(&self) -> Vec<Value> {
        let mut games = Vec::new();
        for lib in &self.libraries {
            let steamapps = Path::new(lib).join("steamapps");
            let Ok(rd) = fs::read_dir(&steamapps) else {
                continue;
            };
            for entry in rd.flatten() {
                let fname = entry.file_name().to_string_lossy().to_string();
                if !(fname.starts_with("appmanifest_") && fname.ends_with(".acf")) {
                    continue;
                }
                let Ok(content) = fs::read_to_string(entry.path()) else {
                    continue;
                };
                let appid = extract_vdf_key_values(&content, "appid").into_iter().next();
                let name = extract_vdf_key_values(&content, "name").into_iter().next();
                let installdir = extract_vdf_key_values(&content, "installdir")
                    .into_iter()
                    .next()
                    .unwrap_or_default();
                let size_bytes = extract_vdf_key_values(&content, "SizeOnDisk")
                    .into_iter()
                    .next()
                    .and_then(|s| s.parse::<u64>().ok())
                    .unwrap_or(0);

                if let (Some(aid), Some(nm)) = (appid, name) {
                    let full_install_path = if installdir.is_empty() {
                        String::new()
                    } else {
                        steamapps
                            .join("common")
                            .join(&installdir)
                            .to_string_lossy()
                            .to_string()
                    };
                    games.push(json!({
                        "appid": aid,
                        "name": nm,
                        "install_dir": full_install_path,
                        "library_path": lib,
                        "size_bytes": size_bytes,
                    }));
                }
            }
        }
        games
    }

    pub async fn get_account_avatar(&self, steamid64: &str) -> Option<String> {
        let sid = steamid64.trim();
        if sid.is_empty() || !sid.chars().all(|c| c.is_ascii_digit()) {
            return None;
        }

        let cache = AVATAR_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
        if let Ok(guard) = cache.lock() {
            if let Some(url) = guard.get(sid) {
                return Some(url.clone());
            }
        }

        let url = format!("https://steamcommunity.com/profiles/{}/?xml=1", sid);
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            .timeout(Duration::from_millis(3500))
            .build()
            .ok()?;

        let text = client.get(&url).send().await.ok()?.text().await.ok()?;
        let avatar_url = extract_cdata_tag(&text, "avatarFull")
            .or_else(|| extract_cdata_tag(&text, "avatarMedium"))
            .or_else(|| extract_cdata_tag(&text, "avatarIcon"))?;

        if let Ok(mut guard) = cache.lock() {
            guard.insert(sid.to_string(), avatar_url.clone());
        }
        Some(avatar_url)
    }

    pub async fn get_user_accounts(&self) -> Vec<Value> {
        #[derive(Clone)]
        struct AccRow {
            steamid64: String,
            account_id: String,
            persona_name: String,
            account_name: String,
            avatar_url: Option<String>,
            most_recent: bool,
            has_shortcuts_vdf: bool,
            shortcuts_count: usize,
        }

        let Some(ref steam_root) = self.steam_path else {
            return Vec::new();
        };

        let mut rows: Vec<AccRow> = Vec::new();
        let mut seen_acc_ids: HashSet<String> = HashSet::new();
        let loginusers_path = steam_root.join("config").join("loginusers.vdf");

        if loginusers_path.is_file() {
            if let Ok(content) = fs::read_to_string(&loginusers_path) {
                let blocks = extract_loginuser_blocks(&content);
                for (idx, (sid64, block)) in blocks.into_iter().enumerate() {
                    let acc32 = sid64
                        .parse::<u64>()
                        .map(|n| (n & 0xFFFF_FFFF).to_string())
                        .unwrap_or_else(|_| sid64.clone());
                    seen_acc_ids.insert(acc32.clone());

                    let persona = extract_vdf_key_values(&block, "PersonaName")
                        .into_iter()
                        .next();
                    let account = extract_vdf_key_values(&block, "AccountName")
                        .into_iter()
                        .next();
                    let most_recent_flag = extract_vdf_key_values(&block, "MostRecent")
                        .into_iter()
                        .next()
                        .as_deref()
                        == Some("1");
                    let auto_login_flag = extract_vdf_key_values(&block, "AutoLogin")
                        .into_iter()
                        .next()
                        .as_deref()
                        == Some("1");
                    let is_recent = most_recent_flag || auto_login_flag;

                    let persona_name = persona
                        .filter(|s| !s.is_empty())
                        .or_else(|| account.clone().filter(|s| !s.is_empty()))
                        .unwrap_or_else(|| acc32.clone());
                    let account_name = account.unwrap_or_default();

                    let shortcuts_vdf = steam_root
                        .join("userdata")
                        .join(&acc32)
                        .join("config")
                        .join("shortcuts.vdf");
                    let has_shortcuts = shortcuts_vdf.is_file();
                    let shortcuts_count = count_shortcuts_in_file(&shortcuts_vdf);

                    let avatar_url = if is_recent || idx < 3 {
                        self.get_account_avatar(&sid64).await
                    } else {
                        None
                    };

                    rows.push(AccRow {
                        steamid64: sid64,
                        account_id: acc32,
                        persona_name,
                        account_name,
                        avatar_url,
                        most_recent: is_recent,
                        has_shortcuts_vdf: has_shortcuts,
                        shortcuts_count,
                    });
                }
            }
        }

        let userdata_dir = steam_root.join("userdata");
        if userdata_dir.is_dir() {
            if let Ok(rd) = fs::read_dir(&userdata_dir) {
                for entry in rd.flatten() {
                    if !entry.path().is_dir() {
                        continue;
                    }
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name == "0"
                        || name.is_empty()
                        || !name.chars().all(|c| c.is_ascii_digit())
                        || seen_acc_ids.contains(&name)
                    {
                        continue;
                    }
                    let sc_vdf = entry.path().join("config").join("shortcuts.vdf");
                    let has_shortcuts = sc_vdf.is_file();
                    let shortcuts_count = count_shortcuts_in_file(&sc_vdf);
                    rows.push(AccRow {
                        steamid64: String::new(),
                        account_id: name.clone(),
                        persona_name: format!("Account {}", name),
                        account_name: String::new(),
                        avatar_url: None,
                        most_recent: false,
                        has_shortcuts_vdf: has_shortcuts,
                        shortcuts_count,
                    });
                }
            }
        }

        rows.sort_by(|a, b| {
            b.most_recent
                .cmp(&a.most_recent)
                .then_with(|| b.shortcuts_count.cmp(&a.shortcuts_count))
        });

        rows.into_iter()
            .map(|a| {
                json!({
                    "steamid64": a.steamid64,
                    "account_id": a.account_id,
                    "persona_name": a.persona_name,
                    "account_name": a.account_name,
                    "avatar_url": a.avatar_url,
                    "most_recent": a.most_recent,
                    "has_shortcuts_vdf": a.has_shortcuts_vdf,
                    "shortcuts_count": a.shortcuts_count,
                })
            })
            .collect()
    }

    pub async fn get_active_account_id(&self, configured_id: Option<&str>) -> String {
        let accounts = self.get_user_accounts().await;
        Self::resolve_active_account_id_from_list(&accounts, configured_id)
    }

    pub fn resolve_active_account_id_from_list(
        accounts: &[Value],
        configured_id: Option<&str>,
    ) -> String {
        let cfg_id = configured_id.unwrap_or("").trim();
        if accounts.is_empty() {
            return cfg_id.to_string();
        }
        if !cfg_id.is_empty() {
            for acc in accounts {
                let aid = acc.get("account_id").and_then(|v| v.as_str()).unwrap_or("");
                let sid = acc.get("steamid64").and_then(|v| v.as_str()).unwrap_or("");
                if aid == cfg_id || sid == cfg_id {
                    return aid.to_string();
                }
            }
        }
        for acc in accounts {
            if acc.get("most_recent").and_then(|v| v.as_bool()).unwrap_or(false) {
                if let Some(aid) = acc.get("account_id").and_then(|v| v.as_str()) {
                    return aid.to_string();
                }
            }
        }
        accounts[0]
            .get("account_id")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    }

    pub async fn shortcuts_path(&self, account_id: Option<&str>) -> Option<PathBuf> {
        let steam_root = self.steam_path.as_ref()?;
        let acc = match account_id.map(str::trim).filter(|s| !s.is_empty()) {
            Some(explicit) => explicit.to_string(),
            None => self.get_active_account_id(None).await,
        };
        if acc.is_empty() {
            return None;
        }
        Some(
            steam_root
                .join("userdata")
                .join(acc)
                .join("config")
                .join("shortcuts.vdf"),
        )
    }

    pub async fn get_shortcuts(
        &self,
        account_id: Option<&str>,
        fanta_games: &Map<String, Value>,
        db_games: &[GameEntry],
    ) -> Vec<Value> {
        let Some(path) = self.shortcuts_path(account_id).await else {
            return Vec::new();
        };
        self.get_shortcuts_from_file(&path, fanta_games, db_games)
    }

    pub fn get_shortcuts_from_file(
        &self,
        path: &Path,
        fanta_games: &Map<String, Value>,
        db_games: &[GameEntry],
    ) -> Vec<Value> {
        let mut shortcuts_list = Vec::new();
        if !path.is_file() {
            return shortcuts_list;
        }
        let Ok(raw_bytes) = fs::read(path) else {
            return shortcuts_list;
        };

        // Build clean installed lookup (skipping legacy catalog-only entries)
        let mut clean_fanta: Vec<(&str, &Map<String, Value>)> = Vec::new();
        for (k, v) in fanta_games {
            if let Some(obj) = v.as_object() {
                if !DatabaseManager::is_catalog_only_entry(obj) {
                    clean_fanta.push((k.as_str(), obj));
                }
            }
        }

        let mut db_titles: HashMap<String, &GameEntry> = HashMap::new();
        for g in db_games {
            let norm = normalize_key(&g.title);
            if !norm.is_empty() {
                db_titles.entry(norm).or_insert(g);
            }
        }

        const GENERIC_ROOTS: [&str; 10] = [
            "c:",
            "d:",
            "e:",
            r"c:\",
            r"d:\",
            r"e:\",
            r"c:\games",
            r"d:\games",
            r"d:\games2",
            r"e:\games",
        ];

        let parsed = BinaryVDF::parse(&raw_bytes);
        let Some(shortcuts_map) = parsed.get_ci("shortcuts").and_then(|v| v.as_map()) else {
            return shortcuts_list;
        };

        for (idx, (key, val)) in shortcuts_map.iter().enumerate() {
            if !matches!(val, VdfValue::Map(_)) {
                continue;
            }
            let app_name = val
                .get_str_ci("AppName")
                .unwrap_or("")
                .trim()
                .to_string();
            let raw_exe = val.get_str_ci("Exe").unwrap_or("").trim().to_string();
            let clean_exe = raw_exe.trim_matches('"').to_string();
            let mut appid = val.get_u32_ci("appid").unwrap_or(0);
            if appid == 0 {
                appid = calculate_appid(&clean_exe, &app_name);
            }
            let short_id_64 = calculate_shortcut_id(appid);
            let steam_url = format!("steam://rungameid/{}", short_id_64);
            let exists_on_disk = !clean_exe.is_empty() && Path::new(&clean_exe).exists();

            let tags: Vec<String> = val
                .get_ci("tags")
                .and_then(|t| t.as_map())
                .map(|m| {
                    m.iter()
                        .filter_map(|(_, tv)| match tv {
                            VdfValue::Str(s) => Some(s.clone()),
                            _ => None,
                        })
                        .collect()
                })
                .unwrap_or_default();

            let devkit_id = val.get_str_ci("DevkitGameID").unwrap_or("").trim();

            let mut is_fanta = devkit_id == "FantaOFME"
                || tags.iter().any(|t| {
                    matches!(
                        t.to_lowercase().as_str(),
                        "online-fix" | "onlinefix" | "fanta" | "fanta ofme"
                    )
                });
            let mut fanta_matched_title = String::new();
            let mut fanta_thumbnail = String::new();
            let mut fanta_version = String::new();

            let name_clean = normalize_key(&app_name);
            let appid_str = appid.to_string();

            // Match explicit steam_url in Data.json
            for (fk, fv) in &clean_fanta {
                let db_steam_url = fv
                    .get("steam_url")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .trim();
                if !db_steam_url.is_empty()
                    && (db_steam_url == steam_url || db_steam_url.contains(&appid_str))
                {
                    is_fanta = true;
                    fanta_matched_title = (*fk).to_string();
                    fanta_thumbnail = fv
                        .get("thumbnail")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    fanta_version = fv
                        .get("version")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    break;
                }
            }

            // Match location or exact title against installed games or catalog
            if !is_fanta {
                let norm_exe = if clean_exe.is_empty() {
                    String::new()
                } else {
                    normalize_win_path(Path::new(&clean_exe))
                        .to_string_lossy()
                        .to_lowercase()
                };
                let exe_dir = Path::new(&norm_exe)
                    .parent()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_default();

                for (fk, fv) in &clean_fanta {
                    let fk_clean = normalize_key(fk);
                    let raw_loc = fv.get("location").and_then(|v| v.as_str()).unwrap_or("");
                    let loc = if raw_loc.trim().is_empty() {
                        String::new()
                    } else {
                        normalize_win_path(Path::new(raw_loc))
                            .to_string_lossy()
                            .to_lowercase()
                    };

                    if !loc.is_empty() && !GENERIC_ROOTS.contains(&loc.as_str()) {
                        let loc_prefix = format!("{}\\", loc);
                        if norm_exe == loc
                            || norm_exe.starts_with(&loc_prefix)
                            || exe_dir == loc
                            || exe_dir.starts_with(&loc_prefix)
                        {
                            is_fanta = true;
                            fanta_matched_title = (*fk).to_string();
                            fanta_thumbnail = fv
                                .get("thumbnail")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string();
                            fanta_version = fv
                                .get("version")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string();
                            break;
                        }
                    }

                    if !fk_clean.is_empty()
                        && (fk_clean == name_clean
                            || app_name.trim().eq_ignore_ascii_case(fk.trim()))
                    {
                        is_fanta = true;
                        fanta_matched_title = (*fk).to_string();
                        fanta_thumbnail = fv
                            .get("thumbnail")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        fanta_version = fv
                            .get("version")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        break;
                    }
                }

                if !is_fanta && !name_clean.is_empty() {
                    if let Some(g) = db_titles.get(&name_clean) {
                        is_fanta = true;
                        fanta_matched_title = g.title.clone();
                        fanta_thumbnail = g.thumbnail.clone();
                        fanta_version = g.version.clone();
                    }
                }
            }

            // Backfill thumbnail/version if matched above via tags/steam_url without thumbnail
            if is_fanta && fanta_thumbnail.is_empty() {
                for (fk, fv) in &clean_fanta {
                    if normalize_key(fk) == name_clean {
                        fanta_matched_title = (*fk).to_string();
                        fanta_thumbnail = fv
                            .get("thumbnail")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        if fanta_version.is_empty() {
                            fanta_version = fv
                                .get("version")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string();
                        }
                        break;
                    }
                }

                if fanta_thumbnail.is_empty() && !name_clean.is_empty() {
                    if let Some(g) = db_titles.get(&name_clean) {
                        if fanta_matched_title.is_empty() {
                            fanta_matched_title = g.title.clone();
                        }
                        fanta_thumbnail = g.thumbnail.clone();
                        if fanta_version.is_empty() {
                            fanta_version = g.version.clone();
                        }
                    }
                }
            }

            let start_dir = val
                .get_str_ci("StartDir")
                .unwrap_or("")
                .trim_matches('"')
                .to_string();
            let icon = val.get_str_ci("icon").unwrap_or("").to_string();
            let launch_options = val.get_str_ci("LaunchOptions").unwrap_or("").to_string();

            shortcuts_list.push(json!({
                "index": idx,
                "key": key,
                "name": app_name,
                "exe": clean_exe,
                "raw_exe": raw_exe,
                "start_dir": start_dir,
                "icon": icon,
                "launch_options": launch_options,
                "appid": appid,
                "shortcut_id": short_id_64.to_string(),
                "steam_url": steam_url,
                "exists_on_disk": exists_on_disk,
                "tags": tags,
                "is_fanta": is_fanta,
                "fanta_title": fanta_matched_title,
                "fanta_thumbnail": fanta_thumbnail,
                "fanta_version": fanta_version,
            }));
        }

        shortcuts_list
    }

    pub async fn add_non_steam_game(&self, req: AddShortcutRequest, artwork_dir: &Path) -> Value {
        let Some(path) = self.shortcuts_path(req.account_id.as_deref()).await else {
            return json!({ "success": false, "error": "Steam userdata directory not found" });
        };

        let mut res = self.write_shortcut_to_file(&path, &req);
        let ok = res.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
        if ok && req.auto_artwork {
            let clean_exe = normalize_win_path(Path::new(req.exe_path.trim_matches('"')))
                .to_string_lossy()
                .to_string();
            let artwork_paths =
                download_and_save_artwork(artwork_dir, &req.name, req.steam_appid.as_deref()).await;
            if !artwork_paths.is_empty() {
                let applied = self
                    .apply_artwork_to_steam_grid(
                        &clean_exe,
                        &req.name,
                        &artwork_paths,
                        req.account_id.as_deref(),
                    )
                    .await;
                if let Some(obj) = res.as_object_mut() {
                    obj.insert(
                        "artwork".into(),
                        json!({
                            "applied": applied,
                            "paths": artwork_paths,
                        }),
                    );
                }
            }
        }
        res
    }

    pub fn write_shortcut_to_file(&self, path: &Path, req: &AddShortcutRequest) -> Value {
        let clean_exe_path = normalize_win_path(Path::new(req.exe_path.trim_matches('"')));
        let clean_exe = clean_exe_path.to_string_lossy().to_string();
        let quoted_exe = format!("\"{}\"", clean_exe);

        let clean_start_dir = if !req.start_dir.trim_matches('"').trim().is_empty() {
            req.start_dir.trim_matches('"').trim().to_string()
        } else {
            clean_exe_path
                .parent()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default()
        };
        let quoted_start_dir = format!("\"{}\"", clean_start_dir);
        let clean_icon = if !req.icon_path.trim_matches('"').trim().is_empty() {
            req.icon_path.trim_matches('"').trim().to_string()
        } else {
            clean_exe.clone()
        };

        let appid = calculate_appid(&clean_exe, &req.name);
        let short_id_64 = calculate_shortcut_id(appid);

        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        let mut current_data = if path.is_file() {
            let bak = PathBuf::from(format!("{}.bak", path.to_string_lossy()));
            let _ = fs::copy(path, bak);
            fs::read(path)
                .map(|b| BinaryVDF::parse(&b))
                .unwrap_or_else(|_| VdfValue::empty_map())
        } else {
            VdfValue::empty_map()
        };

        let shortcuts_entries = match current_data.get_or_insert_empty_map("shortcuts") {
            Some(m) => m,
            None => return json!({ "success": false, "error": "Invalid shortcuts VDF structure" }),
        };

        let mut target_pos: Option<usize> = None;
        for (i, (_k, v)) in shortcuts_entries.iter().enumerate() {
            let v_name = v.get_str_ci("AppName").unwrap_or("").trim();
            let v_exe = v.get_str_ci("Exe").unwrap_or("").trim_matches('"');
            let v_appid = v.get_u32_ci("appid").unwrap_or(0);
            if v_name.eq_ignore_ascii_case(&req.name)
                || v_exe.eq_ignore_ascii_case(&clean_exe)
                || v_appid == appid
            {
                target_pos = Some(i);
                break;
            }
        }

        let target_key = match target_pos {
            Some(idx) => shortcuts_entries[idx].0.clone(),
            None => shortcuts_entries.len().to_string(),
        };

        let mut tags_list: Vec<String> = if req.tags.is_empty() {
            vec!["Online-Fix".into(), "Fanta".into()]
        } else {
            req.tags.clone()
        };
        if !tags_list
            .iter()
            .any(|t| t == "Online-Fix" || t == "OnlineFix")
        {
            tags_list.push("Online-Fix".into());
        }
        if !tags_list.iter().any(|t| t == "Fanta") {
            tags_list.push("Fanta".into());
        }

        let tags_entries: Vec<(String, VdfValue)> = tags_list
            .into_iter()
            .enumerate()
            .map(|(i, t)| (i.to_string(), VdfValue::Str(t)))
            .collect();

        let shortcut_obj = VdfValue::Map(vec![
            ("appid".into(), VdfValue::U32(appid)),
            ("AppName".into(), VdfValue::Str(req.name.clone())),
            ("Exe".into(), VdfValue::Str(quoted_exe)),
            ("StartDir".into(), VdfValue::Str(quoted_start_dir)),
            ("icon".into(), VdfValue::Str(clean_icon)),
            ("ShortcutPath".into(), VdfValue::Str(String::new())),
            ("LaunchOptions".into(), VdfValue::Str(req.launch_options.clone())),
            ("IsHidden".into(), VdfValue::U32(0)),
            ("AllowDesktopConfig".into(), VdfValue::U32(1)),
            ("AllowOverlay".into(), VdfValue::U32(1)),
            ("OpenVR".into(), VdfValue::U32(0)),
            ("Devkit".into(), VdfValue::U32(0)),
            ("DevkitGameID".into(), VdfValue::Str("FantaOFME".into())),
            ("DevkitOverrideAppID".into(), VdfValue::U32(0)),
            ("LastPlayTime".into(), VdfValue::U32(0)),
            ("tags".into(), VdfValue::Map(tags_entries)),
        ]);

        if let Some(pos) = target_pos {
            shortcuts_entries[pos].1 = shortcut_obj;
        } else {
            shortcuts_entries.push((target_key, shortcut_obj));
        }

        let serialized = BinaryVDF::serialize(&current_data);
        if let Err(e) = write_atomic_bytes(path, &serialized) {
            return json!({
                "success": false,
                "error": format!("Failed to save shortcuts.vdf: {}", e)
            });
        }

        println!(
            "[Steam] Successfully injected shortcut '{}' (AppID: {}) into {}",
            req.name,
            appid,
            path.display()
        );

        json!({
            "success": true,
            "name": req.name,
            "appid": appid,
            "shortcut_id": short_id_64.to_string(),
            "steam_url": format!("steam://rungameid/{}", short_id_64),
            "artwork": {},
            "message": format!("Added '{}' to Steam shortcuts.", req.name)
        })
    }

    pub async fn sync_game_artwork(
        &self,
        artwork_dir: &Path,
        name: &str,
        exe_path: &str,
        steam_appid: Option<&str>,
        account_id: Option<&str>,
    ) -> Value {
        let artwork_paths = download_and_save_artwork(artwork_dir, name, steam_appid).await;
        if artwork_paths.is_empty() {
            return json!({
                "success": false,
                "error": format!("Could not find or download artwork for '{}'", name)
            });
        }

        let applied = self
            .apply_artwork_to_steam_grid(exe_path, name, &artwork_paths, account_id)
            .await;

        json!({
            "success": true,
            "applied": applied,
            "artwork_paths": artwork_paths,
            "message": format!("Successfully updated artwork for '{}'.", name)
        })
    }

    pub async fn apply_artwork_to_steam_grid(
        &self,
        exe_path: &str,
        game_name: &str,
        artwork_paths: &HashMap<String, String>,
        account_id: Option<&str>,
    ) -> bool {
        let Some(ref steam_root) = self.steam_path else {
            return false;
        };
        let acc = match account_id.map(str::trim).filter(|s| !s.is_empty()) {
            Some(explicit) => explicit.to_string(),
            None => self.get_active_account_id(None).await,
        };
        if acc.is_empty() {
            return false;
        }
        let grid_dir = steam_root
            .join("userdata")
            .join(acc)
            .join("config")
            .join("grid");
        Self::copy_artwork_to_grid_dir(&grid_dir, exe_path, game_name, artwork_paths)
    }

    pub fn copy_artwork_to_grid_dir(
        grid_dir: &Path,
        exe_path: &str,
        game_name: &str,
        artwork_paths: &HashMap<String, String>,
    ) -> bool {
        if fs::create_dir_all(grid_dir).is_err() {
            return false;
        }
        let clean_exe = normalize_win_path(Path::new(exe_path.trim_matches('"')))
            .to_string_lossy()
            .to_string();
        let appid32 = calculate_appid(&clean_exe, game_name);
        let shortcut_id64 = calculate_shortcut_id(appid32);

        const MAPPINGS: [(&str, &str); 4] = [
            ("Cover", "p.jpg"),
            ("Background", "_hero.jpg"),
            ("Logo", "_logo.png"),
            ("WideCover", ".jpg"),
        ];

        let mut copied = 0usize;
        for (asset_key, suffix) in MAPPINGS {
            if let Some(src_str) = artwork_paths.get(asset_key) {
                let src = Path::new(src_str);
                if src.is_file() {
                    let dest64 = grid_dir.join(format!("{}{}", shortcut_id64, suffix));
                    let dest32 = grid_dir.join(format!("{}{}", appid32, suffix));
                    let ok64 = fs::copy(src, dest64).is_ok();
                    let ok32 = fs::copy(src, dest32).is_ok();
                    if ok64 || ok32 {
                        copied += 1;
                    }
                }
            }
        }
        copied > 0
    }

    pub async fn delete_shortcut(&self, identifier: &str, account_id: Option<&str>) -> Value {
        let Some(path) = self.shortcuts_path(account_id).await else {
            return json!({ "success": false, "error": "shortcuts.vdf not found" });
        };
        self.delete_shortcut_from_file(&path, identifier)
    }

    pub fn delete_shortcut_from_file(&self, path: &Path, identifier: &str) -> Value {
        if !path.is_file() {
            return json!({ "success": false, "error": "shortcuts.vdf not found" });
        }

        let bak = PathBuf::from(format!("{}.bak", path.to_string_lossy()));
        let _ = fs::copy(path, bak);

        let Ok(raw_bytes) = fs::read(path) else {
            return json!({ "success": false, "error": "Failed to read shortcuts.vdf" });
        };
        let mut current_data = BinaryVDF::parse(&raw_bytes);
        let Some(old_entries) = current_data.get_ci("shortcuts").and_then(|v| v.as_map()).cloned() else {
            return json!({ "success": false, "error": format!("Shortcut '{}' not found", identifier) });
        };

        let ident = identifier.trim().to_lowercase();
        let mut new_entries: Vec<(String, VdfValue)> = Vec::new();
        let mut deleted_name: Option<String> = None;
        let mut deleted_appid = String::new();
        let mut cur_idx = 0usize;

        for (k, v) in old_entries {
            if !matches!(v, VdfValue::Map(_)) {
                continue;
            }
            let v_name = v.get_str_ci("AppName").unwrap_or("").trim().to_string();
            let v_appid = v
                .get_u32_ci("appid")
                .map(|n| n.to_string())
                .unwrap_or_default();
            let v_exe = v
                .get_str_ci("Exe")
                .unwrap_or("")
                .trim_matches('"')
                .to_string();
            let v_short64 = v_appid
                .parse::<u32>()
                .map(|n| calculate_shortcut_id(n).to_string())
                .unwrap_or_default();

            if deleted_name.is_none()
                && (ident == v_name.to_lowercase()
                    || (!v_appid.is_empty() && ident == v_appid)
                    || (!v_short64.is_empty() && ident == v_short64)
                    || ident == v_exe.to_lowercase()
                    || ident == k.to_lowercase())
            {
                deleted_name = Some(v_name);
                deleted_appid = v_appid;
                continue;
            }

            new_entries.push((cur_idx.to_string(), v));
            cur_idx += 1;
        }

        let Some(del_name) = deleted_name else {
            return json!({ "success": false, "error": format!("Shortcut '{}' not found", identifier) });
        };

        current_data.set_entry("shortcuts".into(), VdfValue::Map(new_entries.clone()));
        let serialized = BinaryVDF::serialize(&current_data);
        if let Err(e) = write_atomic_bytes(path, &serialized) {
            return json!({
                "success": false,
                "error": format!("Failed to delete shortcut: {}", e)
            });
        }

        json!({
            "success": true,
            "deleted_name": del_name,
            "deleted_appid": deleted_appid,
            "remaining_count": new_entries.len(),
            "message": format!("Removed '{}' from Steam.", del_name)
        })
    }

    pub fn restart_steam(&self) -> Value {
        let steam_exe = self
            .steam_path
            .as_ref()
            .map(|p| p.join("steam.exe"))
            .filter(|p| p.is_file())
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "steam.exe".to_string());

        if is_process_running("steam.exe") {
            println!("[Steam] Gracefully requesting Steam shutdown via -shutdown...");
            let mut shut_cmd = Command::new(&steam_exe);
            shut_cmd.arg("-shutdown");
            #[cfg(target_os = "windows")]
            shut_cmd.creation_flags(CREATE_NO_WINDOW);
            let _ = shut_cmd.output();

            let mut closed = false;
            for _ in 0..12 {
                std::thread::sleep(Duration::from_millis(500));
                if !is_process_running("steam.exe") {
                    closed = true;
                    break;
                }
            }

            if !closed {
                let mut kill_cmd = Command::new("taskkill");
                kill_cmd.args(["/IM", "steam.exe"]);
                #[cfg(target_os = "windows")]
                kill_cmd.creation_flags(CREATE_NO_WINDOW);
                let _ = kill_cmd.output();
                std::thread::sleep(Duration::from_secs(1));
            }
        }

        println!("[Steam] Launching Steam: {}", steam_exe);
        let mut launch_cmd = Command::new(&steam_exe);
        #[cfg(target_os = "windows")]
        launch_cmd.creation_flags(DETACHED_PROCESS);
        match launch_cmd.spawn() {
            Ok(_) => json!({
                "success": true,
                "message": "Steam was restarted successfully. Your updated library shortcuts are now active!"
            }),
            Err(e) => json!({
                "success": false,
                "error": format!("Failed to launch Steam: {}", e)
            }),
        }
    }
}

pub fn default_artwork_dir() -> PathBuf {
    let zuhu_art = get_home_dir()
        .join("Documents")
        .join("ZuhuProjects")
        .join("ZuhuOFME")
        .join("SteamArtwork");
    let _ = fs::create_dir_all(&zuhu_art);
    zuhu_art
}

pub fn sanitize_artwork_filename(name: &str) -> String {
    let mut out = String::with_capacity(name.len());
    let mut prev_dash = false;
    for ch in name.trim().chars() {
        let mapped = match ch {
            '\\' | '/' | '*' | '?' | ':' | '"' | '<' | '>' | '|' => '-',
            _ => ch,
        };
        if mapped == '-' {
            if !prev_dash {
                out.push('-');
                prev_dash = true;
            }
        } else {
            out.push(mapped);
            prev_dash = false;
        }
    }
    out.trim_matches(|c| c == '-' || c == ' ').to_string()
}

pub async fn download_and_save_artwork(
    artwork_dir: &Path,
    game_title: &str,
    steam_appid: Option<&str>,
) -> HashMap<String, String> {
    let _ = fs::create_dir_all(artwork_dir);
    let urls = resolve_artwork_urls(game_title, steam_appid).await;
    let safe_name = sanitize_artwork_filename(game_title);
    let mut saved: HashMap<String, String> = HashMap::new();

    let Ok(client) = reqwest::Client::builder()
        .timeout(Duration::from_secs(12))
        .build()
    else {
        return saved;
    };

    let specs = [
        ("Cover", format!("{}-Cover.jpg", safe_name)),
        ("Background", format!("{}-Background.jpg", safe_name)),
        ("Logo", format!("{}-Logo.png", safe_name)),
        ("WideCover", format!("{}-WideCover.jpg", safe_name)),
    ];

    for (asset_key, filename) in specs {
        let dest_path = artwork_dir.join(filename);
        if let Some(url) = urls.get(asset_key) {
            if download_image_bytes(&client, url, &dest_path).await {
                saved.insert(
                    asset_key.to_string(),
                    dest_path.to_string_lossy().to_string(),
                );
            } else if url.contains("_2x") {
                let fallback = url.replace("_2x", "");
                if download_image_bytes(&client, &fallback, &dest_path).await {
                    saved.insert(
                        asset_key.to_string(),
                        dest_path.to_string_lossy().to_string(),
                    );
                }
            }
        }
        if !saved.contains_key(asset_key) && dest_path.is_file() {
            saved.insert(
                asset_key.to_string(),
                dest_path.to_string_lossy().to_string(),
            );
        }
    }

    saved
}

async fn download_image_bytes(client: &reqwest::Client, url: &str, dest: &Path) -> bool {
    let Ok(resp) = client
        .get(url)
        .header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        .header("Referer", "https://store.steampowered.com/")
        .send()
        .await
    else {
        return false;
    };
    if !resp.status().is_success() {
        return false;
    }
    let Ok(bytes) = resp.bytes().await else {
        return false;
    };
    if bytes.len() <= 500 {
        return false;
    }
    if let Some(parent) = dest.parent() {
        let _ = fs::create_dir_all(parent);
    }
    fs::write(dest, &bytes).is_ok()
}

async fn resolve_artwork_urls(
    game_title: &str,
    appid: Option<&str>,
) -> HashMap<String, String> {
    let mut assets = HashMap::new();
    let mut resolved_appid = appid
        .map(str::trim)
        .filter(|s| !s.is_empty() && s.chars().all(|c| c.is_ascii_digit()))
        .map(str::to_string);

    if let Some(ref aid) = resolved_appid {
        let base = format!("{}/{}", STEAM_CDN_BASE, aid);
        assets.insert("Cover".into(), format!("{}/library_600x900_2x.jpg", base));
        assets.insert("Background".into(), format!("{}/library_hero.jpg", base));
        assets.insert("Logo".into(), format!("{}/logo.png", base));
        assets.insert("WideCover".into(), format!("{}/header.jpg", base));
        return assets;
    }

    if let Some(sgdb_data) = fetch_steamgriddb_metadata(game_title).await {
        if let Some(steam_info) = sgdb_data
            .get("platforms")
            .and_then(|p| p.get("steam"))
            .and_then(|v| v.as_object())
        {
            if let Some(id_val) = steam_info.get("id") {
                let id_str = if let Some(s) = id_val.as_str() {
                    s.to_string()
                } else {
                    id_val.to_string()
                };
                if !id_str.is_empty() && resolved_appid.is_none() {
                    resolved_appid = Some(id_str);
                }
            }

            if let Some(ref aid) = resolved_appid {
                let base_cdn = format!("{}/{}/", STEAM_CDN_BASE, aid);
                if let Some(meta) = steam_info.get("metadata").and_then(|v| v.as_object()) {
                    if let Some(rel) = first_sgdb_rel(meta.get("library_capsule_full"), &["image2x", "image"]) {
                        assets.insert("Cover".into(), format!("{}{}", base_cdn, rel));
                    }
                    if let Some(rel) = first_sgdb_rel(meta.get("library_hero_full"), &["image2x", "image"]) {
                        assets.insert("Background".into(), format!("{}{}", base_cdn, rel));
                    }
                    if let Some(rel) = first_sgdb_rel(meta.get("library_logo_full"), &["image2x", "image"]) {
                        assets.insert("Logo".into(), format!("{}{}", base_cdn, rel));
                    }
                    if let Some(rel) = meta
                        .get("header_image_full")
                        .and_then(|v| v.as_object())
                        .and_then(|m| m.values().next())
                        .and_then(|v| v.as_str())
                    {
                        assets.insert("WideCover".into(), format!("{}{}", base_cdn, rel));
                    }
                }
            }
        }
    }

    if let Some(ref aid) = resolved_appid {
        let base = format!("{}/{}", STEAM_CDN_BASE, aid);
        assets
            .entry("Cover".into())
            .or_insert_with(|| format!("{}/library_600x900_2x.jpg", base));
        assets
            .entry("Background".into())
            .or_insert_with(|| format!("{}/library_hero.jpg", base));
        assets
            .entry("Logo".into())
            .or_insert_with(|| format!("{}/logo.png", base));
        assets
            .entry("WideCover".into())
            .or_insert_with(|| format!("{}/header.jpg", base));
    }

    assets
}

fn first_sgdb_rel<'a>(slot: Option<&'a Value>, subkeys: &[&str]) -> Option<&'a str> {
    let obj = slot?.as_object()?;
    for &sk in subkeys {
        if let Some(sub) = obj.get(sk).and_then(|v| v.as_object()) {
            if let Some(s) = sub.values().next().and_then(|v| v.as_str()) {
                if !s.is_empty() {
                    return Some(s);
                }
            }
        }
    }
    None
}

async fn fetch_steamgriddb_metadata(title: &str) -> Option<Value> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
        .ok()?;

    let mut search_res = sgdb_get_json(
        &client,
        &format!(
            "https://www.steamgriddb.com/api/public/search/autocomplete?term={}",
            percent_encode(title)
        ),
        "https://www.steamgriddb.com",
    )
    .await;

    let has_data = |v: &Option<Value>| {
        v.as_ref()
            .and_then(|j| j.get("data"))
            .and_then(|d| d.as_array())
            .is_some_and(|a| !a.is_empty())
    };

    if !has_data(&search_res) {
        let simple = strip_version_or_subtitle(title);
        if !simple.is_empty() && simple != title {
            search_res = sgdb_get_json(
                &client,
                &format!(
                    "https://www.steamgriddb.com/api/public/search/autocomplete?term={}",
                    percent_encode(&simple)
                ),
                "https://www.steamgriddb.com",
            )
            .await;
        }
    }

    let candidates = search_res?.get("data")?.as_array()?.clone();
    if candidates.is_empty() {
        return None;
    }

    let clean_target = normalize_key(title);
    let mut target_game: Option<&Value> = candidates.iter().find(|c| {
        c.get("name")
            .and_then(|v| v.as_str())
            .is_some_and(|nm| normalize_key(nm) == clean_target)
    });

    if target_game.is_none() {
        target_game = candidates.iter().find(|c| {
            let nm_match = c
                .get("name")
                .and_then(|v| v.as_str())
                .is_some_and(|nm| normalize_key(nm).starts_with(&clean_target));
            let has_steam = c
                .get("types")
                .and_then(|t| t.as_array())
                .is_some_and(|arr| arr.iter().any(|x| x.as_str() == Some("steam")));
            nm_match && has_steam
        });
    }

    let game_id = target_game?.get("id")?.as_u64()?;
    let game_url = format!("https://www.steamgriddb.com/api/public/game/{}", game_id);
    let game_res = sgdb_get_json(
        &client,
        &game_url,
        &format!("https://www.steamgriddb.com/game/{}", game_id),
    )
    .await?;

    if game_res.get("success").and_then(|v| v.as_bool()) == Some(true) {
        return game_res.get("data").cloned();
    }
    None
}

async fn sgdb_get_json(client: &reqwest::Client, url: &str, referer: &str) -> Option<Value> {
    let resp = client
        .get(url)
        .header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        .header("Referer", referer)
        .header("Accept", "application/json, text/plain, */*")
        .send()
        .await
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    resp.json::<Value>().await.ok()
}

fn percent_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len() * 3);
    for &b in input.as_bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~') {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

fn strip_version_or_subtitle(title: &str) -> String {
    let trimmed = title.trim();
    if let Some(idx) = trimmed.find(" - ") {
        return trimmed[..idx].trim().to_string();
    }
    trimmed.to_string()
}

fn write_atomic_bytes(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    let tmp = PathBuf::from(format!("{}.tmp", path.to_string_lossy()));
    fs::write(&tmp, bytes)?;
    if path.is_file() {
        let _ = fs::remove_file(path);
    }
    fs::rename(tmp, path)
}

fn normalize_win_path(p: &Path) -> PathBuf {
    let raw = p.to_string_lossy().replace('/', "\\");
    let trimmed = if raw.len() > 3 {
        raw.trim_end_matches('\\').to_string()
    } else {
        raw
    };
    PathBuf::from(trimmed)
}

fn count_shortcuts_in_file(path: &Path) -> usize {
    if !path.is_file() {
        return 0;
    }
    let Ok(bytes) = fs::read(path) else {
        return 0;
    };
    let vdf = BinaryVDF::parse(&bytes);
    vdf.get_ci("shortcuts")
        .and_then(|v| v.as_map())
        .map(|m| m.len())
        .unwrap_or(0)
}

fn extract_cdata_tag(xml: &str, tag: &str) -> Option<String> {
    let open = format!("<{}><![CDATA[", tag);
    let close = format!("]]></{}>", tag);
    let start = xml.find(&open)? + open.len();
    let end = xml[start..].find(&close)? + start;
    let val = xml[start..end].trim();
    if val.is_empty() {
        None
    } else {
        Some(val.to_string())
    }
}

pub fn extract_vdf_key_values(text: &str, target_key: &str) -> Vec<String> {
    let tokens = tokenize_vdf_quotes(text);
    let mut results = Vec::new();
    let mut i = 0usize;
    while i + 1 < tokens.len() {
        if tokens[i].eq_ignore_ascii_case(target_key) {
            results.push(tokens[i + 1].clone());
            i += 2;
        } else {
            i += 1;
        }
    }
    results
}

fn tokenize_vdf_quotes(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '"' {
            let mut cur = String::new();
            while let Some(ch) = chars.next() {
                if ch == '\\' {
                    if let Some(next_ch) = chars.next() {
                        cur.push(ch);
                        cur.push(next_ch);
                    }
                } else if ch == '"' {
                    break;
                } else {
                    cur.push(ch);
                }
            }
            tokens.push(cur);
        }
    }
    tokens
}

pub fn extract_loginuser_blocks(content: &str) -> Vec<(String, String)> {
    let mut blocks = Vec::new();
    let bytes = content.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] == b'"' {
            let start = i + 1;
            if let Some(rel_end) = content[start..].find('"') {
                let key = &content[start..start + rel_end];
                let after_quote = start + rel_end + 1;
                if (15..=20).contains(&key.len()) && key.bytes().all(|b| b.is_ascii_digit()) {
                    let mut j = after_quote;
                    while j < bytes.len() && bytes[j].is_ascii_whitespace() {
                        j += 1;
                    }
                    if j < bytes.len() && bytes[j] == b'{' {
                        let body_start = j + 1;
                        let mut depth = 1usize;
                        let mut k = body_start;
                        while k < bytes.len() && depth > 0 {
                            if bytes[k] == b'{' {
                                depth += 1;
                            } else if bytes[k] == b'}' {
                                depth -= 1;
                            }
                            k += 1;
                        }
                        if depth == 0 {
                            blocks.push((
                                key.to_string(),
                                content[body_start..k - 1].to_string(),
                            ));
                            i = k;
                            continue;
                        }
                    }
                }
                i = after_quote;
                continue;
            }
        }
        i += 1;
    }
    blocks
}

#[cfg(target_os = "windows")]
fn read_steam_path_from_registry() -> Option<PathBuf> {
    const HKEY_CURRENT_USER: *mut core::ffi::c_void = 0x8000_0001u32 as usize as *mut core::ffi::c_void;
    const HKEY_LOCAL_MACHINE: *mut core::ffi::c_void = 0x8000_0002u32 as usize as *mut core::ffi::c_void;
    const KEY_READ: u32 = 0x20019;
    const REG_SZ: u32 = 1;
    const REG_EXPAND_SZ: u32 = 2;

    #[link(name = "advapi32")]
    extern "system" {
        fn RegOpenKeyExW(
            h_key: *mut core::ffi::c_void,
            lp_sub_key: *const u16,
            ul_options: u32,
            sam_desired: u32,
            phk_result: *mut *mut core::ffi::c_void,
        ) -> i32;
        fn RegQueryValueExW(
            h_key: *mut core::ffi::c_void,
            lp_value_name: *const u16,
            lp_reserved: *mut u32,
            lp_type: *mut u32,
            lp_data: *mut u8,
            lpcb_data: *mut u32,
        ) -> i32;
        fn RegCloseKey(h_key: *mut core::ffi::c_void) -> i32;
    }

    fn to_wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    let targets = [
        (HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ];

    for (hive, subkey, val_name) in targets {
        let mut hkey: *mut core::ffi::c_void = std::ptr::null_mut();
        let wide_sub = to_wide(subkey);
        let rc = unsafe { RegOpenKeyExW(hive, wide_sub.as_ptr(), 0, KEY_READ, &mut hkey) };
        if rc != 0 || hkey.is_null() {
            continue;
        }
        let wide_val = to_wide(val_name);
        let mut reg_type: u32 = 0;
        let mut buf = vec![0u16; 1024];
        let mut cb_data = (buf.len() * 2) as u32;
        let qrc = unsafe {
            RegQueryValueExW(
                hkey,
                wide_val.as_ptr(),
                std::ptr::null_mut(),
                &mut reg_type,
                buf.as_mut_ptr() as *mut u8,
                &mut cb_data,
            )
        };
        unsafe { RegCloseKey(hkey) };
        if qrc == 0 && (reg_type == REG_SZ || reg_type == REG_EXPAND_SZ) {
            let word_len = (cb_data as usize / 2).min(buf.len());
            let end = buf[..word_len].iter().position(|&c| c == 0).unwrap_or(word_len);
            let val_str = String::from_utf16_lossy(&buf[..end]).trim().to_string();
            if !val_str.is_empty() {
                return Some(PathBuf::from(val_str));
            }
        }
    }
    None
}

#[cfg(not(target_os = "windows"))]
fn read_steam_path_from_registry() -> Option<PathBuf> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_test_dir(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!(
            "fanta_steam_test_{}_{}_{}",
            label,
            std::process::id(),
            nanos
        ));
        let _ = fs::create_dir_all(&dir);
        dir
    }

    #[test]
    fn test_binary_vdf_roundtrip() {
        let original = VdfValue::Map(vec![(
            "shortcuts".into(),
            VdfValue::Map(vec![(
                "0".into(),
                VdfValue::Map(vec![
                    ("appid".into(), VdfValue::U32(0x8123_4567)),
                    ("AppName".into(), VdfValue::Str("Megabonk".into())),
                    ("Exe".into(), VdfValue::Str("\"D:\\GAMES2\\Megabonk\\Megabonk.exe\"".into())),
                    ("AllowOverlay".into(), VdfValue::U32(1)),
                    ("LastPlayTime".into(), VdfValue::U64(1_700_000_000_000)),
                    (
                        "tags".into(),
                        VdfValue::Map(vec![
                            ("0".into(), VdfValue::Str("Online-Fix".into())),
                            ("1".into(), VdfValue::Str("Fanta".into())),
                        ]),
                    ),
                ]),
            )]),
        )]);

        let encoded = BinaryVDF::serialize(&original);
        let decoded = BinaryVDF::parse(&encoded);
        assert_eq!(decoded, original);
    }

    #[test]
    fn test_appid_and_shortcut_id_crc32() {
        // Known IEEE CRC32 of "123456789" == 0xCBF43926
        assert_eq!(crc32_ieee(b"123456789"), 0xCBF4_3926);

        let appid = calculate_appid(r"D:\GAMES2\Megabonk\Megabonk.exe", "Megabonk");
        assert_ne!(appid & 0x8000_0000, 0);
        let sid64 = calculate_shortcut_id(appid);
        assert_eq!(sid64 & 0xFFFF_FFFF, 0x0200_0000);
        assert_eq!((sid64 >> 32) as u32, appid);
    }

    #[test]
    fn test_parse_libraryfolders_and_loginusers() {
        let dir = temp_test_dir("vdf_parse");
        let lib_extra = dir.join("ExtraSteamLib");
        fs::create_dir_all(dir.join("steamapps")).unwrap();
        fs::create_dir_all(&lib_extra).unwrap();

        let lib_vdf = format!(
            "\"libraryfolders\"\n{{\n  \"0\"\n  {{\n    \"path\" \"{}\"\n  }}\n  \"1\"\n  {{\n    \"path\" \"{}\"\n  }}\n}}\n",
            dir.to_string_lossy().replace('\\', "\\\\"),
            lib_extra.to_string_lossy().replace('\\', "\\\\"),
        );
        fs::write(dir.join("steamapps").join("libraryfolders.vdf"), lib_vdf).unwrap();

        let mgr = SteamManager::new(Some(&dir.to_string_lossy()));
        assert_eq!(mgr.libraries.len(), 2);

        let loginusers = r#"
        "users"
        {
            "76561198000000001"
            {
                "AccountName" "user_one"
                "PersonaName" "Player One"
                "MostRecent" "1"
            }
        }
        "#;
        let blocks = extract_loginuser_blocks(loginusers);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].0, "76561198000000001");
        assert_eq!(
            extract_vdf_key_values(&blocks[0].1, "PersonaName"),
            vec!["Player One"]
        );

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_add_get_update_delete_shortcuts() {
        let dir = temp_test_dir("shortcuts_crud");
        let sc_path = dir.join("userdata").join("12345").join("config").join("shortcuts.vdf");
        let mgr = SteamManager {
            steam_path: Some(dir.clone()),
            libraries: vec![dir.to_string_lossy().to_string()],
        };

        let exe_path = dir.join("CoolGame").join("CoolGame.exe");
        fs::create_dir_all(exe_path.parent().unwrap()).unwrap();
        fs::write(&exe_path, b"MZ").unwrap();

        let req = AddShortcutRequest {
            name: "Cool Game".into(),
            exe_path: exe_path.to_string_lossy().to_string(),
            auto_artwork: false,
            ..Default::default()
        };
        let add_res = mgr.write_shortcut_to_file(&sc_path, &req);
        assert_eq!(add_res["success"], true);

        let mut fanta_games = Map::new();
        fanta_games.insert(
            "COOL GAME".into(),
            json!({ "downloaded": true, "location": dir.join("CoolGame").to_string_lossy(), "version": "1.2" }),
        );
        let listed = mgr.get_shortcuts_from_file(&sc_path, &fanta_games, &[]);
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0]["name"], "Cool Game");
        assert_eq!(listed[0]["is_fanta"], true);
        assert_eq!(listed[0]["fanta_version"], "1.2");

        // Deleting by name removes it cleanly
        let del_res = mgr.delete_shortcut_from_file(&sc_path, "Cool Game");
        assert_eq!(del_res["success"], true);
        assert_eq!(del_res["remaining_count"], 0);
        let listed_after = mgr.get_shortcuts_from_file(&sc_path, &fanta_games, &[]);
        assert!(listed_after.is_empty());

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_apply_artwork_to_steam_grid() {
        let dir = temp_test_dir("grid_art");
        let art_src_dir = dir.join("src_art");
        let grid_dir = dir.join("grid");
        fs::create_dir_all(&art_src_dir).unwrap();

        let cover = art_src_dir.join("Game-Cover.jpg");
        let logo = art_src_dir.join("Game-Logo.png");
        fs::write(&cover, vec![1u8; 600]).unwrap();
        fs::write(&logo, vec![2u8; 600]).unwrap();

        let mut map = HashMap::new();
        map.insert("Cover".into(), cover.to_string_lossy().to_string());
        map.insert("Logo".into(), logo.to_string_lossy().to_string());

        let exe = r"D:\GAMES2\Test\Test.exe";
        let ok = SteamManager::copy_artwork_to_grid_dir(&grid_dir, exe, "Test", &map);
        assert!(ok);

        let appid32 = calculate_appid(exe, "Test");
        let sid64 = calculate_shortcut_id(appid32);
        assert!(grid_dir.join(format!("{}p.jpg", sid64)).is_file());
        assert!(grid_dir.join(format!("{}p.jpg", appid32)).is_file());
        assert!(grid_dir.join(format!("{}_logo.png", sid64)).is_file());
        assert!(grid_dir.join(format!("{}_logo.png", appid32)).is_file());

        let _ = fs::remove_dir_all(&dir);
    }
}
