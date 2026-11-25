use crate::{AppState, LogEntry};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

fn current_time_label() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let day_secs = secs % 86_400;
    let hours = (day_secs / 3600) % 24;
    let minutes = (day_secs / 60) % 60;
    let seconds = day_secs % 60;
    format!("{:02}:{:02}:{:02}", hours, minutes, seconds)
}

pub fn broadcast_log(app: &AppHandle, raw_text: &str, custom_level: Option<&str>) {
    let clean_text = raw_text.trim();
    if clean_text.is_empty() {
        return;
    }

    let level = if let Some(lvl) = custom_level {
        lvl.to_string()
    } else {
        let lower = clean_text.to_lowercase();
        if lower.contains("error")
            || lower.contains("failed")
            || lower.contains("exception")
            || lower.contains("traceback")
            || lower.contains("errno")
        {
            "danger".to_string()
        } else if lower.contains("warn") || lower.contains("warning") || lower.contains("skipped") {
            "warning".to_string()
        } else if lower.contains("success")
            || lower.contains("connected")
            || lower.contains("loaded")
            || lower.contains("ready")
            || lower.contains("starting")
        {
            "success".to_string()
        } else {
            "info".to_string()
        }
    };

    let entry = LogEntry {
        text: clean_text.to_string(),
        level,
        time: current_time_label(),
    };

    if let Some(state) = app.try_state::<AppState>() {
        if let Ok(mut logs) = state.logs.lock() {
            logs.push(entry.clone());
            if logs.len() > 200 {
                let excess = logs.len() - 200;
                logs.drain(0..excess);
            }
        }
    }

    let _ = app.emit("backend-log", entry);
}

fn find_repo_root() -> Option<PathBuf> {
    let mut roots_to_scan: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        roots_to_scan.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots_to_scan.push(parent.to_path_buf());
        }
    }

    for start in roots_to_scan {
        for ancestor in start.ancestors() {
            if ancestor.join("src").join("backend").join("bridge_server.py").is_file() {
                return Some(ancestor.to_path_buf());
            }
        }
    }
    None
}

fn find_python_executable(repo_root: &Path) -> String {
    if let Ok(env_py) = std::env::var("PYTHON") {
        let trimmed = env_py.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    #[cfg(target_os = "windows")]
    let candidates = [
        repo_root.join(".venv").join("Scripts").join("python.exe"),
        repo_root.join("venv").join("Scripts").join("python.exe"),
    ];
    #[cfg(not(target_os = "windows"))]
    let candidates = [
        repo_root.join(".venv").join("bin").join("python"),
        repo_root.join("venv").join("bin").join("python"),
    ];

    for candidate in candidates {
        if candidate.is_file() {
            return candidate.to_string_lossy().to_string();
        }
    }

    if cfg!(target_os = "windows") {
        "python".to_string()
    } else {
        "python3".to_string()
    }
}

fn find_packaged_sidecar(app: &AppHandle) -> Option<PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let direct = exe_dir.join("bridge_server.exe");
            if direct.is_file() {
                return Some(direct);
            }
            let triple_named = exe_dir.join("bridge_server-x86_64-pc-windows-msvc.exe");
            if triple_named.is_file() {
                return Some(triple_named);
            }
            let in_binaries = exe_dir.join("binaries").join("bridge_server.exe");
            if in_binaries.is_file() {
                return Some(in_binaries);
            }
        }
    }

    if let Ok(res_dir) = app.path().resource_dir() {
        let primary = res_dir.join("backend").join("bridge_server").join("bridge_server.exe");
        if primary.is_file() {
            return Some(primary);
        }
        let fallback = res_dir.join("bridge_server.exe");
        if fallback.is_file() {
            return Some(fallback);
        }
    }

    None
}

fn pipe_reader_threads(app: &AppHandle, child: &mut Child) {
    if let Some(stdout) = child.stdout.take() {
        let app_handle = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line_res in reader.lines() {
                if let Ok(line) = line_res {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        println!("[Python Backend] {}", trimmed);
                        broadcast_log(&app_handle, trimmed, None);
                    }
                }
            }
        });
    }

    if let Some(stderr) = child.stderr.take() {
        let app_handle = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line_res in reader.lines() {
                if let Ok(line) = line_res {
                    let trimmed = line.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    println!("[Python Backend] {}", trimmed);
                    if trimmed.contains("WARNING: This is a development server")
                        || trimmed.contains("WSGI server instead")
                        || trimmed.contains("allow_unsafe_werkzeug")
                    {
                        continue;
                    }
                    if trimmed.contains("HTTP/1.1\" 200")
                        || trimmed.contains("HTTP/1.1\" 304")
                        || trimmed.contains("Running on http://")
                    {
                        broadcast_log(&app_handle, trimmed, Some("info"));
                    } else {
                        broadcast_log(&app_handle, trimmed, None);
                    }
                }
            }
        });
    }
}

pub fn start_backend(app: &AppHandle) {
    let app_version = app.package_info().version.to_string();
    let is_dev = cfg!(debug_assertions);

    let (program, args, cwd, source_mode_str): (String, Vec<String>, PathBuf, &str) = if !is_dev {
        if let Some(sidecar_path) = find_packaged_sidecar(app) {
            let parent = sidecar_path
                .parent()
                .map(Path::to_path_buf)
                .unwrap_or_else(|| PathBuf::from("."));
            (
                sidecar_path.to_string_lossy().to_string(),
                Vec::new(),
                parent,
                "0",
            )
        } else if let Some(root) = find_repo_root() {
            let py = find_python_executable(&root);
            let script = root.join("src").join("backend").join("bridge_server.py");
            (py, vec![script.to_string_lossy().to_string()], root, "1")
        } else {
            broadcast_log(
                app,
                "[Main] Packaged backend sidecar (bridge_server.exe) not found.",
                Some("danger"),
            );
            return;
        }
    } else if let Some(root) = find_repo_root() {
        let py = find_python_executable(&root);
        let script = root.join("src").join("backend").join("bridge_server.py");
        (py, vec![script.to_string_lossy().to_string()], root, "1")
    } else {
        broadcast_log(
            app,
            "[Main] Could not locate src/backend/bridge_server.py from working directory.",
            Some("danger"),
        );
        return;
    };

    let spawn_msg = format!(
        "[Main] Spawning Backend ({}, SourceMode={}): {}",
        if source_mode_str == "0" {
            "Sidecar Binary"
        } else {
            "Python Interpreter"
        },
        source_mode_str == "1",
        program
    );
    println!("{}", spawn_msg);
    broadcast_log(app, &spawn_msg, Some("info"));

    let mut cmd = Command::new(&program);
    cmd.args(&args)
        .current_dir(&cwd)
        .env("PYTHONUNBUFFERED", "1")
        .env("FANTA_BACKEND_PORT", "5004")
        .env("FANTA_SOURCE_MODE", source_mode_str)
        .env("FANTA_APP_VERSION", &app_version)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    match cmd.spawn() {
        Ok(mut child) => {
            pipe_reader_threads(app, &mut child);
            if let Some(state) = app.try_state::<AppState>() {
                if let Ok(mut guard) = state.backend_child.lock() {
                    *guard = Some(child);
                }
            }
        }
        Err(err) => {
            let err_msg = format!("[Main] Failed to spawn Python backend process: {}", err);
            eprintln!("{}", err_msg);
            broadcast_log(app, &err_msg, Some("danger"));
        }
    }
}

pub fn stop_backend(app: &AppHandle) {
    let Some(state) = app.try_state::<AppState>() else {
        return;
    };

    let child_opt = state
        .backend_child
        .lock()
        .ok()
        .and_then(|mut guard| guard.take());

    let Some(mut child) = child_opt else {
        return;
    };

    let pid = child.id();
    println!("[Main] Terminating Python backend process tree (PID {})...", pid);

    #[cfg(target_os = "windows")]
    {
        let mut kill_tree = Command::new("taskkill");
        kill_tree
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW);
        let _ = kill_tree.status();
    }

    let _ = child.kill();
    let _ = child.wait();
}
