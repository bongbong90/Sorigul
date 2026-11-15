"""Run a deterministic synthetic readback demo, without network or credentials.

From backend: python -m qa.colab_readback_fixture
Only an allowlisted receipt is printed; no media, paths or hashes are emitted.
"""
import base64
import io
import json

from qa.colab_readback import QADiagnostics, verify_readback


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

    diagnostics = QADiagnostics()
    passed = verify_readback(lambda: SyntheticResponse(payload), expected=expected,
                             expected_path=path, diagnostics=diagnostics)
    print(json.dumps(diagnostics.snapshot(), sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
