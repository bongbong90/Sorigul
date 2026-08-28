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
    }
}

/// Packaged launch: a pre-built standalone backend binary, resolved from
/// the bundle's resource directory. The binary itself is not produced by
/// this work package -- see docs/runtime: PACKAGING DECISION REQUIRED.
fn packaged_spawn_spec(app: &AppHandle) -> Result<SpawnSpec, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("RESOURCE_DIR_UNAVAILABLE: {err}"))?;
    let exe = resource_dir.join("binaries").join("sorigul-backend.exe");
    Ok(SpawnSpec {
        program: exe.to_string_lossy().into_owned(),
        args: vec!["--port".into(), BACKEND_PORT.to_string()],
        current_dir: None,
    })
}

fn spawn_spec_for_current_build(app: &AppHandle) -> SpawnSpec {
    if cfg!(debug_assertions) {
        dev_spawn_spec()
    } else {
        match packaged_spawn_spec(app) {
            Ok(spec) => spec,
            Err(_) => dev_spawn_spec(),
        }
    }
}

fn start_backend(app: AppHandle, sidecar: Arc<SidecarManager>) {
    std::thread::spawn(move || {
        let probe = HttpHealthProbe {
            url: health_url(),
            timeout: Duration::from_millis(800),
        };
        let spec = spawn_spec_for_current_build(&app);
        let status = sidecar.start(&probe, spec);
        let resolved = match status {
            SidecarStatus::Starting => sidecar.wait_until_healthy(
                &probe,
                Duration::from_secs(20),
                Duration::from_millis(400),
            ),
            other => other,
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
    use super::extract_json_string;

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
