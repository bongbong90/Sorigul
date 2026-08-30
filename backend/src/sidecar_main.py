"""Packaged backend entrypoint.

Supports:
  sorigul-backend.exe --port 8000        (normal run, same FastAPI app as dev)
  sorigul-backend.exe --self-test        (import/runtime checks only, no server,
                                           no model download, no Google login,
                                           no Drive upload, no transcription)

`--self-test` exists so a build script can verify a freshly produced
executable actually carries a working runtime (FastAPI, uvicorn, Google Drive
client libraries, whisper, torch, ffmpeg) without paying the cost, or the
side effects, of really starting the server or touching a network/model.
"""

import argparse
import sys
from pathlib import Path


def _self_test() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            results.append((name, True, ""))
        except Exception as exc:  # noqa: BLE001 - a check failure is a result, not a crash
            results.append((name, False, str(exc)))

    def check_fastapi_app() -> None:
        from src.main import app

        assert app.title == "Sorigul Core Backend"

    def check_uvicorn() -> None:
        import uvicorn  # noqa: F401

    def check_google_drive_runtime() -> None:
        import google.auth.transport.requests  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401

    def check_whisper() -> None:
        import whisper  # noqa: F401

    def check_torch() -> None:
        import torch  # noqa: F401

    def check_ffmpeg() -> None:
        from src.utils.ffmpeg_runtime import resolve_ffmpeg_path

        path = resolve_ffmpeg_path()
        if not path:
            raise RuntimeError("ffmpeg executable not resolvable (PATH or bundled sibling)")

    def check_audio_metadata() -> None:
        import mutagen  # noqa: F401
        from mutagen.mp3 import MP3  # noqa: F401
        from src.services.audio_metadata import AudioMetadataService  # noqa: F401

    def check_runtime_paths() -> None:
        from src.utils.paths import get_app_data_dir

        get_app_data_dir()

    check("fastapi_app_import", check_fastapi_app)
    check("uvicorn_import", check_uvicorn)
    check("google_drive_runtime_import", check_google_drive_runtime)
    check("whisper_import", check_whisper)
    check("torch_import", check_torch)
    check("ffmpeg_availability", check_ffmpeg)
    check("audio_metadata_service_import", check_audio_metadata)
    check("runtime_path_initialization", check_runtime_paths)

    lines = []
    ok = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        line = f"[self-test] {name}: {status}" + (f" ({detail})" if detail else "")
        lines.append(line)
        ok = ok and passed

    output = "\n".join(lines)
    print(output)

    # A frozen, windowed (console=False) build has no attached stdio, so
    # PyInstaller silently discards prints. Always leave a log file next to
    # the executable so a build script can confirm results either way.
    if getattr(sys, "frozen", False):
        log_path = Path(sys.executable).parent / "sorigul-backend-selftest.log"
        try:
            log_path.write_text(output + "\n", encoding="utf-8")
        except OSError:
            pass

    return 0 if ok else 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="sorigul-backend")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    import uvicorn

    from src.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
