mod backend;
mod updater;

use serde::{Deserialize, Serialize};
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
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            logs: Mutex::new(Vec::new()),
            beta_updates: AtomicBool::new(updater::read_beta_updates_setting()),
            backend_child: Mutex::new(None),
            pending_update: Mutex::new(None),
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
