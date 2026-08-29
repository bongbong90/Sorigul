//! Native Windows shutdown boundary. The executor is a trait so automated
//! tests exercise the idempotence/guard logic through a fake instead of
//! ever invoking a real OS shutdown.

use std::sync::atomic::{AtomicBool, Ordering};

pub trait ShutdownExecutor: Send + Sync {
    fn execute(&self) -> Result<(), String>;
}

/// Fixed executable + fixed arguments only; no user input ever reaches the
/// command line.
pub struct RealShutdownExecutor;

impl ShutdownExecutor for RealShutdownExecutor {
    #[cfg(target_os = "windows")]
    fn execute(&self) -> Result<(), String> {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let status = std::process::Command::new("shutdown.exe")
            .args(["/s", "/t", "0"])
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map_err(|err| format!("SHUTDOWN_SPAWN_FAILED: {err}"))?;
        if status.success() {
            Ok(())
        } else {
            Err(format!("SHUTDOWN_EXIT_CODE: {:?}", status.code()))
        }
    }

    #[cfg(not(target_os = "windows"))]
    fn execute(&self) -> Result<(), String> {
        Err("UNSUPPORTED_PLATFORM".into())
    }
}

/// Guarantees the executor runs at most once per countdown cycle, even if
/// triggered repeatedly (duplicate polling, a stale "ready" response
/// racing a cancel, etc.). `reset` re-arms it for the next cycle once the
/// backend state has genuinely left the countdown/ready phases.
pub struct ShutdownGate {
    executed: AtomicBool,
}

impl Default for ShutdownGate {
    fn default() -> Self {
        Self::new()
    }
}

impl ShutdownGate {
    pub fn new() -> Self {
        Self {
            executed: AtomicBool::new(false),
        }
    }

    pub fn trigger<E: ShutdownExecutor>(&self, executor: &E) -> Result<(), String> {
        if self.executed.swap(true, Ordering::SeqCst) {
            return Ok(());
        }
        executor.execute()
    }

    pub fn reset(&self) {
        self.executed.store(false, Ordering::SeqCst);
    }

    /// Public for diagnostics/tests; not currently read by app code.
    #[allow(dead_code)]
    pub fn has_executed(&self) -> bool {
        self.executed.load(Ordering::SeqCst)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;

    #[derive(Default)]
    struct CountingExecutor {
        calls: AtomicUsize,
    }

    impl ShutdownExecutor for CountingExecutor {
        fn execute(&self) -> Result<(), String> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    #[test]
    fn trigger_invokes_executor_on_first_call() {
        let gate = ShutdownGate::new();
        let executor = CountingExecutor::default();

        gate.trigger(&executor).unwrap();

        assert_eq!(executor.calls.load(Ordering::SeqCst), 1);
        assert!(gate.has_executed());
    }

    #[test]
    fn trigger_is_idempotent_across_duplicate_ready_events() {
        let gate = ShutdownGate::new();
        let executor = CountingExecutor::default();

        gate.trigger(&executor).unwrap();
        gate.trigger(&executor).unwrap();
        gate.trigger(&executor).unwrap();

        assert_eq!(
            executor.calls.load(Ordering::SeqCst),
            1,
            "shutdown must execute exactly once"
        );
    }

    #[test]
    fn reset_re_arms_the_gate_for_a_new_countdown_cycle() {
        let gate = ShutdownGate::new();
        let executor = CountingExecutor::default();

        gate.trigger(&executor).unwrap();
        gate.reset();
        gate.trigger(&executor).unwrap();

        assert_eq!(executor.calls.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn never_triggered_gate_has_not_executed() {
        let gate = ShutdownGate::new();
        assert!(!gate.has_executed());
    }
}
