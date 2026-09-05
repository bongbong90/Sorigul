import ast
import io
import tokenize
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def annotated_fields(source, class_name):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            }
    raise AssertionError(f"class not found: {class_name}")


def attribute_name(node):
    return node.attr if isinstance(node, ast.Attribute) else None


def test_navigation_keeps_the_four_product_screens_and_no_dashboard():
    source = read_repo("frontend/src/App.tsx") + "\n" + read_repo(
        "frontend/src/components/layout/AppShell.tsx"
    )
    lowered = source.lower()

    assert "dashboard" not in lowered
    for label in ("전사", "로그", "Folders", "설정"):
        assert label in source


def test_runtime_settings_fields_preserve_the_persistence_boundary():
    source = read_repo("backend/src/services/settings.py")
    runtime_fields = annotated_fields(source, "RuntimeSettings")
    patch_fields = annotated_fields(source, "SettingsPatch")
    required = {
        "transcription_folder",
        "last_course",
        "last_subject",
        "last_engine",
        "drive_exam_root",
        "subject_stage_overrides",
    }

    assert required <= runtime_fields
    assert not runtime_fields & {"drive_auto_upload", "colab_url"}
    assert not patch_fields & {"drive_auto_upload", "colab_url"}


def test_ffprobe_is_absent_from_backend_runtime_tokens():
    for path in (REPO_ROOT / "backend" / "src").rglob("*.py"):
        tokens = tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
        runtime_tokens = [token.string.lower() for token in tokens if token.type != tokenize.COMMENT]
        assert "ffprobe" not in " ".join(runtime_tokens), path


def test_drive_upload_paths_are_txt_json_srt_only():
    source = read_repo("backend/src/services/drive.py")
    tree = ast.parse(source)
    path_lists = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == "paths" for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.List):
            path_lists.append([attribute_name(element) for element in node.value.elts])

    assert path_lists == [["txt", "json", "srt"]]


def test_queue_uses_real_duration_metadata():
    source = read_repo("frontend/src/pages/TranscriptionPage.tsx")

    assert "duration_seconds" in source
    assert "duration: '—'" not in source


def test_runtime_display_uses_elapsed_and_observed_eta():
    source = read_repo("frontend/src/components/transcription/CurrentTaskSection.tsx")

    assert "ETA 계산 중" in source
    assert "etaSeconds" in source
    assert "elapsedSeconds" in source
    assert "formatRuntimeSeconds(elapsedSeconds)" in source
    assert "formatRuntimeSeconds(etaSeconds)" in source
    assert "예상 남은 시간 12분" not in source


def test_colab_internal_units_are_not_user_visible_literals():
    source = "\n".join(
        read_repo(path)
        for path in (
            "frontend/src/components/transcription/CurrentTaskSection.tsx",
            "frontend/src/pages/TranscriptionPage.tsx",
        )
    ).lower()
    forbidden = ("300초", "300 seconds", "chunk 3/5", "chunk 3 / 5", "3 / 5 구간", "300초 조각")

    assert not any(value in source for value in forbidden)


def test_overall_progress_uses_job_denominator():
    page_source = read_repo("frontend/src/pages/TranscriptionPage.tsx")
    actions_source = read_repo("frontend/src/components/transcription/TranscriptionActions.tsx")

    assert "progressDoneCount={job?.done_files ?? null}" in page_source
    assert "progressTotalCount={job && job.total_files > 0 ? job.total_files : null}" in page_source
    assert "totalCount={rows.length}" not in page_source
    assert "job.done_files" not in actions_source
    assert "job.total_files" not in actions_source


def test_drive_auto_upload_defaults_off_without_restore():
    source = read_repo("frontend/src/pages/TranscriptionPage.tsx")

    assert "const [uploadToDrive, setUploadToDrive] = useState(false)" in source
    assert "localStorage" not in source.split("const [uploadToDrive", 1)[0]
    assert "drive_auto_upload" not in source
