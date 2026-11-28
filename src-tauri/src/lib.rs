mod backend;
mod config;
mod database;
mod extractor;
mod updater;

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::atomic::AtomicBool;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

#[derive(Clone, Serialize)]
pub struct LogEntry {
    pub text: String,
    pub level: String,
    pub time: String,
}

pub struct AppState {
    pub logs: Mutex<Vec<LogEntry>>,
    pub beta_updates: AtomicBool,
    pub backend_child: Mutex<Option<Child>>,
    pub pending_update: Mutex<Option<tauri_plugin_updater::Update>>,
    pub downloaded_update: Mutex<Option<(tauri_plugin_updater::Update, Vec<u8>)>>,
    pub config: Mutex<config::ConfigManager>,
    pub database: Mutex<database::DatabaseManager>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            logs: Mutex::new(Vec::new()),
            beta_updates: AtomicBool::new(updater::read_beta_updates_setting()),
            backend_child: Mutex::new(None),
            pending_update: Mutex::new(None),
            downloaded_update: Mutex::new(None),
            config: Mutex::new(config::ConfigManager::default()),
            database: Mutex::new(database::DatabaseManager::default()),
        }
    }
}

#[derive(Deserialize)]
struct FileFilterInput {
    name: String,
    extensions: Vec<String>,
}

#[derive(Deserialize, Default)]
#[serde(rename_all = "camelCase")]
struct SelectFileOptions {
    default_path: Option<String>,
    filters: Option<Vec<FileFilterInput>>,
}

fn resolve_dialog_default_path(raw_path: Option<String>) -> Option<PathBuf> {
    let raw = raw_path?;
    let clean = raw
        .trim()
        .trim_matches(|c| c == '"' || c == '\'')
        .replace('/', "\\");
    if clean.is_empty() {
        return None;
    }

    let mut cur = PathBuf::from(clean);
    loop {
        if cur.exists() {
            return Some(cur);
        }
        match cur.parent() {
            Some(parent) if parent != cur => cur = parent.to_path_buf(),
            _ => return None,
        }
    }
}

fn open_in_file_manager(raw_path: &str, select_file: bool) -> bool {
    let trimmed = raw_path.trim().replace('/', "\\");
    if trimmed.is_empty() {
        return false;
    }

    let target = Path::new(&trimmed);
    #[cfg(target_os = "windows")]
    {
        if target.exists() {
            if target.is_dir() && !select_file {
                return Command::new("explorer.exe").arg(&trimmed).spawn().is_ok();
            }
            if target.is_file() || select_file {
                return Command::new("explorer.exe")
                    .arg(format!("/select,{}", trimmed))
                    .spawn()
                    .is_ok();
            }
            return Command::new("explorer.exe").arg(&trimmed).spawn().is_ok();
        } else if let Some(parent) = target.parent() {
            if parent.exists() {
                return Command::new("explorer.exe").arg(parent).spawn().is_ok();
            }
        }
        false
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = (target, select_file);
        false
    }
}

#[tauri::command]
fn get_app_version(app: AppHandle) -> String {
    app.package_info().version.to_string()
}

#[tauri::command]
fn is_source_mode() -> bool {
    cfg!(debug_assertions)
}

#[tauri::command]
fn is_portable() -> bool {
    std::env::var_os("PORTABLE_EXECUTABLE_DIR").is_some()
        || std::env::var_os("PORTABLE_EXECUTABLE_FILE").is_some()
}

#[tauri::command]
fn get_initial_logs(state: State<'_, AppState>) -> Vec<LogEntry> {
    state
        .logs
        .lock()
        .map(|guard| guard.clone())
        .unwrap_or_default()
}

#[tauri::command]
async fn select_directory(app: AppHandle, default_path: Option<String>) -> Result<Option<String>, String> {
    let mut dialog_builder = app.dialog().file();
    if let Some(mut start) = resolve_dialog_default_path(default_path) {
        if start.is_file() {
            if let Some(parent) = start.parent() {
                start = parent.to_path_buf();
            }
        }
        dialog_builder = dialog_builder.set_directory(start);
    }

    let picked = tauri::async_runtime::spawn_blocking(move || dialog_builder.blocking_pick_folder())
        .await
        .map_err(|e| e.to_string())?;

    Ok(picked
        .and_then(|fp| fp.into_path().ok())
        .map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
async fn select_file(
    app: AppHandle,
    options: Option<SelectFileOptions>,
) -> Result<Option<String>, String> {
    let opts = options.unwrap_or_default();
    let mut dialog_builder = app.dialog().file();

    if let Some(start) = resolve_dialog_default_path(opts.default_path) {
        if start.is_file() {
            if let Some(parent) = start.parent() {
                dialog_builder = dialog_builder.set_directory(parent);
            }
            if let Some(file_name) = start.file_name().and_then(|n| n.to_str()) {
                dialog_builder = dialog_builder.set_file_name(file_name);
            }
        } else {
            dialog_builder = dialog_builder.set_directory(start);
        }
    }

    if let Some(filters) = opts.filters {
        for filter in filters {
            let ext_refs: Vec<&str> = filter.extensions.iter().map(String::as_str).collect();
            dialog_builder = dialog_builder.add_filter(&filter.name, &ext_refs);
        }
    }

    let picked = tauri::async_runtime::spawn_blocking(move || dialog_builder.blocking_pick_file())
        .await
        .map_err(|e| e.to_string())?;

    Ok(picked
        .and_then(|fp| fp.into_path().ok())
        .map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
fn open_path(target_path: String) -> bool {
    open_in_file_manager(&target_path, false)
}

#[tauri::command]
fn show_item_in_folder(item_path: String) -> bool {
    open_in_file_manager(&item_path, true)
}

#[tauri::command]
fn open_external(app: AppHandle, url: String) -> bool {
    let clean = url.trim().to_string();
    let lower = clean.to_lowercase();
    if !(lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("steam://")) {
        return false;
    }

    if app.opener().open_url(&clean, None::<&str>).is_ok() {
        return true;
    }

    #[cfg(target_os = "windows")]
    {
        return Command::new("cmd")
            .args(["/C", "start", "", &clean])
            .spawn()
            .is_ok();
    }

    #[cfg(not(target_os = "windows"))]
    false
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct GamesQueryParams {
    q: String,
    host: String,
    status: String,
    sort: String,
    order: String,
}

#[tauri::command]
fn rust_get_status(app: AppHandle, state: State<'_, AppState>) -> Value {
    let mut cfg = state.config.lock().unwrap();
    cfg.bind_app(&app);
    cfg.reload_if_changed();
    let total_games = {
        let mut db = state.database.lock().unwrap();
        if db.games.is_empty() {
            db.load_local_or_cached(&cfg, false);
        }
        db.games.len()
    };
    let ext = extractor::Extractor::from_config(&cfg);
    let winrar_installed = ext.is_winrar_available();
    let sevenzip_installed = ext.is_sevenzip_available();
    let steam_path = cfg.get_str("steam_path");
    let steam_detected = !steam_path.is_empty() && Path::new(&steam_path).exists();
    let local_db = cfg
        .get_active_db_path()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();

    json!({
        "status": "online",
        "version": app.package_info().version.to_string(),
        "winrar_installed": winrar_installed,
        "sevenzip_installed": sevenzip_installed,
        "steam_detected": steam_detected,
        "total_games": total_games,
        "is_source_mode": cfg!(debug_assertions),
        "use_local_db": cfg.get_bool("use_local_db"),
        "local_db_path": local_db,
        "rust_core": true
    })
}

#[tauri::command]
fn rust_get_settings(app: AppHandle, state: State<'_, AppState>) -> Value {
    let mut cfg = state.config.lock().unwrap();
    cfg.bind_app(&app);
    cfg.reload_if_changed();
    json!({ "settings": cfg.settings })
}

#[tauri::command]
fn rust_save_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    settings: Map<String, Value>,
) -> Value {
    let (old_local, old_path, new_local, new_path) = {
        let mut cfg = state.config.lock().unwrap();
        cfg.bind_app(&app);
        let ol = cfg.get_bool("use_local_db");
        let op = cfg.get_str("local_db_path");
        cfg.update_settings(settings);
        let nl = cfg.get_bool("use_local_db");
        let np = cfg.get_str("local_db_path");
        (ol, op, nl, np)
    };

    if old_local != new_local || old_path != new_path {
        let cfg = state.config.lock().unwrap();
        let mut db = state.database.lock().unwrap();
        db.load_local_or_cached(&cfg, true);
    }

    let cfg = state.config.lock().unwrap();
    json!({ "success": true, "settings": cfg.settings })
}

#[tauri::command]
fn rust_get_games(
    app: AppHandle,
    state: State<'_, AppState>,
    params: Option<GamesQueryParams>,
) -> Value {
    let q = params.unwrap_or_default();
    let mut cfg = state.config.lock().unwrap();
    cfg.bind_app(&app);
    cfg.reload_if_changed();

    let mut db = state.database.lock().unwrap();
    if db.games.is_empty() || cfg.get_bool("use_local_db") {
        db.load_local_or_cached(&cfg, false);
    } else {
        db.update_installed_states(&cfg);
    }

    let status_filter = if q.status.is_empty() { "all" } else { &q.status };
    let sort_by = if q.sort.is_empty() { "default" } else { &q.sort };
    let sort_order = if q.order.is_empty() { "asc" } else { &q.order };
    let games = db.search_and_filter(&q.q, &q.host, status_filter, sort_by, sort_order);
    let total = games.len();

    json!({
        "games": games,
        "total": total,
        "hosts": db.hosts
    })
}

#[tauri::command]
async fn rust_refresh_games(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let (use_local, db_url, cache_json_path) = {
        let mut cfg = state.config.lock().unwrap();
        cfg.bind_app(&app);
        cfg.reload_if_changed();
        (
            cfg.get_bool("use_local_db"),
            cfg.get_str("db_url"),
            cfg.cache_folder.join("Data.json"),
        )
    };

    if !use_local && !db_url.is_empty() && db_url != "local" {
        if let Ok(raw) = database::DatabaseManager::fetch_remote_raw(&db_url, &cache_json_path).await {
            let mut cfg = state.config.lock().unwrap();
            cfg.reload_if_changed();
            let mut db = state.database.lock().unwrap();
            db.apply_raw_catalog(&raw, &cfg, cache_json_path);
            return Ok(json!({
                "success": true,
                "total": db.games.len(),
                "hosts": db.hosts
            }));
        }
    }

    let mut cfg = state.config.lock().unwrap();
    cfg.reload_if_changed();
    let mut db = state.database.lock().unwrap();
    db.load_local_or_cached(&cfg, true);
    Ok(json!({
        "success": true,
        "total": db.games.len(),
        "hosts": db.hosts
    }))
}

#[tauri::command]
fn rust_mark_game_status(
    state: State<'_, AppState>,
    payload: Map<String, Value>,
) -> Result<Value, String> {
    let game_id = payload.get("id").and_then(|v| v.as_str()).unwrap_or("");
    let title = payload
        .get("title")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or(game_id);
    if game_id.is_empty() {
        return Err("Missing game id".to_string());
    }

    let mut cfg = state.config.lock().unwrap();
    cfg.reload_if_changed();
    let key = title.to_uppercase();
    let mut game_state = cfg
        .installed_games
        .get(&key)
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();

    if let Some(dl) = payload.get("downloaded") {
        game_state.insert("downloaded".into(), dl.clone());
    }
    if let Some(ver) = payload.get("installed_version") {
        game_state.insert("version".into(), ver.clone());
    }
    if let Some(loc) = payload.get("location") {
        game_state.insert("location".into(), loc.clone());
    }

    let val = Value::Object(game_state);
    cfg.installed_games.insert(key, val.clone());
    cfg.save_installed_games();

    let mut db = state.database.lock().unwrap();
    db.update_installed_states(&cfg);
    Ok(json!({ "success": true, "game_state": val }))
}

fn find_installed_game_key(
    installed_games: &Map<String, Value>,
    title: &str,
    game_id: &str,
) -> Option<String> {
    let norm_title = database::normalize_key(title);
    let norm_id = database::normalize_key(game_id);

    installed_games
        .iter()
        .filter_map(|(k, v)| {
            let obj = v.as_object()?;
            if database::DatabaseManager::is_catalog_only_entry(obj) {
                return None;
            }
            let kn = database::normalize_key(k);
            let matches = (!title.is_empty() && k.eq_ignore_ascii_case(title))
                || (!norm_title.is_empty() && kn == norm_title)
                || (!norm_id.is_empty() && kn == norm_id);
            if matches {
                Some((
                    database::DatabaseManager::installed_entry_score(k, obj),
                    k.clone(),
                ))
            } else {
                None
            }
        })
        .max_by_key(|(score, _)| *score)
        .map(|(_, k)| k)
}

#[tauri::command]
fn rust_remove_game(
    state: State<'_, AppState>,
    payload: Map<String, Value>,
) -> Result<Value, String> {
    let game_id = payload.get("id").and_then(|v| v.as_str()).unwrap_or("");
    let title = payload.get("title").and_then(|v| v.as_str()).unwrap_or("");
    let delete_folder = payload
        .get("delete_folder")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    if game_id.is_empty() && title.is_empty() {
        return Err("Missing game id or title".to_string());
    }

    let mut cfg = state.config.lock().unwrap();
    cfg.reload_if_changed();

    let found_key = find_installed_game_key(&cfg.installed_games, title, game_id);

    let mut game_location = String::new();
    if let Some(ref fk) = found_key {
        if let Some(loc) = cfg
            .installed_games
            .get(fk)
            .and_then(|v| v.get("location"))
            .and_then(|v| v.as_str())
        {
            game_location = loc.to_string();
        }
        cfg.installed_games.remove(fk);
        cfg.save_installed_games();
    }

    if delete_folder && !game_location.is_empty() {
        let protected: Vec<String> = vec![
            "".into(),
            r"c:\".into(),
            r"d:\".into(),
            r"e:\".into(),
            cfg.get_str("default_download_path").trim_end_matches('\\').to_lowercase(),
            cfg.get_str("extract_path").trim_end_matches('\\').to_lowercase(),
            cfg.get_str("download_path").trim_end_matches('\\').to_lowercase(),
            r"d:\games2".into(),
            r"d:\games".into(),
            r"c:\games".into(),
        ];

        let norm_loc = game_location.trim().replace('/', "\\").trim_end_matches('\\').to_lowercase();
        let target_to_delete: Option<PathBuf> = if protected.contains(&norm_loc) {
            let sub = Path::new(&game_location).join(title);
            if sub.is_dir() { Some(sub) } else { None }
        } else {
            Some(PathBuf::from(&game_location))
        };

        if let Some(target) = target_to_delete {
            let norm_target = target.to_string_lossy().trim_end_matches('\\').to_lowercase();
            if !protected.contains(&norm_target) && target.is_dir() {
                let _ = std::fs::remove_dir_all(&target);
            }
        }
    }

    let mut db = state.database.lock().unwrap();
    db.update_installed_states(&cfg);
    Ok(json!({ "success": true, "removed": found_key.unwrap_or_else(|| title.to_string()) }))
}

#[tauri::command]
fn rust_remove_steam_link(
    state: State<'_, AppState>,
    payload: Map<String, Value>,
) -> Result<Value, String> {
    let game_id = payload.get("id").and_then(|v| v.as_str()).unwrap_or("");
    let title = payload.get("title").and_then(|v| v.as_str()).unwrap_or("");
    if game_id.is_empty() && title.is_empty() {
        return Err("Missing game id or title".to_string());
    }

    let mut cfg = state.config.lock().unwrap();
    cfg.reload_if_changed();
    let found_key = find_installed_game_key(&cfg.installed_games, title, game_id);

    if let Some(ref fk) = found_key {
        if let Some(obj) = cfg.installed_games.get_mut(fk).and_then(|v| v.as_object_mut()) {
            if obj.remove("steam_url").is_some() {
                cfg.save_installed_games();
                let mut db = state.database.lock().unwrap();
                db.update_installed_states(&cfg);
                return Ok(json!({
                    "success": true,
                    "message": "Steam shortcut link removed",
                    "game": fk
                }));
            }
        }
    }

    Ok(json!({
        "success": true,
        "message": "No Steam shortcut link was found for this title"
    }))
}

#[tauri::command]
fn rust_get_extractor_status(app: AppHandle, state: State<'_, AppState>) -> Value {
    let mut cfg = state.config.lock().unwrap();
    cfg.bind_app(&app);
    cfg.reload_if_changed();
    let ext = extractor::Extractor::from_config(&cfg);
    json!({
        "winrar_available": ext.is_winrar_available(),
        "winrar_path": ext.winrar_path.as_ref().map(|p| p.to_string_lossy().to_string()),
        "sevenzip_available": ext.is_sevenzip_available(),
        "sevenzip_path": ext.sevenzip_path.as_ref().map(|p| p.to_string_lossy().to_string()),
        "any_available": ext.is_any_extractor_available()
    })
}

#[tauri::command]
fn rust_find_game_exe(game_dir: String, title: Option<String>) -> Option<String> {
    extractor::Extractor::find_game_exe(Path::new(&game_dir), title.as_deref())
        .map(|p| p.to_string_lossy().to_string())
}

#[tauri::command]
fn rust_extract_archive(
    app: AppHandle,
    state: State<'_, AppState>,
    payload: Map<String, Value>,
) -> Result<Value, String> {
    let job_id = payload
        .get("job_id")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    let archive_path = payload
        .get("archive_path")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "Missing archive_path".to_string())?
        .to_string();
    let title = payload
        .get("title")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let custom_extract_dir = payload
        .get("extract_dir")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string);
    let explicit_version = payload
        .get("version")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string);

    let (extractor_inst, extract_dir, password, cg_password, delete_after, is_fix) = {
        let mut cfg = state.config.lock().unwrap();
        cfg.bind_app(&app);
        cfg.reload_if_changed();

        let ext = extractor::Extractor::from_config(&cfg);
        let password = payload
            .get("password")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                let p = cfg.get_str("rar_password");
                if p.is_empty() {
                    extractor::DEFAULT_RAR_PASSWORD.to_string()
                } else {
                    p
                }
            });
        let cg_password = {
            let p = cfg.get_str("cg_password");
            if p.is_empty() {
                "cracked-games.org".to_string()
            } else {
                p
            }
        };
        let delete_after = payload
            .get("delete_after")
            .and_then(|v| v.as_bool())
            .unwrap_or_else(|| {
                cfg.settings
                    .get("auto_delete_archive")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(true)
            });

        let archive_file_name = Path::new(&archive_path)
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        let is_fix = archive_file_name.contains("fix")
            || archive_path.to_lowercase().contains("_fix.");

        let mut existing_location: Option<String> = None;
        if !title.is_empty() {
            if let Some(fk) = find_installed_game_key(&cfg.installed_games, &title, "") {
                existing_location = cfg
                    .installed_games
                    .get(&fk)
                    .and_then(|v| v.get("location"))
                    .and_then(|l| l.as_str())
                    .filter(|s| !s.trim().is_empty())
                    .map(str::to_string);
            }
        }

        let default_base = {
            let def_dl = cfg.get_str("default_download_path");
            let ext_p = cfg.get_str("extract_path");
            if !def_dl.trim().is_empty() {
                PathBuf::from(def_dl.trim())
            } else if !ext_p.trim().is_empty() {
                PathBuf::from(ext_p.trim())
            } else {
                config::get_default_games_dir()
            }
        };

        let resolved_dir = if let Some(custom) = custom_extract_dir {
            PathBuf::from(custom)
        } else if is_fix {
            if let Some(ref loc) = existing_location {
                let lp = PathBuf::from(loc);
                if lp.is_dir() {
                    lp
                } else {
                    default_base.join(&title)
                }
            } else {
                default_base.join(&title)
            }
        } else if let Some(ref loc) = existing_location {
            let lp = PathBuf::from(loc);
            if lp.is_dir() {
                match lp.parent() {
                    Some(parent)
                        if parent.exists() || parent.to_string_lossy().len() <= 3 =>
                    {
                        parent.to_path_buf()
                    }
                    _ => lp,
                }
            } else {
                default_base
            }
        } else {
            default_base
        };

        (ext, resolved_dir, password, cg_password, delete_after, is_fix)
    };

    let app_handle = app.clone();
    std::thread::spawn(move || {
        let emit_status = |mut payload_obj: Map<String, Value>| {
            payload_obj.insert("title".into(), json!(title));
            if let Some(ref jid) = job_id {
                payload_obj.insert("job_id".into(), json!(jid));
            }
            let _ = app_handle.emit("extraction-status", Value::Object(payload_obj));
        };

        let label = if title.is_empty() {
            archive_path.as_str()
        } else {
            title.as_str()
        };
        backend::broadcast_log(
            &app_handle,
            &format!("[Extractor] Starting extraction for {} -> {}", label, extract_dir.display()),
            Some("info"),
        );

        let opts = extractor::ExtractOptions {
            archive_path: PathBuf::from(&archive_path),
            extract_dir,
            password,
            cg_password,
            delete_after,
            game_title: if title.trim().is_empty() {
                None
            } else {
                Some(title.clone())
            },
            is_fix,
        };

        let result = extractor_inst.extract_archive(opts, |_| {});

        if result.success {
            let game_dir = result
                .game_dir
                .clone()
                .unwrap_or_else(|| result.extract_dir.clone());
            let exe_path = result.exe_path.clone();

            if !result.skipped && !title.trim().is_empty() {
                let state_ref = app_handle.state::<AppState>();
                let mut cfg = state_ref.config.lock().unwrap();
                cfg.reload_if_changed();
                let mut db = state_ref.database.lock().unwrap();
                if db.games.is_empty() {
                    db.load_local_or_cached(&cfg, false);
                }

                let norm_title = database::normalize_key(&title);
                let resolved_version = explicit_version.clone().or_else(|| {
                    db.games
                        .iter()
                        .find(|g| {
                            g.title.eq_ignore_ascii_case(&title)
                                || (!norm_title.is_empty()
                                    && database::normalize_key(&g.title) == norm_title)
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
                record.insert("location".into(), json!(game_dir));
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

            backend::broadcast_log(
                &app_handle,
                &format!("[Extractor] Extraction complete for {} -> {}", label, game_dir),
                Some("success"),
            );

            let mut done_map = Map::new();
            done_map.insert("status".into(), json!("success"));
            done_map.insert("file".into(), json!(archive_path));
            done_map.insert("dest".into(), json!(game_dir));
            done_map.insert("game_dir".into(), json!(game_dir));
            if let Some(ref exe) = exe_path {
                done_map.insert("exe_path".into(), json!(exe));
            }
            emit_status(done_map);
        } else {
            let err_msg = result
                .error
                .unwrap_or_else(|| "Unknown extraction error".to_string());
            backend::broadcast_log(
                &app_handle,
                &format!("[Extractor] Extraction failed for {}: {}", label, err_msg),
                Some("danger"),
            );
            let mut err_map = Map::new();
            err_map.insert("status".into(), json!("error"));
            err_map.insert("file".into(), json!(archive_path));
            err_map.insert("error".into(), json!(err_msg));
            emit_status(err_map);
        }
    });

    Ok(json!({ "success": true, "message": "Extraction started in background" }))
}

#[tauri::command]
fn close_app(app: AppHandle) {
    backend::stop_backend(&app);
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.close();
    }
    app.exit(0);
}

#[tauri::command]
fn show_achievement_overlay(app: AppHandle, data: serde_json::Value) -> Result<(), String> {
    let overlay = match app.get_webview_window("overlay") {
        Some(win) => win,
        None => {
            let overlay_w = 540.0;
            let overlay_h = 150.0;
            let (pos_x, pos_y) = match app.primary_monitor() {
                Ok(Some(monitor)) => {
                    let area = monitor.work_area();
                    let scale = monitor.scale_factor();
                    let logical_w = area.size.width as f64 / scale;
                    let logical_h = area.size.height as f64 / scale;
                    let logical_x = area.position.x as f64 / scale;
                    let logical_y = area.position.y as f64 / scale;
                    (
                        logical_x + ((logical_w - overlay_w) / 2.0).round(),
                        logical_y + logical_h - overlay_h - 35.0,
                    )
                }
                _ => (690.0, 895.0),
            };

            let win = WebviewWindowBuilder::new(&app, "overlay", WebviewUrl::App("overlay.html".into()))
                .title("Fanta OFME Achievement Overlay")
                .inner_size(overlay_w, overlay_h)
                .position(pos_x, pos_y)
                .decorations(false)
                .transparent(true)
                .always_on_top(true)
                .skip_taskbar(true)
                .focused(false)
                .shadow(false)
                .visible(false)
                .build()
                .map_err(|e| e.to_string())?;

            let _ = win.set_ignore_cursor_events(true);
            win
        }
    };

    let _ = overlay.emit("achievement-popup", data);
    let _ = overlay.show();
    Ok(())
}

#[tauri::command]
fn hide_achievement_overlay(app: AppHandle) {
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.hide();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(AppState::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            // Stage 4.1: Warm-load Rust ConfigManager + DatabaseManager immediately
            let handle = app.handle().clone();
            let (use_local, db_url, cache_json) = {
                let state = handle.state::<AppState>();
                let mut cfg = state.config.lock().unwrap();
                cfg.bind_app(&handle);
                cfg.reload_if_changed();
                let mut db = state.database.lock().unwrap();
                db.load_local_or_cached(&cfg, false);
                (
                    cfg.get_bool("use_local_db"),
                    cfg.get_str("db_url"),
                    cfg.cache_folder.join("Data.json"),
                )
            };

            if !use_local && !db_url.is_empty() && db_url != "local" {
                let bg_handle = handle.clone();
                std::thread::spawn(move || {
                    tauri::async_runtime::block_on(async move {
                        if let Ok(raw) = database::DatabaseManager::fetch_remote_raw(&db_url, &cache_json).await {
                            let state = bg_handle.state::<AppState>();
                            let mut cfg = state.config.lock().unwrap();
                            cfg.reload_if_changed();
                            let mut db = state.database.lock().unwrap();
                            db.apply_raw_catalog(&raw, &cfg, cache_json);
                        }
                    });
                });
            }

            backend::start_backend(app.handle());
            updater::spawn_startup_check(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed = event {
                    let app_handle = window.app_handle();
                    backend::stop_backend(app_handle);
                    if let Some(overlay) = app_handle.get_webview_window("overlay") {
                        let _ = overlay.close();
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_app_version,
            is_source_mode,
            is_portable,
            get_initial_logs,
            select_directory,
            select_file,
            open_path,
            show_item_in_folder,
            open_external,
            updater::set_beta_updates,
            updater::check_for_updates,
            updater::start_download_update,
            updater::restart_and_install_update,
            rust_get_status,
            rust_get_settings,
            rust_save_settings,
            rust_get_games,
            rust_refresh_games,
            rust_mark_game_status,
            rust_remove_game,
            rust_remove_steam_link,
            rust_get_extractor_status,
            rust_find_game_exe,
            rust_extract_archive,
            close_app,
            show_achievement_overlay,
            hide_achievement_overlay
        ])
        .build(tauri::generate_context!())
        .expect("error while building Fanta OFME Downloader");

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            backend::stop_backend(app_handle);
        }
    });
}
