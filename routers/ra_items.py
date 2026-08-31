"""위험성평가 — 유해·위험요인 / 감소대책 / 재판정 API (v1.1.0).

Goal: G-ms5zwv4v-b88c4a
설계: docs/ops/tai-risk-assessment/PLAN_risk-assessment-design_v2.md

v1.1.0 (2026-07-29) — 재판정 수렴 결함 정정
  재판정에서 잔여 노출 인원과 승급 사유 플래그를 다시 입력할 수 있게 했다.
  종전에는 요인 등록 시의 노출 인원이 매 재판정마다 그대로 승급에 반영돼,
  대책을 실행해도 등급이 내려가지 않아 고시 제12조제3항의 반복 루프가 끝나지 않았다.

■ 이 라우터가 담당하는 법정 절차 (고시 제8조)
    2. 유해·위험요인 파악      → POST /ra/assessments/{id}/items
    4. 위험성 결정             → 요인 등록·수정 시 자동 판정(ra_decision_svc)
    5. 감소대책 수립 및 실행    → POST /ra/items/{id}/controls, PATCH /ra/controls/{id}
       └ 실행 후 재판정 반복    → POST /ra/items/{id}/reevaluate  (제12조제2항·제3항)

■ 기록 단위를 나눈 이유
  시행규칙 제37조제1항은 1호(대상 유해·위험요인), 2호(위험성 결정의 내용),
  3호(결정에 따른 조치의 내용)를 각각 포함하도록 정한다. 종전처럼 items_json 하나에
  뭉쳐 두면 항목별 입증이 어려워 ra_item / ra_control 로 분리한다.

API:
  POST  /ra/assessments/{assessment_id}/items       요인 등록(자동 판정)
  GET   /ra/assessments/{assessment_id}/items       요인 목록(대책 포함)
  GET   /ra/assessments/{assessment_id}/readiness   완료 가능 여부 점검
  PATCH /ra/items/{item_id}                         요인 수정(재판정 수반)
  POST  /ra/items/{item_id}/controls                감소대책 등록
  POST  /ra/items/{item_id}/reevaluate              재판정(대책 실행 후)
  GET   /ra/items/{item_id}/revisions               재판정 이력
  PATCH /ra/controls/{control_id}                   대책 수정·완료
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company
from services.ra_decision_svc import (
    DecisionError, ESCALATION_LABELS, HIERARCHY_LABELS, assessment_readiness, decide,
)
from services.time import now_kst, serialize_external_utc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ra", tags=["위험성평가 요인·대책"])

VERSION = "1.1.0"


def _now() -> str:
    return serialize_external_utc(now_kst())


def _sb():
    return get_supabase()


def _get_assessment(assessment_id: str) -> Dict[str, Any]:
    res = _sb().table("risk_assessments").select("*").eq("id", assessment_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")
    return res.data[0]


def _ensure_assessment_own(assessment_id: str, current: dict) -> None:
    """부모 평가 소유 확인 — 비-ALL 타사 404."""
    a = _sb().table("risk_assessments").select("company_id").eq("id", assessment_id).limit(1).execute()
    if not a.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")
    _ensure_own_company(a.data[0].get("company_id"), current, _sb(), "위험성평가를 찾을 수 없습니다.")


def _ensure_item_own(item_id: str, current: dict) -> None:
    """요인 → 부모 평가 소유 확인."""
    it = _sb().table("ra_item").select("assessment_id").eq("id", item_id).limit(1).execute()
    if not it.data:
        raise HTTPException(status_code=404, detail="요인을 찾을 수 없습니다.")
    _ensure_assessment_own(str(it.data[0]["assessment_id"]), current)


def _ensure_control_own(control_id: str, current: dict) -> None:
    """대책 → 요인 → 부모 평가 소유 확인."""
    c = _sb().table("ra_control").select("item_id").eq("id", control_id).limit(1).execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="대책을 찾을 수 없습니다.")
    _ensure_item_own(str(c.data[0]["item_id"]), current)


def _get_scale_for(assessment: Dict[str, Any]) -> Dict[str, Any]:
    """평가에 지정된 척도를 가져온다. 없으면 판정 불가(고시 제9조제2항)."""
    scale_id = assessment.get("scale_id")
    if not scale_id:
        raise HTTPException(
            status_code=409,
            detail="이 평가에 척도가 지정되지 않았습니다. 고시 제9조제2항에 따라 "
                   "위험성 수준·판단기준과 허용 가능한 수준을 사전에 확정해야 합니다. "
                   "PATCH /risk-assessments/{id} 로 scale_id 를 지정하세요.")
    res = _sb().table("ra_scale").select("*").eq("id", scale_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="지정된 척도를 찾을 수 없습니다.")
    return res.data[0]


def _controls_of(item_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not item_ids:
        return {}
    res = _sb().table("ra_control").select("*").in_("item_id", item_ids).order("hierarchy").execute()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in (res.data or []):
        out.setdefault(str(c["item_id"]), []).append(c)
    return out


def _record_revision(item_id: str, level: Optional[str], acceptable: Optional[bool],
                     raw_input: Optional[Dict[str, Any]], by: Optional[str],
                     note: Optional[str] = None) -> int:
    """재판정 이력 적재. seq 는 1부터 증가한다(1 = 최초 판정)."""
    prev = (_sb().table("ra_item_revision").select("seq")
            .eq("item_id", item_id).order("seq", desc=True).limit(1).execute())
    seq = (int(prev.data[0]["seq"]) + 1) if prev.data else 1
    _sb().table("ra_item_revision").insert({
        "item_id": item_id, "seq": seq, "level": level, "acceptable": acceptable,
        "raw_input_json": raw_input, "evaluated_by": by, "note": note,
    }).execute()
    return seq


def _next_action(verdict: Dict[str, Any]) -> Optional[str]:
    """허용 불가일 때 무엇을 해야 하는지 알려준다."""
    if verdict.get("acceptable") is True:
        return None
    rules = [r.get("rule") for r in (verdict.get("escalation") or [])]
    if "LEGAL_NONCOMPLIANCE" in rules:
        return "법령에서 규정하는 조치를 먼저 이행해야 합니다(고시 제12조제1항제1호)."
    if "MANY_EXPOSED" in rules:
        return ("노출 인원으로 인해 한 단계 상향되었습니다. 대책 실행으로 노출이 줄었다면 "
                "재판정 시 exposed_count 에 잔여 노출 인원을 입력하십시오.")
    return "추가 감소대책을 수립·실행한 뒤 재판정하십시오(고시 제12조제3항)."


# ── 스키마 ──────────────────────────────────────────────────────────
class ItemBody(BaseModel):
    hazard: str
    work_process: Optional[str] = None
    situation_result: Optional[str] = None
    exposed_count: Optional[int] = None
    legal_basis: Optional[str] = None
    current_controls: Optional[str] = None
    discovery_method: Optional[str] = None      # PATROL | SUGGESTION | INTERVIEW | DATA | CHECKLIST | ETC
    raw_input_json: Dict[str, Any] = {}         # 기법별 입력
    seq: Optional[int] = None
    note: Optional[str] = None
    created_by: Optional[str] = None


class ItemUpdateBody(BaseModel):
    hazard: Optional[str] = None
    work_process: Optional[str] = None
    situation_result: Optional[str] = None
    exposed_count: Optional[int] = None
    legal_basis: Optional[str] = None
    current_controls: Optional[str] = None
    discovery_method: Optional[str] = None
    raw_input_json: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    evaluated_by: Optional[str] = None


class ControlBody(BaseModel):
    hierarchy: int                              # 0 법령 / 1 제거·대체 / 2 공학적 / 3 관리적 / 4 보호구
    content: str
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    due_date: Optional[str] = None
    is_interim: bool = False
    budget_ref: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[str] = None


class ControlUpdateBody(BaseModel):
    content: Optional[str] = None
    hierarchy: Optional[int] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    due_date: Optional[str] = None
    done: Optional[bool] = None                 # true → done_at 기록
    is_interim: Optional[bool] = None
    budget_ref: Optional[str] = None
    note: Optional[str] = None


class ReevaluateBody(BaseModel):
    raw_input_json: Optional[Dict[str, Any]] = None
    # 대책 실행 후 남은 노출 인원. 미입력이면 요인 등록값을 그대로 쓴다.
    exposed_count: Optional[int] = None
    evaluated_by: Optional[str] = None
    note: Optional[str] = None


# ── 요인 ────────────────────────────────────────────────────────────
@router.post("/assessments/{assessment_id}/items")
def create_item(assessment_id: str, body: ItemBody, current: dict = Depends(get_current_user)):
    """유해·위험요인 등록. 등록 즉시 위험성을 결정한다(고시 제10조·제11조)."""
    _ensure_assessment_own(assessment_id, current)
    assessment = _get_assessment(assessment_id)
    scale = _get_scale_for(assessment)

    item = {
        "assessment_id": assessment_id,
        "seq": body.seq,
        "work_process": body.work_process,
        "hazard": body.hazard,
        "situation_result": body.situation_result,
        "exposed_count": body.exposed_count,
        "legal_basis": body.legal_basis,
        "current_controls": body.current_controls,
        "discovery_method": body.discovery_method,
        "raw_input_json": body.raw_input_json or {},
        "note": body.note,
        "created_by": body.created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        verdict = decide(item, scale)
    except DecisionError as e:
        raise HTTPException(status_code=400, detail=e.detail)

    item["level"] = verdict["level"]
    item["acceptable"] = verdict["acceptable"]
    item["escalation_json"] = verdict["escalation"] or None

    res = _sb().table("ra_item").insert(item).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="요인 등록에 실패했습니다.")
    row = res.data[0]

    _record_revision(str(row["id"]), verdict["level"], verdict["acceptable"],
                     body.raw_input_json, body.created_by, "최초 판정")

    return {"status": "success", "message": "요인이 등록되었습니다.",
            "data": {**row, "verdict": verdict, "next_action": _next_action(verdict)}}


@router.get("/assessments/{assessment_id}/items")
def list_items(assessment_id: str, include_controls: bool = Query(True), current: dict = Depends(get_current_user)):
    """요인 목록. 감소대책과 재판정 횟수를 함께 반환한다."""
    _ensure_assessment_own(assessment_id, current)
    _get_assessment(assessment_id)
    res = (_sb().table("ra_item").select("*")
           .eq("assessment_id", assessment_id)
           .order("seq", desc=False).order("created_at").execute())
    items = res.data or []
    ids = [str(i["id"]) for i in items]

    controls = _controls_of(ids) if include_controls else {}
    revs: Dict[str, int] = {}
    if ids:
        rr = _sb().table("ra_item_revision").select("item_id, seq").in_("item_id", ids).execute()
        for r in (rr.data or []):
            k = str(r["item_id"])
            revs[k] = max(revs.get(k, 0), int(r["seq"]))

    for it in items:
        k = str(it["id"])
        it["controls"] = controls.get(k, [])
        it["revision_count"] = revs.get(k, 0)

    return {"status": "success",
            "data": {"items": items, "total": len(items),
                     "escalation_labels": ESCALATION_LABELS,
                     "hierarchy_labels": HIERARCHY_LABELS}}


@router.patch("/items/{item_id}")
def update_item(item_id: str, body: ItemUpdateBody, current: dict = Depends(get_current_user)):
    """요인 수정. 판정에 영향을 주는 입력이 바뀌면 재판정하고 이력을 남긴다."""
    _ensure_item_own(item_id, current)
    cur = _sb().table("ra_item").select("*").eq("id", item_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="요인을 찾을 수 없습니다.")
    item = cur.data[0]

    payload = {k: v for k, v in body.dict(exclude={"evaluated_by"}).items() if v is not None}
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    merged = {**item, **payload}
    verdict = None
    if any(k in payload for k in ("raw_input_json", "exposed_count")):
        assessment = _get_assessment(str(item["assessment_id"]))
        scale = _get_scale_for(assessment)
        try:
            verdict = decide(merged, scale)
        except DecisionError as e:
            raise HTTPException(status_code=400, detail=e.detail)
        payload["level"] = verdict["level"]
        payload["acceptable"] = verdict["acceptable"]
        payload["escalation_json"] = verdict["escalation"] or None

    payload["updated_at"] = _now()
    res = _sb().table("ra_item").update(payload).eq("id", item_id).execute()

    if verdict:
        _record_revision(item_id, verdict["level"], verdict["acceptable"],
                         merged.get("raw_input_json"), body.evaluated_by, "요인 수정에 따른 재판정")

    return {"status": "success", "message": "수정되었습니다.",
            "data": {**(res.data[0] if res.data else {}), "verdict": verdict}}


# ── 감소대책 ────────────────────────────────────────────────────────
@router.post("/items/{item_id}/controls")
def create_control(item_id: str, body: ControlBody, current: dict = Depends(get_current_user)):
    """감소대책 등록. 우선순위는 고시 제12조제1항 각 호를 따른다."""
    _ensure_item_own(item_id, current)
    cur = _sb().table("ra_item").select("id").eq("id", item_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="요인을 찾을 수 없습니다.")
    if body.hierarchy not in HIERARCHY_LABELS:
        raise HTTPException(status_code=400,
                            detail=f"hierarchy 는 0~4 여야 합니다. {HIERARCHY_LABELS}")

    row = {
        "item_id": item_id,
        "hierarchy": body.hierarchy,
        "content": body.content,
        "owner_user_id": body.owner_user_id,
        "owner_name": body.owner_name,
        "due_date": body.due_date,
        "is_interim": body.is_interim,
        "budget_ref": body.budget_ref,
        "note": body.note,
        "created_by": body.created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    res = _sb().table("ra_control").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="대책 등록에 실패했습니다.")

    warn = None
    if body.hierarchy == 4:
        others = _sb().table("ra_control").select("hierarchy").eq("item_id", item_id).execute()
        hs = {int(c["hierarchy"]) for c in (others.data or []) if c.get("hierarchy") is not None}
        if hs == {4}:
            warn = ("개인용 보호구만 등록되었습니다. 고시 제12조제1항은 법령 규정 조치, "
                    "제거·대체, 공학적·관리적 대책을 우선 검토하도록 정합니다.")

    return {"status": "success", "message": "대책이 등록되었습니다.",
            "data": res.data[0], "warning": warn}


@router.patch("/controls/{control_id}")
def update_control(control_id: str, body: ControlUpdateBody, current: dict = Depends(get_current_user)):
    """대책 수정·실행 완료 처리."""
    _ensure_control_own(control_id, current)
    payload = {k: v for k, v in body.dict(exclude={"done"}).items() if v is not None}
    if body.done is not None:
        payload["done_at"] = _now() if body.done else None
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    if "hierarchy" in payload and payload["hierarchy"] not in HIERARCHY_LABELS:
        raise HTTPException(status_code=400, detail="hierarchy 는 0~4 여야 합니다.")

    payload["updated_at"] = _now()
    res = _sb().table("ra_control").update(payload).eq("id", control_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="대책을 찾을 수 없습니다.")
    return {"status": "success", "message": "수정되었습니다.", "data": res.data[0]}


# ── 재판정 ──────────────────────────────────────────────────────────
@router.post("/items/{item_id}/reevaluate")
def reevaluate(item_id: str, body: ReevaluateBody, current: dict = Depends(get_current_user)):
    """감소대책 실행 후 재판정.

    고시 제12조제2항 — 대책 실행 후 허용 가능한 수준인지 확인한다.
    제12조제3항 — 미달이면 허용 가능한 수준이 될 때까지 추가 대책을 수립·실행한다.

    exposed_count 를 함께 보내면 그 값을 '대책 실행 후 남은 노출 인원'으로 보아
    승급 여부를 다시 판단한다. 보내지 않으면 요인 등록값을 그대로 쓴다.
    """
    _ensure_item_own(item_id, current)
    cur = _sb().table("ra_item").select("*").eq("id", item_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="요인을 찾을 수 없습니다.")
    item = cur.data[0]

    assessment = _get_assessment(str(item["assessment_id"]))
    scale = _get_scale_for(assessment)

    raw = dict(item.get("raw_input_json") or {})
    if body.raw_input_json is not None:
        raw = dict(body.raw_input_json)
    if body.exposed_count is not None:
        raw["exposed_count"] = body.exposed_count

    merged = {**item, "raw_input_json": raw}

    try:
        verdict = decide(merged, scale)
    except DecisionError as e:
        raise HTTPException(status_code=400, detail=e.detail)

    upd = {
        "level": verdict["level"],
        "acceptable": verdict["acceptable"],
        "escalation_json": verdict["escalation"] or None,
        "raw_input_json": raw,
        "updated_at": _now(),
    }
    _sb().table("ra_item").update(upd).eq("id", item_id).execute()

    seq = _record_revision(item_id, verdict["level"], verdict["acceptable"],
                           raw, body.evaluated_by,
                           body.note or "감소대책 실행 후 재판정")

    msg = ("허용 가능한 수준입니다." if verdict["acceptable"]
           else "아직 허용 가능한 수준이 아닙니다. 추가 감소대책이 필요합니다(고시 제12조제3항).")
    return {"status": "success", "message": msg,
            "data": {"item_id": item_id, "revision_seq": seq, "verdict": verdict,
                     "next_action": _next_action(verdict)}}


@router.get("/items/{item_id}/revisions")
def list_revisions(item_id: str, current: dict = Depends(get_current_user)):
    """재판정 이력. 반복 실행의 증적이 된다."""
    _ensure_item_own(item_id, current)
    res = (_sb().table("ra_item_revision").select("*")
           .eq("item_id", item_id).order("seq").execute())
    return {"status": "success", "data": {"items": res.data or []}}


# ── 완료 가능 여부 ──────────────────────────────────────────────────
@router.get("/assessments/{assessment_id}/readiness")
def readiness(assessment_id: str, current: dict = Depends(get_current_user)):
    """완료 가능 여부 점검. 허용 불가 요인이 남아 있으면 완료할 수 없다."""
    _ensure_assessment_own(assessment_id, current)
    _get_assessment(assessment_id)
    res = _sb().table("ra_item").select("*").eq("assessment_id", assessment_id).execute()
    items = res.data or []
    controls = _controls_of([str(i["id"]) for i in items])
    return {"status": "success", "data": assessment_readiness(items, controls)}
