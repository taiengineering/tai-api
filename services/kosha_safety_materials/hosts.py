"""KOSHA host allowlist — production enrichment fetch/validate 공통."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin, urlparse

ALLOWED_HOSTS = frozenset({
    "portal.kosha.or.kr",
    "www.kosha.or.kr",
    "kosha.or.kr",
})

DETAIL_HOST = "portal.kosha.or.kr"
DEFAULT_UA = "TAI-SafetyLibraryCollector/1.0 (+https://taieng.co.kr; contact=tai@taieng.co.kr)"


def is_allowed_host(url: Optional[str]) -> bool:
    if not url:
        return False
    p = urlparse(str(url))
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    return host in ALLOWED_HOSTS


def join_kosha_url(path: str | None) -> str | None:
    if not path or not str(path).strip():
        return None
    p = str(path).strip()
    low = p.lower()
    if low.startswith("javascript:") or low.startswith("data:"):
        return None
    if p.startswith("http://") or p.startswith("https://"):
        return p if is_allowed_host(p) else None
    if p.startswith("/"):
        absu = urljoin(f"https://{DETAIL_HOST}", p)
        return absu if is_allowed_host(absu) else None
    return None
