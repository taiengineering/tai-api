"""
routers/contracts_engine.py — v1.0.0
계약서 생성(Claude API) / 웹뷰 / 수정 / 서명(이니시스 간편인증) / 조회

엔드포인트 (prefix: /matching/contracts — main.py 지정):
  POST   /generate                    계약서 HTML 생성 (Claude API)
  GET    /{id}/view                   계약서 웹뷰 (HTMLResponse)
  PATCH  /{id}/revise                 수정 요청 (최대 3회)
  POST   /{id}/sign/prepare           이니시스 간편인증 서명 준비
  POST   /{id}/sign/complete          서명 완료 콜백
  GET    /{id}                        계약서 메타 정보 조회

Claude API: httpx 직접 호출 (anthropic SDK 불필요, 기존 법령엔진과 동일 패턴)
서명: 이니시스 간편인증 — API 키 수령 후 실제 가동
Storage: contracts 버킷 (비공개, 50MB)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.contracts_engine import GenerateContractBody, ReviseBody
from services.contract_helpers import (
    _default_sections,
    _entity_type_label,
    _expert_type_label,
    _now_iso,
)
from services.contract_ai import generate_contract_sections, revise_with_claude
from services.contract_engine_svc import run_generate_contract, run_revise_contract
from services.contract_engine_svc import (
    run_complete_sign,
    run_get_contract_for_view,
    run_get_contract_meta,
    run_prepare_sign,
)

log    = logging.getLogger(__name__)
router = APIRouter()   # prefix: /matching/contracts — main.py에서 지정

# ── 환경변수 ──────────────────────────────────────────────────────────────
INICIS_VERIFY_MID      = os.getenv("INICIS_VERIFY_MID", "")
INICIS_VERIFY_SITE_KEY = os.getenv("INICIS_VERIFY_SITE_KEY", "")

STORAGE_BUCKET = "contracts"


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


# ── 계약서 HTML 템플릿 ──────────────────────────────────────────────────
CONTRACT_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{contract_title}</title>
<style>
  body       {{ font-family: 'Malgun Gothic', sans-serif; font-size: 14px;
                line-height: 1.8; color: #222; max-width: 800px;
                margin: 0 auto; padding: 40px; }}
  h1         {{ text-align: center; font-size: 22px; margin-bottom: 30px; }}
  h2         {{ font-size: 16px; border-bottom: 1px solid #333;
                padding-bottom: 4px; margin-top: 30px; }}
  .party     {{ background: #f8f9fa; padding: 16px; border-radius: 6px;
                margin: 20px 0; }}
  .sign-box  {{ border: 1px solid #ccc; padding: 20px; margin-top: 40px;
                display: flex; justify-content: space-around; flex-wrap: wrap; gap: 16px; }}
  .sign-field  {{ text-align: center; min-width: 200px; }}
  .sign-line   {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 8px; }}
  @media print {{
    .no-print {{ display: none !important; }}
    body {{ padding: 20px; }}
  }}
</style>
</head>
<body>

<h1>{contract_title}</h1>
<p style="text-align:center;color:#666;">
  계약번호: {contract_id} | 작성일: {generated_date}
</p>

<h2>제1조 계약 당사자</h2>
<div class="party">
  <p><strong>위탁자 (갑)</strong><br>
     상호: {client_name} | 사업자번호: {client_biz_no}<br>
     대표자: {client_ceo} | 주소: {client_address}</p>
  <p><strong>수탁자 (을)</strong><br>
     {expert_name} ({entity_type_label})<br>
     {expert_biz_info}</p>
  <p><strong>중개사 (병)</strong><br>
     TAI엔지니어링 | 사업자번호: 000-00-00000</p>
</div>

<h2>제2조 계약 목적 및 서비스</h2>
<p>본 계약은 갑이 을에게 {service_type_label} 서비스를 위탁하고,
   을이 이를 성실히 이행하기 위한 조건을 정함을 목적으로 한다.</p>

<h2>제3조 서비스 범위 및 의무</h2>
{article3}

<h2>제4조 계약 기간 및 금액</h2>
<p>계약 기간: {start_date} ~ {end_date} ({duration_months}개월)</p>
<p>계약 금액: {contract_amount_fmt}원 (부가세 포함)</p>
<p>TAI 중개 수수료: {tai_fee_rate}% ({tai_fee_amount_fmt}원)</p>
<p>을 지급액: {expert_amount_fmt}원</p>

<h2>제5조 지급 조건</h2>
{article5}

<h2>제6조 이행 조건 및 특이사항</h2>
{article6}

<h2>제7조 계약 해지 및 면책</h2>
{article7}

<h2>제8조 분쟁 해결</h2>
<p>본 계약과 관련한 분쟁은 서울중앙지방법원을 관할 법원으로 한다.</p>

<div class="sign-box">
  <div class="sign-field">
    <p><strong>위탁자 (갑)</strong></p>
    <div class="sign-line">{client_signed_info}</div>
  </div>
  <div class="sign-field">
    <p><strong>수탁자 (을)</strong></p>
    <div class="sign-line">{expert_signed_info}</div>
  </div>
  <div class="sign-field">
    <p><strong>중개사 (병)</strong></p>
    <div class="sign-line">TAI엔지니어링<br>(확인)</div>
  </div>
</div>

</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════════════════════════

@router.post("/generate")
async def generate_contract(
    body:         GenerateContractBody,
    current_user: dict = Depends(_require_admin),
):
    """
    계약서 HTML 생성 (Claude API) → Storage 저장
    POST /matching/contracts/generate

    SELECTED 상태 매칭 건만 가능.
    생성 완료 후 matching_requests → CONTRACTING 자동 전이.
    """
    supabase = get_supabase()
    now = _now_iso()
    try:
        data = await run_generate_contract(supabase, body, now, STORAGE_BUCKET, CONTRACT_TEMPLATE)
        log.info(f"[CONTRACT GEN] 생성 완료 contract_id={data['contract_id']}")
        return {"status": "success", "data": data}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{contract_id}/view", response_class=HTMLResponse)
async def view_contract(
    contract_id:  str,
    current_user: dict = Depends(get_current_user),
):
    """
    계약서 HTML 웹뷰 (브라우저 직접 렌더링)
    GET /matching/contracts/{contract_id}/view

    프론트: <iframe> 또는 새 탭으로 호출.
    당사자에게 인쇄(PDF) 버튼 + 서명 버튼 주입.
    """
    supabase = get_supabase()
    uid = current_user["id"]
    is_admin = current_user.get("role_code") == "001"
    try:
        contract, is_party = run_get_contract_for_view(supabase, contract_id, uid, is_admin)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # 당사자에게만 액션 버튼 주입
    action_html = ""
    if is_party and not is_admin:
        is_signed = (
            (uid == contract.get("client_user_id") and contract.get("client_signed"))
            or
            (uid == contract.get("expert_user_id") and contract.get("expert_signed"))
        )
        sign_btn = "" if is_signed else f"""
          <button onclick="requestSign('{contract_id}')"
            style="background:#0d6efd;color:#fff;border:none;padding:10px 24px;
                   border-radius:6px;font-size:14px;cursor:pointer;">
            ✍️ 서명하기 (이니시스 간편인증)
          </button>"""

        action_html = f"""
        <div class="no-print" style="position:fixed;top:20px;right:20px;
             display:flex;gap:10px;z-index:999;">
          <button onclick="window.print()"
            style="background:#28a745;color:#fff;border:none;padding:10px 24px;
                   border-radius:6px;font-size:14px;cursor:pointer;">
            🖨️ PDF 저장 (인쇄)
          </button>
          {sign_btn}
        </div>
        <script>
        async function requestSign(contractId) {{
          const token = localStorage.getItem('access_token') || '';
          const res = await fetch('/matching/contracts/' + contractId + '/sign/prepare',
            {{method:'POST', headers:{{'Authorization':'Bearer ' + token,
                                      'Content-Type':'application/json'}}}});
          const d = await res.json();
          if (d.status === 'success' && d.data.popup_url) {{
            window.open(d.data.popup_url, 'sign_popup', 'width=430,height=600');
          }} else {{
            alert(d.data?.message || '서명 준비 실패');
          }}
        }}
        </script>"""

    html_content = (contract.get("contract_html") or "").replace(
        "</body>", f"{action_html}</body>"
    )
    return HTMLResponse(content=html_content, status_code=200)


@router.patch("/{contract_id}/revise")
async def revise_contract(
    contract_id:  str,
    body:         ReviseBody,
    current_user: dict = Depends(get_current_user),
):
    """
    계약 당사자: 수정 요청 (최대 3회)
    PATCH /matching/contracts/{contract_id}/revise

    3회 초과 → status = ADMIN_HOLD (어드민 개입 필요)
    """
    supabase = get_supabase()
    now = _now_iso()
    try:
        data = await run_revise_contract(
            supabase=supabase,
            contract_id=contract_id,
            revision_note=body.revision_note,
            uid=current_user["id"],
            is_admin=current_user.get("role_code") == "001",
            now=now,
            storage_bucket=STORAGE_BUCKET,
        )
        return {"status": "success", "data": data}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{contract_id}/sign/prepare")
def prepare_sign(
    contract_id:  str,
    current_user: dict = Depends(get_current_user),
):
    """
    이니시스 간편인증 서명 준비
    POST /matching/contracts/{contract_id}/sign/prepare

    ⚠️ 이니시스 간편인증 API 키 수령 후 실제 가동.
    """
    supabase = get_supabase()
    try:
        run_prepare_sign(supabase, contract_id, current_user["id"], _now_iso())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "data": {
            "contract_id": contract_id,
            "popup_url":   "",   # TODO: 이니시스 간편인증 키 수령 후 구현
            "message":     "이니시스 간편인증 서명 준비 중입니다. API 키 수령 후 가동됩니다.",
        },
    }


@router.post("/{contract_id}/sign/complete")
async def complete_sign(
    contract_id: str,
    request:     Request,
):
    """
    이니시스 간편인증 서명 완료 콜백
    POST /matching/contracts/{contract_id}/sign/complete

    CI 저장 → 양측 서명 완료 시 SIGNED → matching_requests CONTRACTED 전이.
    """
    try:
        form = await request.form()
        data: dict = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            data = {}

    ci = data.get("ci", data.get("CI", ""))
    user_id = data.get("user_id", "")
    now = _now_iso()
    supabase = get_supabase()
    result = run_complete_sign(supabase, contract_id, user_id, ci, now)
    if not result["found"] or not result["updated"]:
        return HTMLResponse("<script>window.close();</script>")
    log.info(f"[CONTRACT SIGN] contract_id={contract_id} user={user_id} both_signed={result['both_signed']}")
    return HTMLResponse(
        "<script>window.opener?.onSignComplete({success:true});"
        "window.close();</script>"
    )


@router.get("/{contract_id}")
def get_contract(
    contract_id:  str,
    current_user: dict = Depends(get_current_user),
):
    """
    계약서 메타 정보 조회 (HTML 제외)
    GET /matching/contracts/{contract_id}
    """
    supabase = get_supabase()
    try:
        return {"status": "success", "data": run_get_contract_meta(supabase, contract_id)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
