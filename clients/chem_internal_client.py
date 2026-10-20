"""CHEM internal chemical facts client — WIRING-010 / WIRING-014B.

Endpoints:
  /internal/factories/{id}/leg-input-facts      → load_chemical_facts  (L4 DIRECT)
  /internal/factories/{id}/active-components    → load_active_components  (L2 Reader A)
  /internal/factories/{id}/consumption-lines    → load_consumption_lines  (L2 Reader C1)
  /internal/factories/{id}/issue-lines          → load_issue_lines  (L2 Reader C2)

Auth: X-Internal-Secret header using CHEM_INTERNAL_API_SECRET env.
Base URL: CHEM_INTERNAL_BASE_URL env.
Fail-closed: raises ChemicalSourceLoadError on any failure.
  Never synthesizes False/empty on connection failure.
  Empty list vs. failure are distinct — empty list returns [], failure raises.

B1: is_confidential=True components are returned as-is (internal M2M raw delivery).
  Caller must NOT forward to SAFE external responses, logs, or LEG Canonical results.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

import httpx

from utils.logger import get_logger

log = get_logger(__name__)

_TIMEOUT = float(os.getenv("CHEM_INTERNAL_TIMEOUT", "5.0"))


class ChemicalSourceLoadError(RuntimeError):
    pass


def _base_url() -> str:
    return os.getenv("CHEM_INTERNAL_BASE_URL", "").rstrip("/")


def _secret() -> str:
    return os.environ.get("CHEM_INTERNAL_API_SECRET", "")


def _require_env() -> tuple[str, str]:
    base = _base_url()
    if not base:
        raise ChemicalSourceLoadError("CHEM_INTERNAL_BASE_URL not set")
    secret = _secret()
    if not secret:
        raise ChemicalSourceLoadError("CHEM_INTERNAL_API_SECRET not set")
    return base, secret


def _get(url: str, params: dict, secret: str, timeout: float) -> Any:
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"X-Internal-Secret": secret},
            timeout=timeout,
        )
    except httpx.TimeoutException:
        # `raise ... from None` suppresses the exception chain in tracebacks —
        # original exc may contain internal URL or host info.
        raise ChemicalSourceLoadError("CHEM request timeout") from None
    except httpx.RequestError:
        # Same: suppress chain to prevent internal URL/host from appearing in tracebacks.
        raise ChemicalSourceLoadError("CHEM network error") from None

    if resp.status_code != 200:
        # resp.text omitted — CHEM error body may contain confidential content.
        raise ChemicalSourceLoadError(f"CHEM HTTP {resp.status_code}")

    try:
        return resp.json()
    except Exception:
        # `raise ... from None` suppresses the chain — original exc may contain
        # partial response body with confidential content.
        raise ChemicalSourceLoadError("CHEM invalid JSON response") from None


def _check_factory_id(data: Any, expected: str) -> None:
    if not isinstance(data, dict):
        raise ChemicalSourceLoadError("response is not a JSON object")
    returned = data.get("factory_id")
    if returned != expected:
        # Do not embed the CHEM-returned value — it is untrusted response data.
        raise ChemicalSourceLoadError("factory_id mismatch")


def load_chemical_facts(
    factory_id: str,
    company_id: str,
    timeout: float = _TIMEOUT,
) -> Dict[str, Any]:
    """CHEM internal API → approved LEG-facing chemical facts dict.

    Returns subset of CHEM facts approved for LEG input.
    Currently: {"has_chemical": bool} only.
    contract_gaps are stripped — not LEG input facts.
    Raises ChemicalSourceLoadError on any failure (fail-closed).
    """
    # Delta-1: identity validation parity with L2 Readers.
    _require_identifiers(factory_id, company_id)
    base, secret = _require_env()

    url = f"{base}/internal/factories/{factory_id}/leg-input-facts"
    data = _get(url, {"company_id": company_id}, secret, timeout)
    # Delta-1: verify returned factory_id matches requested factory_id.
    _check_factory_id(data, factory_id)

    raw_facts: Dict[str, Any] = data.get("facts", {}) if isinstance(data, dict) else {}

    # Only approved L4 DIRECT fact at this stage — NON-DIRECT blocked until OBJ04.
    out: Dict[str, Any] = {}
    if "has_chemical" in raw_facts:
        out["has_chemical"] = raw_facts["has_chemical"]
    return out


def _require_identifiers(factory_id: str, company_id: str) -> None:
    if not factory_id or not factory_id.strip():
        raise ChemicalSourceLoadError("factory_id is required")
    if not company_id or not company_id.strip():
        raise ChemicalSourceLoadError("company_id is required")


def load_active_components(
    factory_id: str,
    company_id: str,
    timeout: float = _TIMEOUT,
) -> List[Dict[str, Any]]:
    """CHEM L2 Reader A — MSDS component rows for all ACTIVE material links.

    Returns list of component dicts with original fields preserved.
    is_confidential=True rows are returned as-is (B1 contract).
    Caller must NOT expose confidential components in SAFE responses or logs.
    Empty list (0 active links) is a valid result — not an error.
    Raises ChemicalSourceLoadError on any failure (fail-closed).
    """
    _require_identifiers(factory_id, company_id)
    base, secret = _require_env()

    url = f"{base}/internal/factories/{factory_id}/active-components"
    data = _get(url, {"company_id": company_id}, secret, timeout)

    _check_factory_id(data, factory_id)

    components = data.get("components")
    if not isinstance(components, list):
        raise ChemicalSourceLoadError(
            f"expected 'components' list, got {type(components).__name__}"
        )
    return components


def load_consumption_lines(
    factory_id: str,
    company_id: str,
    from_at: datetime,
    until_at_exclusive: datetime,
    timeout: float = _TIMEOUT,
) -> List[Dict[str, Any]]:
    """CHEM L2 Reader C1 — CONSUMPTION document lines in [from_at, until_at_exclusive).

    Both datetimes must be timezone-aware and from_at < until_at_exclusive.
    Caller is responsible for providing a meaningful period — no auto-generation.
    CONSUMPTION and ISSUE lines must NOT be mixed by the caller.
    Empty list is a valid result — not an error.
    Raises ChemicalSourceLoadError on any failure (fail-closed).
    """
    _require_identifiers(factory_id, company_id)
    if from_at.tzinfo is None:
        raise ChemicalSourceLoadError("from_at must be timezone-aware")
    if until_at_exclusive.tzinfo is None:
        raise ChemicalSourceLoadError("until_at_exclusive must be timezone-aware")
    if from_at >= until_at_exclusive:
        raise ChemicalSourceLoadError("from_at must be strictly before until_at_exclusive")

    base, secret = _require_env()

    url = f"{base}/internal/factories/{factory_id}/consumption-lines"
    data = _get(
        url,
        {
            "company_id": company_id,
            "from_at": from_at.isoformat(),
            "until_at_exclusive": until_at_exclusive.isoformat(),
        },
        secret,
        timeout,
    )

    _check_factory_id(data, factory_id)

    lines = data.get("lines")
    if not isinstance(lines, list):
        raise ChemicalSourceLoadError(
            f"expected 'lines' list, got {type(lines).__name__}"
        )
    return lines


def load_issue_lines(
    factory_id: str,
    company_id: str,
    from_at: datetime,
    until_at_exclusive: datetime,
    timeout: float = _TIMEOUT,
) -> List[Dict[str, Any]]:
    """CHEM L2 Reader C2 — ISSUE document lines in [from_at, until_at_exclusive).

    Both datetimes must be timezone-aware and from_at < until_at_exclusive.
    NOTE: ISSUE occurred_at reflects document creation time, not actual issue time.
      Do not reclassify as usage data or use for legal aggregation automatically.
    Empty list is a valid result — not an error.
    Raises ChemicalSourceLoadError on any failure (fail-closed).
    """
    _require_identifiers(factory_id, company_id)
    if from_at.tzinfo is None:
        raise ChemicalSourceLoadError("from_at must be timezone-aware")
    if until_at_exclusive.tzinfo is None:
        raise ChemicalSourceLoadError("until_at_exclusive must be timezone-aware")
    if from_at >= until_at_exclusive:
        raise ChemicalSourceLoadError("from_at must be strictly before until_at_exclusive")

    base, secret = _require_env()

    url = f"{base}/internal/factories/{factory_id}/issue-lines"
    data = _get(
        url,
        {
            "company_id": company_id,
            "from_at": from_at.isoformat(),
            "until_at_exclusive": until_at_exclusive.isoformat(),
        },
        secret,
        timeout,
    )

    _check_factory_id(data, factory_id)

    lines = data.get("lines")
    if not isinstance(lines, list):
        raise ChemicalSourceLoadError(
            f"expected 'lines' list, got {type(lines).__name__}"
        )
    return lines
