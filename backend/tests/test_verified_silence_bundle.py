"""Issue #238: explicit, source-bound silence; same Writer/Scanner contract."""

import hashlib
import json
import logging
import os

import pytest

from src.domain.models import BundleStatus, FileStatus
from src.domain.transcription import EngineError, SILENCE_MARKER, TranscriptionResult
from src.services.colab_inference_worker import MODEL_REVISION
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter
from src.services.scanner import FileScanner
from test_official_colab_job_adapter import (
    env, full_setup, ml, no_external_network, create, execute, valid_old_bundle,
)
from test_colab_jupyter_files import TOKEN, URL
from test_colab_runtime_client import OAUTH


def trusted_test_silence(source):
    """Unit fixture for the trusted producer; JSON parsing cannot do this."""
    result = TranscriptionResult(text="", segments=[], language="ko")
    result._set_verified_silence(dict(
        version=1, scope="file", engine="official_colab", model_revision=MODEL_REVISION,
        status="complete", duration_seconds=2.0, chunks_verified=1,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), source_size=source.stat().st_size,
        cleanup_complete=True))
    return result


def silence_job(env, durations=(300.0, 12.0)):
    env.mock.server.silent = set(range(len(durations)))
    original = env.mock.pipeline
    def pipeline(*args, **kwargs):
        result = original(*args, **kwargs)
        result.splitter.durations = durations
        return result
    env.mock.pipeline = pipeline
    return env.resolver()


@pytest.mark.parametrize("durations", [(12.0,), (300.0, 12.0)])
def test_full_silence_job_done_and_fresh_scanner_done(env, durations):
    resolver = silence_job(env, durations)
    source = env.source.read_bytes()
    job = create(env)
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and finished.batch_completed
    paths = BundlePaths.final_for(env.source)
    assert paths.txt.read_bytes() == paths.srt.read_bytes() == b""
    payload = json.loads(paths.json.read_text(encoding="utf-8"))
    assert payload["text"] == "" and payload["segments"] == []
    marker = payload[SILENCE_MARKER]
    assert marker["scope"] == "file" and marker["status"] == "complete"
    assert marker["chunks_verified"] == len(durations)
    assert marker["duration_seconds"] == env.mock.ml.duration * len(durations)  # actual decoded durations
    assert marker["cleanup_complete"] is True
    assert env.source.read_bytes() == source
    assert FileScanner(str(env.source.parent)).check_bundle(env.source) is BundleStatus.DONE
    scanned = {f.id: f for f in FileScanner(str(env.source.parent)).scan()}
    assert scanned[env.source.stem].completion_status is BundleStatus.DONE
    reloaded = TranscriptionResult.from_engine_payload(payload)
    assert reloaded.silence_proof is None  # disk JSON isn't an in-memory producer capability
    assert finished.engine_config == {} and finished.upload_to_drive is False
    from fastapi import HTTPException
    before = len(env.mock.server.calls)
    with pytest.raises(HTTPException):
        create(env)  # a subsequent Job creation must skip the scanned silent bundle
    assert len(env.mock.server.calls) == before


def test_mixed_speech_and_silence_is_ordinary_bundle(env):
    env.mock.server.silent = {0}
    resolver = env.resolver()
    finished = execute(env, create(env), resolver)
    assert finished.status is FileStatus.DONE
    payload = json.loads(env.source.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["text"] == "한국어 조각 1" and SILENCE_MARKER not in payload
    assert FileScanner(str(env.source.parent)).check_bundle(env.source) is BundleStatus.DONE


@pytest.mark.parametrize("fault", ["missing-marker", "boolean-marker", "chunk-marker", "not-complete",
    "no-cleanup", "duration-zero", "duration-nan", "no-chunks", "bad-version", "bad-hash", "bad-size",
    "text", "segments", "txt", "srt", "json-corrupt", "duplicate", "partial", "failed",
    "missing-json", "missing-txt", "missing-srt"])
def test_writer_scanner_both_reject_damaged_or_unfounded_silence(env, fault):
    paths = OutputBundleWriter().commit(env.source, trusted_test_silence(env.source))
    payload = json.loads(paths.json.read_text(encoding="utf-8"))
    marker = payload[SILENCE_MARKER]
    if fault == "missing-marker":
        del payload[SILENCE_MARKER]
    elif fault == "boolean-marker":
        payload[SILENCE_MARKER] = True
    elif fault == "chunk-marker":
        marker["scope"] = "chunk"
    elif fault == "not-complete":
        marker["status"] = "partial"
    elif fault == "no-cleanup":
        marker["cleanup_complete"] = False
    elif fault == "duration-zero":
        marker["duration_seconds"] = 0
    elif fault == "duration-nan":
        marker["duration_seconds"] = float("nan")
    elif fault == "no-chunks":
        marker["chunks_verified"] = 0
    elif fault == "bad-version":
        marker["version"] = True
    elif fault == "bad-hash":
        marker["source_sha256"] = "0" * 64
    elif fault == "bad-size":
        marker["source_size"] += 1
    elif fault == "text":
        payload["text"] = "not silent"
    elif fault == "segments":
        payload["segments"] = [{"start": 0, "end": 1, "text": "speech"}]
    elif fault == "partial":
        payload["complete"] = False
    elif fault == "failed":
        payload["error_code"] = "FAILED"
    elif fault == "txt":
        paths.txt.write_text("unexpected text", encoding="utf-8")
    elif fault == "srt":
        paths.srt.write_text("unexpected subtitle", encoding="utf-8")
    paths.json.write_text(json.dumps(payload), encoding="utf-8")
    if fault == "json-corrupt":
        paths.json.write_text("{broken", encoding="utf-8")
    elif fault == "duplicate":
        paths.json.write_text(json.dumps(payload).replace('"cleanup_complete": true',
                              '"cleanup_complete": false, "cleanup_complete": true'), encoding="utf-8")
    elif fault.startswith("missing-") and fault != "missing-marker":
        getattr(paths, fault.split("-")[1]).unlink()
    with pytest.raises(EngineError):
        OutputBundleValidator().validate(paths)
    scanned = FileScanner(str(env.source.parent)).check_bundle(env.source)
    assert scanned is not BundleStatus.DONE
    if fault in ("json-corrupt", "duplicate", "partial", "failed", "text", "segments"):
        assert scanned is BundleStatus.INVALID_RESULT


@pytest.mark.parametrize("mode", ["boolean", "metadata", "payload", "private-field"])
def test_request_or_engine_json_cannot_mint_silence_capability(env, mode):
    marker = trusted_test_silence(env.source).silence_proof
    payload = {"text": "", "segments": [], "verified_silence": True}
    if mode == "boolean":
        payload[SILENCE_MARKER] = True
    elif mode == "metadata":
        payload["metadata"] = {"verified_silence": True, SILENCE_MARKER: marker}
    elif mode == "payload":
        payload[SILENCE_MARKER] = marker
    else:
        payload["_silence_proof"] = marker
    result = TranscriptionResult.from_engine_payload(payload)
    assert result.silence_proof is None and SILENCE_MARKER not in result.output_payload()
    with pytest.raises(EngineError):
        OutputBundleWriter().commit(env.source, result)
    assert not env.source.with_suffix(".json").exists()


def test_source_changed_with_same_size_invalidates_silence_bundle(env):
    paths = OutputBundleWriter().commit(env.source, trusted_test_silence(env.source))
    original = env.source.stat()
    env.source.write_bytes(b"x" * original.st_size)
    os.utime(env.source, ns=(original.st_atime_ns, original.st_mtime_ns))
    with pytest.raises(EngineError) as exc:
        OutputBundleValidator().validate(paths)
    assert exc.value.code == "SILENCE_INVALID"
    assert FileScanner(str(env.source.parent)).check_bundle(env.source) is BundleStatus.INVALID_RESULT


@pytest.mark.parametrize("constructor", [TranscriptionResult, TranscriptionResult.model_validate])
def test_public_model_construction_cannot_set_internal_silence_proof(env, constructor):
    payload = {"text": "", "segments": [], "_silence_proof": trusted_test_silence(env.source).silence_proof,
               "metadata": {"verified_silence": True}}
    result = constructor(payload) if constructor == TranscriptionResult.model_validate else constructor(**payload)
    assert result.silence_proof is None
    assert "_silence_proof" not in TranscriptionResult.model_json_schema()["properties"]
    with pytest.raises(EngineError):
        OutputBundleWriter().commit(env.source, result)


def test_verified_chunk_alone_cannot_be_saved_as_whole_file_silence(env):
    result = TranscriptionResult(text="", segments=[])
    result._set_verified_silence(dict(
        version=1, scope="chunk", engine="official_colab", model_revision=MODEL_REVISION,
        status="verified", duration_seconds=2.0, index=0, input_sha256="a" * 64))
    with pytest.raises(EngineError):
        OutputBundleWriter().commit(env.source, result)
    assert not env.source.with_suffix(".json").exists()


def test_legacy_three_path_bundle_value_contract_is_unchanged(env):
    paths = BundlePaths.final_for(env.source)
    assert paths == BundlePaths(paths.txt, paths.json, paths.srt)
    assert set(paths.as_dict()) == {"txt", "json", "srt"}


@pytest.mark.parametrize("fault", ["decode", "partial", "cleanup", "duration"])
def test_failure_partial_cleanup_or_invalid_duration_cannot_promote_silence(env, fault):
    resolver = silence_job(env)
    if fault == "decode":
        env.mock.server.fail_decode = 0
    elif fault == "partial":
        env.mock.server.mutate = lambda raw: raw.replace(b'"complete": true', b'"complete": false')
    elif fault == "cleanup":
        env.mock.server.delete_status = 500
    else:
        env.mock.ml.duration = 0
    finished = execute(env, create(env), resolver)
    assert finished.status is FileStatus.FAILED
    assert not env.source.with_suffix(".json").exists()
    cache = env.created[0].cache._file_dir(env.source) / "manifest.json"
    if cache.exists():
        for result in json.loads(cache.read_text(encoding="utf-8"))["completed"].values():
            if SILENCE_MARKER in result:
                assert result[SILENCE_MARKER]["scope"] == "chunk"
                assert "cleanup_complete" not in result[SILENCE_MARKER]


@pytest.mark.parametrize("fault", [None, "missing", "hash", "revision", "duration", "index"])
def test_failed_silence_cache_requires_explicit_matching_chunk_evidence(env, fault):
    resolver = silence_job(env)
    env.mock.server.upload_failure = 1
    first = execute(env, create(env), resolver)
    assert first.status is FileStatus.FAILED
    cache = env.created[0].cache._file_dir(env.source) / "manifest.json"
    value = json.loads(cache.read_text(encoding="utf-8"))
    chunk = value["completed"]["0"]
    assert chunk[SILENCE_MARKER]["scope"] == "chunk"
    if fault == "missing":
        del chunk[SILENCE_MARKER]
    elif fault == "hash":
        chunk[SILENCE_MARKER]["input_sha256"] = "0" * 64
    elif fault == "revision":
        chunk[SILENCE_MARKER]["model_revision"] = "0" * 40
    elif fault == "duration":
        chunk[SILENCE_MARKER]["duration_seconds"] = 0
    elif fault == "index":
        chunk[SILENCE_MARKER]["index"] = 1
    cache.write_text(json.dumps(value), encoding="utf-8")
    env.mock.server.upload_failure = None
    second = execute(env, create(env), resolver)
    assert second.status is FileStatus.DONE
    assert len(env.mock.ml.decodes) == (2 if fault is None else 3)
    payload = json.loads(env.source.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload[SILENCE_MARKER]["scope"] == "file"


def test_failed_retranscription_preserves_verified_silence_bundle(env):
    resolver = silence_job(env)
    assert execute(env, create(env), resolver).status is FileStatus.DONE
    paths = BundlePaths.final_for(env.source)
    before = {path: path.read_bytes() for path in paths.as_dict().values()}
    env.mock.server.fail_decode = 0
    failed = execute(env, create(env, force_retranscribe=True), resolver)
    assert failed.status is FileStatus.FAILED
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert FileScanner(str(env.source.parent)).check_bundle(env.source) is BundleStatus.DONE


@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_does_not_promote_new_silence_and_preserves_prior_bundle(env, cancel):
    from src.domain.transcription import CancellationToken
    resolver = silence_job(env)
    before = valid_old_bundle(env.source)
    token = CancellationToken()
    def stop(method, path, body):
        if method == "PUT" and path.endswith(".mp3"):
            (token.request_cancel if cancel else token.request_stop)()
    env.mock.server.after_http = stop
    finished = execute(env, create(env, force_retranscribe=True), resolver, token)
    assert finished.status is (FileStatus.CANCELLED if cancel else FileStatus.STOPPED)
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert not env.created[0].cache._file_dir(env.source).exists()


@pytest.mark.parametrize("member", ["txt", "json", "srt"])
def test_atomic_silence_promotion_rolls_back_each_failed_member(env, member):
    before = valid_old_bundle(env.source)
    def replace(source, target):
        if source.name.endswith(".tmp") and target.suffix == "." + member:
            raise OSError("simulated promotion failure")
        return os.replace(source, target)
    with pytest.raises(EngineError):
        OutputBundleWriter(replace=replace).commit(env.source, trusted_test_silence(env.source))
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert not list(env.source.parent.glob(".*.tmp"))
    assert not list(env.source.parent.glob(".*.bak"))


def test_verified_silence_metadata_and_logs_have_no_transcript_or_credentials(env, caplog, capsys):
    resolver = silence_job(env)
    caplog.set_level(logging.DEBUG)
    finished = execute(env, create(env), resolver)
    assert finished.status is FileStatus.DONE
    captured = capsys.readouterr()
    text = caplog.text + captured.out + captured.err + env.source.with_suffix(".json").read_text(encoding="utf-8")
    for secret in (TOKEN, URL, OAUTH, "가상 전사 내용", "한국어 조각"):
        assert secret not in text
