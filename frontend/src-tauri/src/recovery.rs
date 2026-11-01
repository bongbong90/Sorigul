//! Read-only evidence for explicit offline recovery/exit. Unknown means HOLD.
use serde::Deserialize;
use std::{collections::BTreeMap, net::TcpListener, path::Path};

#[derive(Deserialize)]
struct SavedJob {
    status: String,
    files: BTreeMap<String, String>,
    #[serde(default)]
    drive: BTreeMap<String, SavedDrive>,
}

#[derive(Deserialize)]
struct SavedDrive {
    status: String,
}

pub fn confirm_saved_idle(path: &Path) -> Result<(), String> {
    // No repair, quarantine, rewrite or default-to-empty on failure.
    let bytes = std::fs::read(path).map_err(|_| "JOB_STATE_UNKNOWN")?;
    let jobs: BTreeMap<String, SavedJob> =
        serde_json::from_slice(&bytes).map_err(|_| "JOB_STATE_UNKNOWN")?;
    for job in jobs.values() {
        let terminal =
            |s: &str| matches!(s, "DONE" | "FAILED" | "STOPPED" | "CANCELLED" | "CRASHED");
        if !terminal(&job.status) || job.files.values().any(|s| !terminal(s)) {
            return Err("ACTIVE_OR_UNKNOWN_JOB".into());
        }
        if job.drive.values().any(|d| {
            !matches!(
                d.status.as_str(),
                "DISABLED" | "AUTH_REQUIRED" | "CLASSIFICATION_FAILED" | "DONE" | "FAILED"
            )
        }) {
            return Err("ACTIVE_OR_UNKNOWN_DRIVE".into());
        }
    }
    Ok(())
}

pub fn confirm_port_free(port: u16) -> Result<(), String> {
    // HTTP timeout is not proof of a free port (silent/non-HTTP listener).
    let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port))
        .map_err(|_| "PORT_OCCUPIED_BY_OTHER_SERVICE")?;
    drop(listener);
    Ok(())
}

pub fn confirm_offline_idle(port: u16) -> Result<(), String> {
    let base = std::env::var_os("LOCALAPPDATA").ok_or("JOB_STATE_UNKNOWN")?;
    confirm_saved_idle(&std::path::PathBuf::from(base).join("Sorigul/jobs.json"))?;
    confirm_port_free(port)
}

pub fn message(code: &str) -> &'static str {
    match code.split(':').next().unwrap_or(code) {
        "BACKEND_STILL_RUNNING" => "Backend 프로세스가 아직 실행 중입니다. 다시 연결을 사용해 주세요.",
        "BACKEND_NOT_OWNED" => "이 앱이 소유한 Backend의 종료를 확인할 수 없어 다시 시작을 보류합니다.",
        "OWNED_WORK_STILL_RUNNING" => "Backend 또는 Worker가 남아 있어 다시 시작과 종료를 보류합니다.",
        "ACTIVE_OR_UNKNOWN_JOB" => "완료되지 않았거나 상태가 불명확한 작업이 있어 다시 시작과 종료를 보류합니다.",
        "ACTIVE_OR_UNKNOWN_DRIVE" => "Drive 작업의 완료를 확인할 수 없어 다시 시작과 종료를 보류합니다.",
        "JOB_STATE_UNKNOWN" => "저장된 작업 상태를 읽거나 확인할 수 없어 다시 시작과 종료를 보류합니다.",
        "PORT_OCCUPIED_BY_OTHER_SERVICE" => "Backend 포트를 다른 프로세스가 사용 중입니다. 다시 시작을 보류합니다.",
        "RECOVERY_IN_PROGRESS" => "Backend 시작 또는 정리가 진행 중입니다. 잠시 후 다시 확인해 주세요.",
        "EXIT_IN_PROGRESS" => "앱 종료가 진행 중입니다.",
        "STARTUP_TIMEOUT" => "Backend 시작 시간이 초과되었습니다. 연결 상태와 작업 보존 여부를 확인해 주세요.",
        "SPAWN_FAILED" => "Backend 프로세스를 실행하지 못했습니다. 설치 상태를 확인해 주세요.",
        _ => "Backend 복구 안전성 또는 시작 결과를 확인하지 못했습니다. 표시된 오류 코드를 확인해 주세요.",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    fn check(json: &str) -> Result<(), String> {
        let path = std::env::temp_dir().join(format!(
            "sorigul-recovery-{}-{}.json",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::SeqCst)
        ));
        std::fs::write(&path, json).unwrap();
        let before = std::fs::read(&path).unwrap();
        let result = confirm_saved_idle(&path);
        assert_eq!(std::fs::read(&path).unwrap(), before);
        std::fs::remove_file(path).unwrap();
        result
    }
    #[test]
    fn terminal_history_is_read_only_and_empty_history_is_valid() {
        assert_eq!(check("{}"), Ok(()));
        for state in ["DONE", "FAILED", "STOPPED", "CANCELLED", "CRASHED"] {
            assert_eq!(
                check(&format!(
                    r#"{{"job":{{"status":"{state}","files":{{"f":"{state}"}},"drive":{{"f":{{"status":"DONE"}}}}}}}}"#
                )),
                Ok(())
            );
        }
    }
    // Shape of JobManager._save_jobs_unlocked: model_dump(mode="json"),
    // indent=2, ensure_ascii=False, with fields this check ignores.
    const SAVED: &str = r#"{
  "job-1": {
    "job_id": "job-1",
    "created_at": "2026-10-31T10:00:00.123456",
    "updated_at": "2026-10-31T10:09:20.654321",
    "status": "FILE_STATUS",
    "folder": "C:\\Users\\User\\Desktop\\전사\\민법",
    "engine": "local_whisper",
    "engine_config": {"model": "large-v3", "device": "cuda"},
    "force_retranscribe": false,
    "upload_to_drive": true,
    "total_files": 1,
    "done_files": 1,
    "failed_files": 0,
    "current_file": null,
    "current_progress": null,
    "eta_seconds": null,
    "files": {"f1": "FILE_STATUS"},
    "events": [{"timestamp": "2026-10-31T10:00:00", "level": "warning", "category": "CRASHED", "message": "이전 작업이 비정상 종료되어 복구되었습니다.", "file_id": null, "filename": null}],
    "drive": {"f1": {"status": "DRIVE_STATUS", "error": null, "remote_file_ids": {}, "updated_at": "2026-10-31T10:09:20"}},
    "error": null,
    "course": "민법",
    "subject": null,
    "stage": "1차",
    "file_metadata": {"f1": {"week": "1", "lesson": null, "normalized_name": null}}
  }
}"#;
    #[test]
    fn real_saved_job_shape_is_read() {
        let saved = |file: &str, drive: &str| {
            check(
                &SAVED
                    .replace("FILE_STATUS", file)
                    .replace("DRIVE_STATUS", drive),
            )
        };
        assert_eq!(saved("DONE", "DONE"), Ok(()));
        assert_eq!(saved("CRASHED", "AUTH_REQUIRED"), Ok(()));
        assert!(saved("TRANSCRIBING", "DONE").is_err());
        assert!(saved("DONE", "UPLOADING").is_err());
    }
    #[test]
    fn active_unknown_and_malformed_history_hold() {
        for status in ["WAITING", "TRANSCRIBING", "CANCEL_REQUESTED", "NEW_STATE"] {
            assert!(check(&format!(
                r#"{{"job":{{"status":"{status}","files":{{}}}}}}"#
            ))
            .is_err());
            assert!(check(&format!(
                r#"{{"job":{{"status":"DONE","files":{{"f":"{status}"}}}}}}"#
            ))
            .is_err());
        }
        for status in ["PENDING", "UPLOADING", "NEW_STATE"] {
            assert!(check(&format!(r#"{{"job":{{"status":"DONE","files":{{}},"drive":{{"f":{{"status":"{status}"}}}}}}}}"#)).is_err());
        }
        for json in [
            "bad",
            "[]",
            r#"{"job":{}}"#,
            r#"{"job":{"status":"DONE","files":null}}"#,
        ] {
            assert!(check(json).is_err());
        }
        assert!(confirm_saved_idle(
            &std::env::temp_dir().join("sorigul-nonexistent-recovery-history")
        )
        .is_err());
    }
    #[test]
    fn silent_port_listener_blocks_recovery_and_is_not_killed() {
        let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(confirm_port_free(port).is_err());
        assert!(listener.local_addr().is_ok());
        drop(listener);
        assert_eq!(confirm_port_free(port), Ok(()));
    }
}
