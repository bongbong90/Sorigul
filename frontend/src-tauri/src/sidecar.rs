//! Backend sidecar lifecycle: ownership tracking, health probing, and
//! cleanup. Deliberately decoupled from Tauri so the ownership/duplicate/
//! external-process rules can be unit tested without a running app or a
//! real backend process (see the `HealthProbe` trait).

use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Outcome of a single health-endpoint probe.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProbeResult {
    /// Responded with the expected Sorigul health payload.
    Healthy,
    /// Something answered on the port, but not our backend.
    RespondingUnexpected,
    /// Nothing is listening (connection refused / timed out).
    Unreachable,
}

pub trait HealthProbe: Send + Sync {
    fn probe(&self) -> ProbeResult;
}

/// Real probe: a plain GET against the Sorigul `/api/health` endpoint.
pub struct HttpHealthProbe {
    pub url: String,
    pub timeout: Duration,
}

impl HealthProbe for HttpHealthProbe {
    fn probe(&self) -> ProbeResult {
        let agent = ureq::AgentBuilder::new().timeout(self.timeout).build();
        match agent.get(&self.url).call() {
            Ok(response) => {
                if response.status() != 200 {
                    return ProbeResult::RespondingUnexpected;
                }
                match response.into_string() {
                    Ok(body) if body.contains("\"status\"") && body.contains("\"ok\"") => {
                        ProbeResult::Healthy
                    }
                    _ => ProbeResult::RespondingUnexpected,
                }
            }
            Err(ureq::Error::Status(_, _)) => ProbeResult::RespondingUnexpected,
            Err(ureq::Error::Transport(_)) => ProbeResult::Unreachable,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SidecarStatus {
    /// Owned process spawned; health not confirmed yet.
    Starting,
    /// Health confirmed. `owned` distinguishes our spawned child from an
    /// already-running backend we chose to reuse instead of killing.
    Connected {
        owned: bool,
    },
    StartupFailed(String),
}

#[derive(Debug)]
pub struct SpawnSpec {
    pub program: String,
    pub args: Vec<String>,
    pub current_dir: Option<std::path::PathBuf>,
    /// Extra environment variables applied to the spawned child only --
    /// never the app's own process-wide environment. Used by the packaged
    /// launch to prepend the bundle's `binaries/` resource directory to the
    /// child's `PATH` so the bundled ffmpeg is found ahead of (or instead
    /// of) anything a user happens to have on their system PATH.
    pub env: Vec<(String, String)>,
}

/// Owns at most one backend child process. Never touches a process it did
/// not spawn itself.
pub struct SidecarManager {
    child: Mutex<Option<Child>>,
    owned: AtomicBool,
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            owned: AtomicBool::new(false),
        }
    }

    pub fn is_owned(&self) -> bool {
        self.owned.load(Ordering::SeqCst)
    }

    fn has_process(&self) -> bool {
        self.child.lock().unwrap().is_some()
    }

    /// PID of the currently owned process, if any (does not consume it).
    /// Public for diagnostics/tests; not currently read by app code.
    #[allow(dead_code)]
    pub fn owned_pid(&self) -> Option<u32> {
        if !self.is_owned() {
            return None;
        }
        self.child.lock().unwrap().as_ref().map(|c| c.id())
    }

    /// Decide whether to reuse an already-healthy backend, report a port
    /// conflict, or spawn our own. Never spawns twice.
    pub fn start<P: HealthProbe>(&self, probe: &P, spec: SpawnSpec) -> SidecarStatus {
        if self.has_process() || self.is_owned() {
            return SidecarStatus::Connected {
                owned: self.is_owned(),
            };
        }
        match probe.probe() {
            ProbeResult::Healthy => SidecarStatus::Connected { owned: false },
            ProbeResult::RespondingUnexpected => {
                SidecarStatus::StartupFailed("PORT_OCCUPIED_BY_OTHER_SERVICE".into())
            }
            ProbeResult::Unreachable => match self.spawn(spec) {
                Ok(()) => SidecarStatus::Starting,
                Err(reason) => SidecarStatus::StartupFailed(reason),
            },
        }
    }

    fn spawn(&self, spec: SpawnSpec) -> Result<(), String> {
        let mut command = Command::new(&spec.program);
        command.args(&spec.args);
        if let Some(dir) = &spec.current_dir {
            command.current_dir(dir);
        }
        for (key, value) in &spec.env {
            command.env(key, value);
        }
        command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(target_os = "windows")]
        command.creation_flags(CREATE_NO_WINDOW);

        match command.spawn() {
            Ok(child) => {
                *self.child.lock().unwrap() = Some(child);
                self.owned.store(true, Ordering::SeqCst);
                Ok(())
            }
            Err(err) => Err(format!("SPAWN_FAILED: {err}")),
        }
    }

    /// Polls until healthy, until the owned child exits early (startup
    /// crash), or until `timeout` elapses.
    pub fn wait_until_healthy<P: HealthProbe>(
        &self,
        probe: &P,
        timeout: Duration,
        interval: Duration,
    ) -> SidecarStatus {
        let deadline = Instant::now() + timeout;
        loop {
            if self.is_owned() {
                if let Some(child) = self.child.lock().unwrap().as_mut() {
                    if let Ok(Some(status)) = child.try_wait() {
                        return SidecarStatus::StartupFailed(format!(
                            "BACKEND_EXITED_DURING_STARTUP: {status}"
                        ));
                    }
                }
            }
            match probe.probe() {
                ProbeResult::Healthy => {
                    return SidecarStatus::Connected {
                        owned: self.is_owned(),
                    }
                }
                ProbeResult::RespondingUnexpected => {
                    return SidecarStatus::StartupFailed("PORT_OCCUPIED_BY_OTHER_SERVICE".into())
                }
                ProbeResult::Unreachable => {}
            }
            if Instant::now() >= deadline {
                return SidecarStatus::StartupFailed("STARTUP_TIMEOUT".into());
            }
            std::thread::sleep(interval);
        }
    }

    /// True if the owned process is still alive; `None` when we don't own one.
    /// Public for diagnostics/tests; not currently read by app code.
    #[allow(dead_code)]
    pub fn is_owned_process_alive(&self) -> Option<bool> {
        if !self.is_owned() {
            return None;
        }
        let mut guard = self.child.lock().unwrap();
        guard
            .as_mut()
            .map(|child| matches!(child.try_wait(), Ok(None)))
    }

    /// Terminates only a process this manager spawned itself. A no-op for
    /// a reused external backend, and idempotent across repeated calls.
    pub fn cleanup(&self) {
        if !self.is_owned() {
            return;
        }
        let mut guard = self.child.lock().unwrap();
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            #[cfg(target_os = "windows")]
            {
                let mut kill = Command::new("taskkill.exe");
                kill.args(["/PID", &pid.to_string(), "/T", "/F"]);
                kill.creation_flags(CREATE_NO_WINDOW);
                let _ = kill.status();
            }
            #[cfg(not(target_os = "windows"))]
            {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
        self.owned.store(false, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;
    use std::time::Duration;

    struct FixedProbe {
        result: ProbeResult,
        calls: AtomicUsize,
    }

    impl FixedProbe {
        fn new(result: ProbeResult) -> Self {
            Self {
                result,
                calls: AtomicUsize::new(0),
            }
        }
        fn call_count(&self) -> usize {
            self.calls.load(Ordering::SeqCst)
        }
    }

    impl HealthProbe for FixedProbe {
        fn probe(&self) -> ProbeResult {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.result
        }
    }

    fn long_sleep_spec() -> SpawnSpec {
        SpawnSpec {
            program: "powershell".into(),
            args: vec![
                "-NoProfile".into(),
                "-Command".into(),
                "Start-Sleep -Seconds 5".into(),
            ],
            current_dir: None,
            env: vec![],
        }
    }

    #[test]
    fn reuses_already_healthy_backend_without_spawning() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Healthy);

        let status = manager.start(&probe, long_sleep_spec());

        assert_eq!(status, SidecarStatus::Connected { owned: false });
        assert!(!manager.is_owned());
        assert!(manager.owned_pid().is_none());
    }

    #[test]
    fn reports_startup_failure_on_port_conflict_without_spawning() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::RespondingUnexpected);

        let status = manager.start(&probe, long_sleep_spec());

        assert_eq!(
            status,
            SidecarStatus::StartupFailed("PORT_OCCUPIED_BY_OTHER_SERVICE".into())
        );
        assert!(!manager.is_owned());
    }

    #[test]
    fn spawns_and_owns_when_port_is_unreachable() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);

        let status = manager.start(&probe, long_sleep_spec());

        assert_eq!(status, SidecarStatus::Starting);
        assert!(manager.is_owned());
        assert_eq!(manager.is_owned_process_alive(), Some(true));

        manager.cleanup();
    }

    #[test]
    fn duplicate_start_does_not_spawn_a_second_process() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);

        let first = manager.start(&probe, long_sleep_spec());
        let first_pid = manager.owned_pid();
        let calls_after_first = probe.call_count();
        let second = manager.start(&probe, long_sleep_spec());

        assert_eq!(first, SidecarStatus::Starting);
        assert_eq!(second, SidecarStatus::Connected { owned: true });
        assert_eq!(manager.owned_pid(), first_pid);
        assert_eq!(
            probe.call_count(),
            calls_after_first,
            "second start() must not re-probe/re-spawn"
        );

        manager.cleanup();
    }

    #[test]
    fn cleanup_terminates_the_owned_process() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&probe, long_sleep_spec());
        let pid = manager.owned_pid().expect("owned pid after spawn");

        manager.cleanup();
        std::thread::sleep(Duration::from_millis(400));

        assert!(!manager.is_owned());
        assert!(
            !process_is_running(pid),
            "owned process should be terminated after cleanup"
        );
    }

    #[test]
    fn cleanup_does_not_touch_an_unowned_external_process() {
        // Simulate an unrelated process that happens to be running; the
        // manager never adopted it (owned == false), so cleanup() must be
        // a strict no-op with respect to it.
        let mut unrelated = Command::new("powershell")
            .args(["-NoProfile", "-Command", "Start-Sleep -Seconds 4"])
            .spawn()
            .expect("spawn unrelated process");
        let unrelated_pid = unrelated.id();

        let manager = SidecarManager::new();
        manager.cleanup(); // no-op: nothing owned

        assert!(
            process_is_running(unrelated_pid),
            "unrelated process must survive an unowned cleanup()"
        );

        // Test-owned teardown only (never via SidecarManager, which must
        // never learn this PID).
        let _ = unrelated.kill();
        let _ = unrelated.wait();
    }

    fn process_is_running(pid: u32) -> bool {
        let output = Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .expect("tasklist");
        String::from_utf8_lossy(&output.stdout).contains(&pid.to_string())
    }
}
