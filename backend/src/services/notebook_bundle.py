"""Portable Notebook result contract. No API, model, OAuth or user-state imports."""
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

from src.domain.transcription import TranscriptionResult
from src.services.audio_metadata import AudioMetadataService
from src.services.output_bundle import OutputBundleWriter

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
RESULT_NAMES = ("result.txt", "result.json", "result.srt")


def bounded_sha256(path: Path, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            total += len(chunk)
            if total > limit:
                raise ValueError("파일 크기 제한을 초과합니다.")
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(source: Path) -> dict:
    if source.suffix.lower() != ".mp3" or not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("원본 MP3를 확인할 수 없습니다.")
    duration = AudioMetadataService().duration_seconds(source)
    if duration is None or not math.isfinite(duration) or not 0 < duration <= 301:
        raise ValueError("Notebook 가져오기는 300초 이하의 유효한 MP3를 지원합니다.")
    return {"name": source.name, "size": source.stat().st_size,
            "sha256": bounded_sha256(source, MAX_SOURCE_BYTES), "duration_seconds": duration}


def canonical_bytes(result: TranscriptionResult) -> dict[str, bytes]:
    blocks = [f"{index}\n{OutputBundleWriter._format_timestamp(segment.start)} --> "
              f"{OutputBundleWriter._format_timestamp(segment.end)}\n{segment.text}\n"
              for index, segment in enumerate(result.segments, 1)]
    return {"result.txt": result.text.encode("utf-8"),
            "result.json": json.dumps(result.output_payload(), ensure_ascii=False, indent=2).encode("utf-8"),
            "result.srt": "\n".join(blocks).encode("utf-8")}


def validated_result(payload: dict, duration: float) -> TranscriptionResult:
    result = TranscriptionResult.from_engine_payload(payload)
    # Reject an unsorted payload before the common parser's sorting could hide it.
    if not result.text.strip() or not result.segments or len(result.segments) > 10000:
        raise ValueError("전사 내용과 segment가 필요합니다.")
    if result.text != " ".join(segment.text for segment in result.segments if segment.text):
        raise ValueError("전체 전사와 segment 내용이 일치하지 않습니다.")
    starts = [segment["start"] for segment in payload["segments"]]
    if starts != sorted(starts):
        raise ValueError("segment 순서가 올바르지 않습니다.")
    if any(segment.end > duration + 0.25 for segment in result.segments):
        raise ValueError("timestamp가 원본 MP3 길이를 벗어납니다.")
    return result


def build_archive(source: Path, payload: dict, runtime: dict, *, expected_identity=None) -> bytes:
    identity = source_identity(source)
    if expected_identity is not None and identity != expected_identity:
        raise ValueError("추론 중 원본 MP3가 변경되어 결과를 만들지 않았습니다.")
    result = validated_result(payload, identity["duration_seconds"])
    files = canonical_bytes(result)
    manifest = {"schema_version": 1, "source": identity, "runtime": runtime,
                "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in files.items()}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for name, data in files.items():
            archive.writestr(name, data)
    if len(stream.getvalue()) > MAX_ARCHIVE_BYTES:
        raise ValueError("Notebook 결과가 가져오기 크기 제한을 초과합니다.")
    return stream.getvalue()


def read_archive(source: Path, data: bytes) -> tuple[TranscriptionResult, dict, dict]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("결과 ZIP은 8 MiB 이하여야 합니다.")
    identity = source_identity(source)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != 4 or {item.filename for item in entries} != {*RESULT_NAMES, "manifest.json"}:
            raise ValueError("Notebook ZIP의 파일 구성이 올바르지 않습니다.")
        if any(item.flag_bits & 1 or item.file_size > MAX_ARCHIVE_BYTES for item in entries) or sum(item.file_size for item in entries) > MAX_ARCHIVE_BYTES:
            raise ValueError("압축 해제 크기 또는 암호화 ZIP은 허용되지 않습니다.")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("schema_version") != 1 or manifest.get("source") != identity:
            raise ValueError("원본 MP3의 이름·크기·SHA-256·길이가 결과와 일치하지 않습니다.")
        runtime = manifest.get("runtime", {})
        if (runtime.get("engine"), runtime.get("model")) != ("faster-whisper", "large-v3") or (runtime.get("device"), runtime.get("compute_type")) not in {("cuda", "float16"), ("cpu", "int8")}:
            raise ValueError("Notebook model/device 정보가 올바르지 않습니다.")
        files = {name: archive.read(name) for name in RESULT_NAMES}
    for name, content in files.items():
        content.decode("utf-8", errors="strict")
        if manifest.get("files", {}).get(name) != {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}:
            raise ValueError("결과 파일 체크섬이 일치하지 않습니다.")
    result = validated_result(json.loads(files["result.json"].decode("utf-8")), identity["duration_seconds"])
    if files != canonical_bytes(result):
        raise ValueError("TXT/JSON/SRT 내용·인코딩·timestamp가 서로 일치하지 않습니다.")
    return result, runtime, identity
