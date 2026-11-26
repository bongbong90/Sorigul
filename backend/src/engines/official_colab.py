"""Server-injected, default-off Job boundary for the PHASE 10 pipeline.

No credentials/config from Job data, Runtime creation, OAuth or Local switch.
Only sanitized error codes and user messages cross into the existing Runner.
"""

import math

from src.domain.transcription import (
    CancelRequested, EngineError, ErrorCategory, StopRequested, TranscriptionResult,
)
from src.services.colab_full_file_pipeline import ColabFullFilePipeline, PipelineError


class OfficialColabEngineError(EngineError):
    def __init__(self, kind, message, *, category=ErrorCategory.RUNTIME, fatal=True,
                 cleanup_required=False, local_selection_possible=False):
        if local_selection_possible:
            message += " PC 전사를 선택할 수 있습니다."
        super().__init__("OFFICIAL_COLAB_" + kind, category, message, fatal=fatal)
        self.cleanup_required = cleanup_required
        self.local_selection_possible = local_selection_possible
        self.local_fallback_allowed = local_selection_possible


def disabled_error():
    return OfficialColabEngineError("DISABLED", "이 전사 방식은 현재 사용할 수 없습니다.",
                                    category=ErrorCategory.CONFIGURATION)


PREPARATION_SHARE = 0.20
PREPARATION_PROGRESS = {
    "CHECKING": 0.02, "INSTALL_REQUIRED": 0.03, "INSTALLING": 0.05,
    "MODEL_DOWNLOAD_REQUIRED": 0.08, "DOWNLOADING": 0.10, "VERIFYING": 0.15,
    "READY": PREPARATION_SHARE,
}


class OfficialColabJobEngine:
    def __init__(self, ownership, cache, *, pipeline_factory=ColabFullFilePipeline):
        try:
            self._pipeline = pipeline_factory(ownership, cache)
        except Exception:
            raise OfficialColabEngineError("CONFIG_INVALID", "전사 환경 설정을 확인해 주세요.",
                                            category=ErrorCategory.CONFIGURATION) from None
        self._blocked = False

    @staticmethod
    def _normalize(error, report):
        signals = set(report.signals) if report is not None else set()
        cleanup = bool(report and report.cleanup.cleanup_required)
        if getattr(error, "code", None) == "FFMPEG_PROCESS_CLEANUP_FAILED":
            cleanup = True
        local = bool(report and report.local_selection_possible) and not cleanup
        code = getattr(error, "code", None)
        code = getattr(code, "value", code)
        stage = (report.diagnostic or {}).get("stage") if report is not None and getattr(report, "diagnostic", None) else None
        if cleanup or code == "CLEANUP_REQUIRED":
            return OfficialColabEngineError(
                "CLEANUP_REQUIRED", "원격 작업 정리가 확인되지 않았습니다. 앱이 정리를 자동으로 다시 확인합니다.",
                cleanup_required=True)
        if code in ("PRIOR_EXECUTION_UNRESOLVED", "PRIOR_EXECUTION_STATE_INVALID"):
            return OfficialColabEngineError(
                "PRIOR_EXECUTION_UNRESOLVED",
                "이 파일의 이전 Colab 작업 정리를 확인하고 있습니다. 잠시 후 다시 시도해 주세요.",
                local_selection_possible=local)
        if "REMOTE_STATE_UNCERTAIN" in signals:
            return OfficialColabEngineError("STATE_UNCERTAIN", "원격 작업 상태를 확인할 수 없어 작업을 중단했습니다.")
        if "AUTH_ACCESS_REQUIRED" in signals:
            return OfficialColabEngineError("AUTH_REQUIRED", "계정과 접근 권한을 확인해 주세요.",
                                            category=ErrorCategory.AUTHENTICATION, local_selection_possible=local)
        if "POLICY_USAGE_LIMIT" in signals:
            return OfficialColabEngineError("LIMITED", "이용 정책 또는 사용량 제한으로 작업을 중단했습니다.",
                                            local_selection_possible=local)
        if "MODEL_PREPARATION_REQUIRED" in signals:
            return OfficialColabEngineError("PREPARATION_REQUIRED", "전사 환경 준비가 필요합니다.",
                                            category=ErrorCategory.CONFIGURATION, local_selection_possible=local)
        if "FREE_RESOURCE_UNAVAILABLE" in signals:
            return OfficialColabEngineError("RESOURCE_UNAVAILABLE", "무료 전사 자원을 사용할 수 없습니다.",
                                            local_selection_possible=local)
        if "NETWORK_ERROR" in signals:
            return OfficialColabEngineError("NETWORK_ERROR", "전사 연결을 확인해 주세요.",
                                            category=ErrorCategory.NETWORK, local_selection_possible=local)
        input_codes = {"SOURCE_INVALID", "SOURCE_CHANGED", "SOURCE_OR_CHUNKS_CHANGED", "CHUNK_CHANGED",
                       "LOCAL_FILE_INVALID", "LOCAL_FILE_CHANGED", "AUDIO_EMPTY", "AUDIO_SPLIT_FAILED",
                       "AUDIO_SPLIT_TIMEOUT", "CHUNK_PLAN_INVALID"}
        if "INPUT_INVALID" in signals or getattr(error, "code", None) in input_codes:
            return OfficialColabEngineError("INPUT_INVALID", "이 MP3 파일을 처리할 수 없습니다.",
                                            category=ErrorCategory.INPUT, fatal=False,
                                            local_selection_possible=local)
        if stage == "audio_decode":
            return OfficialColabEngineError("AUDIO_DECODE_FAILED",
                                            "Colab에서 이 MP3를 읽지 못했습니다. 파일이 손상되지 않았는지 확인해 주세요.",
                                            local_selection_possible=local)
        if stage == "model_init" or code == "MODEL_LOAD_FAILED":
            return OfficialColabEngineError("MODEL_LOAD_FAILED", "Colab에서 전사 모델을 불러오지 못했습니다.",
                                            local_selection_possible=local)
        if code in {"CUDA_FAILED", "GPU_UNAVAILABLE"}:
            return OfficialColabEngineError("DEVICE_FAILED", "Colab GPU에서 전사하지 못했습니다.",
                                            local_selection_possible=local)
        return OfficialColabEngineError("FAILED", "전사 작업을 안전하게 완료하지 못했습니다.",
                                        local_selection_possible=local)

    def transcribe(self, source_path, token, event_callback, progress_callback):
        if self._blocked:
            raise OfficialColabEngineError("SESSION_BLOCKED", "이전 원격 작업 상태를 먼저 확인해 주세요.")

        # Stage progress (#60): environment preparation fills 0-20 %, decoded
        # chunks 20-95 %. Never decreases; 100 % stays with the Writer.
        shown = {"value": 0.0}

        def report_progress(value):
            if value > shown["value"]:
                shown["value"] = value
                progress_callback(round(value, 4))

        def progress(value):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                                      or not 0 <= value <= 1):
                raise OfficialColabEngineError("RESULT_INVALID", "전사 진행 상태를 확인할 수 없습니다.")
            # Decode completion is not output-bundle completion. No invented ETA
            # or 100% before the existing Writer verifies/promotes all outputs.
            if value is None or value == 1:
                progress_callback(None)
            elif value == 0:
                progress_callback(shown["value"])
            else:
                report_progress(PREPARATION_SHARE + (0.95 - PREPARATION_SHARE) * value)

        def event(level, category, message):
            from src.services.colab_model_provisioner import MESSAGES
            if isinstance(category, str) and category.startswith("ColabProvisioning:"):
                state = category.partition(":")[2]
                if state in MESSAGES and message == MESSAGES[state]:
                    event_callback("info", category, MESSAGES[state])
                    if state in PREPARATION_PROGRESS:
                        report_progress(PREPARATION_PROGRESS[state])
                    return
            # Do not let arbitrary remote content become a Job event/log.
            event_callback("info", "Colab", "전사 작업을 진행하고 있습니다.")

        try:
            token.raise_if_requested()
            result = self._pipeline.transcribe(source_path, token, event, progress)
            report = self._pipeline.last_report
            # Residue limited to temp files on the owned Runtime is removed by
            # close_session (Runtime delete); the ownership store gates the next launch.
            deferred = (report is not None and report.cleanup.runtime_files_only
                        and "REMOTE_FILES_PENDING_RUNTIME_DELETE" in report.signals)
            if (report is None or report.status != "COMPLETED"
                    or (report.cleanup.cleanup_required and not deferred)
                    or not isinstance(result, TranscriptionResult)):
                raise PipelineError("RESULT_NOT_CONFIRMED")
            token.raise_if_requested()
            validated = TranscriptionResult.from_engine_payload({
                "text": result.text, "language": result.language,
                "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments],
            })
            validated.metadata["colab_recovery_cache_used"] = result.metadata.get("colab_recovery_cache_used") is True
            if result.silence_proof is not None:
                if result.silence_proof["scope"] != "file":
                    raise PipelineError("RESULT_NOT_CONFIRMED")
                validated._set_verified_silence(result.silence_proof)
            return validated
        except (StopRequested, CancelRequested):
            raise
        except Exception as exc:
            normalized = self._normalize(exc, self._pipeline.last_report)
            self._blocked = normalized.fatal
            raise normalized from None
