use crate::{backend, AppState};
use serde::Deserialize;
use std::cmp::Ordering as CmpOrdering;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_updater::UpdaterExt;

const GITHUB_OWNER: &str = "ZuhuInc";
const GITHUB_REPO: &str = "Simple-OFME-Downloader-LIB";
const STABLE_LATEST_JSON_URL: &str =
    "https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/releases/latest/download/latest.json";

#[derive(Debug, Deserialize)]
struct GitHubAsset {
    name: String,
    browser_download_url: String,
}

#[derive(Debug, Deserialize)]
struct GitHubRelease {
    tag_name: Option<String>,
    html_url: Option<String>,
    #[serde(default)]
    draft: bool,
    #[serde(default)]
    assets: Vec<GitHubAsset>,
}

struct ResolvedGitHubRelease {
    version: String,
    release_url: String,
    manifest_url: Option<String>,
}

pub fn read_beta_updates_setting() -> bool {
    let Some(home) = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")) else {
        return false;
    };
    let home_path = PathBuf::from(home);
    let zuhu_dir = home_path.join("Documents").join("ZuhuProjects").join("ZuhuOFME");
    let data_dir = if zuhu_dir.exists() {
        zuhu_dir
    } else {
        home_path.join(".fanta_ofme")
    };

    let settings_path = data_dir.join("Settings.json");
    let Ok(raw) = fs::read_to_string(settings_path) else {
        return false;
    };
    let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&raw) else {
        return false;
    };
    parsed
        .get("beta_updates")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
}

pub fn clean_version(raw: &str) -> String {
    let trimmed = raw.trim().trim_start_matches(['v', 'V']);
    trimmed.split('+').next().unwrap_or("0.0.0").to_string()
}

pub fn compare_semver(a: &str, b: &str) -> CmpOrdering {
    let ca = clean_version(a);
    let cb = clean_version(b);

    let (core_a, pre_a) = match ca.split_once('-') {
        Some((core, pre)) => (core, Some(pre)),
        None => (ca.as_str(), None),
    };
    let (core_b, pre_b) = match cb.split_once('-') {
        Some((core, pre)) => (core, Some(pre)),
        None => (cb.as_str(), None),
    };

    let nums_a: Vec<u64> = core_a
        .split('.')
        .map(|p| p.parse::<u64>().unwrap_or(0))
        .collect();
    let nums_b: Vec<u64> = core_b
        .split('.')
        .map(|p| p.parse::<u64>().unwrap_or(0))
        .collect();

    let max_len = nums_a.len().max(nums_b.len());
    for i in 0..max_len {
        let va = *nums_a.get(i).unwrap_or(&0);
        let vb = *nums_b.get(i).unwrap_or(&0);
        match va.cmp(&vb) {
            CmpOrdering::Equal => continue,
            ord => return ord,
        }
    }

    match (pre_a, pre_b) {
        (None, None) => CmpOrdering::Equal,
        (None, Some(_)) => CmpOrdering::Greater, // Stable > Prerelease
        (Some(_), None) => CmpOrdering::Less,    // Prerelease < Stable
        (Some(pa), Some(pb)) => {
            let toks_a: Vec<&str> = pa.split('.').collect();
            let toks_b: Vec<&str> = pb.split('.').collect();
            for i in 0..toks_a.len().min(toks_b.len()) {
                let ta = toks_a[i];
                let tb = toks_b[i];
                if ta == tb {
                    continue;
                }
                match (ta.parse::<u64>(), tb.parse::<u64>()) {
                    (Ok(na), Ok(nb)) => return na.cmp(&nb),
                    (Ok(_), Err(_)) => return CmpOrdering::Less,
                    (Err(_), Ok(_)) => return CmpOrdering::Greater,
                    (Err(_), Err(_)) => return ta.cmp(tb),
                }
            }
            toks_a.len().cmp(&toks_b.len())
        }
    }
}

async fn resolve_github_release(allow_prerelease: bool) -> Result<Option<ResolvedGitHubRelease>, String> {
    let client = reqwest::Client::builder()
        .user_agent("Fanta-OFME-Downloader")
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let api_url = if allow_prerelease {
        format!(
            "https://api.github.com/repos/{}/{}/releases?per_page=25",
            GITHUB_OWNER, GITHUB_REPO
        )
    } else {
        format!(
            "https://api.github.com/repos/{}/{}/releases/latest",
            GITHUB_OWNER, GITHUB_REPO
        )
    };

    let resp = client.get(&api_url).send().await.map_err(|e| e.to_string())?;
    if resp.status().as_u16() == 404 {
        return Ok(None);
    }
    if !resp.status().is_success() {
        return Err(format!("GitHub API returned HTTP {}", resp.status()));
    }

    let selected: Option<GitHubRelease> = if !allow_prerelease {
        resp.json::<GitHubRelease>().await.ok()
    } else {
        let list = resp.json::<Vec<GitHubRelease>>().await.unwrap_or_default();
        let mut best: Option<GitHubRelease> = None;
        let mut best_ver = String::from("0.0.0");
        for rel in list {
            if rel.draft {
                continue;
            }
            let Some(ref tag) = rel.tag_name else {
                continue;
            };
            let ver = clean_version(tag);
            if best.is_none() || compare_semver(&ver, &best_ver) == CmpOrdering::Greater {
                best_ver = ver;
                best = Some(rel);
            }
        }
        best
    };

    let Some(rel) = selected else {
        return Ok(None);
    };
    let tag = rel.tag_name.unwrap_or_default();
    if tag.is_empty() {
        return Ok(None);
    }

    let manifest_url = rel
        .assets
        .iter()
        .find(|a| {
            let lower = a.name.to_lowercase();
            lower == "latest.json" || lower == "beta.json"
        })
        .map(|a| a.browser_download_url.clone());

    Ok(Some(ResolvedGitHubRelease {
        version: clean_version(&tag),
        release_url: rel.html_url.unwrap_or_else(|| {
            format!("https://github.com/{}/{}/releases", GITHUB_OWNER, GITHUB_REPO)
        }),
        manifest_url,
    }))
}

pub async fn run_update_check(app: &AppHandle) -> serde_json::Value {
    let current_ver = clean_version(&app.package_info().version.to_string());
    let beta_enabled = app
        .try_state::<AppState>()
        .map(|s| s.beta_updates.load(Ordering::Relaxed))
        .unwrap_or(false);

    let _ = app.emit("updater-event", serde_json::json!({ "type": "checking" }));
    backend::broadcast_log(
        app,
        &format!(
            "[AutoUpdater] Checking GitHub releases (channel={})...",
            if beta_enabled { "beta" } else { "stable" }
        ),
        Some("info"),
    );

    let resolved_rel = match resolve_github_release(beta_enabled).await {
        Ok(r) => r,
        Err(err) => {
            backend::broadcast_log(
                app,
                &format!("[AutoUpdater] Update check notice: {}", err),
                Some("warning"),
            );
            let _ = app.emit(
                "updater-event",
                serde_json::json!({ "type": "error", "message": err }),
            );
            return serde_json::json!({ "status": "error", "error": err });
        }
    };

    // If a Tauri updater manifest asset (`latest.json` / `beta.json`) is present and
    // updater signing keys are configured, prefer signed native in-app updating.
    let has_signing_pubkey = app
        .config()
        .plugins
        .0
        .get("updater")
        .and_then(|u| u.get("pubkey"))
        .and_then(|p| p.as_str())
        .map(|s| !s.trim().is_empty())
        .unwrap_or(false);

    let endpoint_str = if !beta_enabled {
        Some(STABLE_LATEST_JSON_URL.to_string())
    } else {
        resolved_rel.as_ref().and_then(|r| r.manifest_url.clone())
    };

    if has_signing_pubkey {
        if let (Some(url_str), Some(rel)) = (endpoint_str, resolved_rel.as_ref()) {
            if rel.manifest_url.is_some() {
                if let Ok(parsed_url) = tauri::Url::parse(&url_str) {
                    if let Ok(builder) = app.updater_builder().endpoints(vec![parsed_url]) {
                        if let Ok(updater) = builder.build() {
                            match updater.check().await {
                                Ok(Some(update)) => {
                                    let new_ver = clean_version(&update.version);
                                    let release_notes = update.body.clone().unwrap_or_default();
                                    if let Some(state) = app.try_state::<AppState>() {
                                        if let Ok(mut guard) = state.pending_update.lock() {
                                            *guard = Some(update);
                                        }
                                    }
                                    backend::broadcast_log(
                                        app,
                                        &format!(
                                            "[AutoUpdater] New update found: v{}! Ready to download.",
                                            new_ver
                                        ),
                                        Some("info"),
                                    );
                                    let _ = app.emit(
                                        "updater-event",
                                        serde_json::json!({
                                            "type": "available",
                                            "version": new_ver,
                                            "releaseNotes": release_notes
                                        }),
                                    );
                                    return serde_json::json!({
                                        "status": "success",
                                        "updateInfo": { "version": new_ver }
                                    });
                                }
                                Ok(None) => {
                                    backend::broadcast_log(
                                        app,
                                        &format!("[AutoUpdater] Current version (v{}) is up-to-date.", current_ver),
                                        Some("info"),
                                    );
                                    let _ = app.emit(
                                        "updater-event",
                                        serde_json::json!({
                                            "type": "not-available",
                                            "version": current_ver
                                        }),
                                    );
                                    return serde_json::json!({
                                        "status": "up-to-date",
                                        "message": "You are running the latest release."
                                    });
                                }
                                Err(err) => {
                                    // Fall through to GitHub Release link fallback cleanly
                                    backend::broadcast_log(
                                        app,
                                        &format!("[AutoUpdater] Signed manifest notice: {}", err),
                                        Some("info"),
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Fallback: GitHub Releases SemVer comparison with clickable Release link
    match resolved_rel {
        Some(rel) => {
            let cmp = compare_semver(&rel.version, &current_ver);
            let returning_to_stable =
                !beta_enabled && current_ver.contains('-') && cmp == CmpOrdering::Less;
            if cmp == CmpOrdering::Greater || returning_to_stable {
                backend::broadcast_log(
                    app,
                    &format!("[AutoUpdater] New release available on GitHub: v{}!", rel.version),
                    Some("success"),
                );
                let _ = app.emit(
                    "updater-event",
                    serde_json::json!({
                        "type": "portable-available",
                        "version": rel.version,
                        "releaseUrl": rel.release_url
                    }),
                );
                serde_json::json!({
                    "status": "portable-update-available",
                    "version": rel.version,
                    "releaseUrl": rel.release_url,
                    "message": format!("New version v{} is available on GitHub!", rel.version)
                })
            } else {
                backend::broadcast_log(
                    app,
                    &format!("[AutoUpdater] Current version (v{}) is up-to-date.", current_ver),
                    Some("info"),
                );
                let _ = app.emit(
                    "updater-event",
                    serde_json::json!({
                        "type": "not-available",
                        "version": current_ver
                    }),
                );
                serde_json::json!({
                    "status": "up-to-date",
                    "message": format!("You are running the latest release (v{}).", current_ver)
                })
            }
        }
        None => {
            let _ = app.emit(
                "updater-event",
                serde_json::json!({
                    "type": "not-available",
                    "version": current_ver
                }),
            );
            serde_json::json!({
                "status": "no-release",
                "message": "No newer releases published on GitHub yet."
            })
        }
    }
}

pub fn spawn_startup_check(app: &AppHandle) {
    if cfg!(debug_assertions) {
        return;
    }
    let handle = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(5));
        tauri::async_runtime::block_on(async move {
            let _ = run_update_check(&handle).await;
        });
    });
}

#[tauri::command]
pub fn set_beta_updates(
    app: AppHandle,
    state: State<'_, AppState>,
    enabled: bool,
) -> serde_json::Value {
    state.beta_updates.store(enabled, Ordering::Relaxed);
    if let Ok(mut pending) = state.pending_update.lock() {
        *pending = None;
    }
    backend::broadcast_log(
        &app,
        &format!(
            "[AutoUpdater] Beta update channel {}",
            if enabled { "ENABLED" } else { "DISABLED" }
        ),
        Some("info"),
    );
    serde_json::json!({
        "success": true,
        "beta_updates": enabled
    })
}

#[tauri::command]
pub async fn check_for_updates(app: AppHandle) -> serde_json::Value {
    run_update_check(&app).await
}

#[tauri::command]
pub async fn start_download_update(app: AppHandle) -> serde_json::Value {
    let pending_opt = app
        .try_state::<AppState>()
        .and_then(|s| s.pending_update.lock().ok().and_then(|mut g| g.take()));

    let Some(update) = pending_opt else {
        return serde_json::json!({
            "status": "error",
            "message": "No signed update package queued (use View Release on GitHub)."
        });
    };

    let version = clean_version(&update.version);
    backend::broadcast_log(
        &app,
        &format!("[AutoUpdater] Downloading update v{}...", version),
        Some("info"),
    );

    let mut transferred: u64 = 0;
    let started = Instant::now();
    let app_progress = app.clone();
    let app_finished = app.clone();

    let res = update
        .download_and_install(
            move |chunk_len, content_len| {
                transferred += chunk_len as u64;
                let total = content_len.unwrap_or(0);
                let percent = if total > 0 {
                    ((transferred as f64 / total as f64) * 100.0).min(100.0) as u64
                } else {
                    0
                };
                let elapsed = started.elapsed().as_secs_f64().max(0.1);
                let speed_mb = (transferred as f64 / (1024.0 * 1024.0)) / elapsed;
                let _ = app_progress.emit(
                    "updater-event",
                    serde_json::json!({
                        "type": "progress",
                        "percent": percent,
                        "speed": format!("{:.1} MB/s", speed_mb),
                        "transferred": transferred,
                        "total": total
                    }),
                );
            },
            move || {
                backend::broadcast_log(
                    &app_finished,
                    "[AutoUpdater] Download verified; preparing install...",
                    Some("info"),
                );
            },
        )
        .await;

    match res {
        Ok(_) => {
            backend::broadcast_log(
                &app,
                &format!("[AutoUpdater] Update v{} downloaded and ready for restart!", version),
                Some("success"),
            );
            let _ = app.emit(
                "updater-event",
                serde_json::json!({
                    "type": "downloaded",
                    "version": version
                }),
            );
            serde_json::json!({ "status": "downloading" })
        }
        Err(err) => {
            let msg = err.to_string();
            backend::broadcast_log(
                &app,
                &format!("[AutoUpdater] Download failed: {}", msg),
                Some("warning"),
            );
            serde_json::json!({ "status": "error", "error": msg })
        }
    }
}

#[tauri::command]
pub fn restart_and_install_update(app: AppHandle) {
    backend::stop_backend(&app);
    app.restart();
}
