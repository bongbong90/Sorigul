//! Sorigul-owned completion toast (Issue #110), the Windows equivalent of
//! the Legacy `TrayToastWindow`: one reusable, pre-created window whose
//! content is replaced by every new FILE_COMPLETED / JOB_COMPLETED event,
//! shown bottom-right and hidden again after a Legacy-length timeout.
//!
//! This module holds only the Tauri-independent logic (request validation,
//! payload replacement, show/hide generations, placement) so it is unit
//! testable without a running `AppHandle`. The payload carries opaque
//! identities only -- never a filesystem path.

use std::time::Duration;

use serde::{Deserialize, Serialize};

/// Label of the single toast window declared in `tauri.conf.json`.
pub const COMPLETION_TOAST_LABEL: &str = "completion-toast";
/// Event delivered only to the toast window when its content changes.
pub const COMPLETION_TOAST_EVENT: &str = "sorigul://completion-toast";
/// Legacy `show_custom_toast(timeout_ms=7200)`.
pub const COMPLETION_TOAST_TIMEOUT: Duration = Duration::from_millis(7200);
/// Legacy `show_at_bottom_right` margin, in logical pixels.
pub const COMPLETION_TOAST_MARGIN: f64 = 16.0;

const SUPPORTED_INTENTS: [&str; 2] = ["FILE_COMPLETED", "JOB_COMPLETED"];
const MAX_MESSAGE_CHARS: usize = 300;
const MAX_FILE_ID_CHARS: usize = 255;

/// Backend Job ids are UUIDs. Anything else is refused before it is ever
/// placed in a backend URL.
pub fn is_opaque_job_id(job_id: &str) -> bool {
    !job_id.is_empty()
        && job_id.len() <= 64
        && job_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
}

/// What the main window's notification hook sends for one completion event.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct CompletionToastRequest {
    pub desktop_intent: String,
    pub job_id: String,
    pub file_id: Option<String>,
    pub message: String,
}

/// What the toast window renders. `generation` identifies one show so a
/// stale auto-hide can never hide a newer toast.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CompletionToastPayload {
    pub generation: u64,
    pub desktop_intent: String,
    pub job_id: String,
    pub file_id: Option<String>,
    pub message: String,
}

impl CompletionToastRequest {
    pub fn validate(self) -> Result<Self, String> {
        if !SUPPORTED_INTENTS.contains(&self.desktop_intent.as_str()) {
            return Err("UNSUPPORTED_INTENT".into());
        }
        if !is_opaque_job_id(&self.job_id) {
            return Err("INVALID_JOB_ID".into());
        }
        let message: String = self
            .message
            .trim()
            .chars()
            .take(MAX_MESSAGE_CHARS)
            .collect();
        if message.is_empty() {
            return Err("EMPTY_MESSAGE".into());
        }
        let file_id = self
            .file_id
            .map(|id| id.chars().take(MAX_FILE_ID_CHARS).collect::<String>())
            .filter(|id| !id.is_empty());
        Ok(Self {
            desktop_intent: self.desktop_intent,
            job_id: self.job_id,
            file_id,
            message,
        })
    }
}

#[derive(Debug, Default)]
pub struct CompletionToastState {
    current: Option<CompletionToastPayload>,
    generation: u64,
    visible: bool,
}

impl CompletionToastState {
    /// Replaces the content (never stacks a second toast) and starts a new
    /// generation, which also resets the auto-hide timeout.
    pub fn present(&mut self, request: CompletionToastRequest) -> CompletionToastPayload {
        self.generation += 1;
        let payload = CompletionToastPayload {
            generation: self.generation,
            desktop_intent: request.desktop_intent,
            job_id: request.job_id,
            file_id: request.file_id,
            message: request.message,
        };
        self.current = Some(payload.clone());
        self.visible = true;
        payload
    }

    /// The content the toast should show right now, if it is showing.
    pub fn snapshot(&self) -> Option<CompletionToastPayload> {
        self.current.clone().filter(|_| self.visible)
    }

    pub fn dismiss(&mut self) {
        self.visible = false;
    }

    /// Auto-hide for `generation`: true only if that exact show is still
    /// the visible one (a newer event has not replaced it).
    pub fn expire(&mut self, generation: u64) -> bool {
        if self.visible && self.generation == generation {
            self.visible = false;
            true
        } else {
            false
        }
    }
}

/// Bottom-right of a monitor work area (taskbar excluded), clamped so the
/// toast never starts left of / above the work area even when the area is
/// smaller than the toast. All values are physical pixels.
pub fn bottom_right_position(
    area_origin: (i32, i32),
    area_size: (u32, u32),
    toast_size: (u32, u32),
    margin: i32,
) -> (i32, i32) {
    let right = i64::from(area_origin.0) + i64::from(area_size.0);
    let bottom = i64::from(area_origin.1) + i64::from(area_size.1);
    let x = (right - i64::from(toast_size.0) - i64::from(margin)).max(i64::from(area_origin.0));
    let y = (bottom - i64::from(toast_size.1) - i64::from(margin)).max(i64::from(area_origin.1));
    (
        i32::try_from(x).unwrap_or(area_origin.0),
        i32::try_from(y).unwrap_or(area_origin.1),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(intent: &str, message: &str) -> CompletionToastRequest {
        CompletionToastRequest {
            desktop_intent: intent.into(),
            job_id: "0f8fad5b-d9cb-469f-a165-70867728950e".into(),
            file_id: Some("개념완성_민법_8주차_4강".into()),
            message: message.into(),
        }
    }

    #[test]
    fn accepts_only_completion_intents() {
        assert!(request("FILE_COMPLETED", "파일 전사 완료: a.mp3")
            .validate()
            .is_ok());
        assert!(request("JOB_COMPLETED", "작업 종료: 성공 1개, 실패 0개")
            .validate()
            .is_ok());
        for other in [
            "SHUTDOWN_COUNTDOWN_STARTED",
            "SHUTDOWN_CANCELLED",
            "",
            "file_completed",
        ] {
            assert_eq!(
                request(other, "x").validate(),
                Err("UNSUPPORTED_INTENT".to_string())
            );
        }
    }

    #[test]
    fn rejects_non_opaque_job_ids() {
        for bad in [
            "",
            "../jobs",
            "a/b",
            "a?b=c",
            "C:\\Users\\x",
            "id with space",
            &"a".repeat(65),
        ] {
            let mut req = request("JOB_COMPLETED", "done");
            req.job_id = bad.to_string();
            assert_eq!(req.validate(), Err("INVALID_JOB_ID".to_string()), "{bad}");
        }
        assert!(is_opaque_job_id("0f8fad5b-d9cb-469f-a165-70867728950e"));
    }

    #[test]
    fn message_is_trimmed_bounded_and_required() {
        let long = "가".repeat(1000);
        let valid = request("FILE_COMPLETED", &long).validate().unwrap();
        assert_eq!(valid.message.chars().count(), 300);
        assert_eq!(
            request("FILE_COMPLETED", "   ").validate(),
            Err("EMPTY_MESSAGE".to_string())
        );
    }

    #[test]
    fn single_toast_payload_is_replaced_not_stacked() {
        let mut state = CompletionToastState::default();
        let first = state.present(request("FILE_COMPLETED", "first").validate().unwrap());
        let second = state.present(request("JOB_COMPLETED", "second").validate().unwrap());
        assert!(second.generation > first.generation);
        let snapshot = state.snapshot().expect("visible toast");
        assert_eq!(snapshot, second);
        assert_eq!(snapshot.message, "second");
    }

    #[test]
    fn stale_timeout_does_not_hide_a_newer_toast() {
        let mut state = CompletionToastState::default();
        let first = state.present(request("FILE_COMPLETED", "first").validate().unwrap());
        let second = state.present(request("FILE_COMPLETED", "second").validate().unwrap());
        assert!(!state.expire(first.generation), "old timer must be a no-op");
        assert!(state.snapshot().is_some());
        assert!(state.expire(second.generation));
        assert!(state.snapshot().is_none());
        assert!(!state.expire(second.generation), "expiry is idempotent");
    }

    #[test]
    fn dismiss_hides_and_next_event_shows_again() {
        let mut state = CompletionToastState::default();
        assert!(state.snapshot().is_none(), "nothing before the first event");
        let first = state.present(request("FILE_COMPLETED", "first").validate().unwrap());
        state.dismiss();
        assert!(state.snapshot().is_none());
        assert!(!state.expire(first.generation));
        state.present(request("JOB_COMPLETED", "next").validate().unwrap());
        assert_eq!(state.snapshot().unwrap().message, "next");
    }

    #[test]
    fn payload_carries_opaque_identities_only() {
        let mut state = CompletionToastState::default();
        let payload = state.present(request("FILE_COMPLETED", "done").validate().unwrap());
        // Exhaustive: adding any field (e.g. a folder path) breaks this test.
        let CompletionToastPayload {
            generation: _,
            desktop_intent: _,
            job_id: _,
            file_id: _,
            message: _,
        } = payload;
    }

    #[test]
    fn bottom_right_uses_work_area_and_margin() {
        // 1920x1080 primary with a 40px taskbar -> work area 1920x1040.
        assert_eq!(
            bottom_right_position((0, 0), (1920, 1040), (360, 176), 16),
            (1920 - 360 - 16, 1040 - 176 - 16)
        );
    }

    #[test]
    fn bottom_right_on_secondary_monitor_with_negative_origin() {
        assert_eq!(
            bottom_right_position((-2560, -200), (2560, 1400), (540, 264), 24),
            (-540 - 24, 1200 - 264 - 24)
        );
    }

    #[test]
    fn bottom_right_never_leaves_a_tiny_work_area() {
        assert_eq!(
            bottom_right_position((100, 50), (200, 100), (360, 176), 16),
            (100, 50)
        );
    }
}
