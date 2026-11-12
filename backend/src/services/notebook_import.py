import os
from pathlib import Path
import tempfile
import uuid

from src.domain.models import FileStatus, JobEvent, JobModel
from src.services.job_manager import JobManager
from src.services.notebook_bundle import read_archive, source_identity, bounded_sha256, MAX_ARCHIVE_BYTES
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter
from src.services.renamer import validate_safe_stem


class NotebookImportService:
    def __init__(self, jobs: JobManager):
        self.jobs = jobs

    def import_result(self, source: Path, archive: bytes) -> JobModel:
        validate_safe_stem(source.stem, "원본 MP3")
        result, runtime, identity = read_archive(source, archive)
        final = BundlePaths.final_for(source)
        if any(os.path.lexists(path) for path in final.as_dict().values()):
            raise FileExistsError("기존 결과가 있어 가져오지 않았습니다. 결과를 덮어쓰지 않습니다.")
        # Hard-link publication is atomic CREATE-only on the target volume.
        # Never use replace/rename over an existing result, even in a race.
        with tempfile.TemporaryDirectory(prefix=".sorigul-import-", dir=source.parent) as temp:
            staged = OutputBundleWriter().commit(Path(temp) / source.name, result)
            installed = []
            try:
                if source_identity(source) != identity:
                    raise ValueError("가져오기 중 원본 MP3가 변경되었습니다.")
                for kind, target in final.as_dict().items():
                    candidate = staged.as_dict()[kind]
                    os.link(candidate, target)
                    installed.append((candidate, target))
                OutputBundleValidator().validate(final)
                job = JobModel(
                    job_id=str(uuid.uuid4()), status=FileStatus.DONE, folder=str(source.parent),
                    engine="notebook_import", engine_config={"notebook_runtime": runtime,
                        "source_sha256": identity["sha256"], "manual_import": True,
                        "result_sha256": {kind: bounded_sha256(path, MAX_ARCHIVE_BYTES)
                                          for kind, path in final.as_dict().items()}},
                    total_files=1, done_files=1, failed_files=0,
                    files={source.stem: FileStatus.DONE}, upload_to_drive=False,
                    events=[JobEvent(level="info", category="Import", message="Notebook 결과 가져오기 완료",
                                     file_id=source.stem, filename=source.name)],
                )
                self.jobs.update_job(job)
                return job
            except Exception:
                for candidate, target in reversed(installed):
                    if target.exists() and os.path.samefile(candidate, target):
                        target.unlink()
                raise

    def matching_job(self, source: Path):
        candidates = [job for job in reversed(self.jobs.list_jobs())
                      if job.engine == "notebook_import" and Path(job.folder) == source.parent
                      and job.files.get(source.stem) == FileStatus.DONE]
        if not candidates:
            return None
        identity = source_identity(source)
        paths = BundlePaths.final_for(source).as_dict()
        if not all(path.is_file() and not path.is_symlink() for path in paths.values()):
            return None
        if sum(path.stat().st_size for path in paths.values()) > MAX_ARCHIVE_BYTES:
            return None
        checksums = {kind: bounded_sha256(path, MAX_ARCHIVE_BYTES) for kind, path in paths.items()}
        for job in candidates:
            if (job.engine_config.get("source_sha256") == identity["sha256"]
                    and job.engine_config.get("result_sha256") == checksums):
                return job
        return None

    def snapshot_for_drive(self, job: JobModel, file_id: str, destination: Path):
        source = Path(job.folder) / f"{file_id}.mp3"
        matching = self.matching_job(source)
        if matching is None or matching.job_id != job.job_id:
            raise ValueError("원본 또는 가져온 결과가 변경되었습니다.")
        total = 0
        for kind, path in BundlePaths.final_for(source).as_dict().items():
            target = destination / path.name
            with path.open("rb") as reader, target.open("xb") as writer:
                while chunk := reader.read(65536):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ValueError("결과 크기 제한을 초과합니다.")
                    writer.write(chunk)
            if bounded_sha256(target, MAX_ARCHIVE_BYTES) != job.engine_config["result_sha256"][kind]:
                raise ValueError("전송 준비 중 결과가 변경되었습니다.")
        if source_identity(source)["sha256"] != job.engine_config["source_sha256"]:
            raise ValueError("전송 준비 중 원본이 변경되었습니다.")
