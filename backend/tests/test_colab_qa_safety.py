"""No network, credentials or native ownership store. Synthetic observations only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
import hashlib
import io
import json
import socket
import ssl
from urllib.error import HTTPError, URLError
import urllib.request

import pytest

from qa.colab_owned_readback import OwnedObservation, OwnedReadbackAdapter, NativeReadbackWire, OwnedReadbackError
from qa.colab_readback import QADiagnostics, verify_readback
from qa.colab_qa_run import UploadEvidence, FileCleanupEvidence, RuntimeCleanupEvidence, run_qa, QAResultSaveError
from src.services.colab_runtime_client import ConnectionInfo, OwnedRuntime
from src.services.colab_runtime_ownership import OwnershipRecord, OwnershipState
from src.services.colab_jupyter_files import FileTransferRecord, RemoteOwnership, TransferStatus, IntegrityLevel

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
BASE = "https://owned.example.invalid/proxy"
TOKEN = "SYNTHETIC_PRIVATE_PROXY"
DATA = b"synthetic binary\x00\xff"
PATH = "sorigul-transfer/" + "b"*32 + "/chunk-00000.mp3"
EXECUTION = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k): pytest.fail("NETWORK_FORBIDDEN")
    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)


def observation():
    record = OwnershipRecord(EXECUTION, "00000000-0000-4000-8000-000000000002",
        "runtimes/sorigul-"+"1"*32, "a"*64, state=OwnershipState.ACTIVE_OWNED,
        operation_name="operations/synthetic", last_remote_state="CONFIRMED", checked_at=NOW.isoformat())
    runtime = OwnedRuntime(record.runtime_name, ConnectionInfo(BASE, TOKEN, NOW+timedelta(hours=1)))
    file = FileTransferRecord(index=0, remote_path=PATH, size=len(DATA), sha256=hashlib.sha256(DATA).hexdigest(),
        chunks_total=11, chunks_acknowledged=11, status=TransferStatus.VERIFIED,
        integrity=IntegrityLevel.CONTENT_SHA256, error_code=None, verification_error=None,
        remote_may_exist=True, all_chunks_sent=True, attempts=1, ownership=RemoteOwnership.OWNED)
    return OwnedObservation(record, record.account_binding, runtime, file, True)


class Response(io.BytesIO):
    def __init__(self, url, status=200):
        raw = json.dumps({"path":PATH,"type":"file","format":"base64","size":len(DATA),
            "content":"c3ludGhldGljIGJpbmFyeQD/"}).encode()
        super().__init__(raw)
        self.url, self.status = url, status
        self.headers = {"Content-Length":str(len(raw))}
    def geturl(self): return self.url


class Wire:
    def __init__(self, status=200, changed_url=None, error=None):
        self.calls, self.status, self.changed_url, self.error = [], status, changed_url, error
    def open(self, url, token, timeout):
        self.calls.append((url, token, timeout))
        if self.error: raise self.error
        return Response(self.changed_url or url, self.status)


def adapter(initial=None, current=None, wire=None, **kwargs):
    initial = initial or observation()
    return OwnedReadbackAdapter(initial=initial, observe=lambda: current or initial,
        wire=wire or Wire(), expected_execution_id=kwargs.get('execution', EXECUTION),
        approved_base=kwargs.get('base', BASE), utcnow=lambda: NOW)


def verify(instance):
    d = QADiagnostics()
    passed = verify_readback(lambda: instance.open_readback(timeout_seconds=20),
        expected=DATA, expected_path=PATH, diagnostics=d)
    serialized = json.dumps(d.snapshot())
    assert TOKEN not in serialized and BASE not in serialized and PATH not in serialized
    return passed, d


def test_owned_pinned_get_success_and_one_attempt_only():
    wire = Wire()
    instance = adapter(wire=wire)
    assert verify(instance)[0]
    assert wire.calls == [(BASE+"/api/contents/"+PATH+"?content=1&format=base64", TOKEN, 20)]
    assert not verify(instance)[0]
    assert len(wire.calls) == 1
    assert TOKEN not in repr(instance) and BASE not in repr(instance)


@pytest.mark.parametrize('change', [
    'account','execution','request','runtime','origin','path','ownership','file_owner','deleted','expired','transfer',
])
def test_cross_execution_or_unowned_observations_block_before_http(change):
    initial = current = observation()
    if change == 'account': current = replace(current, verified_account_binding='f'*64)
    if change == 'execution': current = replace(current,record=replace(current.record,execution_id='00000000-0000-4000-8000-000000000003'))
    if change == 'request': current = replace(current,record=replace(current.record,request_id='00000000-0000-4000-8000-000000000003'))
    if change == 'runtime': current = replace(current,runtime=replace(current.runtime,name='runtimes/sorigul-'+'2'*32))
    if change == 'origin': current = replace(current,runtime=replace(current.runtime,connection_info=replace(current.runtime.connection_info,url='https://other.invalid/proxy')))
    if change == 'path': current = replace(current,file=replace(current.file,remote_path='sorigul-transfer/'+'c'*32+'/chunk-00000.mp3'))
    if change == 'ownership': current = replace(current,record=replace(current.record,state=OwnershipState.RECOVERY_REQUIRED))
    if change == 'file_owner': current = replace(current,file=replace(current.file,ownership=RemoteOwnership.UNCERTAIN))
    if change == 'deleted': current = replace(current,file=replace(current.file,remote_deleted=True))
    if change == 'expired': current = replace(current,runtime=replace(current.runtime,connection_info=replace(current.runtime.connection_info,expire_time=NOW)))
    if change == 'transfer': current = replace(current,transfer_connection_matches=False)
    wire = Wire()
    assert not verify(adapter(initial,current,wire))[0]
    assert wire.calls == []


@pytest.mark.parametrize('path', ['../secret','/etc/passwd',PATH+'?x=1',PATH+'#x',PATH.replace('chunk-','%63hunk-')])
def test_invalid_initial_contents_path_rejected(path):
    initial = observation()
    with pytest.raises(OwnedReadbackError):
        adapter(replace(initial,file=replace(initial.file,remote_path=path)))


@pytest.mark.parametrize('base', ['http://owned.example.invalid/proxy','https://unapproved.invalid/proxy',BASE+'/different'])
def test_initial_unapproved_origin_rejected(base):
    initial = observation()
    with pytest.raises(OwnedReadbackError):
        adapter(replace(initial,runtime=replace(initial.runtime,connection_info=replace(initial.runtime.connection_info,url=base))))


def test_wrong_expected_execution_rejected():
    with pytest.raises(OwnedReadbackError): adapter(execution='other-execution')


def test_redirect_or_changed_response_origin_fails_closed():
    for wire in (Wire(status=302),Wire(changed_url='https://unapproved.invalid')):
        passed, diagnostics = verify(adapter(wire=wire))
        assert not passed and diagnostics.jupyter_accessed
        assert len(wire.calls) == 1


def test_native_wire_builds_no_proxy_no_redirect_tls_and_proxy_only_header():
    handlers, requests = [], []
    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return Response(request.full_url)
    def factory(*items):
        handlers.extend(items)
        return Opener()
    wire = NativeReadbackWire(opener_factory=factory)
    assert verify(adapter(wire=wire))[0]
    request, timeout = requests[0]
    assert request.get_method() == 'GET' and timeout == 20
    assert request.get_header('Authorization') is None
    assert request.get_header('X-colab-runtime-proxy-token') == TOKEN
    assert next(h for h in handlers if isinstance(h,urllib.request.ProxyHandler)).proxies == {}
    redirect = next(h for h in handlers if isinstance(h,urllib.request.HTTPRedirectHandler))
    assert redirect.redirect_request(request,None,302,'',{},'https://evil.invalid') is None
    tls = next(h for h in handlers if isinstance(h,urllib.request.HTTPSHandler))._context
    assert tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize('timeout', [0,-1,21,True,float('inf')])
def test_adapter_timeout_bound(timeout):
    instance = adapter()
    with pytest.raises(OwnedReadbackError):
        with instance.open_readback(timeout_seconds=timeout): pass


def test_adapter_response_read_cap():
    instance = adapter()
    with instance.open_readback(timeout_seconds=20) as response:
        with pytest.raises(OwnedReadbackError): response.read(2*1024*1024+2)


@pytest.mark.parametrize('error', [HTTPError('https://PRIVATE',403,'PRIVATE',{},None),TimeoutError('PRIVATE'),RuntimeError('PRIVATE')])
def test_wire_errors_are_redacted_and_http_timeout_preserved(error):
    passed, d = verify(adapter(wire=Wire(error=error)))
    assert not passed and 'PRIVATE' not in json.dumps(d.snapshot())
    if isinstance(error,HTTPError): assert d.readback.http_status == 403
    if isinstance(error,TimeoutError): assert d.readback.error_code == 'TIMEOUT'


@pytest.mark.parametrize('error,code', [(IncompleteRead(b'PRIVATE',12),'INCOMPLETE_RESPONSE'),
    (URLError('PRIVATE'),'TRANSPORT_ERROR'),(OSError('PRIVATE'),'TRANSPORT_ERROR')])
def test_wire_preserves_safe_transport_failure_categories(error,code):
    passed, d = verify(adapter(wire=Wire(error=error)))
    assert not passed and d.readback.error_code == code
    assert 'PRIVATE' not in json.dumps(d.snapshot())


def test_wire_http_error_close_failure_remains_visible():
    class BrokenClose:
        def close(self): raise OSError('PRIVATE')
    _, d = verify(adapter(wire=Wire(error=HTTPError('https://PRIVATE',403,'PRIVATE',{},BrokenClose()))))
    assert d.readback.error_code == 'HTTP_ERROR'
    assert d.readback.response_close_failed is True


@pytest.mark.parametrize('status,read_error,code', [(403,None,'HTTP_ERROR'),(200,TimeoutError('PRIVATE'),'TIMEOUT'),(200,None,'RESPONSE_CLOSE_FAILED')])
def test_primary_error_survives_normal_response_close_failure(status,read_error,code):
    class Broken(Response):
        def read(self,limit):
            if read_error: raise read_error
            return super().read(limit)
        def __exit__(self,*args):
            super().__exit__(*args)
            raise OSError('PRIVATE')
    d = QADiagnostics()
    assert not verify_readback(lambda: Broken(BASE,status),expected=DATA,expected_path=PATH,diagnostics=d)
    assert d.readback.error_code == code and d.readback.response_close_failed
    assert d.jupyter_accessed and 'PRIVATE' not in json.dumps(d.snapshot())


def test_cancel_survives_a_simultaneous_result_save_failure():
    events=[]
    def cancel(): raise KeyboardInterrupt()
    def runtime():
        events.append('runtime')
        return RuntimeCleanupEvidence(True,True,True,True)
    def save(snapshot): raise RuntimeError('PRIVATE')
    with pytest.raises(KeyboardInterrupt):
        run_qa(upload=UploadEvidence(True,True,True,11,11),expected=DATA,expected_path=PATH,
            transport=adapter(),file_cleanup=cancel,runtime_cleanup=runtime,save_snapshot=save)
    assert events == ['runtime']


def test_caller_handled_exception_is_not_mistaken_for_internal_cancellation():
    def save(snapshot): raise RuntimeError('PRIVATE_WRITER')
    try:
        raise ValueError('PRIVATE_CALLER')
    except ValueError:
        with pytest.raises(QAResultSaveError, match='^QA_RESULT_SAVE_FAILED$'):
            run_qa(upload=UploadEvidence(True,True,True,11,11),expected=DATA,expected_path=PATH,
                transport=adapter(),file_cleanup=lambda:FileCleanupEvidence(True,True,True),
                runtime_cleanup=lambda:RuntimeCleanupEvidence(True,True,True,True),save_snapshot=save)


def test_http_error_from_body_and_failing_response_close_keep_both_facts():
    class Broken(Response):
        def read(self,limit): raise HTTPError('https://PRIVATE',403,'PRIVATE',{},None)
        def __exit__(self,*args): raise OSError('PRIVATE')
    d=QADiagnostics()
    assert not verify_readback(lambda:Broken(BASE),expected=DATA,expected_path=PATH,diagnostics=d)
    assert d.readback.error_code == 'HTTP_ERROR' and d.readback.response_close_failed
