//! Backend sidecar lifecycle: ownership tracking, health probing, and
//! cleanup. Deliberately decoupled from Tauri so the ownership/duplicate/
//! external-process rules can be unit tested without a running app or a
//! real backend process (see the `HealthProbe` trait).

use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[cfg(target_os = "windows")]
use std::os::windows::io::AsRawHandle;
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
#[cfg(target_os = "windows")]
const CREATE_SUSPENDED: u32 = 0x0000_0004;

/// Windows Job Object wrapper, created with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
///
/// This is what protects against an orphaned backend on *abnormal*
/// termination -- Task Manager "End Task", `taskkill /F` (without `/T`),
/// or a desktop-process crash -- none of which ever reach
/// `SidecarManager::cleanup()`'s own graceful `taskkill /T /F`
/// (`RunEvent::ExitRequested` is a normal-exit-only hook). With
/// kill-on-close set and this handle never duplicated to any other
/// process, Windows itself closes this handle as part of tearing down our
/// own process -- by any means -- which makes the OS terminate every
/// process assigned to the job. Job membership is inherited by any child
/// a job member spawns, so the PyInstaller one-file bootloader's unpacked
/// child process is covered too, as long as the bootloader joins the job
/// before it spawns that child (see `supervise_with_job_object` below for
/// how that ordering is guaranteed).
#[cfg(target_os = "windows")]
struct JobObject {
    handle: windows_sys::Win32::Foundation::HANDLE,
}

#[cfg(target_os = "windows")]
impl JobObject {
    fn create_with_kill_on_close() -> Result<Self, String> {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::JobObjects::{
            CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };

        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err("JOB_OBJECT_CREATE_FAILED".into());
            }

            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            let ok = SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const core::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == 0 {
                CloseHandle(handle);
                return Err("JOB_OBJECT_CONFIGURE_FAILED".into());
            }

            Ok(Self { handle })
        }
    }

    /// Assigns an already-created (and, by construction here, still
    /// suspended) process to this job. Never assigns a process this
    /// manager did not itself spawn -- callers only ever pass the handle
    /// of a child `SidecarManager::spawn()` just created.
    fn assign(&self, process_handle: windows_sys::Win32::Foundation::HANDLE) -> Result<(), String> {
        use windows_sys::Win32::System::JobObjects::AssignProcessToJobObject;
        let ok = unsafe { AssignProcessToJobObject(self.handle, process_handle) };
        if ok == 0 {
            return Err("JOB_OBJECT_ASSIGN_FAILED".into());
        }
        Ok(())
    }
}

#[cfg(target_os = "windows")]
impl Drop for JobObject {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.handle);
        }
    }
}

// SAFETY: `handle` is a plain Windows HANDLE value used only via documented
// thread-safe Win32 calls (AssignProcessToJobObject, CloseHandle); no
// interior mutability or aliasing concern beyond what Windows itself
// guarantees for handle values shared across threads.
#[cfg(target_os = "windows")]
unsafe impl Send for JobObject {}

/// No-op marker on non-Windows targets so `OwnedProcess` doesn't need a
/// separate per-platform shape. Never constructed there.
#[cfg(not(target_os = "windows"))]
struct JobObject;

/// Resumes every thread owned by `pid`. Used to resume a child spawned
/// with `CREATE_SUSPENDED` immediately after (successfully or not) trying
/// to assign it to a Job Object -- looked up via a thread snapshot rather
/// than the `CreateProcessW` thread handle, because `std::process::Child`
/// does not expose that handle. Since the child was created suspended, it
/// has not executed a single instruction yet, so Job Object assignment
/// (when it succeeds) can never race the child spawning a grandchild.
#[cfg(target_os = "windows")]
fn resume_all_threads_of_process(pid: u32) -> Result<(), String> {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD, THREADENTRY32,
    };
    use windows_sys::Win32::System::Threading::{OpenThread, ResumeThread, THREAD_SUSPEND_RESUME};

    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if snapshot == INVALID_HANDLE_VALUE {
            return Err("THREAD_SNAPSHOT_FAILED".into());
        }

        let mut entry: THREADENTRY32 = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
        let mut resumed_any = false;

        if Thread32First(snapshot, &mut entry) != 0 {
            loop {
                if entry.th32OwnerProcessID == pid {
                    let thread_handle = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                    if !thread_handle.is_null() {
                        ResumeThread(thread_handle);
                        CloseHandle(thread_handle);
                        resumed_any = true;
                    }
                }
                if Thread32Next(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }

        CloseHandle(snapshot);
        if resumed_any {
            Ok(())
        } else {
            Err("NO_THREAD_FOUND_TO_RESUME".into())
        }
    }
}

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

/// A spawned child together with the (Windows-only) Job Object it was
/// assigned to, if any. `job` drops -- closing its handle -- whenever this
/// struct does, which on Windows is exactly the kill-on-close trigger.
struct OwnedProcess {
    child: Child,
    #[allow(dead_code)]
    job: Option<JobObject>,
}

/// Owns at most one backend child process. Never touches a process it did
/// not spawn itself.
pub struct SidecarManager {
    process: Mutex<Option<OwnedProcess>>,
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
            process: Mutex::new(None),
            owned: AtomicBool::new(false),
        }
    }

    pub fn is_owned(&self) -> bool {
        self.owned.load(Ordering::SeqCst)
    }

    fn has_process(&self) -> bool {
        self.process.lock().unwrap().is_some()
    }

    /// PID of the currently owned process, if any (does not consume it).
    /// Public for diagnostics/tests; not currently read by app code.
    #[allow(dead_code)]
    pub fn owned_pid(&self) -> Option<u32> {
        if !self.is_owned() {
            return None;
        }
        self.process.lock().unwrap().as_ref().map(|p| p.child.id())
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
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);

        match command.spawn() {
            Ok(child) => {
                #[cfg(target_os = "windows")]
                let job = Self::supervise_with_job_object(&child);
                #[cfg(not(target_os = "windows"))]
                let job = None;

                *self.process.lock().unwrap() = Some(OwnedProcess { child, job });
                self.owned.store(true, Ordering::SeqCst);
                Ok(())
            }
            Err(err) => Err(format!("SPAWN_FAILED: {err}")),
        }
    }

    /// Creates a fresh kill-on-close Job Object, assigns the (still
    /// `CREATE_SUSPENDED`) child to it, then resumes the child regardless
    /// of whether assignment succeeded -- a permanently-suspended,
    /// unsupervised child is strictly worse than an unsupervised running
    /// one. Because the child has not executed a single instruction before
    /// assignment happens, this ordering can never race the child spawning
    /// a grandchild before joining the job.
    #[cfg(target_os = "windows")]
    fn supervise_with_job_object(child: &Child) -> Option<JobObject> {
        let process_handle = child.as_raw_handle() as windows_sys::Win32::Foundation::HANDLE;

        let job = match JobObject::create_with_kill_on_close() {
            Ok(job) => match job.assign(process_handle) {
                Ok(()) => Some(job),
                Err(_) => None,
            },
            Err(_) => None,
        };

        let _ = resume_all_threads_of_process(child.id());

        job
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
                if let Some(owned_process) = self.process.lock().unwrap().as_mut() {
                    if let Ok(Some(status)) = owned_process.child.try_wait() {
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
        let mut guard = self.process.lock().unwrap();
        guard
            .as_mut()
            .map(|owned| matches!(owned.child.try_wait(), Ok(None)))
    }

    /// Terminates only a process this manager spawned itself. A no-op for
    /// a reused external backend, and idempotent across repeated calls.
    /// This is the *graceful*-exit path; abnormal termination of our own
    /// process is instead handled by the Job Object's kill-on-close (see
    /// `JobObject` above), which runs even when this method is never
    /// called at all.
    pub fn cleanup(&self) {
        if !self.is_owned() {
            return;
        }
        let mut guard = self.process.lock().unwrap();
        if let Some(mut owned) = guard.take() {
            let pid = owned.child.id();
            #[cfg(target_os = "windows")]
            {
                let mut kill = Command::new("taskkill.exe");
                kill.args(["/PID", &pid.to_string(), "/T", "/F"]);
                kill.creation_flags(CREATE_NO_WINDOW);
                let _ = kill.status();
            }
            #[cfg(not(target_os = "windows"))]
            {
                let _ = owned.child.kill();
            }
            let _ = owned.child.wait();
            // `owned.job` drops here too, closing the Job Object handle;
            // harmless since the tree above is already dead by this point.
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

    /// Returns `Unreachable` for the first `unreachable_calls` probes, then
    /// `Healthy` forever after -- simulates a backend that becomes healthy
    /// partway through a startup wait.
    struct BecomesHealthyAfter {
        unreachable_calls: usize,
        calls: AtomicUsize,
    }

    impl HealthProbe for BecomesHealthyAfter {
        fn probe(&self) -> ProbeResult {
            let call_index = self.calls.fetch_add(1, Ordering::SeqCst);
            if call_index < self.unreachable_calls {
                ProbeResult::Unreachable
            } else {
                ProbeResult::Healthy
            }
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

    /// A spec whose process tree resembles PyInstaller one-file: the root
    /// process itself launches a *child* process and then keeps running,
    /// mirroring the bootloader -> unpacked-child pattern the real
    /// packaged backend exhibits (both processes alive at once).
    #[cfg(target_os = "windows")]
    fn spawn_spec_that_launches_a_child_and_stays_alive() -> SpawnSpec {
        SpawnSpec {
            program: "powershell".into(),
            args: vec![
                "-NoProfile".into(),
                "-Command".into(),
                "Start-Process -FilePath powershell -ArgumentList '-NoProfile','-Command','Start-Sleep -Seconds 8' -WindowStyle Hidden; Start-Sleep -Seconds 8".into(),
            ],
            current_dir: None,
            env: vec![],
        }
    }

    #[cfg(target_os = "windows")]
    fn child_pids_of(parent_pid: u32) -> Vec<u32> {
        let output = Command::new("powershell")
            .args([
                "-NoProfile",
                "-Command",
                &format!(
                    "(Get-CimInstance Win32_Process -Filter \"ParentProcessId={parent_pid}\").ProcessId"
                ),
            ])
            .output()
            .expect("query child processes via Get-CimInstance");
        String::from_utf8_lossy(&output.stdout)
            .lines()
            .filter_map(|line| line.trim().parse::<u32>().ok())
            .collect()
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

    #[test]
    #[cfg(target_os = "windows")]
    fn job_object_kill_on_close_terminates_owned_process_when_handle_closes_without_cleanup() {
        // Simulates abnormal desktop termination: the Job Object handle is
        // dropped directly (as it would be if our own process were killed
        // and Windows tore down its handles) *instead of* going through
        // `SidecarManager::cleanup()`'s graceful taskkill. The owned child
        // must still die -- via kill-on-close alone.
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&probe, long_sleep_spec());
        let pid = manager.owned_pid().expect("owned pid after spawn");

        {
            // Take the OwnedProcess out and drop its `job` field directly,
            // mirroring "the process's handles are closed but no cleanup
            // code runs". `std::process::Child` has no Drop impl that
            // kills/waits on the process, so dropping it too just releases
            // the Rust-side wrapper -- the assertion below is attributable
            // to the Job Object alone.
            let mut guard = manager.process.lock().unwrap();
            let mut owned = guard.take().expect("owned process present");
            drop(owned.job.take()); // closes the Job Object handle
            drop(owned.child);
        }
        manager.owned.store(false, Ordering::SeqCst);

        std::thread::sleep(Duration::from_millis(500));

        assert!(
            !process_is_running(pid),
            "kill-on-close Job Object should terminate the owned process once its handle closes"
        );
    }

    #[test]
    #[cfg(target_os = "windows")]
    fn job_object_supervision_also_terminates_a_child_the_owned_process_spawns() {
        // Mirrors the PyInstaller one-file bootloader -> unpacked-child
        // pattern: the root process we spawn launches its own child and
        // both stay alive. Job Object membership must cover that child
        // too, and closing the Job Object handle directly (not
        // `cleanup()`'s PID-targeted `taskkill /T`) must be what kills it
        // -- isolating the mechanism this test is actually about.
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&probe, spawn_spec_that_launches_a_child_and_stays_alive());
        let root_pid = manager.owned_pid().expect("owned pid after spawn");

        std::thread::sleep(Duration::from_millis(1500)); // let the root actually launch its child

        let child_pids = child_pids_of(root_pid);
        assert!(
            !child_pids.is_empty(),
            "test setup: root process should have spawned a child"
        );
        for pid in &child_pids {
            assert!(
                process_is_running(*pid),
                "test setup: child should be running before the Job Object handle closes"
            );
        }

        {
            // std::process::Child has no Drop impl that kills/waits on the
            // process -- dropping it just closes the Rust-side handle
            // wrapper, so this really does isolate "only the Job Object
            // handle closes" as the trigger, with no help from `cleanup()`.
            let mut guard = manager.process.lock().unwrap();
            let mut owned = guard.take().expect("owned process present");
            drop(owned.job.take());
            drop(owned.child);
        }
        manager.owned.store(false, Ordering::SeqCst);

        std::thread::sleep(Duration::from_millis(800));

        assert!(
            !process_is_running(root_pid),
            "root process should be terminated"
        );
        for pid in child_pids {
            assert!(
                !process_is_running(pid),
                "kill-on-close Job Object should terminate a child the owned root spawned, not just the root itself"
            );
        }
    }

    #[test]
    fn cleanup_is_safe_to_call_twice_in_a_row() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&probe, long_sleep_spec());

        manager.cleanup();
        manager.cleanup(); // must not panic, must remain a no-op the second time

        assert!(!manager.is_owned());
    }

    // -- wait_until_healthy timeout semantics (PART B: packaged cold-start
    // timeout hardening) --------------------------------------------------

    #[test]
    fn wait_until_healthy_reports_connected_as_soon_as_health_succeeds_before_timeout() {
        let manager = SidecarManager::new();
        let start_probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&start_probe, long_sleep_spec());

        // Becomes healthy after a couple of polls, well before a generous
        // timeout -- must return Connected promptly, not wait out the full
        // timeout window (the actual UX requirement: a long packaged
        // ceiling must never force a slow-feeling happy path).
        let probe = BecomesHealthyAfter {
            unreachable_calls: 2,
            calls: AtomicUsize::new(0),
        };

        let began = Instant::now();
        let status =
            manager.wait_until_healthy(&probe, Duration::from_secs(60), Duration::from_millis(20));
        let elapsed = began.elapsed();

        assert_eq!(status, SidecarStatus::Connected { owned: true });
        assert!(
            elapsed < Duration::from_secs(5),
            "should return promptly once healthy, not wait near the 60s ceiling (took {elapsed:?})"
        );

        manager.cleanup();
    }

    #[test]
    fn wait_until_healthy_reports_startup_timeout_once_the_deadline_passes() {
        let manager = SidecarManager::new();
        let start_probe = FixedProbe::new(ProbeResult::Unreachable);
        manager.start(&start_probe, long_sleep_spec());

        let probe = FixedProbe::new(ProbeResult::Unreachable);
        let status = manager.wait_until_healthy(
            &probe,
            Duration::from_millis(150),
            Duration::from_millis(30),
        );

        assert_eq!(
            status,
            SidecarStatus::StartupFailed("STARTUP_TIMEOUT".into())
        );

        manager.cleanup();
    }

    #[test]
    fn wait_until_healthy_reports_backend_exited_immediately_without_waiting_out_the_timeout() {
        let manager = SidecarManager::new();
        let start_probe = FixedProbe::new(ProbeResult::Unreachable);
        // A process that exits almost immediately on its own -- simulates
        // a packaged backend crashing during startup.
        let exits_immediately_spec = SpawnSpec {
            program: "cmd".into(),
            args: vec!["/C".into(), "exit".into(), "1".into()],
            current_dir: None,
            env: vec![],
        };
        manager.start(&start_probe, exits_immediately_spec);

        let probe = FixedProbe::new(ProbeResult::Unreachable);
        let began = Instant::now();
        // A long timeout: the point of this test is that early process
        // exit is detected well before the deadline, not that the deadline
        // itself works (covered by the STARTUP_TIMEOUT test above).
        let status =
            manager.wait_until_healthy(&probe, Duration::from_secs(30), Duration::from_millis(100));
        let elapsed = began.elapsed();

        match status {
            SidecarStatus::StartupFailed(reason) => {
                assert!(
                    reason.starts_with("BACKEND_EXITED_DURING_STARTUP"),
                    "unexpected failure reason: {reason}"
                );
            }
            other => {
                panic!("expected StartupFailed(BACKEND_EXITED_DURING_STARTUP...), got {other:?}")
            }
        }
        assert!(
            elapsed < Duration::from_secs(10),
            "early exit should be detected well before a 30s deadline (took {elapsed:?})"
        );
    }

    fn process_is_running(pid: u32) -> bool {
        let output = Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .expect("tasklist");
        String::from_utf8_lossy(&output.stdout).contains(&pid.to_string())
    }
}
