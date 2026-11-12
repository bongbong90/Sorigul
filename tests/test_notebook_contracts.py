import json
from pathlib import Path
import subprocess
import hashlib
import importlib.util
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def test_notebook_is_clean_manual_cells_without_servers_or_polling():
    notebook = json.loads((ROOT / "colab/Sorigul_large_v3_notebook.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    code = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        assert cell["execution_count"] is None and cell["outputs"] == []
        source = "".join(cell["source"])
        compile("\n".join(line for line in source.splitlines() if not line.startswith("%")), "notebook-cell", "exec")
        code.append(source)
    combined = "\n".join(code)
    for forbidden in ("start_tunnel(", "create_app(", "drive.mount(", "uvicorn", "while True", "requests.get"):
        assert forbidden not in combined
    assert combined.count("transcribe_once(") == 1
    assert "SORIGUL_INFERENCE_STARTED" in combined and "EXPECTED_AUDIO_SHA256" in combined


def test_notebook_import_ui_with_production_component():
    result = subprocess.run(["node", "tests/frontend/notebook_import_harness.cjs"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_portable_code_package_contains_only_exact_dependencies(tmp_path):
    spec = importlib.util.spec_from_file_location("prepare_notebook", ROOT / "tools/prepare_notebook_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "sorigul_notebook_code.zip"
    module.build_package(output, "0" * 40, lambda name: (ROOT / name).read_bytes())
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {*module.FILES, "code_manifest.json"}
        manifest = json.loads(archive.read("code_manifest.json"))
        for name in module.FILES:
            content = archive.read(name)
            assert hashlib.sha256(content).hexdigest() == manifest["sha256"][name]
            compile(content, name, "exec")
