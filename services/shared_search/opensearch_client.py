"""OpenSearch client factory — WO-TAI-SHARED-SEARCH-F3 §9.

ONE shared entry-point for every OpenSearch consumer in Shared Search.
No consumer creates its own client.

Environment variables (repo convention, see .env.example):
    TAI_OPENSEARCH_URL      Full URL incl. scheme, host, port.
                            Example: http://localhost:9200
                            Required for any production path.
    TAI_OPENSEARCH_USER     HTTP Basic auth user (optional).
    TAI_OPENSEARCH_PASS     HTTP Basic auth password (optional).
    TAI_OPENSEARCH_VERIFY_CERTS
                            "true" (default) / "false" — TLS verify.

Production hard-fence: this module never performs writes.
Writes go through opensearch_store.py (RebuildWriter).
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError as OSConnectionError, TransportError


# ---------------------------------------------------------------------------
# Environment variable names (single authority)
# ---------------------------------------------------------------------------
ENV_URL          = "TAI_OPENSEARCH_URL"
ENV_USER         = "TAI_OPENSEARCH_USER"
ENV_PASS         = "TAI_OPENSEARCH_PASS"
ENV_VERIFY_CERTS = "TAI_OPENSEARCH_VERIFY_CERTS"

# Logical alias — application always uses this, never the physical name.
CURRENT_ALIAS    = "tai-shared-search-current"
# Run metadata index (one per cluster)
RUNS_INDEX       = "tai-shared-search-runs"

# Shared Search timeout defaults
_CONNECT_TIMEOUT  = 5    # seconds
_REQUEST_TIMEOUT  = 30   # seconds

_client: Optional[OpenSearch] = None
_lock   = threading.Lock()


class OpenSearchUnavailable(Exception):
    """Raised when OpenSearch is not configured or unreachable.

    The API layer maps this to HTTP 503 (§41).
    """


def _parse_url(url: str) -> tuple[str, int, bool]:
    """Parse TAI_OPENSEARCH_URL into (host, port, use_ssl)."""
    url = url.rstrip("/")
    use_ssl = url.startswith("https://")
    host = url.split("://", 1)[-1]
    if ":" in host:
        host, port_str = host.rsplit(":", 1)
        port = int(port_str)
    else:
        port = 443 if use_ssl else 9200
    return host, port, use_ssl


def get_client() -> OpenSearch:
    """Return the process-singleton OpenSearch client.

    Thread-safe lazy init.  Raises ``OpenSearchUnavailable`` if
    TAI_OPENSEARCH_URL is not set.
    """
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        url = os.environ.get(ENV_URL, "").strip()
        if not url:
            raise OpenSearchUnavailable(
                f"OpenSearch not configured: {ENV_URL} is not set. "
                "Set it in the environment or .env file."
            )
        host, port, use_ssl = _parse_url(url)
        user = os.environ.get(ENV_USER, "").strip() or None
        pwd  = os.environ.get(ENV_PASS, "").strip() or None
        verify_raw = os.environ.get(ENV_VERIFY_CERTS, "true").strip().lower()
        verify_certs = verify_raw not in ("false", "0", "no")

        http_auth = (user, pwd) if user and pwd else None
        _client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=http_auth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnection,
            timeout=_REQUEST_TIMEOUT,
        )
    return _client


def reset_client() -> None:
    """Force re-init on next call (used in tests)."""
    global _client
    with _lock:
        _client = None


def check_health(client: Optional[OpenSearch] = None) -> dict:
    """Return cluster health dict.  Raises ``OpenSearchUnavailable`` on error."""
    c = client or get_client()
    try:
        return c.cluster.health()
    except (OSConnectionError, TransportError) as exc:
        raise OpenSearchUnavailable(f"OpenSearch cluster unreachable: {exc}") from exc
