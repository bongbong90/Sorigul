from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.services.results import (
    _TEXT_ENCODINGS,
    _read_text_with_fallback,
    ResultsService,
)


UTF8_TEXT = "공인중개사 민법 전사 결과\n제1강"
EUC_KR_TEXT = "공인중개사 민법 강의\n첫째 시간"
MALFORMED_BYTES = b"broken: \xff\xfe\x80 end"


def _write_fixture(path: Path, content: str, encoding: str) -> None:
    path.write_bytes(content.encode(encoding))


def _scan_item(service: ResultsService, folder: Path, filename: str):
    result = service.scan(str(folder), "results")
    return result.scan_id, next(item.id for item in result.items if item.filename == filename)


@pytest.mark.parametrize(
    ("filename", "encoding", "content"),
    [
        ("utf8.txt", "utf-8", UTF8_TEXT),
        ("utf8_sig.txt", "utf-8-sig", UTF8_TEXT),
        ("cp949.txt", "cp949", UTF8_TEXT),
        ("euc_kr.txt", "euc-kr", EUC_KR_TEXT),
    ],
)
def test_preview_and_full_decode_supported_encodings_consistently(
    tmp_path, filename, encoding, content
):
    path = tmp_path / filename
    _write_fixture(path, content, encoding)
    service = ResultsService(preview_chars=9)
    scan_id, item_id = _scan_item(service, tmp_path, filename)

    preview = service.read_text(scan_id, item_id)
    full = service.read_text(scan_id, item_id, full=True)

    assert full.text == content
    assert preview.text == full.text[:9]
    assert preview.truncated is (len(content) > 9)
    assert "\ufeff" not in preview.text
    assert "\ufeff" not in full.text
    assert "\ufffd" not in full.text


def test_malformed_bytes_use_utf8_replacement_for_preview_and_full(tmp_path):
    path = tmp_path / "malformed.txt"
    path.write_bytes(MALFORMED_BYTES)
    expected = MALFORMED_BYTES.decode("utf-8", errors="replace")
    service = ResultsService(preview_chars=10)
    scan_id, item_id = _scan_item(service, tmp_path, path.name)

    preview = service.read_text(scan_id, item_id)
    full = service.read_text(scan_id, item_id, full=True)

    assert full.text == expected
    assert "\ufffd" in full.text
    assert preview.text == full.text[:10]
    assert preview.truncated is (len(expected) > 10)


def test_reads_do_not_change_source_bytes_or_mtime(tmp_path):
    path = tmp_path / "외부 수정 결과.txt"
    path.write_bytes(UTF8_TEXT.encode("cp949"))
    before_bytes = path.read_bytes()
    before_mtime_ns = path.stat().st_mtime_ns
    service = ResultsService(preview_chars=8)
    scan_id, item_id = _scan_item(service, tmp_path, path.name)

    service.read_text(scan_id, item_id)
    service.read_text(scan_id, item_id, full=True)

    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime_ns


def test_preview_is_bounded_but_full_view_keeps_size_limit(tmp_path):
    path = tmp_path / "large.txt"
    path.write_bytes(("가" * 20).encode("cp949"))
    service = ResultsService(preview_chars=5, max_text_bytes=10)
    scan_id, item_id = _scan_item(service, tmp_path, path.name)

    preview = service.read_text(scan_id, item_id)

    assert preview.text == "가" * 5
    assert preview.truncated is True
    with pytest.raises(ValueError, match="TXT_TOO_LARGE"):
        service.read_text(scan_id, item_id, full=True)


def test_fallback_order_and_each_attempt_use_the_preview_bound():
    calls = []

    class FakeHandle:
        def __init__(self, encoding, errors):
            self.encoding = encoding
            self.errors = errors

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, max_chars):
            calls.append((self.encoding, self.errors, max_chars))
            if self.errors == "strict":
                raise UnicodeDecodeError(self.encoding, b"\xff", 0, 1, "invalid")
            return "\ufffd"

    class FakePath:
        def open(self, mode, encoding, errors):
            assert mode == "r"
            return FakeHandle(encoding, errors)

    assert _TEXT_ENCODINGS == ("utf-8-sig", "utf-8", "cp949", "euc-kr")
    assert _read_text_with_fallback(FakePath(), max_chars=501) == "\ufffd"
    assert calls == [
        ("utf-8-sig", "strict", 501),
        ("utf-8", "strict", 501),
        ("cp949", "strict", 501),
        ("euc-kr", "strict", 501),
        ("utf-8", "replace", 501),
    ]


@pytest.mark.parametrize("error_type", [PermissionError, OSError])
def test_filesystem_errors_are_not_retried_as_encoding_failures(
    tmp_path, monkeypatch, error_type
):
    path = tmp_path / "unreadable.txt"
    path.write_text(UTF8_TEXT, encoding="utf-8")
    service = ResultsService()
    scan_id, item_id = _scan_item(service, tmp_path, path.name)
    original_open = Path.open
    calls = []

    def fail_target_open(self, *args, **kwargs):
        if self == path:
            calls.append(kwargs.get("encoding"))
            raise error_type("cannot read")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_target_open)
    with pytest.raises(error_type):
        service.read_text(scan_id, item_id)
    assert calls == ["utf-8-sig"]


def test_scan_item_and_extension_boundaries_remain_enforced(tmp_path):
    txt = tmp_path / "safe.txt"
    txt.write_text(UTF8_TEXT, encoding="utf-8")
    json_path = tmp_path / "safe.json"
    json_path.write_text("{}", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    service = ResultsService()
    result = service.scan(str(tmp_path), "results")
    ids = {item.filename: item.id for item in result.items}

    with pytest.raises(KeyError, match="SCAN_NOT_FOUND"):
        service.read_text("unknown-scan", ids[txt.name])
    with pytest.raises(KeyError, match="ITEM_NOT_FOUND"):
        service.read_text(result.scan_id, "unknown-item")
    with pytest.raises(ValueError, match="UNEXPECTED_EXTENSION"):
        service.read_text(result.scan_id, ids[json_path.name])

    service._contexts[result.scan_id].paths[ids[txt.name]] = outside
    with pytest.raises(PermissionError, match="PATH_OUTSIDE_SCAN"):
        service.read_text(result.scan_id, ids[txt.name])


@pytest.fixture
def route_client(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app

    service = ResultsService(preview_chars=7, max_text_bytes=64)
    monkeypatch.setattr(routes, "results_service", service)
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_routes_return_decoded_cp949_and_malformed_text(route_client, tmp_path):
    cp949_path = tmp_path / "한글 cp949.txt"
    cp949_path.write_bytes(UTF8_TEXT.encode("cp949"))
    malformed_path = tmp_path / "malformed.txt"
    malformed_path.write_bytes(MALFORMED_BYTES)

    scan = route_client.post(
        "/api/folders/scan", json={"folder": str(tmp_path), "filter": "results"}
    )
    assert scan.status_code == 200
    body = scan.json()
    ids = {item["filename"]: item["id"] for item in body["items"]}

    cp949_preview = route_client.get(
        f"/api/folders/{body['scan_id']}/items/{ids[cp949_path.name]}/preview"
    )
    cp949_full = route_client.get(
        f"/api/folders/{body['scan_id']}/items/{ids[cp949_path.name]}/text"
    )
    malformed_full = route_client.get(
        f"/api/folders/{body['scan_id']}/items/{ids[malformed_path.name]}/text"
    )

    assert cp949_preview.status_code == 200
    assert cp949_preview.json()["text"] == UTF8_TEXT[:7]
    assert cp949_preview.json()["truncated"] is True
    assert cp949_full.status_code == 200
    assert cp949_full.json()["text"] == UTF8_TEXT
    assert malformed_full.status_code == 200
    assert malformed_full.json()["text"] == MALFORMED_BYTES.decode(
        "utf-8", errors="replace"
    )


def test_routes_preserve_size_extension_and_lookup_errors(route_client, tmp_path):
    oversized = tmp_path / "oversized.txt"
    oversized.write_text("x" * 65, encoding="utf-8")
    json_path = tmp_path / "result.json"
    json_path.write_text("{}", encoding="utf-8")
    scan = route_client.post(
        "/api/folders/scan", json={"folder": str(tmp_path), "filter": "results"}
    ).json()
    ids = {item["filename"]: item["id"] for item in scan["items"]}
    base = f"/api/folders/{scan['scan_id']}/items"

    preview = route_client.get(f"{base}/{ids[oversized.name]}/preview")
    too_large = route_client.get(f"{base}/{ids[oversized.name]}/text")
    non_txt = route_client.get(f"{base}/{ids[json_path.name]}/preview")
    unknown_item = route_client.get(f"{base}/unknown-item/preview")
    unknown_scan = route_client.get(
        f"/api/folders/unknown-scan/items/{ids[oversized.name]}/preview"
    )
    oversized.unlink()
    moved_after_scan = route_client.get(f"{base}/{ids[oversized.name]}/preview")

    assert preview.status_code == 200
    assert preview.json() == {
        "filename": oversized.name,
        "text": "x" * 7,
        "truncated": True,
    }
    assert too_large.status_code == 400
    assert too_large.json() == {"detail": "TXT 파일이 전체 보기 제한보다 큽니다."}
    assert non_txt.status_code == 400
    assert non_txt.json() == {"detail": "TXT 파일만 읽을 수 있습니다."}
    assert unknown_item.status_code == 404
    assert unknown_scan.status_code == 404
    assert moved_after_scan.status_code == 404
    assert moved_after_scan.json() == {"detail": "TXT 파일이 존재하지 않습니다."}
