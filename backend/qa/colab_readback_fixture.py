"""Run a deterministic synthetic readback demo, without network or credentials.

From backend: python -m qa.colab_readback_fixture
Only an allowlisted receipt is printed; no media, paths or hashes are emitted.
"""
import base64
import io
import json

from qa.colab_qa_run import FileCleanupEvidence, RuntimeCleanupEvidence, UploadEvidence, run_qa


def main():
    expected = (bytes(range(256)) * 2588)[:662508]
    path = "sorigul-transfer/offline-fixture/synthetic.bin"
    payload = json.dumps({
        "path": path, "type": "file", "format": "base64", "size": len(expected),
        "content": base64.encodebytes(expected).decode("ascii"),
    }).encode()

    class SyntheticResponse(io.BytesIO):
        status = 200
        headers = {"Content-Length": str(len(payload))}

    class SyntheticTransport:
        def open_readback(self, *, timeout_seconds):
            return SyntheticResponse(payload)

    diagnostics = run_qa(upload=UploadEvidence(True, True, True, 11, 11),
        expected=expected, expected_path=path, transport=SyntheticTransport(),
        file_cleanup=lambda: FileCleanupEvidence(True, True, True),
        runtime_cleanup=lambda: RuntimeCleanupEvidence(True, True, True, True),
        save_snapshot=lambda snapshot: print(json.dumps(snapshot, sort_keys=True)))
    return 0 if diagnostics.run_outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
