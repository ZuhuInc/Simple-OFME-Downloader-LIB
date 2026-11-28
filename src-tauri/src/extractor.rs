use crate::config::ConfigManager;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::fs::{self, File};
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub const DEFAULT_RAR_PASSWORD: &str = "online-fix.me";

#[derive(Clone, Debug, Default)]
pub struct ExtractOptions {
    pub archive_path: PathBuf,
    pub extract_dir: PathBuf,
    pub password: String,
    pub cg_password: String,
    pub delete_after: bool,
    pub game_title: Option<String>,
    pub is_fix: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExtractResult {
    pub success: bool,
    pub skipped: bool,
    pub message: Option<String>,
    pub error: Option<String>,
    pub extract_dir: String,
    pub game_dir: Option<String>,
    pub exe_path: Option<String>,
}

impl ExtractResult {
    fn err(extract_dir: &Path, msg: impl Into<String>) -> Self {
        Self {
            success: false,
            skipped: false,
            message: None,
            error: Some(msg.into()),
            extract_dir: extract_dir.to_string_lossy().to_string(),
            game_dir: None,
            exe_path: None,
        }
    }
}

pub struct Extractor {
    pub winrar_path: Option<PathBuf>,
    pub sevenzip_path: Option<PathBuf>,
}

impl Extractor {
    pub fn new(winrar_path: Option<&str>, sevenzip_path: Option<&str>) -> Self {
        Self {
            winrar_path: find_winrar(winrar_path),
            sevenzip_path: find_sevenzip(sevenzip_path),
        }
    }

    pub fn from_config(cfg: &ConfigManager) -> Self {
        let wr = cfg.get_str("winrar_path");
        let sz = cfg.get_str("sevenzip_path");
        Self::new(
            if wr.trim().is_empty() { None } else { Some(wr.trim()) },
            if sz.trim().is_empty() { None } else { Some(sz.trim()) },
        )
    }

    pub fn is_winrar_available(&self) -> bool {
        self.winrar_path.as_ref().is_some_and(|p| p.is_file())
    }

    pub fn is_sevenzip_available(&self) -> bool {
        self.sevenzip_path.as_ref().is_some_and(|p| p.is_file())
    }

    #[allow(dead_code)]
    pub fn is_any_extractor_available(&self) -> bool {
        self.is_winrar_available() || self.is_sevenzip_available()
    }

    pub fn get_blocking_processes(target_dir: &Path) -> Vec<String> {
        if !target_dir.exists() {
            return Vec::new();
        }
        if is_drive_or_root(target_dir) {
            return Vec::new();
        }
        get_blocking_processes_impl(target_dir)
    }

    pub fn extract_archive<F>(&self, opts: ExtractOptions, mut progress_cb: F) -> ExtractResult
    where
        F: FnMut(Value),
    {
        if !opts.archive_path.exists() {
            return ExtractResult::err(
                &opts.extract_dir,
                format!("Archive not found: {}", opts.archive_path.display()),
            );
        }

        let mut archive_path = opts.archive_path.clone();
        let mut archive_name = archive_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        // Multi-part check: if part2+ passed, route to part 1 if present (unless Forza Horizon 2 / Azimuth)
        let lower_name = archive_name.to_lowercase();
        let title_lower = opts
            .game_title
            .as_deref()
            .unwrap_or("")
            .to_lowercase();
        if let Some((_start, _end, part_num)) = parse_multipart_number(&lower_name) {
            if part_num > 1 && !(title_lower.contains("forza horizon 2") || lower_name.contains("azimuth")) {
                if let Some(routed) = find_part1_sibling(&archive_path) {
                    let routed_name = routed
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_default();
                    println!(
                        "[Rust Backend] [Extractor] Multi-part {} routed to primary volume {}",
                        archive_name, routed_name
                    );
                    archive_path = routed;
                    archive_name = routed_name;
                } else {
                    return ExtractResult {
                        success: true,
                        skipped: true,
                        message: Some(format!(
                            "Skipping multi-part piece {} (handled by part 1)",
                            archive_name
                        )),
                        error: None,
                        extract_dir: opts.extract_dir.to_string_lossy().to_string(),
                        game_dir: None,
                        exe_path: None,
                    };
                }
            }
        }

        // Check blocking processes inside the specific target game directory only
        let target_check_dir = resolve_target_check_dir(
            &opts.extract_dir,
            opts.game_title.as_deref(),
            opts.is_fix,
        );
        if let Some(ref check_dir) = target_check_dir {
            let blocking = Self::get_blocking_processes(check_dir);
            if !blocking.is_empty() {
                let err = format!(
                    "The game is currently running ({}). Please close the game before extracting.",
                    blocking.join(", ")
                );
                println!("[Rust Backend] [Extractor] Aborting extraction: {}", err);
                progress_cb(json!({
                    "status": "error",
                    "error": err,
                    "file": archive_name
                }));
                return ExtractResult::err(&opts.extract_dir, err);
            }
        }

        if let Err(e) = fs::create_dir_all(&opts.extract_dir) {
            let err = format!("Failed to create extract directory: {}", e);
            progress_cb(json!({
                "status": "error",
                "error": err,
                "file": archive_name
            }));
            return ExtractResult::err(&opts.extract_dir, err);
        }

        progress_cb(json!({
            "status": "extracting",
            "file": archive_name,
            "dir": opts.extract_dir.to_string_lossy().to_string()
        }));

        let before_entries = list_dir_entry_names(&opts.extract_dir);
        let passwords_to_try = build_password_candidates(&opts.password, &opts.cg_password);

        let mut success = false;
        let mut error_msg = String::new();

        let is_zip = archive_path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| e.eq_ignore_ascii_case("zip"));

        // Method 1: Native Rust zip extraction for .zip archives (instant, zero GUI popups)
        if is_zip {
            println!("[Rust Backend] [Extractor] Running native Zip extraction for {}...", archive_name);
            match extract_zip_native(&archive_path, &opts.extract_dir, &passwords_to_try) {
                Ok(()) => {
                    success = true;
                    error_msg.clear();
                }
                Err(e) => {
                    error_msg = format!("Zip extraction error: {}", e);
                }
            }
        }

        // Method 2: WinRAR CLI (silent background mode, dialogs suppressed)
        if !success {
            if let Some(ref wr_exe) = self.winrar_path {
                if wr_exe.is_file() {
                    let dest_arg = format!("{}\\", opts.extract_dir.to_string_lossy().trim_end_matches(['\\', '/']));
                    for p in &passwords_to_try {
                        let pwd_arg = if p.is_empty() {
                            "-p-".to_string()
                        } else {
                            format!("-p{}", p)
                        };
                        println!("[Rust Backend] [Extractor] Running WinRAR -> {}", opts.extract_dir.display());
                        match run_hidden_extractor(
                            wr_exe,
                            &[
                                "x",
                                "-ibck",
                                "-inul",
                                &pwd_arg,
                                "-o+",
                                "-y",
                                &archive_path.to_string_lossy(),
                                &dest_arg,
                            ],
                        ) {
                            Ok(output) => {
                                let code = output.status.code().unwrap_or(-1);
                                if code == 0 || code == 1 {
                                    success = true;
                                    error_msg.clear();
                                    break;
                                } else {
                                    let stderr = String::from_utf8_lossy(&output.stderr);
                                    let stdout = String::from_utf8_lossy(&output.stdout);
                                    let detail = if !stderr.trim().is_empty() {
                                        stderr.trim().to_string()
                                    } else {
                                        stdout.trim().to_string()
                                    };
                                    error_msg = format!("WinRAR code {}: {}", code, detail);
                                }
                            }
                            Err(e) => {
                                error_msg = format!("WinRAR execution error: {}", e);
                            }
                        }
                    }
                }
            }
        }

        // Method 3: 7-Zip CLI fallback
        if !success {
            if let Some(ref sz_exe) = self.sevenzip_path {
                if sz_exe.is_file() {
                    let out_arg = format!("-o{}", opts.extract_dir.to_string_lossy());
                    for p in &passwords_to_try {
                        let pwd_arg = if p.is_empty() {
                            "-p-".to_string()
                        } else {
                            format!("-p{}", p)
                        };
                        println!("[Rust Backend] [Extractor] Running 7-Zip -> {}", opts.extract_dir.display());
                        match run_hidden_extractor(
                            sz_exe,
                            &[
                                "x",
                                "-y",
                                "-aoa",
                                &pwd_arg,
                                &out_arg,
                                &archive_path.to_string_lossy(),
                            ],
                        ) {
                            Ok(output) => {
                                let code = output.status.code().unwrap_or(-1);
                                if code == 0 || code == 1 {
                                    success = true;
                                    error_msg.clear();
                                    break;
                                } else {
                                    let stderr = String::from_utf8_lossy(&output.stderr);
                                    let stdout = String::from_utf8_lossy(&output.stdout);
                                    let detail = if !stderr.trim().is_empty() {
                                        stderr.trim().to_string()
                                    } else {
                                        stdout.trim().to_string()
                                    };
                                    error_msg = format!("7-Zip code {}: {}", code, detail);
                                }
                            }
                            Err(e) => {
                                error_msg = format!("7-Zip execution error: {}", e);
                            }
                        }
                    }
                }
            }
        }

        if !success {
            if error_msg.is_empty() {
                error_msg = "No extraction tool found. Please install WinRAR or 7-Zip.".to_string();
            }
            progress_cb(json!({
                "status": "error",
                "error": error_msg,
                "file": archive_name
            }));
            return ExtractResult::err(&opts.extract_dir, error_msg);
        }

        // Unwrap hardcoded container folders (GAMES2 / GAMES)
        if !opts.is_fix {
            Self::unwrap_archive_containers(&opts.extract_dir, Some(&before_entries));
        }

        // Detect extracted game directory
        let mut game_dir = if opts.is_fix {
            opts.extract_dir.clone()
        } else {
            detect_extracted_game_dir(
                &opts.extract_dir,
                opts.game_title.as_deref(),
                &before_entries,
            )
        };

        // Check for Azimuth compatibility layer (Forza Horizon 2)
        let exe_path = if game_dir.join("azimuth.exe").exists() {
            let az_exe = game_dir.join("azimuth.exe");
            Self::ensure_azimuth_config(&game_dir);
            Some(az_exe)
        } else {
            Self::find_game_exe(&game_dir, opts.game_title.as_deref())
        };

        // Update game_dir in case Azimuth root was resolved
        if !game_dir.exists() {
            game_dir = opts.extract_dir.clone();
        }

        // Cleanup raw archive + siblings + .part leftovers
        if opts.delete_after {
            cleanup_after_extraction(&archive_path);
        } else {
            let part_file = PathBuf::from(format!("{}.part", archive_path.to_string_lossy()));
            if part_file.is_file() {
                let _ = fs::remove_file(part_file);
            }
        }

        let game_dir_str = game_dir.to_string_lossy().to_string();
        let exe_path_str = exe_path.as_ref().map(|p| p.to_string_lossy().to_string());

        progress_cb(json!({
            "status": "extracted",
            "file": archive_name,
            "extract_dir": opts.extract_dir.to_string_lossy().to_string(),
            "game_dir": game_dir_str,
            "exe_path": exe_path_str
        }));

        println!(
            "[Rust Backend] [Extractor] Extraction COMPLETE: {} -> {}",
            archive_name, game_dir_str
        );

        ExtractResult {
            success: true,
            skipped: false,
            message: None,
            error: None,
            extract_dir: opts.extract_dir.to_string_lossy().to_string(),
            game_dir: Some(game_dir_str),
            exe_path: exe_path_str,
        }
    }

    #[allow(dead_code)]
    pub fn apply_fix<F>(
        &self,
        fix_archive_path: PathBuf,
        game_dir: PathBuf,
        password: &str,
        cg_password: &str,
        delete_after: bool,
        progress_cb: F,
    ) -> ExtractResult
    where
        F: FnMut(Value),
    {
        self.extract_archive(
            ExtractOptions {
                archive_path: fix_archive_path,
                extract_dir: game_dir,
                password: if password.is_empty() {
                    DEFAULT_RAR_PASSWORD.to_string()
                } else {
                    password.to_string()
                },
                cg_password: cg_password.to_string(),
                delete_after,
                game_title: None,
                is_fix: true,
            },
            progress_cb,
        )
    }

    pub fn ensure_azimuth_config(az_root: &Path) {
        let data_dir = az_root.join("data");
        if fs::create_dir_all(&data_dir).is_err() {
            return;
        }
        let ini_path = data_dir.join("azimuth.ini");

        if ini_path.is_file() {
            if let Ok(bytes) = fs::read(&ini_path) {
                let text = decode_utf16_or_utf8(&bytes);
                if text.contains("[title-1a96545b]") {
                    return;
                }
            }
        }

        let mut anthem_rel = "Anthem_1.0.0.64_x64__8wekyb3d8bbwe".to_string();
        if let Ok(entries) = fs::read_dir(az_root) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.is_dir() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name.to_lowercase().starts_with("anthem") || p.join("Mount").exists() {
                        anthem_rel = name;
                        break;
                    }
                }
            }
        }

        let mut storm_rel =
            r"Forza Horizon 2 Storm Island (1.0.0.36)\StormIsland_1.0.0.36_neutral__8wekyb3d8bbwe"
                .to_string();
        if let Some(found) = find_dir_prefix_recursive(az_root, "stormisland") {
            if let Ok(rel) = found.strip_prefix(az_root) {
                storm_rel = rel.to_string_lossy().replace('/', "\\");
            }
        }

        let ini_content = format!(
            "[launcher]\n\
            game=1a96545b\n\
            resolution=1080\n\
            aspect=16:9\n\
            antialiasing=msaax4\n\
            graphics=default\n\
            shadows=default\n\
            reflections=default\n\
            car_detail=default\n\
            particles=default\n\
            motion_blur=default\n\
            texture_filtering=default\n\
            audio=stereo\n\
            frame_rate=60\n\
            frame_pacing=fixed\n\
            vsync=on\n\
            display=fullscreen\n\
            hdr=off\n\
            hdr_peak=\n\
            hdr_paper_white=200\n\
            hdr_black=0\n\
            language=\n\
            speech=\n\
            player_name=Fanta OFME\n\
            settings_version=1\n\
            [title-1a96545b]\n\
            folder={}\n\
            content={}\n\
            name=Forza Horizon 2\n",
            anthem_rel, storm_rel
        );

        let mut bytes = Vec::with_capacity(2 + ini_content.len() * 2);
        bytes.extend_from_slice(&[0xFF, 0xFE]); // UTF-16LE BOM matching Python encoding="utf-16"
        for unit in ini_content.encode_utf16() {
            bytes.extend_from_slice(&unit.to_le_bytes());
        }
        if let Ok(()) = fs::write(&ini_path, bytes) {
            println!(
                "[Rust Backend] [Extractor] Generated azimuth.ini for Forza Horizon 2 at: {}",
                ini_path.display()
            );
        }
    }

    pub fn is_title_matching_dir(item_path: &Path, game_title: &str) -> bool {
        if game_title.trim().is_empty() || !item_path.is_dir() {
            return false;
        }
        let name = item_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        if name.starts_with('_') || name.to_lowercase().contains("redist") {
            return false;
        }
        let norm_title = norm_alnum(game_title);
        let norm_item = norm_alnum(&name);
        if norm_title.is_empty() || norm_item.is_empty() {
            return false;
        }
        if norm_item == norm_title || norm_item.contains(&norm_title) {
            return true;
        }
        if norm_item.len() >= 5 && norm_title.contains(&norm_item) {
            return true;
        }
        let no_the_title = norm_title.strip_prefix("the").unwrap_or(&norm_title);
        let no_the_item = norm_item.strip_prefix("the").unwrap_or(&norm_item);
        !no_the_title.is_empty()
            && !no_the_item.is_empty()
            && (no_the_item == no_the_title || no_the_item.contains(no_the_title))
    }

    pub fn unwrap_archive_containers(extract_dir: &Path, before_entries: Option<&HashSet<String>>) {
        if !extract_dir.is_dir() {
            return;
        }
        let base_name_lower = extract_dir
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();

        let Ok(entries_rd) = fs::read_dir(extract_dir) else {
            return;
        };
        let entries: Vec<PathBuf> = entries_rd.flatten().map(|e| e.path()).collect();

        for wrapper_dir in entries {
            if !wrapper_dir.is_dir() {
                continue;
            }
            let Some(entry_name) = wrapper_dir.file_name().map(|n| n.to_string_lossy().to_string()) else {
                continue;
            };
            let entry_lower = entry_name.to_lowercase();
            let is_games2 = entry_lower == "games2";
            let is_games_wrapper = entry_lower == "games"
                && base_name_lower != "games"
                && base_name_lower != "games2"
                && before_entries.is_none_or(|b| !b.contains(&entry_name));

            if !(is_games2 || is_games_wrapper) {
                continue;
            }

            let Ok(children_rd) = fs::read_dir(&wrapper_dir) else {
                continue;
            };
            let children: Vec<PathBuf> = children_rd.flatten().map(|e| e.path()).collect();

            if is_games_wrapper {
                let has_dir = children.iter().any(|c| c.is_dir());
                let has_rom = children.iter().any(|c| {
                    let s = c.to_string_lossy().to_lowercase();
                    s.ends_with(".nup")
                        || s.ends_with(".nsp")
                        || s.ends_with(".xci")
                        || s.ends_with(".rom")
                        || s.ends_with(".iso")
                });
                if !has_dir || has_rom {
                    continue;
                }
            }

            println!(
                "[Rust Backend] [Extractor] Unwrapping container folder '{}' in {}...",
                entry_name,
                extract_dir.display()
            );

            for src_item in children {
                let Some(child_name) = src_item.file_name() else {
                    continue;
                };
                let dst_item = extract_dir.join(child_name);
                if let Err(e) = move_or_merge(&src_item, &dst_item) {
                    println!(
                        "[Rust Backend] [Extractor] Warning moving unwrapped item '{}': {}",
                        child_name.to_string_lossy(),
                        e
                    );
                }
            }

            if fs::read_dir(&wrapper_dir)
                .map(|mut d| d.next().is_none())
                .unwrap_or(false)
            {
                let _ = fs::remove_dir(&wrapper_dir);
            }
        }
    }

    pub fn find_game_exe(game_dir: &Path, game_title: Option<&str>) -> Option<PathBuf> {
        if !game_dir.is_dir() {
            return None;
        }

        let norm_dir = game_dir
            .to_string_lossy()
            .replace('/', "\\")
            .trim_end_matches('\\')
            .to_uppercase();
        if matches!(
            norm_dir.as_str(),
            "C:" | "D:" | "E:" | "F:" | r"C:\GAMES" | r"D:\GAMES" | r"D:\GAMES2"
        ) || is_drive_or_root(game_dir)
        {
            return None;
        }

        // Protection: avoid library root dirs with >10 independent game subfolders
        if let Ok(rd) = fs::read_dir(game_dir) {
            let subdirs = rd
                .flatten()
                .filter(|e| {
                    e.path().is_dir() && {
                        let name = e.file_name().to_string_lossy().to_string();
                        !name.starts_with('.') && !name.starts_with('_')
                    }
                })
                .count();
            if subdirs > 10 {
                return None;
            }
        }

        let is_forza = game_title
            .is_some_and(|t| t.to_lowercase().contains("forza"))
            || game_dir.to_string_lossy().to_lowercase().contains("forza");
        if is_forza {
            let az = game_dir.join("azimuth.exe");
            if az.is_file() {
                return Some(az);
            }
        }

        let ignored_names: [&str; 11] = [
            "unitycrashhandler64.exe",
            "unitycrashhandler32.exe",
            "dxwebsetup.exe",
            "unins000.exe",
            "uninstall.exe",
            "forza_durango_release_final.exe",
            "crashreport.exe",
            "crashreportclient.exe",
            "epicgameslauncher.exe",
            "steamservice.exe",
            "vcredist_x64.exe",
        ];
        let ignored_dirs: [&str; 9] = [
            "_redist",
            "redist",
            "commonredist",
            "_commonredist",
            "directx",
            "support",
            "dependencies",
            "tools",
            "crashreports",
        ];

        let mut candidates: Vec<PathBuf> = Vec::new();
        collect_exe_candidates(
            game_dir,
            &ignored_names,
            &ignored_dirs,
            &mut candidates,
        );
        if candidates.is_empty() {
            return None;
        }

        let norm_title = game_title.map(norm_alnum).unwrap_or_default();
        let folder_name = game_dir
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let norm_folder = norm_alnum(&folder_name);

        let score_candidate = |path: &Path| -> f64 {
            let base_name = path
                .file_name()
                .map(|n| n.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            let stem = path
                .file_stem()
                .map(|s| s.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            let norm_stem = norm_alnum(&stem);
            let mut score = 0.0f64;

            if !norm_title.is_empty() {
                if norm_stem == norm_title {
                    score += 1000.0;
                } else if norm_stem.contains(&norm_title) {
                    score += 500.0;
                } else if norm_stem.len() >= 4 && norm_title.contains(&norm_stem) {
                    score += 300.0;
                }
            }

            if !norm_folder.is_empty() {
                if norm_stem == norm_folder {
                    score += 400.0;
                } else if norm_stem.contains(&norm_folder) {
                    score += 200.0;
                }
            }

            if matches!(
                stem.as_str(),
                "launcher" | "game" | "play" | "start" | "shipping" | "client" | "boot"
            ) {
                score += 250.0;
            }

            if is_forza && base_name == "azimuth.exe" {
                score += 1500.0;
            }

            if let Ok(rel) = path.strip_prefix(game_dir) {
                let comps = rel.components().count();
                let depth = comps.saturating_sub(1);
                score -= (depth as f64) * 50.0;
            }

            if let Ok(meta) = fs::metadata(path) {
                score += (meta.len() as f64 / (1024.0 * 1024.0)).min(50.0);
            }

            score
        };

        candidates.sort_by(|a, b| {
            score_candidate(b)
                .partial_cmp(&score_candidate(a))
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        candidates.into_iter().next()
    }
}

fn find_winrar(configured: Option<&str>) -> Option<PathBuf> {
    if let Some(cfg_path) = configured {
        let p = PathBuf::from(cfg_path);
        if p.is_file() {
            return Some(p);
        }
    }
    for cand in [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    ] {
        let p = PathBuf::from(cand);
        if p.is_file() {
            return Some(p);
        }
    }
    for exe in ["WinRAR.exe", "winrar.exe", "UnRAR.exe", "unrar.exe"] {
        if let Some(p) = which_in_path(exe) {
            return Some(p);
        }
    }
    None
}

fn find_sevenzip(configured: Option<&str>) -> Option<PathBuf> {
    if let Some(cfg_path) = configured {
        let p = PathBuf::from(cfg_path);
        if p.is_file() {
            return Some(p);
        }
    }
    for cand in [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\7-Zip\7za.exe",
    ] {
        let p = PathBuf::from(cand);
        if p.is_file() {
            return Some(p);
        }
    }
    for exe in ["7z.exe", "7za.exe"] {
        if let Some(p) = which_in_path(exe) {
            return Some(p);
        }
    }
    None
}

fn which_in_path(binary: &str) -> Option<PathBuf> {
    let path_var = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path_var) {
        let candidate = dir.join(binary);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn is_drive_or_root(path: &Path) -> bool {
    let norm = path
        .to_string_lossy()
        .replace('/', "\\")
        .trim_end_matches('\\')
        .to_ascii_lowercase();
    if norm.len() == 2 && norm.as_bytes()[0].is_ascii_alphabetic() && norm.as_bytes()[1] == b':' {
        return true;
    }
    path.parent().is_none()
}

#[cfg(target_os = "windows")]
mod win_proc {
    pub const TH32CS_SNAPPROCESS: u32 = 0x0000_0002;
    pub const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;

    #[repr(C)]
    pub struct ProcessEntry32W {
        pub dw_size: u32,
        pub cnt_usage: u32,
        pub th32_process_id: u32,
        pub th32_default_heap_id: usize,
        pub th32_module_id: u32,
        pub cnt_threads: u32,
        pub th32_parent_process_id: u32,
        pub pc_pri_class_base: i32,
        pub dw_flags: u32,
        pub sz_exe_file: [u16; 260],
    }

    impl ProcessEntry32W {
        pub fn zeroed() -> Self {
            Self {
                dw_size: std::mem::size_of::<Self>() as u32,
                cnt_usage: 0,
                th32_process_id: 0,
                th32_default_heap_id: 0,
                th32_module_id: 0,
                cnt_threads: 0,
                th32_parent_process_id: 0,
                pc_pri_class_base: 0,
                dw_flags: 0,
                sz_exe_file: [0; 260],
            }
        }

        pub fn exe_name(&self) -> String {
            let end = self
                .sz_exe_file
                .iter()
                .position(|&c| c == 0)
                .unwrap_or(self.sz_exe_file.len());
            String::from_utf16_lossy(&self.sz_exe_file[..end])
        }
    }

    extern "system" {
        pub fn CreateToolhelp32Snapshot(dw_flags: u32, th32_process_id: u32) -> *mut core::ffi::c_void;
        pub fn Process32FirstW(h_snapshot: *mut core::ffi::c_void, lppe: *mut ProcessEntry32W) -> i32;
        pub fn Process32NextW(h_snapshot: *mut core::ffi::c_void, lppe: *mut ProcessEntry32W) -> i32;
        pub fn OpenProcess(dw_desired_access: u32, b_inherit_handle: i32, dw_process_id: u32) -> *mut core::ffi::c_void;
        pub fn QueryFullProcessImageNameW(
            h_process: *mut core::ffi::c_void,
            dw_flags: u32,
            lp_exe_name: *mut u16,
            lpdw_size: *mut u32,
        ) -> i32;
        pub fn CloseHandle(h_object: *mut core::ffi::c_void) -> i32;
    }
}

#[cfg(target_os = "windows")]
pub fn is_process_running(exe_name: &str) -> bool {
    let needle = exe_name.trim();
    if needle.is_empty() {
        return false;
    }
    let invalid_handle = (-1isize) as *mut core::ffi::c_void;
    let snapshot = unsafe { win_proc::CreateToolhelp32Snapshot(win_proc::TH32CS_SNAPPROCESS, 0) };
    if snapshot.is_null() || snapshot == invalid_handle {
        return false;
    }

    let mut entry = win_proc::ProcessEntry32W::zeroed();
    let mut found = false;
    unsafe {
        if win_proc::Process32FirstW(snapshot, &mut entry) != 0 {
            loop {
                if entry.exe_name().eq_ignore_ascii_case(needle) {
                    found = true;
                    break;
                }
                if win_proc::Process32NextW(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }
        win_proc::CloseHandle(snapshot);
    }
    found
}

#[cfg(not(target_os = "windows"))]
pub fn is_process_running(_exe_name: &str) -> bool {
    false
}

#[cfg(target_os = "windows")]
fn get_blocking_processes_impl(target_dir: &Path) -> Vec<String> {
    let invalid_handle = (-1isize) as *mut core::ffi::c_void;
    let abs_target = fs::canonicalize(target_dir)
        .unwrap_or_else(|_| target_dir.to_path_buf())
        .to_string_lossy()
        .replace('/', "\\")
        .trim_start_matches(r"\\?\")
        .to_lowercase();
    let target_trimmed = abs_target.trim_end_matches('\\').to_string();
    let target_prefix = format!("{}\\", target_trimmed);

    let snapshot = unsafe { win_proc::CreateToolhelp32Snapshot(win_proc::TH32CS_SNAPPROCESS, 0) };
    if snapshot.is_null() || snapshot == invalid_handle {
        return Vec::new();
    }

    let mut blocking: HashSet<String> = HashSet::new();
    let mut entry = win_proc::ProcessEntry32W::zeroed();

    unsafe {
        if win_proc::Process32FirstW(snapshot, &mut entry) != 0 {
            loop {
                let pid = entry.th32_process_id;
                if pid > 4 {
                    let proc_handle =
                        win_proc::OpenProcess(win_proc::PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
                    if !proc_handle.is_null() {
                        let mut buf = [0u16; 1024];
                        let mut size = buf.len() as u32;
                        let ok = win_proc::QueryFullProcessImageNameW(
                            proc_handle,
                            0,
                            buf.as_mut_ptr(),
                            &mut size,
                        );
                        win_proc::CloseHandle(proc_handle);
                        if ok != 0 && size > 0 {
                            let exe_str = String::from_utf16_lossy(&buf[..size as usize]);
                            let exe_lower = exe_str.replace('/', "\\").to_lowercase();
                            if exe_lower.starts_with(&target_prefix) || exe_lower == target_trimmed
                            {
                                let proc_name = entry.exe_name();
                                let fallback_name = Path::new(&exe_str)
                                    .file_name()
                                    .map(|n| n.to_string_lossy().to_string())
                                    .unwrap_or_default();
                                let final_name = if !proc_name.is_empty() {
                                    proc_name
                                } else {
                                    fallback_name
                                };
                                if !final_name.is_empty() {
                                    blocking.insert(final_name);
                                }
                            }
                        }
                    }
                }

                if win_proc::Process32NextW(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }
        win_proc::CloseHandle(snapshot);
    }

    let mut sorted: Vec<String> = blocking.into_iter().collect();
    sorted.sort();
    sorted
}

#[cfg(not(target_os = "windows"))]
fn get_blocking_processes_impl(_target_dir: &Path) -> Vec<String> {
    Vec::new()
}

/// Matches `(?:^|[\._\-\s])part0*([0-9]+)` case-insensitively and returns `(span_start, digits_end, number)`.
pub fn parse_multipart_number(filename: &str) -> Option<(usize, usize, u32)> {
    let lower = filename.to_ascii_lowercase();
    let bytes = lower.as_bytes();
    let mut i = 0usize;
    while i + 4 < bytes.len() {
        let boundary_ok = i == 0 || matches!(bytes[i - 1], b'.' | b'_' | b'-' | b' ');
        if boundary_ok && bytes[i..].starts_with(b"part") {
            let mut j = i + 4;
            while j < bytes.len() && bytes[j] == b'0' {
                j += 1;
            }
            let num_start = i + 4;
            let mut k = num_start;
            while k < bytes.len() && bytes[k].is_ascii_digit() {
                k += 1;
            }
            if k > num_start {
                if let Ok(num) = lower[num_start..k].parse::<u32>() {
                    return Some((i, k, num));
                }
            }
        }
        i += 1;
    }
    None
}

fn find_part1_sibling(archive_path: &Path) -> Option<PathBuf> {
    let parent = archive_path.parent()?;
    let fname = archive_path.file_name()?.to_str()?;
    let (part_start, digits_end, _) = parse_multipart_number(fname)?;
    let prefix = &fname[..part_start];
    let suffix = &fname[digits_end..];

    let candidates = [
        format!("{}part1{}", prefix, suffix),
        format!("{}part01{}", prefix, suffix),
        format!("{}Part1{}", prefix, suffix),
        format!("{}Part01{}", prefix, suffix),
        format!("{}.part1{}", prefix.trim_end_matches(['.', '_', '-', ' ']), suffix),
        format!("{}_Part1{}", prefix.trim_end_matches(['.', '_', '-', ' ']), suffix),
    ];

    for cand in candidates {
        let full = parent.join(cand);
        if full.is_file() {
            return Some(full);
        }
    }
    None
}

fn cleanup_after_extraction(archive_path: &Path) {
    let part_file = PathBuf::from(format!("{}.part", archive_path.to_string_lossy()));
    if part_file.is_file() {
        let _ = fs::remove_file(&part_file);
    }

    if let (Some(parent), Some(fname)) = (archive_path.parent(), archive_path.file_name().and_then(|n| n.to_str())) {
        if let Some((part_start, _, _)) = parse_multipart_number(fname) {
            let base_prefix = fname[..part_start].to_ascii_lowercase();
            if let Ok(rd) = fs::read_dir(parent) {
                for entry in rd.flatten() {
                    let p = entry.path();
                    if p == archive_path || !p.is_file() {
                        continue;
                    }
                    let sibling_name = entry.file_name().to_string_lossy().to_string();
                    if let Some((s_start, _, _)) = parse_multipart_number(&sibling_name) {
                        if sibling_name[..s_start].to_ascii_lowercase() == base_prefix {
                            let _ = fs::remove_file(&p);
                        }
                    }
                }
            }
        } else if archive_path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| e.eq_ignore_ascii_case("rar"))
        {
            if let Some(stem) = archive_path.file_stem().and_then(|s| s.to_str()) {
                let stem_lower = stem.to_ascii_lowercase();
                if let Ok(rd) = fs::read_dir(parent) {
                    for entry in rd.flatten() {
                        let p = entry.path();
                        if !p.is_file() {
                            continue;
                        }
                        if let (Some(s_stem), Some(ext)) = (
                            p.file_stem().and_then(|s| s.to_str()),
                            p.extension().and_then(|e| e.to_str()),
                        ) {
                            if s_stem.to_ascii_lowercase() == stem_lower
                                && ext.len() == 3
                                && (ext.starts_with('r') || ext.starts_with('R'))
                                && ext[1..].chars().all(|c| c.is_ascii_digit())
                            {
                                let _ = fs::remove_file(&p);
                            }
                        }
                    }
                }
            }
        }
    }

    if archive_path.is_file() {
        match fs::remove_file(archive_path) {
            Ok(()) => println!(
                "[Rust Backend] [Extractor] Successfully deleted raw archive after extraction: {}",
                archive_path.display()
            ),
            Err(e) => println!(
                "[Rust Backend] [Extractor] Notice: Could not remove archive {}: {}",
                archive_path.display(),
                e
            ),
        }
    }
}

fn resolve_target_check_dir(
    extract_dir: &Path,
    game_title: Option<&str>,
    is_fix: bool,
) -> Option<PathBuf> {
    if is_fix {
        if extract_dir.exists() {
            return Some(extract_dir.to_path_buf());
        }
        return None;
    }

    let title = game_title?.trim();
    if title.is_empty() || !extract_dir.exists() {
        return None;
    }

    let direct = extract_dir.join(title);
    if direct.is_dir() {
        return Some(direct);
    }

    let norm_title = norm_alnum(title);
    let title_lower = title.to_lowercase();
    if let Ok(rd) = fs::read_dir(extract_dir) {
        for entry in rd.flatten() {
            let p = entry.path();
            if p.is_dir() {
                let name = entry.file_name().to_string_lossy().to_string();
                let entry_norm = norm_alnum(&name);
                if (!entry_norm.is_empty() && entry_norm == norm_title)
                    || name.to_lowercase() == title_lower
                {
                    return Some(p);
                }
            }
        }
    }

    None
}

fn list_dir_entry_names(dir: &Path) -> HashSet<String> {
    let mut set = HashSet::new();
    if let Ok(rd) = fs::read_dir(dir) {
        for entry in rd.flatten() {
            set.insert(entry.file_name().to_string_lossy().to_string());
        }
    }
    set
}

fn build_password_candidates(primary: &str, cg: &str) -> Vec<String> {
    let mut out = Vec::new();
    for raw in [
        primary,
        if cg.is_empty() { "cracked-games.org" } else { cg },
        DEFAULT_RAR_PASSWORD,
        "",
    ] {
        let owned = raw.to_string();
        if !out.contains(&owned) {
            out.push(owned);
        }
    }
    out
}

fn extract_zip_native(
    archive_path: &Path,
    extract_dir: &Path,
    passwords: &[String],
) -> Result<(), String> {
    let file = File::open(archive_path).map_err(|e| e.to_string())?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;

    let mut chosen_password: Option<String> = None;
    let total = archive.len();

    for i in 0..total {
        let mut success_this_entry = false;
        let mut last_err = String::new();

        // Try previously matched password first, else try unencrypted first
        let try_order: Vec<Option<String>> = if let Some(ref cp) = chosen_password {
            vec![Some(cp.clone())]
        } else {
            let mut v = vec![None];
            for p in passwords {
                if !p.is_empty() {
                    v.push(Some(p.clone()));
                }
            }
            v
        };

        for maybe_pwd in try_order {
            let open_res = match &maybe_pwd {
                None => archive.by_index(i),
                Some(p) => archive.by_index_decrypt(i, p.as_bytes()),
            };

            match open_res {
                Ok(mut entry) => {
                    let Some(rel) = entry.enclosed_name() else {
                        return Err("Unsafe archive path".to_string());
                    };
                    let out_path = extract_dir.join(rel);
                    if entry.is_dir() {
                        fs::create_dir_all(&out_path).map_err(|e| e.to_string())?;
                    } else {
                        if let Some(parent) = out_path.parent() {
                            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
                        }
                        let mut outfile = File::create(&out_path).map_err(|e| e.to_string())?;
                        io::copy(&mut entry, &mut outfile).map_err(|e| e.to_string())?;
                    }
                    if maybe_pwd.is_some() && chosen_password.is_none() {
                        chosen_password = maybe_pwd;
                    }
                    success_this_entry = true;
                    break;
                }
                Err(e) => {
                    last_err = e.to_string();
                }
            }
        }

        if !success_this_entry {
            return Err(if last_err.is_empty() {
                "Failed to decrypt or unpack zip entry".to_string()
            } else {
                last_err
            });
        }
    }

    Ok(())
}

fn run_hidden_extractor(exe: &Path, args: &[&str]) -> io::Result<std::process::Output> {
    let mut cmd = Command::new(exe);
    cmd.args(args);
    #[cfg(target_os = "windows")]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.output()
}

fn detect_extracted_game_dir(
    extract_dir: &Path,
    game_title: Option<&str>,
    before_entries: &HashSet<String>,
) -> PathBuf {
    let mut game_dir = extract_dir.to_path_buf();

    if let Some(title) = game_title {
        if let Ok(rd) = fs::read_dir(extract_dir) {
            let mut items: Vec<PathBuf> = rd.flatten().map(|e| e.path()).collect();
            items.sort();
            for item_path in items {
                if Extractor::is_title_matching_dir(&item_path, title) {
                    game_dir = item_path;
                    break;
                }
            }
        }
    }

    if game_dir == extract_dir {
        let after = list_dir_entry_names(extract_dir);
        let real_dirs: Vec<PathBuf> = after
            .difference(before_entries)
            .map(|e| extract_dir.join(e))
            .filter(|p| {
                p.is_dir() && {
                    let b = p
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_default();
                    !b.starts_with('_') && !b.to_lowercase().contains("redist")
                }
            })
            .collect();
        if real_dirs.len() == 1 {
            game_dir = real_dirs[0].clone();
        }
    }

    if let Some(title) = game_title {
        if game_dir != extract_dir && game_dir.is_dir() {
            if let Ok(rd) = fs::read_dir(&game_dir) {
                let sub_dirs: Vec<PathBuf> = rd
                    .flatten()
                    .map(|e| e.path())
                    .filter(|p| {
                        p.is_dir() && {
                            let b = p
                                .file_name()
                                .map(|n| n.to_string_lossy().to_string())
                                .unwrap_or_default();
                            !b.starts_with('_') && !b.to_lowercase().contains("redist")
                        }
                    })
                    .collect();
                if sub_dirs.len() == 1 && Extractor::is_title_matching_dir(&sub_dirs[0], title) {
                    game_dir = sub_dirs[0].clone();
                }
            }
        }
    }

    game_dir
}

fn move_or_merge(src: &Path, dst: &Path) -> io::Result<()> {
    if !dst.exists() {
        if fs::rename(src, dst).is_ok() {
            return Ok(());
        }
        // Fallback copy + remove across volumes or locks
        if src.is_dir() {
            copy_dir_recursive(src, dst)?;
            let _ = fs::remove_dir_all(src);
        } else {
            fs::copy(src, dst)?;
            let _ = fs::remove_file(src);
        }
        return Ok(());
    }

    if src.is_dir() && dst.is_dir() {
        copy_dir_recursive(src, dst)?;
        let _ = fs::remove_dir_all(src);
    } else if src.is_file() {
        fs::copy(src, dst)?;
        let _ = fs::remove_file(src);
    }
    Ok(())
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let p = entry.path();
        let target = dst.join(entry.file_name());
        if p.is_dir() {
            copy_dir_recursive(&p, &target)?;
        } else {
            fs::copy(&p, &target)?;
        }
    }
    Ok(())
}

fn collect_exe_candidates(
    dir: &Path,
    ignored_names: &[&str],
    ignored_dirs: &[&str],
    out: &mut Vec<PathBuf>,
) {
    let Ok(rd) = fs::read_dir(dir) else {
        return;
    };
    for entry in rd.flatten() {
        let p = entry.path();
        if p.is_dir() {
            let dname = entry.file_name().to_string_lossy().to_lowercase();
            if dname.starts_with('_') || dname.contains("redist") || ignored_dirs.contains(&dname.as_str()) {
                continue;
            }
            collect_exe_candidates(&p, ignored_names, ignored_dirs, out);
        } else if p.is_file() {
            let fname_lower = entry.file_name().to_string_lossy().to_lowercase();
            if fname_lower.ends_with(".exe")
                && !ignored_names.contains(&fname_lower.as_str())
                && !fname_lower.starts_with("vcredist")
                && !fname_lower.starts_with("unins")
                && !fname_lower.contains("_durango_")
            {
                out.push(p);
            }
        }
    }
}

fn find_dir_prefix_recursive(root: &Path, prefix_lower: &str) -> Option<PathBuf> {
    let rd = fs::read_dir(root).ok()?;
    for entry in rd.flatten() {
        let p = entry.path();
        if p.is_dir() {
            let name_lower = entry.file_name().to_string_lossy().to_lowercase();
            if name_lower.starts_with(prefix_lower) {
                return Some(p);
            }
            if let Some(sub) = find_dir_prefix_recursive(&p, prefix_lower) {
                return Some(sub);
            }
        }
    }
    None
}

fn decode_utf16_or_utf8(bytes: &[u8]) -> String {
    if bytes.starts_with(&[0xFF, 0xFE]) {
        let units: Vec<u16> = bytes[2..]
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect();
        return String::from_utf16_lossy(&units);
    }
    if bytes.starts_with(&[0xFE, 0xFF]) {
        let units: Vec<u16> = bytes[2..]
            .chunks_exact(2)
            .map(|c| u16::from_be_bytes([c[0], c[1]]))
            .collect();
        return String::from_utf16_lossy(&units);
    }
    String::from_utf8_lossy(bytes).to_string()
}

fn norm_alnum(s: &str) -> String {
    s.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .flat_map(|c| c.to_lowercase())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn make_temp_dir(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!(
            "fanta_ext_test_{}_{}_{}",
            label,
            std::process::id(),
            nanos
        ));
        let _ = fs::create_dir_all(&dir);
        dir
    }

    #[test]
    fn test_multipart_routing_and_forza_exemption() {
        assert_eq!(parse_multipart_number("Halo.part02.rar").map(|v| v.2), Some(2));
        assert_eq!(parse_multipart_number("game_Part1.rar").map(|v| v.2), Some(1));
        assert_eq!(parse_multipart_number("no_part_here.zip"), None);

        let dir = make_temp_dir("multipart");
        let part2 = dir.join("CoolGame.part02.rar");
        fs::write(&part2, b"dummy").unwrap();

        let ext = Extractor::new(None, None);
        // Without part1 present -> skipped gracefully
        let skipped = ext.extract_archive(
            ExtractOptions {
                archive_path: part2.clone(),
                extract_dir: dir.join("out"),
                game_title: Some("Cool Game".into()),
                ..Default::default()
            },
            |_| {},
        );
        assert!(skipped.success);
        assert!(skipped.skipped);

        // Forza Horizon 2 should NOT skip part2 as routed multi-part (will proceed and fail due to dummy content/missing tools)
        let fh2_res = ext.extract_archive(
            ExtractOptions {
                archive_path: part2,
                extract_dir: dir.join("out_fh2"),
                game_title: Some("Forza Horizon 2".into()),
                ..Default::default()
            },
            |_| {},
        );
        assert!(!fh2_res.skipped);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_title_matching_dir() {
        let dir = make_temp_dir("titlematch");
        let g1 = dir.join("The Legend of Zelda Ocarina");
        let redist = dir.join("_Redist");
        fs::create_dir_all(&g1).unwrap();
        fs::create_dir_all(&redist).unwrap();

        assert!(Extractor::is_title_matching_dir(&g1, "Legend of Zelda Ocarina"));
        assert!(!Extractor::is_title_matching_dir(&redist, "_Redist"));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_unwrap_archive_containers_and_rom_protection() {
        let dir = make_temp_dir("unwrap");

        // 1. GAMES2 wrapper should always unwrap
        let wrapper2 = dir.join("GAMES2").join("MyAwesomeGame");
        fs::create_dir_all(&wrapper2).unwrap();
        fs::write(wrapper2.join("MyAwesomeGame.exe"), b"exe").unwrap();
        Extractor::unwrap_archive_containers(&dir, None);
        assert!(dir.join("MyAwesomeGame").join("MyAwesomeGame.exe").is_file());
        assert!(!dir.join("GAMES2").exists());

        // 2. 'games' containing ROMs (.nsp) must NOT unwrap
        let rom_dir = make_temp_dir("rom_guard");
        let rom_games = rom_dir.join("games");
        fs::create_dir_all(rom_games.join("sub")).unwrap();
        fs::write(rom_games.join("game.nsp"), b"rom").unwrap();
        Extractor::unwrap_archive_containers(&rom_dir, None);
        assert!(rom_dir.join("games").join("game.nsp").is_file());

        let _ = fs::remove_dir_all(&dir);
        let _ = fs::remove_dir_all(&rom_dir);
    }

    #[test]
    fn test_find_game_exe_scoring_and_root_guard() {
        assert_eq!(Extractor::find_game_exe(Path::new(r"D:\"), Some("Halo")), None);
        assert_eq!(Extractor::find_game_exe(Path::new(r"D:\Games"), Some("Halo")), None);

        let game_dir = make_temp_dir("findexe");
        let redist = game_dir.join("_CommonRedist");
        fs::create_dir_all(&redist).unwrap();
        fs::write(redist.join("vcredist_x64.exe"), b"vc").unwrap();
        fs::write(game_dir.join("UnityCrashHandler64.exe"), b"crash").unwrap();

        let sub = game_dir.join("Binaries");
        fs::create_dir_all(&sub).unwrap();
        fs::write(sub.join("helper.exe"), b"small").unwrap();
        let real_exe = game_dir.join("CrimsonMoon.exe");
        fs::write(&real_exe, vec![0u8; 2048]).unwrap();

        let found = Extractor::find_game_exe(&game_dir, Some("Crimson Moon"));
        assert_eq!(found, Some(real_exe));
        let _ = fs::remove_dir_all(&game_dir);
    }

    #[test]
    fn test_native_zip_extraction_and_cleanup() {
        let dir = make_temp_dir("nativezip");
        let zip_path = dir.join("TestGame.zip");
        let out_dir = dir.join("Extracted");

        {
            let file = File::create(&zip_path).unwrap();
            let mut zw = zip::ZipWriter::new(file);
            let opts = zip::write::SimpleFileOptions::default()
                .compression_method(zip::CompressionMethod::Deflated);
            zw.start_file("TestGame/TestGame.exe", opts).unwrap();
            zw.write_all(b"MZ-test-binary").unwrap();
            zw.start_file("TestGame/readme.txt", opts).unwrap();
            zw.write_all(b"hello world").unwrap();
            zw.finish().unwrap();
        }

        let ext = Extractor::new(None, None);
        let mut events = Vec::new();
        let res = ext.extract_archive(
            ExtractOptions {
                archive_path: zip_path.clone(),
                extract_dir: out_dir.clone(),
                delete_after: true,
                game_title: Some("TestGame".into()),
                ..Default::default()
            },
            |ev| events.push(ev),
        );

        assert!(res.success, "expected success, err={:?}", res.error);
        assert!(!zip_path.exists(), "raw zip should be deleted after extraction");
        assert!(out_dir.join("TestGame").join("TestGame.exe").is_file());
        assert_eq!(
            res.game_dir.as_deref(),
            Some(out_dir.join("TestGame").to_string_lossy().as_ref())
        );
        assert_eq!(
            res.exe_path.as_deref(),
            Some(out_dir.join("TestGame").join("TestGame.exe").to_string_lossy().as_ref())
        );
        assert!(events.iter().any(|e| e["status"] == "extracting"));
        assert!(events.iter().any(|e| e["status"] == "extracted"));

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_azimuth_ini_generation_and_idempotency() {
        let az_root = make_temp_dir("azimuth");
        fs::create_dir_all(az_root.join("Anthem_Custom").join("Mount")).unwrap();
        fs::create_dir_all(az_root.join("DLC").join("StormIsland_Pack")).unwrap();

        Extractor::ensure_azimuth_config(&az_root);
        let ini = az_root.join("data").join("azimuth.ini");
        assert!(ini.is_file());
        let text = decode_utf16_or_utf8(&fs::read(&ini).unwrap());
        assert!(text.contains("[title-1a96545b]"));
        assert!(text.contains("folder=Anthem_Custom"));
        assert!(text.contains("content=DLC\\StormIsland_Pack"));

        // Custom edit should be preserved on idempotent re-run
        let custom = "[title-1a96545b]\nplayer_name=Custom\n";
        let mut custom_bytes = vec![0xFF, 0xFE];
        for u in custom.encode_utf16() {
            custom_bytes.extend_from_slice(&u.to_le_bytes());
        }
        fs::write(&ini, &custom_bytes).unwrap();
        Extractor::ensure_azimuth_config(&az_root);
        let after = decode_utf16_or_utf8(&fs::read(&ini).unwrap());
        assert!(after.contains("player_name=Custom"));

        let _ = fs::remove_dir_all(&az_root);
    }
}
