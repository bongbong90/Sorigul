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

    TrayIconBuilder::new()
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
