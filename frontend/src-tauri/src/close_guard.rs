//! Active-work close protection (#128).
//!
//! A main-window close with `close_behavior = "exit"` ends the app only when
//! the backend confirms no critical work (transcription run or Drive upload)
//! is in progress. The window event callback never blocks: it prevents the
//! close, and one background check asks the backend's read-only close guard.
//! Active work, or any doubt about it, hides the window to the tray instead.
//! The tray "종료" item (#174) goes through the very same check.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::Duration;

use super::{extract_json_string, BACKEND_PORT};

/// Short on purpose: a local read-only snapshot; X must never feel stuck.
pub const CLOSE_GUARD_TIMEOUT: Duration = Duration::from_millis(1500);

pub fn close_guard_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}/api/desktop/close-guard")
}

#[derive(Debug, Clone, PartialEq)]
pub enum ActiveWork {
    Transcription {
        current_file: Option<String>,
        progress: Option<f64>,
    },
    Drive,
}

#[derive(Debug, Clone, PartialEq)]
pub enum GuardReport {
    Idle,
    Active(ActiveWork),
}

/// What the CloseRequested callback does right away (the close itself is
/// always prevented first).
#[derive(Debug, PartialEq, Eq)]
pub enum CloseRequestAction {
    /// `tray`: hide immediately, no backend check.
    HideNow,
    /// `exit`: start the single background close-guard check.
    CheckCriticalWork,
    /// `exit` while a check is already pending: coalesced, nothing to do.
    AlreadyChecking,
}

/// Where a finished close-guard check leads.
#[derive(Debug, Clone, PartialEq)]
pub enum CloseOutcome {
    /// Confirmed active work: hide to tray, keep everything running.
    ProtectedHide(ActiveWork),
    /// Confirmed idle: real exit through the centralized ExitRequested path.
    ConfirmedExit,
    /// The guard could not be read: never exit on doubt.
    SafeHide,
    /// The user reopened the window while the check was pending.
    Superseded,
}

/// Single pending check + generation so a late "idle" answer cannot close a
/// window the user has reopened in the meantime.
#[derive(Default)]
pub struct CloseCheck {
    in_progress: AtomicBool,
    generation: AtomicU64,
}

impl CloseCheck {
    pub fn on_close_requested(&self, behavior: &str) -> (CloseRequestAction, u64) {
        let generation = self.generation.load(Ordering::SeqCst);
        if behavior != "exit" {
            return (CloseRequestAction::HideNow, generation);
        }
        match self
            .in_progress
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        {
            Ok(_) => (CloseRequestAction::CheckCriticalWork, generation),
            Err(_) => (CloseRequestAction::AlreadyChecking, generation),
        }
    }

    /// Tray "종료" (#174): always the guarded exit path, whatever
    /// `close_behavior` says, through the same single pending check as X.
    /// `Some(generation)` starts the check; `None` means one is already
    /// pending (repeated clicks coalesce).
    pub fn on_exit_requested(&self) -> Option<u64> {
        match self.on_close_requested("exit") {
            (CloseRequestAction::CheckCriticalWork, generation) => Some(generation),
            _ => None,
        }
    }

    /// The window was shown again (tray "앱 열기").
    pub fn window_reopened(&self) {
        self.generation.fetch_add(1, Ordering::SeqCst);
    }

    /// Resolves a finished check and releases the pending slot.
    pub fn finish(&self, started: u64, result: Result<GuardReport, String>) -> CloseOutcome {
        let outcome = match result {
            Ok(GuardReport::Active(work)) => CloseOutcome::ProtectedHide(work),
            Ok(GuardReport::Idle) if self.generation.load(Ordering::SeqCst) != started => {
                CloseOutcome::Superseded
            }
            Ok(GuardReport::Idle) => CloseOutcome::ConfirmedExit,
            Err(_) => CloseOutcome::SafeHide,
        };
        self.in_progress.store(false, Ordering::SeqCst);
        outcome
    }
}

/// Blocking GET -- only ever called from the background close-check thread.
pub fn fetch_close_guard(url: &str) -> Result<GuardReport, String> {
    let agent = ureq::AgentBuilder::new()
        .timeout(CLOSE_GUARD_TIMEOUT)
        .build();
    let response = match agent.get(url).call() {
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
    parse_close_guard(&body)
}

/// Strict minimal parse: anything but a consistent guard object is an error
/// (which the caller turns into a safe hide).
pub fn parse_close_guard(body: &str) -> Result<GuardReport, String> {
    let trimmed = body.trim();
    if !trimmed.starts_with('{') || !trimmed.ends_with('}') {
        return Err("GUARD_PARSE_ERROR: not an object".into());
    }
    let protect = match json_scalar(trimmed, "protect_exit") {
        Some("true") => true,
        Some("false") => false,
        _ => return Err("GUARD_PARSE_ERROR: protect_exit".into()),
    };
    let activity = extract_json_string(trimmed, "activity")
        .ok_or_else(|| "GUARD_PARSE_ERROR: activity".to_string())?;
    match (protect, activity.as_str()) {
        (false, "idle") => Ok(GuardReport::Idle),
        (true, "transcription") => Ok(GuardReport::Active(ActiveWork::Transcription {
            current_file: extract_json_string(trimmed, "current_file")
                .filter(|name| !name.trim().is_empty()),
            progress: json_scalar(trimmed, "progress").and_then(|raw| raw.parse::<f64>().ok()),
        })),
        (true, "drive") => Ok(GuardReport::Active(ActiveWork::Drive)),
        _ => Err("GUARD_PARSE_ERROR: inconsistent guard".into()),
    }
}

/// Raw non-string value of a top-level key (`true`, `42.5`, `null`).
fn json_scalar<'a>(body: &'a str, key: &str) -> Option<&'a str> {
    let search = format!("\"{key}\":");
    let start = body.find(&search)? + search.len();
    let rest = body[start..].trim_start();
    let end = rest.find([',', '}']).unwrap_or(rest.len());
    Some(rest[..end].trim())
}

/// OS notice text. Only a file name and progress -- never a folder path.
pub fn notice_body(outcome: &CloseOutcome) -> Option<String> {
    match outcome {
        CloseOutcome::ProtectedHide(ActiveWork::Transcription {
            current_file,
            progress,
        }) => {
            let mut body =
                String::from("전사 작업은 계속 진행 중입니다. 앱은 Tray로 이동했습니다.");
            if let Some(name) = current_file {
                body.push_str(&format!("\n현재 파일: {}", file_name_only(name)));
            }
            if let Some(value) = progress.filter(|value| value.is_finite()) {
                body.push_str(&format!("\n진행률: {}%", value.clamp(0.0, 100.0).round()));
            }
            Some(body)
        }
        CloseOutcome::ProtectedHide(ActiveWork::Drive) => {
            Some("Google Drive 업로드가 진행 중입니다. 앱은 Tray로 이동했습니다.".into())
        }
        CloseOutcome::SafeHide => {
            Some("작업 상태를 확인하지 못해 안전하게 Tray로 이동했습니다.".into())
        }
        CloseOutcome::ConfirmedExit | CloseOutcome::Superseded => None,
    }
}

fn file_name_only(name: &str) -> &str {
    name.rsplit(['\\', '/']).next().unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    fn transcription(file: Option<&str>, progress: Option<f64>) -> ActiveWork {
        ActiveWork::Transcription {
            current_file: file.map(str::to_string),
            progress,
        }
    }

    #[test]
    fn tray_behavior_hides_immediately_without_a_check() {
        let check = CloseCheck::default();
        assert_eq!(
            check.on_close_requested("tray").0,
            CloseRequestAction::HideNow
        );
        assert_eq!(
            check.on_close_requested("tray").0,
            CloseRequestAction::HideNow
        );
    }

    #[test]
    fn exit_behavior_checks_once_and_coalesces_repeated_x() {
        let check = CloseCheck::default();
        let (first, generation) = check.on_close_requested("exit");
        assert_eq!(first, CloseRequestAction::CheckCriticalWork);
        assert_eq!(
            check.on_close_requested("exit").0,
            CloseRequestAction::AlreadyChecking
        );
        assert_eq!(
            check.on_close_requested("exit").0,
            CloseRequestAction::AlreadyChecking
        );

        let outcome = check.finish(generation, Ok(GuardReport::Active(ActiveWork::Drive)));
        assert_eq!(outcome, CloseOutcome::ProtectedHide(ActiveWork::Drive));
        // Hidden, then reopened and closed again: a fresh check is allowed.
        check.window_reopened();
        assert_eq!(
            check.on_close_requested("exit").0,
            CloseRequestAction::CheckCriticalWork
        );
    }

    #[test]
    fn exit_outcomes_follow_the_guard_and_fail_safe() {
        let cases = [
            (
                Ok(GuardReport::Active(transcription(
                    Some("A.mp3"),
                    Some(42.0),
                ))),
                CloseOutcome::ProtectedHide(transcription(Some("A.mp3"), Some(42.0))),
            ),
            (
                Ok(GuardReport::Active(ActiveWork::Drive)),
                CloseOutcome::ProtectedHide(ActiveWork::Drive),
            ),
            (Ok(GuardReport::Idle), CloseOutcome::ConfirmedExit),
            (Err("BACKEND_UNREACHABLE".into()), CloseOutcome::SafeHide),
            (Err("GUARD_PARSE_ERROR".into()), CloseOutcome::SafeHide),
        ];
        for (result, expected) in cases {
            let check = CloseCheck::default();
            let (_, generation) = check.on_close_requested("exit");
            assert_eq!(check.finish(generation, result), expected);
        }
    }

    #[test]
    fn late_idle_answer_does_not_exit_a_reopened_window() {
        let check = CloseCheck::default();
        let (_, generation) = check.on_close_requested("exit");
        check.window_reopened();
        assert_eq!(
            check.finish(generation, Ok(GuardReport::Idle)),
            CloseOutcome::Superseded
        );
        // Active work still hides even if reopened: hiding never loses work.
        let (_, generation) = check.on_close_requested("exit");
        check.window_reopened();
        assert!(matches!(
            check.finish(generation, Ok(GuardReport::Active(ActiveWork::Drive))),
            CloseOutcome::ProtectedHide(_)
        ));
        assert_eq!(
            check.on_close_requested("exit").0,
            CloseRequestAction::CheckCriticalWork
        );
    }

    #[test]
    fn tray_exit_always_checks_and_coalesces_repeated_clicks() {
        let check = CloseCheck::default();
        let generation = check
            .on_exit_requested()
            .expect("first click starts a check");
        assert_eq!(check.on_exit_requested(), None);
        assert_eq!(check.on_exit_requested(), None);
        // The X button shares the same pending slot.
        assert_eq!(
            check.on_close_requested("exit").0,
            CloseRequestAction::AlreadyChecking
        );
        assert_eq!(
            check.finish(generation, Ok(GuardReport::Idle)),
            CloseOutcome::ConfirmedExit
        );
        assert!(check.on_exit_requested().is_some(), "slot released");
    }

    #[test]
    fn tray_exit_is_refused_while_x_check_is_pending() {
        let check = CloseCheck::default();
        let (_, generation) = check.on_close_requested("exit");
        assert_eq!(check.on_exit_requested(), None);
        check.finish(generation, Ok(GuardReport::Active(ActiveWork::Drive)));
        assert!(check.on_exit_requested().is_some());
    }

    #[test]
    fn tray_exit_outcomes_follow_the_guard_and_fail_safe() {
        let cases = [
            (Ok(GuardReport::Idle), CloseOutcome::ConfirmedExit),
            (
                Ok(GuardReport::Active(transcription(Some("A.mp3"), Some(7.0)))),
                CloseOutcome::ProtectedHide(transcription(Some("A.mp3"), Some(7.0))),
            ),
            (
                Ok(GuardReport::Active(ActiveWork::Drive)),
                CloseOutcome::ProtectedHide(ActiveWork::Drive),
            ),
            (Err("BACKEND_UNREACHABLE".into()), CloseOutcome::SafeHide),
            (
                Err("BACKEND_ERROR: HTTP 500".into()),
                CloseOutcome::SafeHide,
            ),
            (Err("GUARD_PARSE_ERROR".into()), CloseOutcome::SafeHide),
            (
                Err("BACKEND_UNREACHABLE: timed out".into()),
                CloseOutcome::SafeHide,
            ),
        ];
        for (result, expected) in cases {
            let check = CloseCheck::default();
            let generation = check.on_exit_requested().unwrap();
            assert_eq!(check.finish(generation, result), expected);
        }
    }

    #[test]
    fn tray_exit_late_idle_after_reopen_is_superseded() {
        let check = CloseCheck::default();
        let generation = check.on_exit_requested().unwrap();
        check.window_reopened();
        assert_eq!(
            check.finish(generation, Ok(GuardReport::Idle)),
            CloseOutcome::Superseded
        );
    }

    #[test]
    fn parses_valid_guard_snapshots() {
        assert_eq!(
            parse_close_guard(
                r#"{"protect_exit":false,"activity":"idle","job_id":null,"current_file":null,"progress":null}"#
            ),
            Ok(GuardReport::Idle)
        );
        assert_eq!(
            parse_close_guard(
                r#"{"protect_exit":true,"activity":"transcription","job_id":"0f8f","current_file":"\uac15\uc758 A.mp3","progress":42.5}"#
            ),
            Ok(GuardReport::Active(transcription(
                Some("강의 A.mp3"),
                Some(42.5)
            )))
        );
        assert_eq!(
            parse_close_guard(
                r#"{"protect_exit":true,"activity":"transcription","job_id":null,"current_file":null,"progress":null}"#
            ),
            Ok(GuardReport::Active(transcription(None, None)))
        );
        assert_eq!(
            parse_close_guard(
                r#"{"protect_exit":true,"activity":"drive","job_id":"0f8f","current_file":"A.mp3","progress":null}"#
            ),
            Ok(GuardReport::Active(ActiveWork::Drive))
        );
    }

    #[test]
    fn malformed_or_inconsistent_guard_is_an_error() {
        for body in [
            "",
            "null",
            "<html>proxy</html>",
            r#"{"detail":"Invalid host header"}"#,
            r#"{"protect_exit":"false","activity":"idle"}"#,
            r#"{"protect_exit":false}"#,
            r#"{"protect_exit":false,"activity":"transcription"}"#,
            r#"{"protect_exit":true,"activity":"idle"}"#,
            r#"{"protect_exit":true,"activity":"unknown"}"#,
            r#"{"protect_exit":false,"activity":"idle""#,
        ] {
            assert!(parse_close_guard(body).is_err(), "{body}");
        }
    }

    #[test]
    fn guard_url_is_the_fixed_loopback_route() {
        assert_eq!(
            close_guard_url(),
            "http://127.0.0.1:8000/api/desktop/close-guard"
        );
    }

    fn serve_once(status_line: &'static str, body: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buffer = [0u8; 2048];
                let _ = stream.read(&mut buffer);
                let response = format!(
                    "{status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(response.as_bytes());
            }
        });
        format!("http://127.0.0.1:{port}/api/desktop/close-guard")
    }

    #[test]
    fn fetch_reads_a_live_guard_response() {
        let url = serve_once(
            "HTTP/1.1 200 OK",
            r#"{"protect_exit":true,"activity":"drive","job_id":null,"current_file":null,"progress":null}"#,
        );
        assert_eq!(
            fetch_close_guard(&url),
            Ok(GuardReport::Active(ActiveWork::Drive))
        );
    }

    #[test]
    fn fetch_failures_all_lead_to_safe_hide() {
        let unreachable = {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let port = listener.local_addr().unwrap().port();
            drop(listener);
            format!("http://127.0.0.1:{port}/api/desktop/close-guard")
        };
        let urls = [
            unreachable,
            serve_once("HTTP/1.1 500 Internal Server Error", r#"{"detail":"x"}"#),
            serve_once(
                "HTTP/1.1 400 Bad Request",
                r#"{"detail":"Invalid host header"}"#,
            ),
            serve_once("HTTP/1.1 200 OK", "not json"),
        ];
        for url in urls {
            let result = fetch_close_guard(&url);
            assert!(result.is_err(), "{url}: {result:?}");
            let check = CloseCheck::default();
            let (_, generation) = check.on_close_requested("exit");
            assert_eq!(check.finish(generation, result), CloseOutcome::SafeHide);
        }
    }

    #[test]
    fn stalled_backend_times_out_into_safe_hide() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            // Accept and hold the connection open without ever answering.
            if let Ok((stream, _)) = listener.accept() {
                std::thread::sleep(CLOSE_GUARD_TIMEOUT * 3);
                drop(stream);
            }
        });
        let url = format!("http://127.0.0.1:{port}/api/desktop/close-guard");
        let started = std::time::Instant::now();
        let result = fetch_close_guard(&url);
        assert!(result.is_err(), "{result:?}");
        assert!(started.elapsed() < CLOSE_GUARD_TIMEOUT * 2);
        let check = CloseCheck::default();
        let generation = check.on_exit_requested().unwrap();
        assert_eq!(check.finish(generation, result), CloseOutcome::SafeHide);
    }

    #[test]
    fn notices_explain_the_hide_without_paths() {
        let transcription_notice = notice_body(&CloseOutcome::ProtectedHide(transcription(
            Some("C:\\Users\\me\\비밀\\강의 A.mp3"),
            Some(42.4),
        )))
        .unwrap();
        assert!(transcription_notice
            .starts_with("전사 작업은 계속 진행 중입니다. 앱은 Tray로 이동했습니다."));
        assert!(transcription_notice.contains("현재 파일: 강의 A.mp3"));
        assert!(transcription_notice.contains("진행률: 42%"));
        assert!(!transcription_notice.contains("비밀") && !transcription_notice.contains("Users"));

        assert_eq!(
            notice_body(&CloseOutcome::ProtectedHide(ActiveWork::Drive)).unwrap(),
            "Google Drive 업로드가 진행 중입니다. 앱은 Tray로 이동했습니다."
        );
        assert_eq!(
            notice_body(&CloseOutcome::SafeHide).unwrap(),
            "작업 상태를 확인하지 못해 안전하게 Tray로 이동했습니다."
        );
        assert_eq!(notice_body(&CloseOutcome::ConfirmedExit), None);
        assert_eq!(notice_body(&CloseOutcome::Superseded), None);
    }
}
