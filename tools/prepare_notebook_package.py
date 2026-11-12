"""Export only portable Notebook dependencies from one exact Git commit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

FILES = (
    "colab/sorigul_colab_bootstrap.py", "colab/sorigul_notebook.py",
    "backend/src/domain/transcription.py", "backend/src/services/audio_metadata.py",
    "backend/src/services/output_bundle.py", "backend/src/services/notebook_bundle.py",
)


def build_package(output: Path, commit: str, read_file):
    sources = {name: read_file(name) for name in FILES}
    manifest = {"source_commit": commit, "sha256": {
        name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}}
    with output.open("xb") as handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
        archive.writestr("code_manifest.json", json.dumps(manifest))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    build_package(args.output, commit, lambda name: subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo))
    print("NOTEBOOK_SOURCE_PACKAGE_CREATED — exact committed source; no credentials or user data")


if __name__ == "__main__":
    main()
