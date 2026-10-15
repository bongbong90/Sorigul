import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_OF_TRUTH = REPO_ROOT / "docs/project/CURRENT_SOURCE_OF_TRUTH.md"
HISTORICAL_EVIDENCE = {
    "docs/release/CORE_WORKFLOW_REFINEMENT_BUILD_VALIDATION.md",
    "docs/release/FINAL_FEATURE_PARITY_REGRESSION.md",
    "docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md",
    "docs/runtime/STUDY_USE_CURRENT_HEAD_INSTALLED_VALIDATION_2026-10-02.md",
    "docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md",
}
GENERATED_RESOURCES = {
    "binaries/sorigul-backend.exe": "binaries/sorigul-backend.exe",
    "binaries/ffmpeg.exe": "binaries/ffmpeg.exe",
    "binaries/sorigul-build-manifest.json": "sorigul-build-manifest.json",
}
STATIC_RESOURCES = {
    "../../third_party/THIRD_PARTY_NOTICES.txt": "THIRD_PARTY_NOTICES.txt",
    "../../third_party/licenses/ffmpeg-gpl-3.0.txt": "licenses/ffmpeg-gpl-3.0.txt",
    "../../third_party/licenses/imageio-ffmpeg-bsd-2-clause.txt": (
        "licenses/imageio-ffmpeg-bsd-2-clause.txt"
    ),
}
CLASSIFICATIONS = {
    "CURRENT CONTRACT",
    "SUPERSEDED",
    "HISTORICAL EVIDENCE ONLY",
    "STALE",
    "AMBIGUOUS",
}


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def classification_rows():
    rows = {}
    pattern = re.compile(
        r"^\| `(?P<path>docs/[^`]+\.md)` \| (?P<classification>[^|]+?) \|"
    )
    for line in SOURCE_OF_TRUTH.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            path = match.group("path")
            assert path not in rows, f"duplicate classification row: {path}"
            rows[path] = match.group("classification").strip()
    return rows


def test_current_source_of_truth_and_living_release_status_exist():
    assert SOURCE_OF_TRUTH.is_file()
    assert (REPO_ROOT / "docs/README.md").is_file()
    assert (REPO_ROOT / "docs/release/CURRENT_RELEASE_STATUS.md").is_file()


def test_every_markdown_document_is_classified_exactly_once():
    actual = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "docs").rglob("*.md")
    }
    rows = classification_rows()

    assert set(rows) == actual
    assert set(rows.values()) <= CLASSIFICATIONS


def test_current_plan_and_historical_evidence_classifications_are_locked():
    rows = classification_rows()

    assert rows["docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md"] == "CURRENT CONTRACT"
    for path in HISTORICAL_EVIDENCE:
        assert rows[path] == "HISTORICAL EVIDENCE ONLY"
    assert rows["docs/release/RELEASE_CHECKLIST.md"] == "STALE"


def test_base_tauri_config_has_no_generated_artifact_dependency():
    config = json.loads(read_repo("frontend/src-tauri/tauri.conf.json"))
    resources = config["bundle"]["resources"]

    assert resources == STATIC_RESOURCES
    assert not GENERATED_RESOURCES.keys() & resources.keys()


def test_release_tauri_config_declares_complete_final_resource_map():
    config = json.loads(read_repo("frontend/src-tauri/tauri.release.conf.json"))

    assert config["bundle"]["resources"] == GENERATED_RESOURCES | STATIC_RESOURCES


def test_installer_uses_release_only_config_without_package_download():
    script = read_repo("scripts/build_windows_installer.ps1")

    assert "npx.cmd --no-install tauri build" in script
    assert '--config "src-tauri\\tauri.release.conf.json"' in script
    assert "--bundles msi" in script


def test_regression_is_canonical_offline_and_has_no_resource_workaround():
    script = read_repo("scripts/run_core_workflow_regression.ps1")

    assert "TAURI_CONFIG" not in script
    assert "CARGO_NET_OFFLINE" in script
    assert "cargo.exe' -Arguments @('fmt', '--check')" in script
    assert "cargo.exe' -Arguments @('check', '--locked')" in script
    assert "'clippy', '--locked', '--all-targets'" in script
    assert "cargo.exe' -Arguments @('test', '--locked')" in script
    for forbidden in (
        "pip install",
        "npm install",
        "npm ci",
        "cargo install",
        "TAURI_CONFIG",
        "placeholder",
    ):
        assert forbidden not in script


def test_runtime_requirement_lines_are_exactly_pinned():
    requirement_files = (
        "backend/requirements.txt",
        "backend/requirements-whisper.txt",
        "colab/requirements.txt",
        "tools/requirements-packaging.txt",
        "tools/requirements-torch-cuda.txt",
    )
    package_line = re.compile(r"^[A-Za-z0-9_.-]+==[^\s]+$")

    for relative in requirement_files:
        for line in read_repo(relative).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "--")):
                continue
            assert package_line.fullmatch(stripped), f"unpinned: {relative}: {stripped}"

    assert "python-multipart==0.0.32" in read_repo("colab/requirements.txt").splitlines()
    assert "python-multipart" not in read_repo("backend/requirements.txt")


def test_cuda_and_python_release_contracts_remain_exact():
    torch_requirements = read_repo("tools/requirements-torch-cuda.txt")
    core_build_script = read_repo("scripts/build_backend_sidecar.ps1")
    local_build_script = read_repo("scripts/build_local_whisper_runtime.ps1")

    assert "torch==2.13.0+cu130" in torch_requirements.splitlines()
    assert '$ExpectedTorch = "torch==2.13.0+cu130"' in local_build_script
    assert '$ExpectedCuda = "13.0"' in local_build_script
    assert 'StartsWith("3.13.")' in local_build_script
    assert "requirements-torch-cuda.txt" not in core_build_script


def test_current_manifest_ownership_routes_local_identity_away_from_core():
    contract = read_repo("docs/project/CURRENT_PRODUCT_CONTRACT.md")
    truth = SOURCE_OF_TRUTH.read_text(encoding="utf-8")

    for requirement in (
        "Core build manifest owns Core provenance only",
        "Core manifest MUST NOT own `torch_requirement` / `expected_cuda`",
        "Local Runtime manifest owns Local runtime identity",
        'torch_requirement = "torch==2.13.0+cu130"',
        'expected_cuda = "13.0"',
        "Runtime discovery is the fail-closed consumer of Local-only metadata",
        "Local/Core `source_head` pairing remains mandatory",
    ):
        assert requirement in contract
    assert "in the **Local Runtime manifest**" in truth
    assert "Historical pre-split Core" in truth
    assert "is superseded by Current Product Contract §7" in truth


def test_current_release_gate_orders_fresh_split_artifacts_before_installed_cuda():
    status = read_repo("docs/release/CURRENT_RELEASE_STATUS.md")
    steps = re.findall(r"^\d+\. (.+)$", status, re.MULTILINE)
    gates = (
        "Release Freeze:",
        "fresh Local Runtime build",
        "fresh Core build",
        "fresh MSI",
        "clean install",
        "installed Core/Local provenance pairing",
        "installed CUDA synthetic tensor",
        "only then actual Local MP3 gate",
    )
    positions = [next(i for i, step in enumerate(steps) if step.startswith(gate)) for gate in gates]

    assert positions == sorted(positions)
    assert "fresh current-HEAD CUDA sidecar" not in status
    assert "#113 remains BLOCKED until the prerequisites complete" in status
    assert "separate 6A-R3c Core" in status
    assert "one branch, one frozen HEAD and one artifact session" in status


def test_no_paid_ci_workflow_exists():
    workflows = REPO_ROOT / ".github/workflows"

    assert not workflows.exists() or not any(path.is_file() for path in workflows.rglob("*"))


def test_zero_cost_release_rule_and_honest_verdict_are_current():
    truth = SOURCE_OF_TRUTH.read_text(encoding="utf-8")
    status = read_repo("docs/release/CURRENT_RELEASE_STATUS.md")

    assert "Unclear cost fails closed" in truth
    assert "RELEASE READY = NO" in status
    assert "PENDING_ZERO_COST_EXTERNAL_VALIDATION" in status
    assert "INVALID RELEASE EVIDENCE" in status


def test_canonical_regression_connects_all_behavioral_validation_layers():
    script = read_repo("scripts/run_core_workflow_regression.ps1")

    for evidence in (
        "pytest', 'tests'",
        "Backend full pytest",
        "npm.cmd' -Arguments @('run', 'lint')",
        "npm.cmd' -Arguments @('run', 'typecheck')",
        "npm.cmd' -Arguments @('run', 'build')",
        "cargo.exe' -Arguments @('test', '--locked')",
    ):
        assert evidence in script
