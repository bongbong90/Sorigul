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

/// Why supervising a freshly spawned owned backend failed. Each variant
/// keeps the identity of the failing step and maps to a stable
/// `StartupFailed` reason code -- a supervision failure is never collapsed
/// into "run it unsupervised anyway".
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SupervisionError {
    CreateJobObject,
    ConfigureJobObject,
    AssignToJobObject,
    /// Resuming the suspended child failed. Carries the resume helper's
    /// precise reason (`THREAD_RESUME_FAILED`, `THREAD_OPEN_FAILED`,
    /// `THREAD_SNAPSHOT_FAILED`, `NO_THREAD_FOUND_TO_RESUME`).
    ResumeChild(&'static str),
}

impl SupervisionError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::CreateJobObject => "JOB_OBJECT_CREATE_FAILED",
            Self::ConfigureJobObject => "JOB_OBJECT_CONFIGURE_FAILED",
            Self::AssignToJobObject => "JOB_OBJECT_ASSIGN_FAILED",
            Self::ResumeChild(reason) => reason,
        }
    }
}

/// A live supervision handle for one owned child. Dropping it releases
/// supervision -- on Windows that closes the kill-on-close Job Object
/// handle, which terminates every process assigned to the job.
pub trait SupervisedJob: Send {
    fn assign(&self, child: &Child) -> Result<(), SupervisionError>;
}

/// The steps that must *all* succeed before an owned backend may run:
/// create a kill-on-close job, assign the still-suspended child to it, then
/// resume it. A trait only so tests can inject a failure at each step
/// deterministically; production always uses `PlatformSupervisor`.
pub trait ProcessSupervisor: Send + Sync {
    /// Creates the job and configures kill-on-close.
    fn create_job(&self) -> Result<Box<dyn SupervisedJob>, SupervisionError>;
    fn resume(&self, child: &Child) -> Result<(), SupervisionError>;
}

/// Real supervisor: a Windows Job Object with kill-on-close. On other
/// targets the child is not spawned suspended and there is no job to join.
pub struct PlatformSupervisor;

#[cfg(target_os = "windows")]
impl ProcessSupervisor for PlatformSupervisor {
    fn create_job(&self) -> Result<Box<dyn SupervisedJob>, SupervisionError> {
        Ok(Box::new(JobObject::create_with_kill_on_close()?))
    }

    fn resume(&self, child: &Child) -> Result<(), SupervisionError> {
        resume_all_threads_of_process(child.id()).map_err(SupervisionError::ResumeChild)
    }
}

#[cfg(not(target_os = "windows"))]
struct NoJob;

#[cfg(not(target_os = "windows"))]
impl SupervisedJob for NoJob {
    fn assign(&self, _child: &Child) -> Result<(), SupervisionError> {
        Ok(())
    }
}

#[cfg(not(target_os = "windows"))]
impl ProcessSupervisor for PlatformSupervisor {
    fn create_job(&self) -> Result<Box<dyn SupervisedJob>, SupervisionError> {
        Ok(Box::new(NoJob))
    }

    fn resume(&self, _child: &Child) -> Result<(), SupervisionError> {
        Ok(())
    }
}

/// Runs every supervision step in order. On any failure the job (if one
/// was created) is dropped before returning, so an already-assigned child
/// is killed by kill-on-close; the caller still terminates and reaps the
/// exact child itself.
fn supervise(
    supervisor: &dyn ProcessSupervisor,
    child: &Child,
) -> Result<Box<dyn SupervisedJob>, SupervisionError> {
    let job = supervisor.create_job()?;
    job.assign(child)?;
    supervisor.resume(child)?;
    Ok(job)
}

/// A child this manager spawned but refused to adopt because supervision
/// failed. Kept for diagnostics/tests only; the child itself is gone.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RejectedChild {
    pub pid: u32,
    /// True once the terminated child was successfully waited on.
    pub reaped: bool,
}

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
    fn create_with_kill_on_close() -> Result<Self, SupervisionError> {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::JobObjects::{
            CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };

        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err(SupervisionError::CreateJobObject);
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
                return Err(SupervisionError::ConfigureJobObject);
            }

            Ok(Self { handle })
        }
    }
}

#[cfg(target_os = "windows")]
impl SupervisedJob for JobObject {
    /// Assigns an already-created (and, by construction here, still
    /// suspended) process to this job. Never assigns a process this
    /// manager did not itself spawn -- callers only ever pass a child
    /// `SidecarManager::spawn()` just created.
    fn assign(&self, child: &Child) -> Result<(), SupervisionError> {
        use windows_sys::Win32::System::JobObjects::AssignProcessToJobObject;
        let process_handle = child.as_raw_handle() as windows_sys::Win32::Foundation::HANDLE;
        let ok = unsafe { AssignProcessToJobObject(self.handle, process_handle) };
        if ok == 0 {
            return Err(SupervisionError::AssignToJobObject);
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

/// Resumes every thread owned by `pid`. Used to resume a child spawned
/// with `CREATE_SUSPENDED` only after it was successfully assigned to a
/// Job Object -- looked up via a thread snapshot rather than the
/// `CreateProcessW` thread handle, because `std::process::Child` does not
/// expose that handle. Since the child was created suspended, it has not
/// executed a single instruction yet, so Job Object assignment can never
/// race the child spawning a grandchild. Any thread that cannot be opened
/// or resumed is a failure: a partially resumed child is not "running".
#[cfg(target_os = "windows")]
fn resume_all_threads_of_process(pid: u32) -> Result<(), &'static str> {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD, THREADENTRY32,
    };
    use windows_sys::Win32::System::Threading::{OpenThread, ResumeThread, THREAD_SUSPEND_RESUME};

    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if snapshot == INVALID_HANDLE_VALUE {
            return Err("THREAD_SNAPSHOT_FAILED");
        }

        let mut entry: THREADENTRY32 = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
        let mut resumed_any = false;
        let mut failure: Option<&'static str> = None;

        if Thread32First(snapshot, &mut entry) != 0 {
            loop {
                if entry.th32OwnerProcessID == pid {
                    let thread_handle = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                    if thread_handle.is_null() {
                        failure.get_or_insert("THREAD_OPEN_FAILED");
                    } else {
                        // ResumeThread returns (DWORD)-1 on failure.
                        let previous_count = ResumeThread(thread_handle);
                        CloseHandle(thread_handle);
                        if previous_count == u32::MAX {
                            failure.get_or_insert("THREAD_RESUME_FAILED");
                        } else {
                            resumed_any = true;
                        }
                    }
                }
                if Thread32Next(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }

        CloseHandle(snapshot);
        match failure {
            Some(reason) => Err(reason),
            None if resumed_any => Ok(()),
            None => Err("NO_THREAD_FOUND_TO_RESUME"),
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

/// A spawned, fully supervised child together with its supervision job.
/// Only ever constructed after every supervision step succeeded. `job`
/// drops -- closing its handle -- whenever this struct does, which on
/// Windows is exactly the kill-on-close trigger. It is an `Option` only so
/// tests can drop the job handle in isolation.
struct OwnedProcess {
    child: Child,
    #[allow(dead_code)]
    job: Option<Box<dyn SupervisedJob>>,
}

/// Owns at most one backend child process. Never touches a process it did
/// not spawn itself. An owned child is either fully supervised (Job
/// Object created, kill-on-close configured, child assigned, child
/// resumed) or not running at all.
pub struct SidecarManager {
    process: Mutex<Option<OwnedProcess>>,
    owned: AtomicBool,
    supervisor: Box<dyn ProcessSupervisor>,
    last_rejected_child: Mutex<Option<RejectedChild>>,
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SidecarManager {
    pub fn new() -> Self {
        Self::with_supervisor(Box::new(PlatformSupervisor))
    }

    fn with_supervisor(supervisor: Box<dyn ProcessSupervisor>) -> Self {
        Self {
            process: Mutex::new(None),
            owned: AtomicBool::new(false),
            supervisor,
            last_rejected_child: Mutex::new(None),
        }
    }

    /// The most recent child that was spawned but terminated instead of
    /// adopted because supervision failed. Diagnostics/tests only.
    #[allow(dead_code)]
    pub fn last_rejected_child(&self) -> Option<RejectedChild> {
        *self.last_rejected_child.lock().unwrap()
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

        let mut child = command
            .spawn()
            .map_err(|err| format!("SPAWN_FAILED: {err}"))?;

        // Fail closed: the child is adopted (stored + owned=true) only
        // after the Job Object exists with kill-on-close, the child is
        // assigned to it, and the suspended child resumed. Anything less
        // and this exact child -- never anything found by PID/name search
        // -- is terminated and reaped here, and never becomes "owned".
        match supervise(self.supervisor.as_ref(), &child) {
            Ok(job) => {
                *self.process.lock().unwrap() = Some(OwnedProcess {
                    child,
                    job: Some(job),
                });
                self.owned.store(true, Ordering::SeqCst);
                Ok(())
            }
            Err(err) => {
                let pid = child.id();
                let _ = child.kill();
                let reaped = child.wait().is_ok();
                *self.last_rejected_child.lock().unwrap() = Some(RejectedChild { pid, reaped });
                Err(err.code().to_string())
            }
        }
    }

    /// Production startup orchestration: `start`, then -- only for a child
    /// this call just spawned -- wait for health. Any startup failure after
    /// an owned spawn (timeout, early exit, port taken by another service)
    /// terminates that owned child immediately instead of leaving it
    /// running until app exit. A reused external backend is never touched
    /// (`cleanup` is a no-op when nothing is owned).
    pub fn start_and_wait<P: HealthProbe>(
        &self,
        probe: &P,
        spec: SpawnSpec,
        timeout: Duration,
        interval: Duration,
    ) -> SidecarStatus {
        match self.start(probe, spec) {
            SidecarStatus::Starting => {
                let status = self.wait_until_healthy(probe, timeout, interval);
                if matches!(status, SidecarStatus::StartupFailed(_)) {
                    self.cleanup();
                }
                status
            }
            other => other,
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

    // -- Fail-closed Job Object supervision (AUD-PROC-001) -----------------

    #[derive(Clone, Copy, PartialEq, Eq, Debug)]
    enum FailAt {
        Create,
        Configure,
        Assign,
        Resume,
    }

    /// Wraps the real platform supervisor and injects a failure at exactly
    /// one step. Steps before the injected one run for real, so e.g. the
    /// resume-failure case exercises a genuinely assigned Job Object.
    struct FaultInjectingSupervisor {
        fail_at: FailAt,
    }

    struct FaultInjectingJob {
        inner: Box<dyn SupervisedJob>,
        fail_assign: bool,
    }

    impl SupervisedJob for FaultInjectingJob {
        fn assign(&self, child: &Child) -> Result<(), SupervisionError> {
            if self.fail_assign {
                return Err(SupervisionError::AssignToJobObject);
            }
            self.inner.assign(child)
        }
    }

    impl ProcessSupervisor for FaultInjectingSupervisor {
        fn create_job(&self) -> Result<Box<dyn SupervisedJob>, SupervisionError> {
            match self.fail_at {
                FailAt::Create => Err(SupervisionError::CreateJobObject),
                FailAt::Configure => Err(SupervisionError::ConfigureJobObject),
                FailAt::Assign | FailAt::Resume => Ok(Box::new(FaultInjectingJob {
                    inner: PlatformSupervisor.create_job()?,
                    fail_assign: self.fail_at == FailAt::Assign,
                })),
            }
        }

        fn resume(&self, child: &Child) -> Result<(), SupervisionError> {
            if self.fail_at == FailAt::Resume {
                return Err(SupervisionError::ResumeChild("THREAD_RESUME_FAILED"));
            }
            PlatformSupervisor.resume(child)
        }
    }

    fn assert_supervision_failure_is_fail_closed(fail_at: FailAt, expected_reason: &str) {
        let manager =
            SidecarManager::with_supervisor(Box::new(FaultInjectingSupervisor { fail_at }));
        let probe = FixedProbe::new(ProbeResult::Unreachable);

        let status = manager.start(&probe, long_sleep_spec());

        assert_eq!(
            status,
            SidecarStatus::StartupFailed(expected_reason.into()),
            "{fail_at:?}: supervision failure must surface its exact reason"
        );
        assert!(!manager.is_owned(), "{fail_at:?}: must stay owned=false");
        assert!(!manager.has_process(), "{fail_at:?}: no process slot");
        assert!(manager.owned_pid().is_none());
        assert_eq!(manager.is_owned_process_alive(), None);

        let rejected = manager
            .last_rejected_child()
            .expect("the spawned child must have been explicitly rejected");
        assert!(
            rejected.reaped,
            "{fail_at:?}: rejected child must be reaped"
        );
        assert!(
            !process_is_running(rejected.pid),
            "{fail_at:?}: the exact rejected child must be terminated"
        );

        // A later cleanup() has nothing to act on and must stay a no-op.
        manager.cleanup();
        assert!(!manager.is_owned());
    }

    #[test]
    fn job_object_create_failure_is_fail_closed() {
        assert_supervision_failure_is_fail_closed(FailAt::Create, "JOB_OBJECT_CREATE_FAILED");
    }

    #[test]
    fn job_object_configure_failure_is_fail_closed() {
        assert_supervision_failure_is_fail_closed(FailAt::Configure, "JOB_OBJECT_CONFIGURE_FAILED");
    }

    #[test]
    fn job_object_assign_failure_is_fail_closed() {
        assert_supervision_failure_is_fail_closed(FailAt::Assign, "JOB_OBJECT_ASSIGN_FAILED");
    }

    #[test]
    fn resume_failure_after_successful_assign_is_fail_closed() {
        assert_supervision_failure_is_fail_closed(FailAt::Resume, "THREAD_RESUME_FAILED");
    }

    #[test]
    fn supervision_error_codes_are_distinct_and_stable() {
        let codes = [
            SupervisionError::CreateJobObject.code(),
            SupervisionError::ConfigureJobObject.code(),
            SupervisionError::AssignToJobObject.code(),
            SupervisionError::ResumeChild("THREAD_RESUME_FAILED").code(),
        ];
        assert_eq!(
            codes,
            [
                "JOB_OBJECT_CREATE_FAILED",
                "JOB_OBJECT_CONFIGURE_FAILED",
                "JOB_OBJECT_ASSIGN_FAILED",
                "THREAD_RESUME_FAILED",
            ]
        );
    }

    #[test]
    fn successful_supervision_adopts_a_running_owned_child() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);

        assert_eq!(
            manager.start(&probe, long_sleep_spec()),
            SidecarStatus::Starting
        );
        assert!(manager.is_owned());
        assert_eq!(manager.is_owned_process_alive(), Some(true));
        assert!(manager.last_rejected_child().is_none());

        manager.cleanup();
    }

    // -- Startup failure cleanup (AUD-PROC-002) -----------------------------

    /// Replays `results` in order (repeating the last one) and records the
    /// manager's owned PID on every call, so a test can prove which exact
    /// child existed during startup and that it is gone afterwards.
    struct RecordingProbe<'a> {
        manager: &'a SidecarManager,
        results: Vec<ProbeResult>,
        calls: AtomicUsize,
        seen_pid: Mutex<Option<u32>>,
    }

    impl<'a> RecordingProbe<'a> {
        fn new(manager: &'a SidecarManager, results: Vec<ProbeResult>) -> Self {
            Self {
                manager,
                results,
                calls: AtomicUsize::new(0),
                seen_pid: Mutex::new(None),
            }
        }

        fn seen_pid(&self) -> Option<u32> {
            *self.seen_pid.lock().unwrap()
        }
    }

    impl HealthProbe for RecordingProbe<'_> {
        fn probe(&self) -> ProbeResult {
            if let Some(pid) = self.manager.owned_pid() {
                *self.seen_pid.lock().unwrap() = Some(pid);
            }
            let index = self.calls.fetch_add(1, Ordering::SeqCst);
            self.results[index.min(self.results.len() - 1)]
        }
    }

    fn assert_owned_child_cleaned_up(manager: &SidecarManager, pid: Option<u32>) {
        let pid = pid.expect("an owned child must have existed during startup");
        assert!(!manager.is_owned());
        assert!(!manager.has_process());
        assert!(manager.owned_pid().is_none());
        std::thread::sleep(Duration::from_millis(300));
        assert!(
            !process_is_running(pid),
            "failed owned child must be terminated immediately, not at app exit"
        );
    }

    #[test]
    fn startup_timeout_immediately_cleans_up_the_owned_child() {
        let manager = SidecarManager::new();
        let probe = RecordingProbe::new(&manager, vec![ProbeResult::Unreachable]);

        let status = manager.start_and_wait(
            &probe,
            long_sleep_spec(),
            Duration::from_millis(300),
            Duration::from_millis(50),
        );

        assert_eq!(
            status,
            SidecarStatus::StartupFailed("STARTUP_TIMEOUT".into())
        );
        assert_owned_child_cleaned_up(&manager, probe.seen_pid());
    }

    #[test]
    fn port_taken_during_startup_immediately_cleans_up_the_owned_child() {
        let manager = SidecarManager::new();
        let probe = RecordingProbe::new(
            &manager,
            vec![
                ProbeResult::Unreachable,
                ProbeResult::Unreachable,
                ProbeResult::RespondingUnexpected,
            ],
        );

        let status = manager.start_and_wait(
            &probe,
            long_sleep_spec(),
            Duration::from_secs(10),
            Duration::from_millis(50),
        );

        assert_eq!(
            status,
            SidecarStatus::StartupFailed("PORT_OCCUPIED_BY_OTHER_SERVICE".into())
        );
        assert_owned_child_cleaned_up(&manager, probe.seen_pid());
    }

    #[test]
    fn backend_exit_during_startup_releases_ownership_immediately() {
        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Unreachable);
        let exits_immediately_spec = SpawnSpec {
            program: "cmd".into(),
            args: vec!["/C".into(), "exit".into(), "1".into()],
            current_dir: None,
            env: vec![],
        };

        let status = manager.start_and_wait(
            &probe,
            exits_immediately_spec,
            Duration::from_secs(30),
            Duration::from_millis(100),
        );

        match status {
            SidecarStatus::StartupFailed(reason) => {
                assert!(
                    reason.starts_with("BACKEND_EXITED_DURING_STARTUP"),
                    "{reason}"
                )
            }
            other => panic!("expected BACKEND_EXITED_DURING_STARTUP, got {other:?}"),
        }
        assert!(!manager.is_owned());
        assert!(!manager.has_process());
    }

    #[test]
    fn healthy_startup_keeps_the_owned_child() {
        let manager = SidecarManager::new();
        let probe = RecordingProbe::new(
            &manager,
            vec![ProbeResult::Unreachable, ProbeResult::Healthy],
        );

        let status = manager.start_and_wait(
            &probe,
            long_sleep_spec(),
            Duration::from_secs(10),
            Duration::from_millis(50),
        );

        assert_eq!(status, SidecarStatus::Connected { owned: true });
        assert!(manager.is_owned());
        assert_eq!(manager.is_owned_process_alive(), Some(true));

        manager.cleanup();
    }

    #[test]
    fn reused_external_backend_is_never_cleaned_up_by_startup_orchestration() {
        // Stands in for an already-running external backend: the manager
        // only ever sees it through a Healthy probe and must never adopt,
        // clean up, or kill it.
        let mut external = Command::new("powershell")
            .args(["-NoProfile", "-Command", "Start-Sleep -Seconds 6"])
            .spawn()
            .expect("spawn stand-in external process");
        let external_pid = external.id();

        let manager = SidecarManager::new();
        let probe = FixedProbe::new(ProbeResult::Healthy);
        let status = manager.start_and_wait(
            &probe,
            long_sleep_spec(),
            Duration::from_millis(200),
            Duration::from_millis(50),
        );

        assert_eq!(status, SidecarStatus::Connected { owned: false });
        assert!(!manager.is_owned());
        assert!(!manager.has_process());
        manager.cleanup();
        assert!(
            process_is_running(external_pid),
            "external backend must survive startup orchestration and cleanup()"
        );

        let _ = external.kill();
        let _ = external.wait();
    }

    fn process_is_running(pid: u32) -> bool {
        let output = Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .expect("tasklist");
        String::from_utf8_lossy(&output.stdout).contains(&pid.to_string())
    }
}
