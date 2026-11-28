use reqwest::header::SET_COOKIE;
use reqwest::redirect::Policy;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const GOFILE_SALT: &str = "12af056dacea0b";
const CHROME_UA: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

static GOFILE_TOKEN_CACHE: OnceLock<Mutex<(String, u64)>> = OnceLock::new();

#[derive(Clone, Debug)]
pub struct ResolvedLink {
    pub direct_url: String,
    pub filename: Option<String>,
    pub cookies: HashMap<String, String>,
}

pub fn normalize_browser_name(raw_name: &str) -> String {
    let raw = raw_name.to_lowercase();
    if raw.contains("brave") {
        return "Brave".to_string();
    }
    if raw.contains("opera gx") || raw.contains("operagx") {
        return "Opera GX".to_string();
    }
    if raw.contains("chrome") && raw.contains("google") {
        return "Google Chrome".to_string();
    }
    if raw.contains("firefox") {
        return "Firefox".to_string();
    }
    if raw.contains("opera") && !raw.contains("gx") {
        return "Opera".to_string();
    }
    if raw.contains("vivaldi") {
        return "Vivaldi".to_string();
    }
    if raw.contains("edge") {
        return "Microsoft Edge".to_string();
    }
    raw_name.to_string()
}

pub fn get_installed_browsers() -> Map<String, Value> {
    let prog_files = std::env::var("PROGRAMFILES").unwrap_or_else(|_| r"C:\Program Files".into());
    let prog_files_x86 =
        std::env::var("PROGRAMFILES(X86)").unwrap_or_else(|_| r"C:\Program Files (x86)".into());
    let local_appdata = std::env::var("LOCALAPPDATA")
        .unwrap_or_else(|_| r"C:\Users\Default\AppData\Local".into());

    let mut found: HashMap<String, String> = HashMap::new();

    let candidates: [(&str, Vec<String>); 7] = [
        (
            "Brave",
            vec![
                format!(r"{}\BraveSoftware\Brave-Browser\Application\brave.exe", prog_files),
                format!(r"{}\BraveSoftware\Brave-Browser\Application\brave.exe", prog_files_x86),
                format!(r"{}\BraveSoftware\Brave-Browser\Application\brave.exe", local_appdata),
            ],
        ),
        (
            "Opera GX",
            vec![
                format!(r"{}\Programs\Opera GX\launcher.exe", local_appdata),
                format!(r"{}\Programs\Opera GX\opera.exe", local_appdata),
            ],
        ),
        (
            "Google Chrome",
            vec![
                format!(r"{}\Google\Chrome\Application\chrome.exe", prog_files),
                format!(r"{}\Google\Chrome\Application\chrome.exe", prog_files_x86),
                format!(r"{}\Google\Chrome\Application\chrome.exe", local_appdata),
            ],
        ),
        (
            "Firefox",
            vec![
                format!(r"{}\Mozilla Firefox\firefox.exe", prog_files),
                format!(r"{}\Mozilla Firefox\firefox.exe", local_appdata),
            ],
        ),
        (
            "Opera",
            vec![
                format!(r"{}\Programs\Opera\launcher.exe", local_appdata),
                format!(r"{}\Opera\launcher.exe", prog_files),
            ],
        ),
        (
            "Vivaldi",
            vec![
                format!(r"{}\Vivaldi\Application\vivaldi.exe", local_appdata),
                format!(r"{}\Vivaldi\Application\vivaldi.exe", prog_files),
            ],
        ),
        (
            "Microsoft Edge",
            vec![
                format!(r"{}\Microsoft\Edge\Application\msedge.exe", prog_files_x86),
                format!(r"{}\Microsoft\Edge\Application\msedge.exe", prog_files),
            ],
        ),
    ];

    for (name, paths) in candidates {
        for p in paths {
            if Path::new(&p).exists() {
                found.insert(name.to_string(), p);
                break;
            }
        }
    }

    scan_registry_browsers(&mut found);

    let priority = [
        "Brave",
        "Opera GX",
        "Google Chrome",
        "Firefox",
        "Opera",
        "Vivaldi",
        "Microsoft Edge",
    ];
    let mut sorted = Map::new();
    for p in priority {
        if let Some(val) = found.remove(p) {
            sorted.insert(p.to_string(), json!(val));
        }
    }
    let mut remaining: Vec<(String, String)> = found.into_iter().collect();
    remaining.sort_by(|a, b| a.0.cmp(&b.0));
    for (k, v) in remaining {
        sorted.insert(k, json!(v));
    }
    sorted
}

#[cfg(target_os = "windows")]
fn scan_registry_browsers(found: &mut HashMap<String, String>) {
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
        fn RegEnumKeyExW(
            h_key: *mut core::ffi::c_void,
            dw_index: u32,
            lp_name: *mut u16,
            lpcch_name: *mut u32,
            lp_reserved: *mut u32,
            lp_class: *mut u16,
            lpcch_class: *mut u32,
            lpft_last_write_time: *mut core::ffi::c_void,
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

    let roots = [
        (HKEY_CURRENT_USER, r"SOFTWARE\Clients\StartMenuInternet"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\Clients\StartMenuInternet"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"),
    ];

    for (hive, reg_path) in roots {
        let mut hkey: *mut core::ffi::c_void = std::ptr::null_mut();
        let wide_root = to_wide(reg_path);
        if unsafe { RegOpenKeyExW(hive, wide_root.as_ptr(), 0, KEY_READ, &mut hkey) } != 0
            || hkey.is_null()
        {
            continue;
        }

        let mut idx = 0u32;
        loop {
            let mut name_buf = [0u16; 256];
            let mut name_len = name_buf.len() as u32;
            let erc = unsafe {
                RegEnumKeyExW(
                    hkey,
                    idx,
                    name_buf.as_mut_ptr(),
                    &mut name_len,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                )
            };
            if erc != 0 {
                break;
            }
            idx += 1;
            let subkey = String::from_utf16_lossy(&name_buf[..name_len as usize]);
            if subkey.to_lowercase().contains("iexplore") {
                continue;
            }
            let norm_name = normalize_browser_name(&subkey);
            if found.contains_key(&norm_name) {
                continue;
            }

            let cmd_sub = format!(r"{}\{}\shell\open\command", reg_path, subkey);
            let mut cmd_hkey: *mut core::ffi::c_void = std::ptr::null_mut();
            let wide_cmd = to_wide(&cmd_sub);
            if unsafe { RegOpenKeyExW(hive, wide_cmd.as_ptr(), 0, KEY_READ, &mut cmd_hkey) } == 0
                && !cmd_hkey.is_null()
            {
                let mut reg_type = 0u32;
                let mut val_buf = [0u16; 1024];
                let mut cb_data = (val_buf.len() * 2) as u32;
                let empty_w = [0u16];
                let qrc = unsafe {
                    RegQueryValueExW(
                        cmd_hkey,
                        empty_w.as_ptr(),
                        std::ptr::null_mut(),
                        &mut reg_type,
                        val_buf.as_mut_ptr() as *mut u8,
                        &mut cb_data,
                    )
                };
                unsafe { RegCloseKey(cmd_hkey) };
                if qrc == 0 && (reg_type == REG_SZ || reg_type == REG_EXPAND_SZ) {
                    let words = (cb_data as usize / 2).min(val_buf.len());
                    let end = val_buf[..words].iter().position(|&c| c == 0).unwrap_or(words);
                    let raw = String::from_utf16_lossy(&val_buf[..end]).trim().to_string();
                    let cleaned = raw.trim_matches('"').to_string();
                    if Path::new(&cleaned).exists() {
                        found.insert(norm_name, cleaned);
                    }
                }
            }
        }
        unsafe { RegCloseKey(hkey) };
    }
}

#[cfg(not(target_os = "windows"))]
fn scan_registry_browsers(_found: &mut HashMap<String, String>) {}

pub fn sha256_hex(data: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];

    let bit_len = (data.len() as u64).wrapping_mul(8);
    let mut padded = data.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[i * 4],
                chunk[i * 4 + 1],
                chunk[i * 4 + 2],
                chunk[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }

        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }

    let mut hex = String::with_capacity(64);
    for word in h {
        hex.push_str(&format!("{:08x}", word));
    }
    hex
}

pub struct GoFileResolver;

impl GoFileResolver {
    pub async fn get_token(custom_token: Option<&str>) -> String {
        if let Some(tok) = custom_token {
            let trimmed = tok.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);

        let cache = GOFILE_TOKEN_CACHE.get_or_init(|| Mutex::new((String::new(), 0)));
        if let Ok(guard) = cache.lock() {
            if !guard.0.is_empty() && now.saturating_sub(guard.1) < 86_400 {
                return guard.0.clone();
            }
        }

        if let Ok(client) = reqwest::Client::builder().timeout(Duration::from_secs(8)).build() {
            if let Ok(resp) = client
                .post("https://api.gofile.io/accounts")
                .header("User-Agent", CHROME_UA)
                .header("Accept-Language", "en-US")
                .send()
                .await
            {
                if resp.status().is_success() {
                    if let Ok(json_val) = resp.json::<Value>().await {
                        if json_val.get("status").and_then(|v| v.as_str()) == Some("ok") {
                            if let Some(tok) = json_val
                                .get("data")
                                .and_then(|d| d.get("token"))
                                .and_then(|t| t.as_str())
                            {
                                let token = tok.to_string();
                                if let Ok(mut guard) = cache.lock() {
                                    guard.0 = token.clone();
                                    guard.1 = now;
                                }
                                return token;
                            }
                        }
                    }
                }
            }
        }

        cache
            .lock()
            .map(|g| g.0.clone())
            .unwrap_or_default()
    }

    pub async fn resolve(
        folder_id: &str,
        custom_token: Option<&str>,
    ) -> (Option<String>, Option<String>, String) {
        let token = Self::get_token(custom_token).await;
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let time_window = now / 14_400;
        let raw = format!("{}::en-US::{}::{}::{}", CHROME_UA, token, time_window, GOFILE_SALT);
        let wt = sha256_hex(raw.as_bytes());

        let url = format!(
            "https://api.gofile.io/contents/{}?page=1&pageSize=100&sortField=name&sortDirection=1",
            folder_id
        );
        if let Ok(client) = reqwest::Client::builder().timeout(Duration::from_secs(10)).build() {
            let mut req = client
                .get(&url)
                .header("User-Agent", CHROME_UA)
                .header("Accept-Language", "en-US,en;q=0.9")
                .header("X-Website-Token", wt)
                .header("X-BL", "en-US");
            if !token.is_empty() {
                req = req.header("Authorization", format!("Bearer {}", token));
            }

            if let Ok(resp) = req.send().await {
                if resp.status().is_success() {
                    if let Ok(data) = resp.json::<Value>().await {
                        if data.get("status").and_then(|v| v.as_str()) == Some("ok") {
                            if let Some(children) = data
                                .get("data")
                                .and_then(|d| d.get("children"))
                                .and_then(|c| c.as_object())
                            {
                                for (_cid, cinfo) in children {
                                    let link = cinfo
                                        .get("link")
                                        .and_then(|v| v.as_str())
                                        .map(str::to_string);
                                    let name = cinfo
                                        .get("name")
                                        .and_then(|v| v.as_str())
                                        .map(str::to_string);
                                    if link.is_some() {
                                        return (link, name, token);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        (None, None, token)
    }
}

pub async fn resolve_url<F>(
    raw_url: &str,
    custom_gofile_token: Option<&str>,
    _game_name: Option<&str>,
    mut log_cb: F,
) -> Result<ResolvedLink, String>
where
    F: FnMut(&str),
{
    let url = raw_url.trim();
    if url.is_empty() {
        return Err("Empty URL provided".to_string());
    }

    // 0a. Dropbox direct stream resolver
    if url.contains("dropbox.com/") {
        log_cb(&format!("Resolving Dropbox URL: {}", url));
        let direct_url = resolve_dropbox_url(url);
        let file_name = url_archive_basename(&direct_url);
        log_cb(&format!("Dropbox link resolved to direct stream: {}", direct_url));
        return Ok(ResolvedLink {
            direct_url,
            filename: Some(file_name.unwrap_or_else(|| "dropbox_archive.zip".to_string())),
            cookies: HashMap::new(),
        });
    }

    // 0b. Archive.org direct download & cluster bypass
    if url.contains("archive.org/download/") {
        log_cb(&format!("Resolving Archive.org URL: {}", url));
        let mut direct_url = url.to_string();
        let file_name = url_basename_decoded(url);
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .timeout(Duration::from_secs(5))
            .build()
            .map_err(|e| e.to_string())?;

        let mut needs_fallback = false;
        match client.head(url).send().await {
            Ok(resp) => {
                if resp.status().as_u16() >= 400 {
                    needs_fallback = true;
                } else {
                    direct_url = resp.url().to_string();
                }
            }
            Err(_) => needs_fallback = true,
        }

        if needs_fallback {
            if let Some(after) = url.split("archive.org/download/").nth(1) {
                if let Some((item_id, file_path)) = after.split_once('/') {
                    let meta_url = format!("https://archive.org/metadata/{}", item_id);
                    if let Ok(resp) = reqwest::Client::builder()
                        .timeout(Duration::from_secs(6))
                        .build()
                        .map_err(|e| e.to_string())?
                        .get(&meta_url)
                        .send()
                        .await
                    {
                        if resp.status().is_success() {
                            if let Ok(mdata) = resp.json::<Value>().await {
                                let server = mdata
                                    .get("server")
                                    .or_else(|| mdata.get("d1"))
                                    .or_else(|| mdata.get("d2"))
                                    .and_then(|v| v.as_str());
                                let dir_path = mdata.get("dir").and_then(|v| v.as_str());
                                if let (Some(srv), Some(dp)) = (server, dir_path) {
                                    direct_url = format!("https://{}{}/{}", srv, dp, file_path);
                                    log_cb(&format!(
                                        "Archive.org CDN bypass: rerouted to primary storage cluster: {}",
                                        direct_url
                                    ));
                                }
                            }
                        }
                    }
                }
            }
        }

        return Ok(ResolvedLink {
            direct_url,
            filename: file_name,
            cookies: HashMap::new(),
        });
    }

    // 1. PixelDrain resolver
    if url.contains("pixeldrain.com/u/") || url.contains("pixeldrain.com/api/file/") {
        let after_u = url.split("/u/").last().unwrap_or(url);
        let after_api = after_u.split("/api/file/").last().unwrap_or(after_u);
        let file_id = after_api
            .split('?')
            .next()
            .unwrap_or("")
            .split('/')
            .next()
            .unwrap_or("");
        let direct_url = format!("https://pixeldrain.com/api/file/{}?download", file_id);
        let mut file_name: Option<String> = None;

        if let Ok(client) = reqwest::Client::builder().timeout(Duration::from_secs(5)).build() {
            if let Ok(resp) = client
                .get(format!("https://pixeldrain.com/api/file/{}/info", file_id))
                .send()
                .await
            {
                if resp.status().is_success() {
                    if let Ok(info) = resp.json::<Value>().await {
                        file_name = info
                            .get("name")
                            .and_then(|v| v.as_str())
                            .filter(|s| !s.is_empty())
                            .map(str::to_string);
                    }
                }
            }
        }
        let resolved_name = file_name.unwrap_or_else(|| format!("pixeldrain_{}.zip", file_id));
        log_cb(&format!(
            "PixelDrain link resolved to direct stream: {} (name: {})",
            direct_url, resolved_name
        ));
        return Ok(ResolvedLink {
            direct_url,
            filename: Some(resolved_name),
            cookies: HashMap::new(),
        });
    }

    // 2. FileDitch resolver
    if url.contains("fileditch.com") || url.contains("fileditchfiles") {
        log_cb(&format!("Resolving FileDitch link: {}", url));
        if let Some(arch) = url_archive_basename(url) {
            log_cb(&format!("FileDitch direct archive detected: {}", arch));
            return Ok(ResolvedLink {
                direct_url: url.to_string(),
                filename: Some(arch),
                cookies: HashMap::new(),
            });
        }

        if let Ok(client) = reqwest::Client::builder()
            .user_agent(CHROME_UA)
            .timeout(Duration::from_secs(10))
            .build()
        {
            if let Ok(resp) = client.get(url).send().await {
                if resp.status().is_success() {
                    if let Ok(html) = resp.text().await {
                        if let Some(href) = extract_fileditch_download_href(&html) {
                            let direct = join_url(url, &href);
                            let fn_opt = url_basename_decoded(&direct);
                            log_cb(&format!("FileDitch landing page resolved to direct stream: {}", direct));
                            return Ok(ResolvedLink {
                                direct_url: direct,
                                filename: fn_opt,
                                cookies: HashMap::new(),
                            });
                        }
                    }
                }
            }
        }

        let fallback_name = url_basename_decoded(url).filter(|n| n.contains('.'));
        return Ok(ResolvedLink {
            direct_url: url.to_string(),
            filename: fallback_name,
            cookies: HashMap::new(),
        });
    }

    // 3. BuzzHeavier & bzzhr.to resolver
    if url.contains("buzzheavier.com/") || url.contains("bzzhr.to/") {
        log_cb(&format!("Resolving BuzzHeavier / bzzhr.to link: {}", url));
        let tail = url
            .split("buzzheavier.com/")
            .last()
            .unwrap_or(url)
            .split("bzzhr.to/")
            .last()
            .unwrap_or(url);
        let file_id = tail
            .split('?')
            .next()
            .unwrap_or("")
            .trim_matches('/')
            .replace("f/", "");

        let page_client = reqwest::Client::builder()
            .user_agent(CHROME_UA)
            .timeout(Duration::from_secs(12))
            .build()
            .map_err(|e| e.to_string())?;
        let no_redir_client = reqwest::Client::builder()
            .user_agent(CHROME_UA)
            .redirect(Policy::none())
            .timeout(Duration::from_secs(12))
            .build()
            .map_err(|e| e.to_string())?;

        for base_domain in ["https://buzzheavier.com", "https://bzzhr.to"] {
            let target_url = format!("{}/{}", base_domain, file_id);
            match page_client
                .get(&target_url)
                .header("Referer", "https://steamrip.com/")
                .header(
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                )
                .header("Accept-Language", "en-US,en;q=0.9")
                .send()
                .await
            {
                Ok(resp) => {
                    let mut cookies = collect_set_cookies(resp.headers());
                    let status_code = resp.status().as_u16();
                    let cf_mitigated = resp
                        .headers()
                        .get("cf-mitigated")
                        .and_then(|v| v.to_str().ok())
                        .unwrap_or("")
                        .to_string();
                    if resp.status().is_success() {
                        if let Ok(html) = resp.text().await {
                            let (file_name, hx_get) = extract_buzzheavier_meta(&html);
                            if let Some(hx) = hx_get {
                                let trigger_url = if hx.starts_with('/') {
                                    format!("{}{}", base_domain, hx)
                                } else {
                                    hx
                                };
                                let mut dl_req = no_redir_client
                                    .get(&trigger_url)
                                    .header("HX-Request", "true")
                                    .header("HX-Current-URL", &target_url)
                                    .header("Referer", &target_url);
                                if !cookies.is_empty() {
                                    dl_req = dl_req.header("Cookie", format_cookie_header(&cookies));
                                }
                                if let Ok(r_dl) = dl_req.send().await {
                                    for (ck, cv) in collect_set_cookies(r_dl.headers()) {
                                        cookies.insert(ck, cv);
                                    }
                                    let redir = r_dl
                                        .headers()
                                        .get("hx-redirect")
                                        .or_else(|| r_dl.headers().get("location"))
                                        .and_then(|v| v.to_str().ok())
                                        .map(str::to_string);
                                    if let Some(direct_url) = redir {
                                        let preview = &direct_url[..direct_url.len().min(80)];
                                        let resolved_name = file_name
                                            .unwrap_or_else(|| format!("buzzheavier_{}.zip", file_id));
                                        log_cb(&format!(
                                            "BuzzHeavier direct stream resolved: {}... Filename: '{}'",
                                            preview, resolved_name
                                        ));
                                        return Ok(ResolvedLink {
                                            direct_url,
                                            filename: Some(resolved_name),
                                            cookies,
                                        });
                                    }
                                }
                            }
                        }
                    } else if cf_mitigated.eq_ignore_ascii_case("challenge") {
                        log_cb(&format!(
                            "BuzzHeavier ({}) returned HTTP {} (Cloudflare challenge)",
                            base_domain, status_code
                        ));
                    } else {
                        log_cb(&format!(
                            "BuzzHeavier ({}) returned HTTP {}",
                            base_domain, status_code
                        ));
                    }
                }
                Err(err) => {
                    log_cb(&format!(
                        "BuzzHeavier ({}) request notice: {}",
                        base_domain, err
                    ));
                }
            }
        }

        let fallback_url = if !file_id.is_empty() && !file_id.ends_with("/download") {
            format!("https://buzzheavier.com/{}/download", file_id)
        } else {
            url.to_string()
        };
        return Ok(ResolvedLink {
            direct_url: fallback_url,
            filename: Some(format!("buzzheavier_{}.zip", file_id)),
            cookies: HashMap::new(),
        });
    }

    // 3b. MegaDB resolver
    if url.contains("megadb.net/") {
        log_cb(&format!("Resolving MegaDB link: {}", url));
        let file_id = url
            .split("megadb.net/")
            .last()
            .unwrap_or("")
            .split('?')
            .next()
            .unwrap_or("")
            .trim_matches('/');
        let target_url = format!("https://megadb.net/{}", file_id);

        if let Ok(client) = reqwest::Client::builder()
            .user_agent(CHROME_UA)
            .redirect(Policy::none())
            .timeout(Duration::from_secs(15))
            .build()
        {
            if let Ok(resp) = client
                .get(&target_url)
                .header("Referer", "https://steamrip.com/")
                .send()
                .await
            {
                let mut cookies = collect_set_cookies(resp.headers());
                if resp.status().is_success() {
                    if let Ok(html) = resp.text().await {
                        let file_name = extract_between_ci(&html, "<title>", "</title>")
                            .and_then(|t| t.split(" - MegaDB").next().map(|s| s.trim().to_string()))
                            .filter(|s| !s.is_empty());

                        if let Some(final_dl_url) = extract_js_single_quoted(&html, "finalDownloadUrl") {
                            let wait_secs = extract_js_var_int(&html, "seconds").unwrap_or(10);
                            log_cb(&format!(
                                "MegaDB countdown timer: waiting {}s for direct stream token...",
                                wait_secs
                            ));
                            let wait_ms = wait_secs.saturating_mul(1000).saturating_add(500);
                            let _ = tauri::async_runtime::spawn_blocking(move || {
                                std::thread::sleep(Duration::from_millis(wait_ms));
                            })
                            .await;

                            let mut dl_req = client
                                .get(&final_dl_url)
                                .header("Referer", &target_url);
                            if !cookies.is_empty() {
                                dl_req = dl_req.header("Cookie", format_cookie_header(&cookies));
                            }
                            if let Ok(r_dl) = dl_req.send().await {
                                for (ck, cv) in collect_set_cookies(r_dl.headers()) {
                                    cookies.insert(ck, cv);
                                }
                                let mut direct_opt = r_dl
                                    .headers()
                                    .get("location")
                                    .and_then(|v| v.to_str().ok())
                                    .map(str::to_string);
                                if direct_opt.is_none() {
                                    if let Ok(dl_body) = r_dl.text().await {
                                        direct_opt = extract_meta_refresh_url(&dl_body);
                                    }
                                }
                                if let Some(direct_url) = direct_opt {
                                    let resolved_name = file_name
                                        .unwrap_or_else(|| format!("megadb_{}.rar", file_id));
                                    return Ok(ResolvedLink {
                                        direct_url,
                                        filename: Some(resolved_name),
                                        cookies,
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }

        return Ok(ResolvedLink {
            direct_url: target_url,
            filename: Some(format!("megadb_{}.rar", file_id)),
            cookies: HashMap::new(),
        });
    }

    // 4. GoFile resolver
    if url.contains("gofile.io/d/") {
        log_cb(&format!("Resolving GoFile URL: {}...", url));
        let folder_id = url
            .split("/d/")
            .nth(1)
            .unwrap_or("")
            .split('?')
            .next()
            .unwrap_or("")
            .split('/')
            .next()
            .unwrap_or("");
        let (direct_link, name, token) = GoFileResolver::resolve(folder_id, custom_gofile_token).await;
        if let Some(link) = direct_link {
            log_cb(&format!("GoFile API resolved direct stream: {}", link));
            let mut cookies = HashMap::new();
            if !token.is_empty() {
                cookies.insert("accountToken".to_string(), token);
            }
            return Ok(ResolvedLink {
                direct_url: link,
                filename: name,
                cookies,
            });
        }
    }

    // 5. Direct URL / HEAD fallback
    if let Ok(client) = reqwest::Client::builder()
        .user_agent(CHROME_UA)
        .timeout(Duration::from_secs(6))
        .build()
    {
        if let Ok(head_resp) = client.head(url).send().await {
            let final_url = head_resp.url().to_string();
            let cd = head_resp
                .headers()
                .get("content-disposition")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("");
            let fn_opt = extract_content_disposition_filename(cd);
            return Ok(ResolvedLink {
                direct_url: final_url,
                filename: fn_opt,
                cookies: HashMap::new(),
            });
        }
    }

    Ok(ResolvedLink {
        direct_url: url.to_string(),
        filename: None,
        cookies: HashMap::new(),
    })
}

pub fn resolve_dropbox_url(url: &str) -> String {
    if url.contains("dl=0") {
        url.replace("dl=0", "dl=1")
    } else if url.contains("dl=1") {
        url.to_string()
    } else if url.contains('?') {
        format!("{}&dl=1", url)
    } else {
        format!("{}?dl=1", url)
    }
}

pub fn extract_content_disposition_filename(header: &str) -> Option<String> {
    let lower = header.to_ascii_lowercase();
    for marker in ["filename*=utf-8''", "filename*=", "filename="] {
        if let Some(idx) = lower.find(marker) {
            let rest = header[idx + marker.len()..].trim();
            let raw = if let Some(stripped) = rest.strip_prefix('"') {
                stripped.split('"').next().unwrap_or("")
            } else if let Some(stripped) = rest.strip_prefix('\'') {
                stripped.split('\'').next().unwrap_or("")
            } else {
                rest.split(';').next().unwrap_or("")
            };
            let cleaned = percent_decode(raw.trim());
            if !cleaned.is_empty() {
                return Some(cleaned);
            }
        }
    }
    None
}

pub fn extract_buzzheavier_meta(html: &str) -> (Option<String>, Option<String>) {
    let mut file_name: Option<String> = None;

    // Look for <p ... class="...file-name...">NAME</p>
    let lower = html.to_ascii_lowercase();
    let mut pos = 0usize;
    while let Some(rel) = lower[pos..].find("<p") {
        let tag_start = pos + rel;
        if let Some(gt_rel) = lower[tag_start..].find('>') {
            let tag_end = tag_start + gt_rel;
            let tag = &lower[tag_start..tag_end];
            if tag.contains("file-name") {
                if let Some(close_rel) = lower[tag_end + 1..].find("</p>") {
                    let inner = html[tag_end + 1..tag_end + 1 + close_rel].trim();
                    if !inner.is_empty() {
                        file_name = Some(inner.to_string());
                        break;
                    }
                }
            }
            pos = tag_end + 1;
        } else {
            break;
        }
    }

    if file_name.is_none() {
        pos = 0;
        while let Some(rel) = lower[pos..].find("<meta") {
            let tag_start = pos + rel;
            if let Some(gt_rel) = lower[tag_start..].find('>') {
                let tag_end = tag_start + gt_rel;
                let tag_orig = &html[tag_start..tag_end];
                if get_html_attr(tag_orig, "name").as_deref() == Some("title") {
                    if let Some(c) = get_html_attr(tag_orig, "content") {
                        if !c.trim().is_empty() {
                            file_name = Some(c.trim().to_string());
                            break;
                        }
                    }
                }
                pos = tag_end + 1;
            } else {
                break;
            }
        }
    }

    // Look for <a ... class="...download-btn..." ... hx-get="...">
    let mut hx_get: Option<String> = None;
    pos = 0;
    while let Some(rel) = lower[pos..].find("<a") {
        let tag_start = pos + rel;
        if let Some(gt_rel) = lower[tag_start..].find('>') {
            let tag_end = tag_start + gt_rel;
            let tag_orig = &html[tag_start..tag_end];
            let tag_low = &lower[tag_start..tag_end];
            if tag_low.contains("download-btn") || tag_low.contains("hx-get") {
                if let Some(hx) = get_html_attr(tag_orig, "hx-get") {
                    hx_get = Some(hx);
                    break;
                }
            }
            pos = tag_end + 1;
        } else {
            break;
        }
    }

    (file_name, hx_get)
}

fn extract_fileditch_download_href(html: &str) -> Option<String> {
    let lower = html.to_ascii_lowercase();
    let mut pos = 0usize;
    while let Some(rel) = lower[pos..].find("<a") {
        let tag_start = pos + rel;
        let Some(gt_rel) = lower[tag_start..].find('>') else {
            break;
        };
        let tag_end = tag_start + gt_rel;
        let tag_orig = &html[tag_start..tag_end];
        if let Some(href) = get_html_attr(tag_orig, "href") {
            let h_low = href.to_ascii_lowercase();
            if h_low.contains("fileditchfiles")
                || h_low.contains("/download/")
                || h_low.ends_with(".rar")
                || h_low.ends_with(".zip")
                || h_low.ends_with(".7z")
            {
                return Some(href);
            }
        }
        pos = tag_end + 1;
    }
    None
}

fn get_html_attr(tag: &str, attr_name: &str) -> Option<String> {
    let lower = tag.to_ascii_lowercase();
    let needle = format!("{}=", attr_name.to_ascii_lowercase());
    let mut search = 0usize;
    while let Some(rel) = lower[search..].find(&needle) {
        let start = search + rel;
        let prev_ok = start == 0 || lower.as_bytes()[start - 1].is_ascii_whitespace();
        if prev_ok {
            let rest = tag[start + needle.len()..].trim_start();
            if let Some(q) = rest.chars().next() {
                if q == '"' || q == '\'' {
                    let inner = &rest[1..];
                    if let Some(end) = inner.find(q) {
                        return Some(inner[..end].to_string());
                    }
                } else {
                    let val: String = rest.chars().take_while(|c| !c.is_ascii_whitespace()).collect();
                    return Some(val);
                }
            }
        }
        search = start + needle.len();
    }
    None
}

fn collect_set_cookies(headers: &reqwest::header::HeaderMap) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for val in headers.get_all(SET_COOKIE) {
        if let Ok(s) = val.to_str() {
            let pair = s.split(';').next().unwrap_or("").trim();
            if let Some((k, v)) = pair.split_once('=') {
                map.insert(k.trim().to_string(), v.trim().to_string());
            }
        }
    }
    map
}

pub fn format_cookie_header(cookies: &HashMap<String, String>) -> String {
    cookies
        .iter()
        .map(|(k, v)| format!("{}={}", k, v))
        .collect::<Vec<String>>()
        .join("; ")
}

fn url_basename_decoded(url: &str) -> Option<String> {
    let no_query = url.split('?').next().unwrap_or(url);
    let base = no_query.rsplit('/').next().unwrap_or("").trim();
    if base.is_empty() {
        None
    } else {
        Some(percent_decode(base))
    }
}

fn url_archive_basename(url: &str) -> Option<String> {
    let base = url_basename_decoded(url)?;
    let lower = base.to_ascii_lowercase();
    if [".rar", ".zip", ".7z", ".bin", ".iso", ".tar", ".gz", ".exe"]
        .iter()
        .any(|ext| lower.ends_with(ext))
    {
        Some(base)
    } else {
        None
    }
}

fn join_url(base: &str, href: &str) -> String {
    if href.starts_with("http://") || href.starts_with("https://") {
        return href.to_string();
    }
    if let Some(scheme_idx) = base.find("://") {
        let host_start = scheme_idx + 3;
        let host_end = base[host_start..]
            .find('/')
            .map(|i| host_start + i)
            .unwrap_or(base.len());
        let origin = &base[..host_end];
        if href.starts_with('/') {
            return format!("{}{}", origin, href);
        }
        return format!("{}/{}", origin, href.trim_start_matches('/'));
    }
    href.to_string()
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (
                (bytes[i + 1] as char).to_digit(16),
                (bytes[i + 2] as char).to_digit(16),
            ) {
                out.push(((h << 4) | l) as u8);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).to_string()
}

fn extract_between_ci(text: &str, start_tag: &str, end_tag: &str) -> Option<String> {
    let lower = text.to_ascii_lowercase();
    let s_idx = lower.find(&start_tag.to_ascii_lowercase())? + start_tag.len();
    let e_rel = lower[s_idx..].find(&end_tag.to_ascii_lowercase())?;
    Some(text[s_idx..s_idx + e_rel].to_string())
}

fn extract_js_single_quoted(text: &str, var_name: &str) -> Option<String> {
    let idx = text.find(var_name)?;
    let rest = &text[idx + var_name.len()..];
    let q_idx = rest.find('\'')? + 1;
    let end_rel = rest[q_idx..].find('\'')?;
    Some(rest[q_idx..q_idx + end_rel].to_string())
}

fn extract_js_var_int(text: &str, var_name: &str) -> Option<u64> {
    let needle = format!("var {}", var_name);
    let idx = text.find(&needle)?;
    let rest = &text[idx + needle.len()..];
    let eq = rest.find('=')? + 1;
    let digits: String = rest[eq..]
        .trim_start()
        .chars()
        .take_while(|c| c.is_ascii_digit())
        .collect();
    digits.parse::<u64>().ok()
}

fn extract_meta_refresh_url(html: &str) -> Option<String> {
    let lower = html.to_ascii_lowercase();
    if !lower.contains("http-equiv=\"refresh\"") && !lower.contains("http-equiv='refresh'") {
        return None;
    }
    let idx = lower.find("url='")?;
    let start = idx + 5;
    let end_rel = html[start..].find('\'')?;
    Some(html[start..start + end_rel].to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sha256_nist_vector() {
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn test_dropbox_and_content_disposition_helpers() {
        assert_eq!(
            resolve_dropbox_url("https://www.dropbox.com/scl/fi/abc/Game.zip?rlkey=123&dl=0"),
            "https://www.dropbox.com/scl/fi/abc/Game.zip?rlkey=123&dl=1"
        );
        assert_eq!(
            resolve_dropbox_url("https://www.dropbox.com/s/xyz/Mod.rar"),
            "https://www.dropbox.com/s/xyz/Mod.rar?dl=1"
        );
        assert_eq!(
            extract_content_disposition_filename("attachment; filename=\"Megabonk-SteamRIP.rar\""),
            Some("Megabonk-SteamRIP.rar".to_string())
        );
        assert_eq!(
            extract_content_disposition_filename("inline; filename*=UTF-8''Cool%20Game.zip"),
            Some("Cool Game.zip".to_string())
        );
    }

    #[test]
    fn test_buzzheavier_html_parsing() {
        let html = r#"
            <html>
              <head><meta name="title" content="Fallback.zip"></head>
              <body>
                <p class="text-lg file-name">Megabonk-SteamRIP.com.rar</p>
                <a class="btn download-btn" hx-get="/jacb00xgmt7c/download">Download</a>
              </body>
            </html>
        "#;
        let (fname, hx) = extract_buzzheavier_meta(html);
        assert_eq!(fname.as_deref(), Some("Megabonk-SteamRIP.com.rar"));
        assert_eq!(hx.as_deref(), Some("/jacb00xgmt7c/download"));
    }
}
