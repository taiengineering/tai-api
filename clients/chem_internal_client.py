"""CHEM internal chemical facts client — WIRING-010.

Calls CHEM /internal/factories/{id}/leg-input-facts to retrieve
L4 DIRECT chemical facts (has_chemical only at this stage).

Auth: X-Internal-Secret header using CHEM_INTERNAL_API_SECRET env.
Base URL: CHEM_INTERNAL_BASE_URL env.
Fail-closed: raises ChemicalSourceLoadError on any failure.
  Never synthesizes False on connection failure.
contract_gaps are stripped — they are CHEM internal gaps, not LEG facts.
"""
from __future__ import annotations

import os
from typing import Any, Dict

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
    base = _base_url()
    if not base:
        raise ChemicalSourceLoadError("CHEM_INTERNAL_BASE_URL not set")
    secret = _secret()
    if not secret:
        raise ChemicalSourceLoadError("CHEM_INTERNAL_API_SECRET not set")

    url = f"{base}/internal/factories/{factory_id}/leg-input-facts"
    try:
        resp = httpx.get(
            url,
            params={"company_id": company_id},
            headers={"X-Internal-Secret": secret},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ChemicalSourceLoadError(f"timeout: {exc}") from exc
    except httpx.RequestError as exc:
        raise ChemicalSourceLoadError(f"network: {exc}") from exc

    if resp.status_code != 200:
        raise ChemicalSourceLoadError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except Exception as exc:
        raise ChemicalSourceLoadError(f"invalid json: {exc}") from exc

    raw_facts: Dict[str, Any] = data.get("facts", {}) if isinstance(data, dict) else {}

    # Only approved L4 DIRECT fact at this stage — NON-DIRECT blocked until OBJ04.
    out: Dict[str, Any] = {}
    if "has_chemical" in raw_facts:
        out["has_chemical"] = raw_facts["has_chemical"]
    return out
