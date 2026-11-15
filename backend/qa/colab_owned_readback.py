"""QA-only owned Contents adapter; no credentials, Runtime API or delete methods.

Only a trusted, separately approved QA coordinator may supply the observer.
It must obtain the current durable record, verified account binding, Runtime
and OWNED transfer record under the existing ownership/lease discipline.
No bool/string received from product UI or settings is an ownership authority.
The native HTTP wire is explicit and is never constructed by this adapter.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import IncompleteRead
import math
import re
import ssl
import sys
import urllib.request
from urllib.error import HTTPError, URLError

from qa.colab_readback import CheckFailed, Code, _close_error

from src.services.colab_jupyter_client import ColabJupyterClient, _NoRedirectHTTP
from src.services.colab_jupyter_files import FileTransferRecord, RemoteOwnership, IntegrityLevel, TransferStatus
from src.services.colab_runtime_client import OwnedRuntime
from src.services.colab_runtime_ownership import OwnershipRecord, OwnershipState


class OwnedReadbackError(CheckFailed):
    def __init__(self, *, http_status=None, response_received=False):
        super().__init__(Code.OWNED_TRANSPORT_BLOCKED, http_status=http_status,
                         response_received=response_received)


def _private_call(callback):
    try:
        return callback()
    except HTTPError as exc:
        failed_close = _close_error(exc)
        safe = HTTPError("", exc.code, "OWNED_HTTP_ERROR", {}, None)
        safe._qa_close_failed = failed_close
        raise safe from None
    except TimeoutError:
        raise TimeoutError("OWNED_TIMEOUT") from None
    except IncompleteRead:
        raise IncompleteRead(b"", None) from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise TimeoutError("OWNED_TIMEOUT") from None
        raise URLError("OWNED_TRANSPORT_ERROR") from None
    except OSError:
        raise OSError("OWNED_TRANSPORT_ERROR") from None
    except CheckFailed:
        raise
    except Exception:
        raise OwnedReadbackError() from None


@dataclass(frozen=True, repr=False)
class OwnedObservation:
    record: OwnershipRecord
    verified_account_binding: str
    runtime: OwnedRuntime
    file: FileTransferRecord
    transfer_connection_matches: bool


class NativeReadbackWire:
    """Explicit future-live boundary. Tests inject an opener and never use HTTP.

    No OAuth, redirects, environment proxies, configurable headers or retries.
    Request data and private connection values must never be logged by a wire.
    """
    def __init__(self, *, opener_factory=urllib.request.build_opener):
        self._opener = opener_factory(urllib.request.ProxyHandler({}), _NoRedirectHTTP(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def open(self, url, proxy_token, timeout):
        request = urllib.request.Request(url, method="GET", headers={
            "X-Colab-Runtime-Proxy-Token": proxy_token})
        return self._opener.open(request, timeout=timeout)

    def __repr__(self):
        return "NativeReadbackWire(<private>)"


class OwnedReadbackAdapter:
    """Pin one execution/account/Runtime/origin/exact OWNED path; one GET only.

    `initial` and `observe` are trusted coordinator observations, not proofs
    generated from caller labels. No actual observation is performed at import.
    Refreshing the observer may rotate proxy tokens only within the same binding.
    An invalid/ambiguous attempt consumes this instance; no fallback or retry.
    """
    def __init__(self, *, initial: OwnedObservation, observe, wire,
                 expected_execution_id: str, approved_base: str,
                 utcnow=lambda: datetime.now(timezone.utc)):
        self._observe, self._wire, self._utcnow = observe, wire, utcnow
        self._execution_id, self._approved_base = expected_execution_id, approved_base
        self._attempted = False
        try:
            self._pin = self._validate(initial)
        except Exception:
            raise OwnedReadbackError() from None

    def __repr__(self):
        return "OwnedReadbackAdapter(<private>)"

    @property
    def expected_path(self):
        # Coordinator uses this same bound path for JSON validation. Never log.
        return self._pin[-1]

    def _validate(self, observation):
        if type(observation) is not OwnedObservation:
            raise OwnedReadbackError()
        r, runtime, f = observation.record, observation.runtime, observation.file
        if type(r) is not OwnershipRecord or type(runtime) is not OwnedRuntime or type(f) is not FileTransferRecord:
            raise OwnedReadbackError()
        r.validate()
        if (r.execution_id != self._execution_id
                or r.state is not OwnershipState.ACTIVE_OWNED or r.cleanup_required is not True
                or observation.verified_account_binding != r.account_binding
                or runtime.name != r.runtime_name
                or observation.transfer_connection_matches is not True
                or f.ownership is not RemoteOwnership.OWNED or f.status is not TransferStatus.VERIFIED
                or f.integrity is not IntegrityLevel.CONTENT_SHA256 or f.all_chunks_sent is not True
                or type(f.chunks_total) is not int or f.chunks_total < 1
                or f.chunks_acknowledged != f.chunks_total
                or type(f.size) is not int or f.size < 0
                or not isinstance(f.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", f.sha256)
                or f.remote_may_exist is not True or f.remote_deleted is not False
                or not re.fullmatch(r"sorigul-transfer/[0-9a-f]{32}/chunk-[0-9]{5}\.mp3", f.remote_path)):
            raise OwnedReadbackError()
        origin = ColabJupyterClient._validate_info(runtime.connection_info)
        if origin != self._approved_base or runtime.connection_info.expire_time <= self._utcnow():
            raise OwnedReadbackError()
        return (r.execution_id, r.request_id, r.account_binding, r.runtime_name,
                f.index, f.size, f.sha256, origin, f.remote_path)

    @contextmanager
    def open_readback(self, *, timeout_seconds):
        try:
            if (self._attempted or isinstance(timeout_seconds, bool)
                    or not isinstance(timeout_seconds, (int, float))
                    or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 20):
                raise OwnedReadbackError()
            self._attempted = True
            current = self._observe()
            if self._validate(current) != self._pin:
                raise OwnedReadbackError()
            url = self._pin[-2] + "/api/contents/" + self._pin[-1] + "?content=1&format=base64"
            manager = _private_call(lambda: self._wire.open(url, current.runtime.connection_info.token, timeout_seconds))
        except (HTTPError, TimeoutError, IncompleteRead, URLError, OSError):
            raise
        except Exception:
            # No raw URL-bearing transport exception can escape this boundary.
            raise OwnedReadbackError() from None
        # Enter/close via the outer verifier, so its receipt observes and protects
        # ordinary response close failures. This adapter has no logging surface.
        class BoundResponse:
            def __init__(self, raw):
                self.raw, self.read_once = raw, False
                self.status, self.headers = raw.status, raw.headers
            def read(self, limit):
                if self.read_once or type(limit) is not int or not 0 <= limit <= 2*1024*1024+1:
                    raise OwnedReadbackError()
                self.read_once = True
                return _private_call(lambda: self.raw.read(limit))
        raw = _private_call(manager.__enter__)
        pending = (None, None, None)
        try:
            if _private_call(raw.geturl) != url:
                raise OwnedReadbackError(http_status=raw.status, response_received=True)
            yield BoundResponse(raw)
        except BaseException:
            pending = sys.exc_info()
            raise
        finally:
            try:
                manager.__exit__(*pending)
            except Exception:
                # Never let the wire's URL-bearing close error escape. The outer
                # scope marks response_close_failed and retains its primary error.
                raise OwnedReadbackError() from None
