use serde::Deserialize;

pub(crate) const IDLE_TRAY_TOOLTIP: &str = "Sorigul - 대기 중";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct TrayProgressPayload {
    pub(crate) status: String,
    pub(crate) current_file: Option<String>,
    pub(crate) current_progress: Option<f64>,
}

fn status_label(status: &str) -> Option<&'static str> {
    match status {
        "WAITING" | "PREPARING" => Some("준비 중"),
        "TRANSCRIBING" => Some("전사 진행 중"),
        "SAVING" => Some("결과 저장 중"),
        "VERIFYING" => Some("결과 확인 중"),
        "CANCEL_REQUESTED" => Some("취소 요청 중"),
        "DONE" => Some("완료"),
        "FAILED" | "CRASHED" => Some("실패"),
        "STOPPED" => Some("중지됨"),
        "CANCELLED" => Some("취소됨"),
        _ => None,
    }
}

fn filename_only(value: Option<&str>) -> Option<String> {
    let value = value?.trim_end_matches(['/', '\\']);
    let filename = value
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or_default()
        .replace(['\r', '\n'], " ");
    let filename = filename.trim();
    (!filename.is_empty()).then(|| filename.to_string())
}

pub(crate) fn format_tray_tooltip(payload: &TrayProgressPayload) -> String {
    let Some(label) = status_label(&payload.status) else {
        return IDLE_TRAY_TOOLTIP.to_string();
    };

    let terminal = matches!(
        payload.status.as_str(),
        "DONE" | "FAILED" | "CRASHED" | "STOPPED" | "CANCELLED"
    );
    let mut tooltip = format!("Sorigul - {label}");

    if !terminal {
        if let Some(progress) = payload
            .current_progress
            .filter(|progress| progress.is_finite() && (0.0..=100.0).contains(progress))
        {
            tooltip.push_str(&format!(" {}%", progress.round() as u8));
        }
        if let Some(filename) = filename_only(payload.current_file.as_deref()) {
            tooltip.push('\n');
            tooltip.push_str(&filename);
        }
    } else if payload.status == "DONE" {
        if let Some(filename) = filename_only(payload.current_file.as_deref()) {
            tooltip.push_str("\n마지막 작업: ");
            tooltip.push_str(&filename);
        }
    }

    tooltip
}

pub(crate) fn update_tooltip_if_changed<E>(
    last_tooltip: &mut Option<String>,
    tooltip: &str,
    set_tooltip: impl FnOnce(&str) -> Result<(), E>,
) -> Result<bool, E> {
    if last_tooltip.as_deref() == Some(tooltip) {
        return Ok(false);
    }
    set_tooltip(tooltip)?;
    *last_tooltip = Some(tooltip.to_string());
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::convert::Infallible;

    fn payload(status: &str, file: Option<&str>, progress: Option<f64>) -> TrayProgressPayload {
        TrayProgressPayload {
            status: status.to_string(),
            current_file: file.map(str::to_string),
            current_progress: progress,
        }
    }

    #[test]
    fn formats_idle_and_every_supported_status() {
        let cases = [
            ("IDLE", "Sorigul - 대기 중"),
            ("UNKNOWN", "Sorigul - 대기 중"),
            ("WAITING", "Sorigul - 준비 중"),
            ("PREPARING", "Sorigul - 준비 중"),
            ("SAVING", "Sorigul - 결과 저장 중"),
            ("VERIFYING", "Sorigul - 결과 확인 중"),
            ("CANCEL_REQUESTED", "Sorigul - 취소 요청 중"),
            ("FAILED", "Sorigul - 실패"),
            ("CRASHED", "Sorigul - 실패"),
            ("STOPPED", "Sorigul - 중지됨"),
            ("CANCELLED", "Sorigul - 취소됨"),
        ];

        for (status, expected) in cases {
            assert_eq!(format_tray_tooltip(&payload(status, None, None)), expected);
        }
    }

    #[test]
    fn formats_honest_running_progress_and_omits_missing_progress() {
        assert_eq!(
            format_tray_tooltip(&payload(
                "TRANSCRIBING",
                Some("민법_4주차_2강.mp3"),
                Some(42.3),
            )),
            "Sorigul - 전사 진행 중 42%\n민법_4주차_2강.mp3"
        );
        assert_eq!(
            format_tray_tooltip(&payload("TRANSCRIBING", Some("민법_4주차_2강.mp3"), None,)),
            "Sorigul - 전사 진행 중\n민법_4주차_2강.mp3"
        );
    }

    #[test]
    fn accepts_real_progress_boundaries_and_rejects_invalid_values() {
        for (progress, expected) in [(0.0, " 0%"), (100.0, " 100%")] {
            assert!(
                format_tray_tooltip(&payload("PREPARING", None, Some(progress)))
                    .ends_with(expected)
            );
        }
        for progress in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -1.0, 101.0] {
            assert_eq!(
                format_tray_tooltip(&payload("PREPARING", None, Some(progress))),
                "Sorigul - 준비 중"
            );
        }
    }

    #[test]
    fn terminal_states_never_show_progress_and_done_uses_only_a_real_filename() {
        assert_eq!(
            format_tray_tooltip(&payload(
                "DONE",
                Some("C:\\Users\\User\\lecture.mp3"),
                Some(100.0),
            )),
            "Sorigul - 완료\n마지막 작업: lecture.mp3"
        );
        assert_eq!(
            format_tray_tooltip(&payload("FAILED", Some("/private/lecture.mp3"), Some(50.0))),
            "Sorigul - 실패"
        );
    }

    #[test]
    fn strips_windows_posix_and_unicode_paths() {
        for path in [
            "C:\\Users\\User\\lecture.mp3",
            "C:/Users/User/lecture.mp3",
            "/content/foo/lecture.mp3",
        ] {
            let tooltip = format_tray_tooltip(&payload("TRANSCRIBING", Some(path), None));
            assert_eq!(tooltip, "Sorigul - 전사 진행 중\nlecture.mp3");
            assert!(!tooltip.contains("Users"));
            assert!(!tooltip.contains("content"));
        }
        assert_eq!(
            format_tray_tooltip(&payload(
                "TRANSCRIBING",
                Some("C:\\강의\\민법 4주차.mp3"),
                None,
            )),
            "Sorigul - 전사 진행 중\n민법 4주차.mp3"
        );
    }

    #[test]
    fn suppresses_duplicate_native_updates() {
        let calls = Cell::new(0);
        let mut last = None;
        let set = |_: &str| -> Result<(), Infallible> {
            calls.set(calls.get() + 1);
            Ok(())
        };

        assert!(update_tooltip_if_changed(&mut last, "42%", set).unwrap());
        assert!(!update_tooltip_if_changed(&mut last, "42%", set).unwrap());
        assert!(update_tooltip_if_changed(&mut last, "43%", set).unwrap());
        assert_eq!(calls.get(), 2);
    }
}
