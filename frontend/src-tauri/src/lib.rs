mod close_guard;
mod completion_toast;
mod shutdown;
mod sidecar;
mod tray_tooltip;
#[cfg(target_os = "windows")]
mod windows_system;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_notification::NotificationExt;

use close_guard::{
    close_guard_url, fetch_close_guard, notice_body, CloseCheck, CloseOutcome, CloseRequestAction,
};

use completion_toast::{
    bottom_right_position, is_opaque_job_id, CompletionToastPayload, CompletionToastRequest,
    CompletionToastState, COMPLETION_TOAST_EVENT, COMPLETION_TOAST_LABEL, COMPLETION_TOAST_MARGIN,
    COMPLETION_TOAST_TIMEOUT,
};
use shutdown::{RealShutdownExecutor, ShutdownGate};
use sidecar::{HttpHealthProbe, SidecarManager, SidecarStatus, SpawnSpec};
use tray_tooltip::{
    format_tray_tooltip, update_tooltip_if_changed, TrayProgressPayload, IDLE_TRAY_TOOLTIP,
};

const BACKEND_PORT: u16 = 8000;
const TRAY_ID: &str = "sorigul-main-tray";

#[cfg(target_os = "windows")]
const PATH_LIST_SEPARATOR: &str = ";";
#[cfg(not(target_os = "windows"))]
const PATH_LIST_SEPARATOR: &str = ":";

struct AppState {
    sidecar: Arc<SidecarManager>,
    sidecar_status: Mutex<SidecarStatusPayload>,
    shutdown_gate: ShutdownGate,
    close_behavior: Mutex<String>,
    close_check: CloseCheck,
    completion_toast: Mutex<CompletionToastState>,
    last_tray_tooltip: Mutex<Option<String>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct SidecarStatusPayload {
    state: &'static str,
    owned: Option<bool>,
    code: Option<String>,
    message: Option<String>,
}

impl SidecarStatusPayload {
    fn starting() -> Self {
        Self {
            state: "STARTING",
            owned: None,
            code: None,
            message: None,
        }
    }

    fn from_status(status: &SidecarStatus) -> Self {
        match status {
            SidecarStatus::Starting => Self::starting(),
            SidecarStatus::Connected { owned } => Self {
                state: "CONNECTED",
                owned: Some(*owned),
                code: None,
                message: None,
            },
            SidecarStatus::StartupFailed(reason) => {
                let code = reason.split(':').next().unwrap_or("STARTUP_FAILED").trim();
                let message = match code {
                    "JOB_STORAGE_READ_FAILED" => "작업 기록 파일을 읽을 수 없어 Backend를 시작하지 못했습니다. 파일 권한이나 디스크 상태를 확인해 주세요.",
                    "JOB_STORAGE_QUARANTINE_FAILED" => "손상된 작업 기록을 안전하게 보관하지 못해 Backend를 시작하지 못했습니다.",
                    "JOB_STORAGE_WRITE_FAILED" => "작업 기록 파일을 저장할 수 없어 Backend를 시작하지 못했습니다. 파일 권한이나 디스크 상태를 확인해 주세요.",
                    "PORT_OCCUPIED_BY_OTHER_SERVICE" => "Backend 포트를 다른 프로그램이 사용 중입니다. 해당 프로그램을 종료한 뒤 다시 시도해 주세요.",
                    "STARTUP_TIMEOUT" => "Backend 시작 시간이 초과되었습니다. 다시 시도해 주세요.",
                    _ => "Backend를 시작하지 못했습니다. 다시 시도해 주세요.",
                };
                Self {
                    state: "STARTUP_FAILED",
                    owned: None,
                    code: Some(code.to_string()),
                    message: Some(message.to_string()),
                }
            }
        }
    }
}

fn publish_sidecar_status(app: &AppHandle, payload: SidecarStatusPayload) {
    if let Some(state) = app.try_state::<AppState>() {
        *state.sidecar_status.lock().unwrap() = payload.clone();
    }
    let _ = app.emit("sorigul://sidecar-status", payload);
}

#[tauri::command]
fn get_sidecar_status(state: State<AppState>) -> SidecarStatusPayload {
    state.sidecar_status.lock().unwrap().clone()
}

#[tauri::command]
fn retry_sidecar_startup(app: AppHandle, state: State<AppState>) {
    let current = state.sidecar_status.lock().unwrap().clone();
    if current.state != "STARTUP_FAILED" {
        return;
    }
    let sidecar = state.sidecar.clone();
    publish_sidecar_status(&app, SidecarStatusPayload::starting());
    start_backend(app, sidecar);
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

#[tauri::command]
fn set_tray_progress(
    app: AppHandle,
    state: State<AppState>,
    payload: TrayProgressPayload,
) -> Result<(), String> {
    let tooltip = format_tray_tooltip(&payload);
    let tray = app
        .tray_by_id(TRAY_ID)
        .ok_or_else(|| "TRAY_NOT_AVAILABLE".to_string())?;
    let mut last_tooltip = state
        .last_tray_tooltip
        .lock()
        .map_err(|_| "TRAY_TOOLTIP_STATE_UNAVAILABLE".to_string())?;
    update_tooltip_if_changed(&mut last_tooltip, &tooltip, |value| {
        tray.set_tooltip(Some(value))
    })
    .map_err(|error| format!("TRAY_TOOLTIP_UPDATE_FAILED: {error}"))?;
    Ok(())
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
    let intent = fetch_folder_intent(&url)?;
    open_in_explorer(&intent.folder, intent.item_filename.as_deref())
        .map_err(|err| format!("EXPLORER_OPEN_FAILED: {err}"))
}

/// Completion toast "폴더 열기" (Issue #110). The toast holds only the opaque
/// job_id; the backend resolves and validates that Job's transcription
/// folder, and only then is Explorer launched. Runs off the main thread
/// because the backend round-trip is blocking.
#[tauri::command(async)]
fn open_notification_folder(app: AppHandle, job_id: String) -> Result<(), String> {
    let url = notification_folder_intent_url(&job_id)?;
    open_validated_folder(&url, open_in_explorer)?;
    dismiss_completion_toast_window(&app);
    Ok(())
}

fn notification_folder_intent_url(job_id: &str) -> Result<String, String> {
    if !is_opaque_job_id(job_id) {
        return Err("INVALID_JOB_ID".into());
    }
    Ok(format!(
        "http://127.0.0.1:{BACKEND_PORT}/api/desktop/jobs/{job_id}/open-folder-intent"
    ))
}

/// Opens only the folder of a backend intent (never an item inside it).
/// `open` is injectable so tests can prove a bad intent never reaches it.
fn open_validated_folder(
    url: &str,
    open: impl FnOnce(&str, Option<&str>) -> std::io::Result<()>,
) -> Result<(), String> {
    let intent = fetch_folder_intent(url)?;
    open(&intent.folder, None).map_err(|err| format!("EXPLORER_OPEN_FAILED: {err}"))
}

#[derive(Debug, PartialEq, Eq)]
struct FolderIntent {
    folder: String,
    item_filename: Option<String>,
}

/// POSTs to a fixed local backend intent endpoint and extracts the two
/// validated fields. Any transport, status or shape problem is an error, so
/// Explorer is never launched on a partial or foreign response.
fn fetch_folder_intent(url: &str) -> Result<FolderIntent, String> {
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(5))
        .build();

    let response = match agent.post(url).call() {
        Ok(response) => response,
        Err(ureq::Error::Status(code, _)) => return Err(format!("BACKEND_ERROR: HTTP {code}")),
        Err(err) => return Err(format!("BACKEND_UNREACHABLE: {err}")),
    };

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
        .filter(|folder| !folder.trim().is_empty())
        .ok_or_else(|| "INTENT_PARSE_ERROR: missing folder".to_string())?;
    let item_filename = extract_json_string(&body, "item_filename");
    Ok(FolderIntent {
        folder,
        item_filename,
    })
}

/// Called by the main window's notification hook for every new completion
/// event. Replaces the single toast's content, shows it bottom-right without
/// taking focus, and (re)starts the auto-hide timeout. An error here tells
/// the caller to use the plain OS notification fallback instead.
#[tauri::command]
fn show_completion_toast(
    app: AppHandle,
    state: State<AppState>,
    request: CompletionToastRequest,
) -> Result<(), String> {
    let request = request.validate()?;
    let window = app
        .get_webview_window(COMPLETION_TOAST_LABEL)
        .ok_or_else(|| "TOAST_WINDOW_UNAVAILABLE".to_string())?;
    let payload = state.completion_toast.lock().unwrap().present(request);

    let shown = app
        .emit_to(COMPLETION_TOAST_LABEL, COMPLETION_TOAST_EVENT, &payload)
        .map_err(|err| format!("TOAST_EMIT_FAILED: {err}"))
        .and_then(|()| {
            place_completion_toast(&app, &window);
            window
                .show()
                .map_err(|err| format!("TOAST_SHOW_FAILED: {err}"))
        });
    if let Err(err) = shown {
        state.completion_toast.lock().unwrap().dismiss();
        let _ = window.hide();
        return Err(err);
    }

    let generation = payload.generation;
    std::thread::spawn(move || {
        std::thread::sleep(COMPLETION_TOAST_TIMEOUT);
        let Some(state) = app.try_state::<AppState>() else {
            return;
        };
        if state.completion_toast.lock().unwrap().expire(generation) {
            if let Some(window) = app.get_webview_window(COMPLETION_TOAST_LABEL) {
                let _ = window.hide();
            }
        }
    });
    Ok(())
}

/// Toast window mount: the current content, so an event emitted before its
/// listener was ready is never lost.
#[tauri::command]
fn get_completion_toast(state: State<AppState>) -> Option<CompletionToastPayload> {
    state.completion_toast.lock().unwrap().snapshot()
}

/// Toast "확인".
#[tauri::command]
fn dismiss_completion_toast(app: AppHandle) {
    dismiss_completion_toast_window(&app);
}

fn dismiss_completion_toast_window(app: &AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        state.completion_toast.lock().unwrap().dismiss();
    }
    if let Some(window) = app.get_webview_window(COMPLETION_TOAST_LABEL) {
        let _ = window.hide();
    }
}

/// Bottom-right of the work area of the monitor the main window is on
/// (hidden-to-tray included), else the primary monitor. Best effort: if no
/// monitor is resolvable the toast keeps its previous position.
fn place_completion_toast(app: &AppHandle, toast: &tauri::WebviewWindow) {
    let monitor = app
        .get_webview_window("main")
        .and_then(|main| main.current_monitor().ok().flatten())
        .or_else(|| toast.primary_monitor().ok().flatten());
    let (Some(monitor), Ok(size)) = (monitor, toast.outer_size()) else {
        return;
    };
    let area = monitor.work_area();
    let margin = (COMPLETION_TOAST_MARGIN * monitor.scale_factor()).round() as i32;
    let (x, y) = bottom_right_position(
        (area.position.x, area.position.y),
        (area.size.width, area.size.height),
        (size.width, size.height),
        margin,
    );
    let _ = toast.set_position(tauri::PhysicalPosition::new(x, y));
}

/// Opens a folder in Windows Explorer, optionally revealing a specific file.
/// Uses `std::process::Command` with a fixed executable and a sanitised
/// argument list -- no shell string concatenation.
fn open_in_explorer(folder: &str, item_filename: Option<&str>) -> std::io::Result<()> {
    #[cfg(target_os = "windows")]
    {
        explorer_command(folder, item_filename)?.spawn()?;
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

/// `<Windows>\explorer.exe <target>` by trusted absolute path (#122); never
/// resolved through `PATH`. Built separately so tests inspect it unlaunched.
#[cfg(target_os = "windows")]
fn explorer_command(
    folder: &str,
    item_filename: Option<&str>,
) -> std::io::Result<std::process::Command> {
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

    let explorer = windows_system::SystemUtility::Explorer
        .path()
        .map_err(|err| std::io::Error::new(std::io::ErrorKind::NotFound, err))?;
    let mut command = std::process::Command::new(explorer);
    command.arg(&target).creation_flags(CREATE_NO_WINDOW);
    Ok(command)
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
        // `start_and_wait` terminates an owned child the moment startup
        // fails, before the failure status is emitted -- never at app exit.
        let resolved = match spawn_spec_for_current_build(&app) {
            Ok(spec) => sidecar.start_and_wait(
                &probe,
                spec,
                startup_timeout_for_current_build(),
                Duration::from_millis(400),
            ),
            Err(reason) => SidecarStatus::StartupFailed(reason),
        };
        publish_sidecar_status(&app, SidecarStatusPayload::from_status(&resolved));
    });
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open_item = MenuItem::with_id(app, "open", "앱 열기", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

    let tray = TrayIconBuilder::with_id(TRAY_ID)
        .icon(
            app.default_window_icon()
                .cloned()
                .expect("default window icon configured"),
        )
        .tooltip(IDLE_TRAY_TOOLTIP)
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
    if let Some(state) = app.try_state::<AppState>() {
        state.close_check.window_reopened();
    }
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Runs in the FIRST instance when Sorigul is launched again (#168). The
/// second process never reaches `setup` (no tray, no backend) and exits
/// inside the single-instance plugin; here the existing main window is only
/// shown and focused -- hidden-to-tray included. The second launch's argv/cwd
/// are deliberately ignored: no file open, folder change or command dispatch.
fn handle_second_instance(app: &AppHandle, _argv: Vec<String>, _cwd: String) {
    show_main_window(app);
}

/// Background close-guard check for a `close_behavior = "exit"` close.
/// Confirmed idle exits through `app.exit(0)`, so RunEvent::ExitRequested
/// stays the single sidecar cleanup path. Active work or any doubt hides the
/// window to the tray; the notice is best-effort and never weakens that.
fn spawn_close_check(app: AppHandle, generation: u64) {
    std::thread::spawn(move || {
        let result = fetch_close_guard(&close_guard_url());
        let Some(state) = app.try_state::<AppState>() else {
            return;
        };
        let outcome = state.close_check.finish(generation, result);
        match outcome {
            CloseOutcome::ConfirmedExit => app.exit(0),
            CloseOutcome::Superseded => {}
            CloseOutcome::ProtectedHide(_) | CloseOutcome::SafeHide => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
                if let Some(body) = notice_body(&outcome) {
                    let _ = app
                        .notification()
                        .builder()
                        .title("Sorigul")
                        .body(body)
                        .show();
                }
            }
        }
    });
}

pub fn run() {
    let sidecar = Arc::new(SidecarManager::new());
    let sidecar_for_exit = sidecar.clone();
    let sidecar_for_setup = sidecar.clone();

    let app = tauri::Builder::default()
        // Must stay the first plugin: a second launch exits inside this
        // plugin's setup before any other plugin, the tray or the backend
        // sidecar is initialised (#168).
        .plugin(tauri_plugin_single_instance::init(handle_second_instance))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            sidecar: sidecar.clone(),
            sidecar_status: Mutex::new(SidecarStatusPayload::starting()),
            shutdown_gate: ShutdownGate::new(),
            close_behavior: Mutex::new("tray".into()),
            close_check: CloseCheck::default(),
            completion_toast: Mutex::new(CompletionToastState::default()),
            last_tray_tooltip: Mutex::new(Some(IDLE_TRAY_TOOLTIP.to_string())),
        })
        .invoke_handler(tauri::generate_handler![
            set_close_behavior,
            native_shutdown,
            reset_shutdown_gate,
            set_tray_progress,
            open_folder_by_intent,
            open_notification_folder,
            show_completion_toast,
            get_completion_toast,
            dismiss_completion_toast,
            get_sidecar_status,
            retry_sidecar_startup,
        ])
        .setup(move |app| {
            build_tray(app)?;
            start_backend(app.handle().clone(), sidecar_for_setup.clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == COMPLETION_TOAST_LABEL {
                // The toast is never closed on its own (e.g. Alt+F4): it only
                // hides, so it stays reusable and close-to-tray is unaffected.
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    dismiss_completion_toast_window(window.app_handle());
                }
                return;
            }
            if let WindowEvent::Destroyed = event {
                // Main window destroyed on a real exit: take the hidden toast
                // down with it so no orphan toast window remains. A protected
                // close only hides main, so the toast is left alone.
                if let Some(toast) = window
                    .app_handle()
                    .get_webview_window(COMPLETION_TOAST_LABEL)
                {
                    let _ = toast.destroy();
                }
                return;
            }
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let Some(state) = app.try_state::<AppState>() else {
                    return;
                };
                let behavior = state.close_behavior.lock().unwrap().clone();
                // Always prevent first: with "exit" the app ends only after
                // the backend confirms no active work (#128), and that check
                // never runs on this callback.
                api.prevent_close();
                match state.close_check.on_close_requested(&behavior) {
                    (CloseRequestAction::HideNow, _) => {
                        let _ = window.hide();
                    }
                    (CloseRequestAction::CheckCriticalWork, generation) => {
                        spawn_close_check(app.clone(), generation);
                    }
                    (CloseRequestAction::AlreadyChecking, _) => {}
                }
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
    use super::{
        extract_json_string, notification_folder_intent_url, open_validated_folder,
        packaged_spawn_spec_from_resource_dir, SidecarStatus, SidecarStatusPayload,
    };

    #[test]
    fn sidecar_status_payload_is_structured_and_sanitizes_failure_detail() {
        let payload = SidecarStatusPayload::from_status(&SidecarStatus::StartupFailed(
            "SPAWN_FAILED: C:\\private\\backend.exe".into(),
        ));
        assert_eq!(payload.state, "STARTUP_FAILED");
        assert_eq!(payload.code.as_deref(), Some("SPAWN_FAILED"));
        assert_eq!(
            payload.message.as_deref(),
            Some("Backend를 시작하지 못했습니다. 다시 시도해 주세요.")
        );
        assert!(!payload.message.unwrap().contains("private"));
    }

    #[test]
    fn job_storage_startup_failure_has_specific_user_message() {
        let payload = SidecarStatusPayload::from_status(&SidecarStatus::StartupFailed(
            "JOB_STORAGE_READ_FAILED".into(),
        ));
        assert_eq!(payload.code.as_deref(), Some("JOB_STORAGE_READ_FAILED"));
        assert!(payload.message.unwrap().contains("작업 기록 파일"));
    }

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
    fn notification_intent_url_is_fixed_localhost_backend_route() {
        assert_eq!(
            notification_folder_intent_url("0f8fad5b-d9cb-469f-a165-70867728950e").unwrap(),
            "http://127.0.0.1:8000/api/desktop/jobs/0f8fad5b-d9cb-469f-a165-70867728950e/open-folder-intent"
        );
    }

    #[test]
    fn notification_intent_url_refuses_non_opaque_job_ids() {
        for bad in [
            "",
            "../folders/x",
            "a?folder=C:\\x",
            "a#b",
            "http://evil",
            "C:\\Users",
        ] {
            assert_eq!(
                notification_folder_intent_url(bad),
                Err("INVALID_JOB_ID".to_string()),
                "{bad}"
            );
        }
    }

    /// One-shot local HTTP stub: answers the first request with `response`.
    fn stub_backend(response: &'static str) -> String {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 4096];
                let _ = stream.read(&mut buf);
                let _ = stream.write_all(response.as_bytes());
            }
        });
        format!("http://127.0.0.1:{port}/api/desktop/jobs/x/open-folder-intent")
    }

    fn http(status: &str, body: &str) -> &'static str {
        Box::leak(
            format!(
                "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            )
            .into_boxed_str(),
        )
    }

    fn never_opened(
        opened: &std::cell::Cell<bool>,
    ) -> impl FnOnce(&str, Option<&str>) -> std::io::Result<()> + '_ {
        move |_, _| {
            opened.set(true);
            Ok(())
        }
    }

    #[test]
    fn valid_intent_opens_only_the_backend_folder() {
        let url = stub_backend(http(
            "200 OK",
            r#"{"action":"OPEN_FOLDER","folder":"C:\\전사자료\\개념완성_민법","item_filename":"x.txt"}"#,
        ));
        let mut seen = None;
        open_validated_folder(&url, |folder, item| {
            seen = Some((folder.to_owned(), item.map(str::to_owned)));
            Ok(())
        })
        .unwrap();
        assert_eq!(seen, Some(("C:\\전사자료\\개념완성_민법".to_owned(), None)));
    }

    #[test]
    fn backend_404_and_410_never_launch_explorer() {
        for status in ["404 Not Found", "410 Gone"] {
            let url = stub_backend(http(status, r#"{"detail":"x"}"#));
            let opened = std::cell::Cell::new(false);
            let err = open_validated_folder(&url, never_opened(&opened)).unwrap_err();
            assert!(err.starts_with("BACKEND_ERROR: HTTP 4"), "{err}");
            assert!(!opened.get());
        }
    }

    #[test]
    fn invalid_intent_response_never_launches_explorer() {
        for body in [
            r#"{"detail":"no folder here"}"#,
            r#"{"action":"OPEN_FOLDER","folder":null}"#,
            r#"{"action":"OPEN_FOLDER","folder":"   "}"#,
            "not json",
        ] {
            let url = stub_backend(http("200 OK", body));
            let opened = std::cell::Cell::new(false);
            let err = open_validated_folder(&url, never_opened(&opened)).unwrap_err();
            assert!(err.starts_with("INTENT_PARSE_ERROR"), "{body}: {err}");
            assert!(!opened.get());
        }
    }

    #[test]
    fn unavailable_backend_is_a_safe_error() {
        let port = {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            listener.local_addr().unwrap().port()
        };
        let url = format!("http://127.0.0.1:{port}/api/desktop/jobs/x/open-folder-intent");
        let opened = std::cell::Cell::new(false);
        let err = open_validated_folder(&url, never_opened(&opened)).unwrap_err();
        assert!(err.starts_with("BACKEND_UNREACHABLE"), "{err}");
        assert!(!opened.get());
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

    /// Both `open_folder_by_intent` and `open_notification_folder` reach
    /// Explorer only through `open_in_explorer` -> `explorer_command`.
    /// Inspected only; Explorer is never launched here.
    #[cfg(target_os = "windows")]
    #[test]
    fn explorer_command_uses_trusted_windows_directory_and_single_target_arg() {
        let command = super::explorer_command("C:\\Lectures\\Week 1", Some("a b.txt")).unwrap();
        let program = std::path::Path::new(command.get_program());
        assert!(program.is_absolute(), "{program:?}");
        assert_eq!(
            program,
            super::windows_system::SystemUtility::Explorer
                .path()
                .unwrap()
        );
        assert!(!program
            .parent()
            .and_then(|dir| dir.file_name())
            .unwrap()
            .eq_ignore_ascii_case("System32"));
        let args: Vec<_> = command.get_args().collect();
        assert_eq!(args, ["C:\\Lectures\\Week 1\\a b.txt"]);
    }
}
