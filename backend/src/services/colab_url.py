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
        
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
        
    return f"{parsed.scheme}://{netloc}"

