"""Single-use loopback-only OAuth return. No code/state/query logging."""

import http.server
import secrets
import threading
from urllib.parse import parse_qs, urlsplit


class ColabLoopbackCallback:
    PATH = "/oauth/colab/callback"

    def __init__(self, state):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._result = None
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(2.0)
                super().setup()
            def log_message(self, *args):
                pass
            def do_GET(self):
                ok = owner.accept(self.path, self.headers.get("Host"), self.client_address[0], state)
                body = ("소리글에서 Google Colab 연결 상태를 확인해 주세요. 이 창은 닫아도 됩니다."
                        if ok else "인증 응답을 확인할 수 없습니다. 소리글에서 다시 연결해 주세요.").encode("utf-8")
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
        class Server(http.server.HTTPServer):
            def handle_error(self, request, client_address):
                pass  # no traceback/query from a malformed browser request
        self._http = Server(("127.0.0.1", 0), Handler)
        self._http.timeout = 0.25
        self.port = self._http.server_address[1]

    @property
    def redirect_uri(self):
        return f"http://127.0.0.1:{self.port}{self.PATH}"

    def accept(self, target, host, peer, expected_state):
        # Only relative origin-form on the exact callback host/path is accepted.
        try:
            parsed = urlsplit(target)
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
            if (len(target) > 8192 or peer != "127.0.0.1" or host != f"127.0.0.1:{self.port}"
                    or parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != self.PATH
                    or any(len(values) != 1 for values in query.values())
                    or not secrets.compare_digest(query.get("state", [""])[0], expected_state)
                    or ("code" in query) == ("error" in query)
                    or not (query.get("code") or query.get("error"))[0]):
                return False
        except (ValueError, TypeError):
            return False
        with self._lock:
            if self._event.is_set():
                return False
            # No caller-supplied scope, redirect_uri or error_description is trusted.
            self._result = query["code"][0] if "code" in query else None
            self._event.set()
            return True

    def wait_for_code(self, timeout=300):
        import time
        end = time.monotonic() + timeout
        try:
            while not self._event.is_set() and time.monotonic() < end:
                self._http.handle_request()
            return self._result
        finally:
            self.shutdown()

    def shutdown(self):
        self._event.set()
        self._http.server_close()
