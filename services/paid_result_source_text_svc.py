"""services/paid_result_source_text_svc.py — PAID RESULT SOURCE-TEXT SIDECAR v1.

WO-DQ-WHAT-05C-PAID-RESULT-SOURCE-TEXT-ASSEMBLY-001

WHAT THIS IS
    유료진단 결과의 잘린 duty.what 대신, 각 의무의 canonical 법령 원문(source-text)을
    LEG Runtime /rtm/source-texts 로 한 번에 받아 obligation 기준 sidecar 로 복원한다.

    materials["normalized_obligations"]
        -> 각 obligation 의 PRIMARY ATOM
        -> first-seen ordered unique atom_ids
        -> loader(atom_ids)  (= LEG Runtime, 최대 1회)
        -> obligation 기준 items / unresolved

경계
    · INPUT 은 오직 materials["normalized_obligations"]. row / full_result / DB 직접 read = 0.
    · obligation 1건 -> item 또는 unresolved 1건. grouping / dedup / collapse = 0.
    · HTTP 는 atom 기준으로만 dedup(query). 결과 obligation row 는 병합하지 않는다.
    · materials / normalized obligation / identity mutation = 0 (읽기만).
    · resolver 실패(network/contract)는 삼키지 않고 그대로 전파한다(빈 결과 위장 금지).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

SOURCE_TEXT_VERSION = 1
SOURCE_MODE = "LIVE_LEG_SOURCE"

STATUS_EXACT = "EXACT"
STATUS_SOURCE_MISMATCH = "SOURCE_MISMATCH"
STATUS_UNRESOLVED = "UNRESOLVED"

# local unresolved reasons (obligation -> atom 해결 실패)
REASON_ATOM_ID_MISSING = "ATOM_ID_MISSING"
REASON_ATOM_ID_AMBIGUOUS = "ATOM_ID_AMBIGUOUS"
REASON_RESOLVER_RESULT_MISSING = "RESOLVER_RESULT_MISSING"


class PaidResultSourceTextError(RuntimeError):
    """resolver 응답 계약 위반 / source-text 조립 실패. 빈 결과로 변환하지 않는다."""


def _default_loader(atom_ids: List[str]) -> Dict[str, Any]:
    """production loader = LEG Runtime client. lazy import(테스트는 loader 주입)."""
    from clients.leg_runtime_client import fetch_source_texts
    return fetch_source_texts(atom_ids)


def _distinct_valid(ids: Any) -> List[str]:
    out: List[str] = []
    for a in (ids or []):
        if isinstance(a, str) and a.strip():
            s = a.strip()
            if s not in out:
                out.append(s)
    return out


def _primary_atom(identity: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(primary_atom_id, reason). §5 PRIMARY ATOM RULE — 추정 금지.

    identity.atom_id 가 non-empty string -> PRIMARY.
    없으면 source_atom_ids 의 valid distinct 가 EXACT 1 일 때만 PRIMARY.
    0 -> ATOM_ID_MISSING · 2+ -> ATOM_ID_AMBIGUOUS.
    """
    atom_id = identity.get("atom_id")
    if isinstance(atom_id, str) and atom_id.strip():
        return atom_id.strip(), None
    distinct = _distinct_valid(identity.get("source_atom_ids"))
    if len(distinct) == 1:
        return distinct[0], None
    if len(distinct) == 0:
        return None, REASON_ATOM_ID_MISSING
    return None, REASON_ATOM_ID_AMBIGUOUS


def _validate_resolver_response(resp: Any) -> None:
    """§12 — dict · version==1 · source_mode==LIVE_LEG_SOURCE · items/unresolved list. 아니면 fail closed."""
    if not isinstance(resp, dict):
        raise PaidResultSourceTextError("resolver response is not a dict")
    if resp.get("version") != 1:
        raise PaidResultSourceTextError("resolver response version != 1")
    if resp.get("source_mode") != SOURCE_MODE:
        raise PaidResultSourceTextError("resolver response source_mode mismatch")
    if not isinstance(resp.get("items"), list):
        raise PaidResultSourceTextError("resolver response items is not a list")
    if not isinstance(resp.get("unresolved"), list):
        raise PaidResultSourceTextError("resolver response unresolved is not a list")


def build_paid_result_source_text_v1(
    materials: Any,
    loader: Optional[Callable[[List[str]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """materials -> paid_result_source_text_v1. loader 미주입 시 LEG Runtime client 사용."""
    loader = loader or _default_loader

    obligations: List[Any] = []
    if isinstance(materials, dict):
        raw = materials.get("normalized_obligations")
        if isinstance(raw, list):
            obligations = raw

    # 1) obligation 별 PRIMARY ATOM 결정 + first-seen unique atom 수집
    plan: List[Dict[str, Any]] = []
    unique_atoms: List[str] = []
    for ob in obligations:
        identity = ob.get("identity") if isinstance(ob, dict) else None
        identity = identity if isinstance(identity, dict) else {}
        raw_atom = identity.get("atom_id")
        primary, reason = _primary_atom(identity)
        plan.append({
            "obligation_ref": identity.get("source_index"),
            "raw_atom_id": raw_atom if (isinstance(raw_atom, str) and raw_atom.strip()) else None,
            "source_atom_ids": list(identity.get("source_atom_ids") or []),
            "primary": primary,
            "reason": reason,
        })
        if primary is not None and primary not in unique_atoms:
            unique_atoms.append(primary)

    # 2) LEG Runtime 호출 (최대 1회; resolvable atom 없으면 0회)
    items_by_atom: Dict[str, Dict[str, Any]] = {}
    unresolved_by_atom: Dict[str, Dict[str, Any]] = {}
    if unique_atoms:
        resp = loader(unique_atoms)
        _validate_resolver_response(resp)
        for it in resp["items"]:
            if isinstance(it, dict) and it.get("atom_id") is not None:
                items_by_atom[str(it["atom_id"])] = it
        for u in resp["unresolved"]:
            if isinstance(u, dict) and u.get("atom_id") is not None:
                unresolved_by_atom[str(u["atom_id"])] = u

    # 3) obligation 기준 복원 (1 obligation -> 1 item 또는 1 unresolved)
    items: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    for p in plan:
        ref = p["obligation_ref"]
        src_ids = list(p["source_atom_ids"])
        primary = p["primary"]

        if primary is None:
            unresolved.append({
                "obligation_ref": ref,
                "atom_id": p["raw_atom_id"],
                "source_atom_ids": src_ids,
                "resolution_status": STATUS_UNRESOLVED,
                "reason": p["reason"],
            })
            continue

        if primary in items_by_atom:
            it = items_by_atom[primary]
            status = it.get("resolution_status")
            text = it.get("text")
            sha = it.get("source_sha256")
            if status == STATUS_SOURCE_MISMATCH:
                text = None
                sha = None
            items.append({
                "obligation_ref": ref,
                "atom_id": primary,
                "source_atom_ids": src_ids,
                "semantic_clause_id": it.get("semantic_clause_id"),
                "source_part_id": it.get("source_part_id"),
                "law_name": it.get("law_name"),
                "law_article": it.get("law_article"),
                "text": text,
                "source_sha256": sha,
                "resolution_status": status,
            })
        elif primary in unresolved_by_atom:
            u = unresolved_by_atom[primary]
            unresolved.append({
                "obligation_ref": ref,
                "atom_id": primary,
                "source_atom_ids": src_ids,
                "resolution_status": STATUS_UNRESOLVED,
                "reason": u.get("reason"),
            })
        else:
            unresolved.append({
                "obligation_ref": ref,
                "atom_id": primary,
                "source_atom_ids": src_ids,
                "resolution_status": STATUS_UNRESOLVED,
                "reason": REASON_RESOLVER_RESULT_MISSING,
            })

    return {
        "version": SOURCE_TEXT_VERSION,
        "source_mode": SOURCE_MODE,
        "items": items,
        "unresolved": unresolved,
    }


__all__ = [
    "SOURCE_TEXT_VERSION",
    "SOURCE_MODE",
    "PaidResultSourceTextError",
    "build_paid_result_source_text_v1",
]
