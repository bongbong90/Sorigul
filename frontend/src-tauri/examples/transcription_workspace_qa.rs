//! Synthetic source UI host only: no product backend, plugins or app state.
//! Build on Windows (Common Controls v6 manifest required for an example):
//! cargo rustc --locked --offline --example transcription_workspace_qa --
//!   -C link-arg=/MANIFEST:EMBED
//!   -C link-arg=/MANIFESTINPUT:examples/transcription_workspace_qa.manifest
//! Run through tests/frontend/transcription_workspace_dom.mjs --webview2.
use tauri::{WebviewUrl, WebviewWindowBuilder};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert_eq!(
        args.len(),
        4,
        "expected synthetic URL, isolated profile, CDP port"
    );
    assert!(
        args[1].starts_with("http://127.0.0.1:") && !args[1].starts_with("http://127.0.0.1:8000/"),
        "only the synthetic loopback fixture is allowed"
    );
    let url = args[1].parse().expect("invalid synthetic URL");
    let profile = std::path::PathBuf::from(&args[2]);
    assert!(profile.is_absolute(), "isolated profile must be absolute");
    let owned_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tmp")
        .canonicalize()
        .unwrap();
    assert!(
        profile.canonicalize().unwrap().starts_with(owned_root),
        "profile must stay in workspace tmp"
    );
    let browser_args = format!(
        "--remote-debugging-port={} --disable-background-networking",
        args[3]
    );
    let mut context = tauri::generate_context!();
    context.config_mut().app.windows.clear();
    context.config_mut().app.security.csp = None;
    context.config_mut().app.security.dev_csp = None;
    tauri::Builder::default()
        .setup(move |app| {
            WebviewWindowBuilder::new(app, "synthetic-qa", WebviewUrl::External(url))
                .title("Sorigul synthetic source UI QA")
                .data_directory(profile)
                .additional_browser_args(&browser_args)
                .inner_size(1440.0, 926.0)
                .visible(false)
                .build()?;
            Ok(())
        })
        .run(context)
        .expect("synthetic UI host failed");
}
