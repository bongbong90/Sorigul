import ipaddress
from urllib.parse import urlparse

class ColabUrlError(ValueError):
    pass

def normalize_colab_base_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlparse(value)
    except Exception:
        raise ColabUrlError("Invalid URL")

    if parsed.scheme not in ("http", "https"):
        raise ColabUrlError("Invalid scheme")
    if not parsed.hostname:
        raise ColabUrlError("Missing hostname")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ColabUrlError("Unsupported components")

    path = parsed.path
    if path == "/health":
        path = ""
    elif path == "/transcribe":
        path = ""
    elif path == "/":
        path = ""

    if path != "":
        raise ColabUrlError("Unsupported path")

    hostname = parsed.hostname.lower()
    if parsed.scheme == "http":
        is_loopback = hostname == "localhost"
        try:
            is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        if not is_loopback:
            raise ColabUrlError("Remote HTTP is not allowed")

    netloc = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError:
        raise ColabUrlError("Invalid port")

    if port:
        netloc = f"{netloc}:{port}"

    return f"{parsed.scheme}://{netloc}"

