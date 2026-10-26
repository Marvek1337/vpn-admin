from urllib.parse import urlsplit, urlunsplit


ALLOWED_NEXT_PREFIXES = ("/cabinet", "/admin", "/claim/attach")


def safe_next_url(value: str | None, default: str = "/cabinet") -> str:
    if not value:
        return default

    raw = str(value).strip()
    if not raw or raw.startswith("//") or "\\" in raw:
        return default

    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return default

    path = parsed.path or default
    if not path.startswith("/"):
        return default
    if not any(path == prefix or path.startswith(f"{prefix}/") for prefix in ALLOWED_NEXT_PREFIXES):
        return default

    return urlunsplit(("", "", path, parsed.query, ""))
