"""Versioned Local Whisper worker. Stdout is reserved for one JSON response."""

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from src.domain.transcription import TranscriptionResult
from src.engines.local_whisper import EXPECTED_CUDA, PROTOCOL_VERSION, TORCH_REQUIREMENT
from src.services.output_bundle import OutputBundleWriter


def _cuda_build_detail(torch_module) -> str:
    cuda_version = torch_module.version.cuda
    if cuda_version is None:
        raise RuntimeError(f"CPU-only torch build: {torch_module.__version__}")
    return f"torch={torch_module.__version__}, cuda={cuda_version}"


def _cuda_available_detail(torch_module) -> str:
    device_count = torch_module.cuda.device_count()
    if not torch_module.cuda.is_available() or device_count < 1:
        raise RuntimeError(
            "CUDA runtime unavailable"
            f" (torch={torch_module.__version__}, cuda={torch_module.version.cuda},"
            f" devices={device_count})"
        )
    device_name = torch_module.cuda.get_device_name(0)
    if not device_name:
        raise RuntimeError("CUDA device name unavailable")
    return f"torch={torch_module.__version__}, cuda={torch_module.version.cuda}, device={device_name}"


def _cuda_compute_detail(torch_module) -> str:
    left = torch_module.tensor(
        [[1.0, 2.0], [3.0, 4.0]], device="cuda", dtype=torch_module.float32
    )
    right = torch_module.tensor(
        [[5.0, 6.0], [7.0, 8.0]], device="cuda", dtype=torch_module.float32
    )
    result = torch_module.matmul(left, right)
    torch_module.cuda.synchronize()
    actual = result.cpu().tolist()
    if actual != [[19.0, 22.0], [43.0, 50.0]]:
        raise RuntimeError(f"unexpected CUDA matrix product: {actual!r}")
    return "2x2 CUDA matrix multiply verified"


def _validate_request(request: Any) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    if type(request.get("protocol_version")) is not int or request["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("protocol version mismatch")
    if request.get("action") != "transcribe":
        raise ValueError("unsupported action")
    if request.get("model") != "medium":
        raise ValueError("unsupported model")
    expected_options = {
        "language": "ko",
        "task": "transcribe",
        "temperature": 0,
        "beam_size": 5,
        "best_of": 5,
        "patience": 1.0,
        "condition_on_previous_text": False,
    }
    if request.get("options") != expected_options:
        raise ValueError("unsupported transcription options")
    if type(request.get("input_path")) is not str or type(request.get("output_dir")) is not str:
        raise ValueError("input_path/output_dir must be strings")
    return request


def _transcribe(request: dict) -> dict:
    import torch
    import whisper

    source_path = Path(request["input_path"])
    output_dir = Path(request["output_dir"])
    if not source_path.is_file():
        raise ValueError("input file does not exist")
    if not output_dir.is_dir():
        raise ValueError("output directory does not exist")

    device = "cpu"
    model = None
    if torch.cuda.is_available():
        try:
            model = whisper.load_model("medium", device="cuda")
            device = "cuda"
        except Exception as exc:  # noqa: BLE001 - prescribed CPU fallback
            print(f"CUDA model load failed; using CPU: {exc}", file=sys.stderr, flush=True)
    if model is None:
        model = whisper.load_model("medium", device="cpu")

    options = dict(request["options"])
    options["fp16"] = device == "cuda"
    try:
        payload = model.transcribe(str(source_path), **options)
    except Exception as exc:  # noqa: BLE001 - prescribed fp16 fallback
        lowered = str(exc).lower()
        if options["fp16"] and any(marker in lowered for marker in ("fp16", "float16", "half", "cublas")):
            print("fp16 fallback", file=sys.stderr, flush=True)
            options["fp16"] = False
            payload = model.transcribe(str(source_path), **options)
        else:
            raise

    result = TranscriptionResult.from_engine_payload(payload)
    paths = OutputBundleWriter().commit(output_dir / source_path.name, result)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "ok": True,
        "status": "DONE",
        "device": device,
        "outputs": {key: str(value) for key, value in paths.as_dict().items()},
        "error": None,
    }


def _self_test() -> dict:
    import torch
    import whisper  # noqa: F401

    if torch.__version__ != TORCH_REQUIREMENT.removeprefix("torch=="):
        raise RuntimeError("torch requirement mismatch")
    if torch.version.cuda != EXPECTED_CUDA:
        raise RuntimeError("CUDA version mismatch")
    _cuda_build_detail(torch)
    _cuda_available_detail(torch)
    _cuda_compute_detail(torch)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "ok": True,
        "status": "DONE",
        "device": "cuda",
        "outputs": {},
        "error": None,
    }


def _failure(exc: Exception) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "ok": False,
        "status": "FAILED",
        "error": {"code": "LOCAL_RUNTIME_ERROR", "message": str(exc)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sorigul-local-whisper")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.self_test:
                response = _self_test()
            else:
                if args.request is not None:
                    request = json.loads(args.request.read_text(encoding="utf-8"))
                else:
                    request = json.load(sys.stdin)
                response = _transcribe(_validate_request(request))
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0 if response["ok"] else 1
    except Exception as exc:  # noqa: BLE001 - stable protocol boundary, no traceback
        sys.stdout.write(json.dumps(_failure(exc), ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
