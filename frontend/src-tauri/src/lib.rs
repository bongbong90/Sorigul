mod shutdown;
mod sidecar;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};

use shutdown::{RealShutdownExecutor, ShutdownGate};
use sidecar::{HttpHealthProbe, SidecarManager, SidecarStatus, SpawnSpec};

const BACKEND_PORT: u16 = 8000;

#[cfg(target_os = "windows")]
const PATH_LIST_SEPARATOR: &str = ";";
#[cfg(not(target_os = "windows"))]
const PATH_LIST_SEPARATOR: &str = ":";

struct AppState {
    sidecar: Arc<SidecarManager>,
    shutdown_gate: ShutdownGate,
    close_behavior: Mutex<String>,
}

#[tauri::command]
fn set_close_behavior(state: State<AppState>, behavior: String) {
    if behavior == "tray" || behavior == "exit" {
        *state.close_behavior.lock().unwrap() = behavior;
    }
}

/// Only meaningful once the backend has reported `ready_to_shutdown`.
/// Idempotent: a duplicate/stale call after the first is a silent no-op.
#[tauri::command]
fn native_shutdown(state: State<AppState>) -> Result<(), String> {
    state.shutdown_gate.trigger(&RealShutdownExecutor)
}

/// Re-arms the shutdown gate once the backend state has left the
/// countdown/ready phases (cancelled, or a later fresh job finished).
#[tauri::command]
fn reset_shutdown_gate(state: State<AppState>) {
    state.shutdown_gate.reset();
}

/// Opens the backend-validated folder (or reveals a specific item within it)
/// in Windows Explorer. The frontend passes only opaque identifiers (scan_id,
/// optional item_id); this command fetches the validated path from the backend
/// and opens it -- the frontend never constructs or passes a raw filesystem
/// path to any native open call.
///
/// Security: `opener:allow-open-path` and `opener:allow-reveal-item-in-dir`
/// are NOT granted to the frontend capability. All filesystem open calls
/// happen inside this Rust command after backend validation.
#[tauri::command]
fn open_folder_by_intent(scan_id: String, item_id: Option<String>) -> Result<(), String> {
    let url = format!(
        "http://127.0.0.1:{BACKEND_PORT}/api/folders/{scan_id}/open-intent{}",
        item_id
            .as_deref()
            .map(|id| format!("?item_id={id}"))
            .unwrap_or_default()
    );

    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(5))
        .build();

    let response = agent
        .post(&url)
        .call()
        .map_err(|err| format!("BACKEND_UNREACHABLE: {err}"))?;

    if response.status() != 200 {
        return Err(format!("BACKEND_ERROR: HTTP {}", response.status()));
    }

    let body = response
        .into_string()
        .map_err(|err| format!("RESPONSE_READ_ERROR: {err}"))?;

    // Parse the validated folder and optional item_filename from the backend JSON.
    // We do minimal parsing here -- we only extract the two fields we need,
    // never forwarding any other data to the OS command.
    let folder = extract_json_string(&body, "folder")
        .ok_or_else(|| "INTENT_PARSE_ERROR: missing folder".to_string())?;
    let item_filename = extract_json_string(&body, "item_filename");

    open_in_explorer(&folder, item_filename.as_deref())
        .map_err(|err| format!("EXPLORER_OPEN_FAILED: {err}"))
}

/// Opens a folder in Windows Explorer, optionally revealing a specific file.
/// Uses `std::process::Command` with a fixed executable and a sanitised
/// argument list -- no shell string concatenation.
fn open_in_explorer(folder: &str, item_filename: Option<&str>) -> std::io::Result<()> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;

        let target = match item_filename {
            Some(name) => {
                let mut p = std::path::PathBuf::from(folder);
                p.push(name);
                p.to_string_lossy().into_owned()
            }
            None => folder.to_owned(),
        };

        std::process::Command::new("explorer.exe")
            .arg(&target)
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()?;
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        // Non-Windows fallback: open the folder with xdg-open / open.
        let _ = item_filename; // item reveal not supported on non-Windows in this impl
        std::process::Command::new("xdg-open").arg(folder).spawn()?;
        Ok(())
    }
}

/// Minimal JSON string extractor -- avoids pulling in a full JSON crate
/// just for two string fields. Handles `null` values (returns `None`).
fn extract_json_string(body: &str, key: &str) -> Option<String> {
    let search = format!("\"{}\":", key);
    let start = body.find(&search)? + search.len();
    let rest = body[start..].trim_start();
    if rest.starts_with("null") {
        return None;
    }
    if !rest.starts_with('"') {
        return None;
    }
    // Walk forward, respecting `\"` escapes.
    let mut result = String::new();
    let mut chars = rest[1..].chars();
    loop {
        match chars.next()? {
            '\\' => {
                match chars.next()? {
                    '"' => result.push('"'),
                    '\\' => result.push('\\'),
                    'n' => result.push('\n'),
                    'r' => result.push('\r'),
                    't' => result.push('\t'),
                    'u' => {
                        // \uXXXX -- decode the four hex digits
                        let hex: String = chars.by_ref().take(4).collect();
                        if let Ok(code) = u32::from_str_radix(&hex, 16) {
                            if let Some(c) = char::from_u32(code) {
                                result.push(c);
                            }
                        }
                    }
                    other => result.push(other),
                }
            }
            '"' => break,
            c => result.push(c),
        }
    }
    Some(result)
}

fn health_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}/api/health")
}

fn repo_root() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

fn dev_python_executable() -> String {
    if let Ok(value) = std::env::var("SORIGUL_BACKEND_PYTHON") {
        return value;
    }
    let venv_python = repo_root().join("venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        venv_python.to_string_lossy().into_owned()
    } else {
        "python".into()
    }
}

/// Development launch: run the backend straight from source through the
/// project's own (or system) Python, exactly like the documented manual
/// `uvicorn` invocation, so dev and packaged runs hit the same product API.
/// The dev child inherits this process's own PATH untouched -- bundled
/// ffmpeg is a packaged-release concept only; dev relies on whatever
/// ffmpeg the developer already has on PATH, same as before this work
/// package.
fn dev_spawn_spec() -> SpawnSpec {
    SpawnSpec {
        program: dev_python_executable(),
        args: vec![
            "-m".into(),
            "uvicorn".into(),
            "src.main:app".into(),
            "--host".into(),
            "127.0.0.1".into(),
            "--port".into(),
            BACKEND_PORT.to_string(),
        ],
        current_dir: Some(repo_root().join("backend")),
        env: vec![],
    }
}

/// Packaged launch: a pre-built standalone backend binary and a bundled
/// ffmpeg, both resolved from the bundle's resource directory
/// (`resource_dir/binaries/`). Every failure mode here is a distinct,
/// explicit error -- this function never falls back to `dev_spawn_spec()`.
/// A release build that can't find its own packaged resources must fail
/// loudly, not silently start hunting for a system Python/venv that might
/// happen to exist on the install machine and mask the real problem.
fn packaged_spawn_spec(app: &AppHandle) -> Result<SpawnSpec, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("RESOURCE_DIR_UNAVAILABLE: {err}"))?;
    packaged_spawn_spec_from_resource_dir(&resource_dir)
}

/// Tauri-independent core of `packaged_spawn_spec`, split out so the
/// missing-backend / missing-ffmpeg / present-and-wired failure and
/// success paths are unit-testable without a running `AppHandle`.
fn packaged_spawn_spec_from_resource_dir(
    resource_dir: &std::path::Path,
) -> Result<SpawnSpec, String> {
    let binaries_dir = resource_dir.join("binaries");

    let exe = binaries_dir.join("sorigul-backend.exe");
    if !exe.is_file() {
        return Err(format!("PACKAGED_BACKEND_MISSING: {}", exe.display()));
    }

    let ffmpeg = binaries_dir.join("ffmpeg.exe");
    if !ffmpeg.is_file() {
        return Err(format!("PACKAGED_FFMPEG_MISSING: {}", ffmpeg.display()));
    }

    // Prepend (never replace) the bundled binaries directory onto PATH for
    // the child only -- the app's own process-wide environment is never
    // touched. This lets the packaged backend resolve `ffmpeg` without
    // requiring one on the installing machine's system PATH.
    let existing_path = std::env::var("PATH").unwrap_or_default();
    let child_path = if existing_path.is_empty() {
        binaries_dir.to_string_lossy().into_owned()
    } else {
        format!(
            "{}{PATH_LIST_SEPARATOR}{existing_path}",
            binaries_dir.display()
        )
    };

    Ok(SpawnSpec {
        program: exe.to_string_lossy().into_owned(),
        args: vec!["--port".into(), BACKEND_PORT.to_string()],
        current_dir: None,
        env: vec![("PATH".into(), child_path)],
    })
}

/// Selects the spawn path for this build. Debug builds always use the dev
/// spawn spec; release builds always use the packaged spawn spec -- with
/// no fallback in either direction. A release build's resource resolution
/// failure surfaces as `SidecarStatus::StartupFailed` (see `start_backend`),
/// never as a silent switch to `dev_spawn_spec()`.
fn spawn_spec_for_current_build(app: &AppHandle) -> Result<SpawnSpec, String> {
    if cfg!(debug_assertions) {
        Ok(dev_spawn_spec())
    } else {
        packaged_spawn_spec(app)
    }
}

/// Dev backend (a plain `uvicorn` process on an already-warm interpreter)
/// starts in well under a second; the existing 20s ceiling is unchanged.
const DEV_STARTUP_TIMEOUT: Duration = Duration::from_secs(20);

/// The packaged PyInstaller one-file backend re-extracts its ~230MB bundle
/// to a temp directory on every launch. Measured cold-start latency in
/// this project's own installer validation was ~15-18s; 20s left too
/// little margin on a slower disk or with antivirus real-time scanning a
/// freshly-placed exe. 60s gives real headroom without changing the happy
/// path at all -- `wait_until_healthy` already returns the moment health
/// succeeds (polled every 400ms, unchanged), so a fast cold start still
/// reports `Connected` in a few seconds; this only raises the ceiling
/// before a slow one is declared `STARTUP_TIMEOUT`.
const PACKAGED_STARTUP_TIMEOUT: Duration = Duration::from_secs(60);

fn startup_timeout_for_current_build() -> Duration {
    if cfg!(debug_assertions) {
        DEV_STARTUP_TIMEOUT
    } else {
        PACKAGED_STARTUP_TIMEOUT
    }
}

fn start_backend(app: AppHandle, sidecar: Arc<SidecarManager>) {
    std::thread::spawn(move || {
        let probe = HttpHealthProbe {
            url: health_url(),
            timeout: Duration::from_millis(800),
        };
        let resolved = match spawn_spec_for_current_build(&app) {
            Ok(spec) => match sidecar.start(&probe, spec) {
                SidecarStatus::Starting => sidecar.wait_until_healthy(
                    &probe,
                    startup_timeout_for_current_build(),
                    Duration::from_millis(400),
                ),
                other => other,
            },
            Err(reason) => SidecarStatus::StartupFailed(reason),
        };
        let _ = app.emit("sorigul://sidecar-status", format!("{resolved:?}"));
    });
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open_item = MenuItem::with_id(app, "open", "앱 열기", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

    let tray = TrayIconBuilder::new()
        .icon(
            app.default_window_icon()
                .cloned()
                .expect("default window icon configured"),
        )
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_main_window(app),
            "quit" => {
                if let Some(state) = app.try_state::<AppState>() {
                    state.sidecar.cleanup();
                }
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    // Explicitly mark the tray visible. On some Windows/Tauri combinations
    // build() registers the icon with the shell but does not call
    // Shell_NotifyIcon(NIM_SETVERSION) + NIF_STATE until set_visible(true)
    // is also called; without it the icon may be registered but hidden.
    let _ = tray.set_visible(true);

    Ok(())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

pub fn run() {
    let sidecar = Arc::new(SidecarManager::new());
    let sidecar_for_exit = sidecar.clone();
    let sidecar_for_setup = sidecar.clone();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            sidecar: sidecar.clone(),
            shutdown_gate: ShutdownGate::new(),
            close_behavior: Mutex::new("tray".into()),
        })
        .invoke_handler(tauri::generate_handler![
            set_close_behavior,
            native_shutdown,
            reset_shutdown_gate,
            open_folder_by_intent,
        ])
        .setup(move |app| {
            build_tray(app)?;
            start_backend(app.handle().clone(), sidecar_for_setup.clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let Some(state) = app.try_state::<AppState>() else {
                    return;
                };
                let behavior = state.close_behavior.lock().unwrap().clone();
                if behavior == "tray" {
                    api.prevent_close();
                    let _ = window.hide();
                }
                // "exit": let the close proceed; RunEvent::ExitRequested
                // below performs the owned-backend cleanup centrally.
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building the Sorigul desktop application");

    app.run(move |_app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            sidecar_for_exit.cleanup();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{extract_json_string, packaged_spawn_spec_from_resource_dir};

    /// A fresh, empty scratch directory under the OS temp dir, cleaned up
    /// when dropped. Avoids pulling in a `tempfile` dependency for three
    /// tests.
    struct ScratchDir(std::path::PathBuf);

    impl ScratchDir {
        fn new(label: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "sorigul-packaged-spawn-spec-test-{label}-{}",
                std::process::id()
            ));
            let _ = std::fs::remove_dir_all(&path);
            std::fs::create_dir_all(&path).expect("create scratch dir");
            Self(path)
        }
    }

    impl Drop for ScratchDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn packaged_spawn_spec_fails_explicitly_when_backend_exe_is_missing() {
        let scratch = ScratchDir::new("missing-backend");

        let result = packaged_spawn_spec_from_resource_dir(&scratch.0);

        let err = result.expect_err("must fail without a backend exe present");
        assert!(
            err.starts_with("PACKAGED_BACKEND_MISSING"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn packaged_spawn_spec_fails_explicitly_when_ffmpeg_is_missing() {
        let scratch = ScratchDir::new("missing-ffmpeg");
        let binaries = scratch.0.join("binaries");
        std::fs::create_dir_all(&binaries).unwrap();
        std::fs::write(binaries.join("sorigul-backend.exe"), b"stub").unwrap();

        let result = packaged_spawn_spec_from_resource_dir(&scratch.0);

        let err = result.expect_err("must fail without ffmpeg present");
        assert!(
            err.starts_with("PACKAGED_FFMPEG_MISSING"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn packaged_spawn_spec_succeeds_and_prepends_binaries_dir_to_child_path_when_both_present() {
        let scratch = ScratchDir::new("both-present");
        let binaries = scratch.0.join("binaries");
        std::fs::create_dir_all(&binaries).unwrap();
        std::fs::write(binaries.join("sorigul-backend.exe"), b"stub").unwrap();
        std::fs::write(binaries.join("ffmpeg.exe"), b"stub").unwrap();

        let spec =
            packaged_spawn_spec_from_resource_dir(&scratch.0).expect("both resources present");

        assert_eq!(
            spec.program,
            binaries.join("sorigul-backend.exe").to_string_lossy()
        );
        assert_eq!(spec.args, vec!["--port".to_string(), "8000".to_string()]);
        assert!(spec.current_dir.is_none());
        assert_eq!(spec.env.len(), 1);
        let (key, value) = &spec.env[0];
        assert_eq!(key, "PATH");
        assert!(
            value.starts_with(&binaries.to_string_lossy().into_owned()),
            "child PATH must be prepended with the bundled binaries dir: {value}"
        );
    }

    fn make_intent(folder: &str, item_filename: Option<&str>) -> String {
        let item_part = match item_filename {
            Some(name) => format!("\"{}\"", name),
            None => "null".to_owned(),
        };
        format!(
            r#"{{"action":"OPEN_FOLDER","folder":"{}","item_filename":{}}}"#,
            folder, item_part
        )
    }

    #[test]
    fn extracts_ascii_folder() {
        let body = make_intent("C:\\\\Users\\\\test\\\\docs", None);
        assert_eq!(
            extract_json_string(&body, "folder"),
            Some("C:\\Users\\test\\docs".to_owned())
        );
    }

    #[test]
    fn extracts_korean_unicode_folder() {
        // Korean path injected directly (no \\uXXXX encoding needed for UTF-8 JSON)
        let body = r#"{"action":"OPEN_FOLDER","folder":"C:\\전사자료\\개념완성_민법","item_filename":null}"#;
        assert_eq!(
            extract_json_string(body, "folder"),
            Some("C:\\전사자료\\개념완성_민법".to_owned())
        );
    }

    #[test]
    fn returns_none_for_null_item_filename() {
        let body = make_intent("C:\\\\docs", None);
        assert_eq!(extract_json_string(&body, "item_filename"), None);
    }

    #[test]
    fn extracts_item_filename() {
        let body = make_intent("C:\\\\docs", Some("result.txt"));
        assert_eq!(
            extract_json_string(&body, "item_filename"),
            Some("result.txt".to_owned())
        );
    }

    #[test]
    fn path_traversal_string_is_extracted_verbatim_not_executed() {
        // The parser just extracts the string; it does not validate path safety.
        // That validation is the backend's responsibility. We confirm the value
        // comes through unchanged so the backend contract is the single source.
        // Use raw JSON directly to avoid double-escaping confusion.
        let body =
            r#"{"action":"OPEN_FOLDER","folder":"..\\..\\Windows\\System32","item_filename":null}"#;
        assert_eq!(
            extract_json_string(body, "folder"),
            Some("..\\..\\Windows\\System32".to_owned())
        );
    }
}
