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

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter()   # prefix: /matching/contracts — main.py에서 지정

# ── 환경변수 ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL         = "claude-sonnet-4-20250514"

INICIS_VERIFY_MID      = os.getenv("INICIS_VERIFY_MID", "")
INICIS_VERIFY_SITE_KEY = os.getenv("INICIS_VERIFY_SITE_KEY", "")

STORAGE_BUCKET = "contracts"


# ── 유틸 ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


def _expert_type_label(expert_type: str) -> str:
    return {"EXPERT": "선임대행", "CONSULTING": "컨설팅", "REPAIR": "수선중개"}.get(expert_type, expert_type)


def _entity_type_label(entity_type: str) -> str:
    return {
        "INDIVIDUAL":      "개인",
        "SOLE_PROPRIETOR": "개인사업자",
        "SIMPLIFIED_TAX":  "간이과세자",
        "CORPORATION":     "법인",
    }.get(entity_type, entity_type)


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


# ── Claude API 호출 (httpx — 기존 법령엔진과 동일 패턴) ─────────────────
def _default_sections(expert_type: str) -> dict:
    """Claude API 미설정 또는 실패 시 기본 조항"""
    return {
        "article3": "<p>을은 갑의 사업장에서 관계 법령에서 정한 안전관리 업무를 성실히 이행하여야 한다.</p>",
        "article5": "<p>갑은 계약 체결 후 계약금액을 TAI엔지니어링이 지정한 가상계좌로 입금한다.</p>",
        "article6": "<p>을은 계약 내용을 성실히 이행하여야 하며, 관계 법령의 변경 시 상호 협의하여 계약 내용을 조정할 수 있다.</p>",
        "article7": "<p>계약 당사자 일방이 계약을 위반하거나 계약의 목적을 달성할 수 없는 경우 서면 통보 후 계약을 해지할 수 있다.</p>",
    }


async def _generate_contract_sections(
    expert_type: str,
    contract_amount: int,
    duration_months: int,
    client_name: str,
    expert_name: str,
    description: str,
    proposal_note: str,
) -> dict:
    """Claude API로 서비스별 핵심 조항 생성 (JSON 응답)"""
    if not ANTHROPIC_API_KEY:
        return _default_sections(expert_type)

    prompt = f"""다음 정보를 바탕으로 안전관리 서비스 계약서의 조항을 한국어로 작성해 주세요.

서비스 유형: {expert_type} ({_expert_type_label(expert_type)})
계약 금액: {contract_amount:,}원
계약 기간: {duration_months}개월
위탁자: {client_name}
수탁자: {expert_name}
요구사항: {description}
특이사항: {proposal_note}

아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만:
{{
  "article3": "<p>서비스 범위 및 의무 내용...</p>",
  "article5": "<p>지급 조건 내용...</p>",
  "article6": "<p>이행 조건 및 특이사항 내용...</p>",
  "article7": "<p>해지 및 면책 조건 내용...</p>"
}}

작성 기준:
- 산업안전보건법 관련 법령 준수
- 명확하고 법적으로 유효한 문구
- HTML 태그(<p>, <ul>, <li>) 사용
- 각 조항 200자 이상"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":          ANTHROPIC_API_KEY,
                    "anthropic-version":  "2023-06-01",
                    "content-type":       "application/json",
                },
                json={
                    "model":      CLAUDE_MODEL,
                    "max_tokens": 2000,
                    "messages":   [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            log.error(f"[CONTRACT GEN] Claude API {resp.status_code}: {resp.text[:200]}")
            return _default_sections(expert_type)

        raw = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                raw += block["text"]

        raw = re.sub(r"```json\s*", "", raw.strip())
        raw = re.sub(r"```\s*",     "", raw).strip()
        return json.loads(raw)

    except Exception as e:
        log.error(f"[CONTRACT GEN] Claude 오류: {e}")
        return _default_sections(expert_type)


async def _revise_with_claude(original_html: str, revision_note: str) -> str:
    """수정 요청을 반영하여 계약서 HTML 재생성"""
    if not ANTHROPIC_API_KEY:
        return original_html

    prompt = f"""아래는 기존 계약서 HTML입니다.
수정 요청 내용을 반영하여 계약서를 수정해 주세요.
HTML 전체를 반환하되, 수정 요청에 해당하는 부분만 변경하세요.

수정 요청: {revision_note}

기존 계약서:
{original_html[:6000]}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":          ANTHROPIC_API_KEY,
                    "anthropic-version":  "2023-06-01",
                    "content-type":       "application/json",
                },
                json={
                    "model":      CLAUDE_MODEL,
                    "max_tokens": 4000,
                    "messages":   [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            log.error(f"[CONTRACT REVISE] Claude API {resp.status_code}")
            return original_html

        raw = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                raw += block["text"]
        return raw.strip() or original_html

    except Exception as e:
        log.error(f"[CONTRACT REVISE] Claude 오류: {e}")
        return original_html


# ════════════════════════════════════════════════════════════════════════
# Pydantic 모델
# ════════════════════════════════════════════════════════════════════════

class GenerateContractBody(BaseModel):
    request_id: str   # matching_requests.id
    result_id:  str   # matching_results.id (선택된 전문가)


class ReviseBody(BaseModel):
    revision_note: str


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
    now      = _now_iso()

    # ── 1. 데이터 수집 ────────────────────────────────────────────────
    req_res = (
        supabase.table("matching_requests")
        .select("*")
        .eq("id", body.request_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    if req_res.data[0]["status"] != "SELECTED":
        raise HTTPException(status_code=400, detail="SELECTED 상태인 신청만 계약서를 생성할 수 있습니다.")

    result_res = (
        supabase.table("matching_results")
        .select("*")
        .eq("id", body.result_id)
        .limit(1)
        .execute()
    )
    if not result_res.data or not result_res.data[0].get("is_selected"):
        raise HTTPException(status_code=400, detail="선택된 전문가의 제안서만 계약서 생성 가능합니다.")

    req_data    = req_res.data[0]
    result_data = result_res.data[0]
    expert_type = req_data.get("expert_type", "EXPERT")

    # 전문가 정보 (supplier_type 분기)
    supplier_table = {
        "personnel": "safety_personnel",
        "agency":    "safety_agencies",
        "repair":    "repair_companies",
    }.get(result_data.get("supplier_type", ""), "safety_personnel")

    expert_res  = (
        supabase.table(supplier_table)
        .select("*")
        .eq("id", result_data["supplier_id"])
        .limit(1)
        .execute()
    )
    expert_d = expert_res.data[0] if expert_res.data else {}

    # 고객사 정보
    client_info: dict = {}
    if req_data.get("company_id"):
        co = (
            supabase.table("companies")
            .select("name, business_number, representative_name, address")
            .eq("id", req_data["company_id"])
            .limit(1)
            .execute()
        )
        if co.data:
            client_info = co.data[0]

    # 수수료 계산 (기본 10%)
    contract_amount = result_data.get("proposal_amount", 0)
    duration_months = result_data.get("proposal_period", 1)
    tai_fee_rate    = 10.0
    tai_fee_amount  = round(contract_amount * tai_fee_rate / 100)
    expert_amount   = contract_amount - tai_fee_amount

    # ── 2. Claude API — 조항 생성 ─────────────────────────────────────
    expert_name = (
        expert_d.get("name")
        or expert_d.get("agency_name")
        or expert_d.get("company_name")
        or ""
    )
    claude_sections = await _generate_contract_sections(
        expert_type     = expert_type,
        contract_amount = contract_amount,
        duration_months = duration_months,
        client_name     = client_info.get("name", ""),
        expert_name     = expert_name,
        description     = req_data.get("description", ""),
        proposal_note   = result_data.get("proposal_note", ""),
    )

    # ── 3. HTML 조합 ──────────────────────────────────────────────────
    start_dt = datetime.now(timezone.utc)
    end_dt   = start_dt + timedelta(days=duration_months * 30)

    html = CONTRACT_TEMPLATE.format(
        contract_id         = "PENDING",
        contract_title      = f"{_expert_type_label(expert_type)} 서비스 계약서",
        generated_date      = start_dt.strftime("%Y년 %m월 %d일"),
        client_name         = client_info.get("name", "-"),
        client_biz_no       = client_info.get("business_number", "-"),
        client_ceo          = client_info.get("representative_name", "-"),
        client_address      = client_info.get("address", "-"),
        expert_name         = expert_name or "-",
        entity_type_label   = _entity_type_label(expert_d.get("entity_type", "")),
        expert_biz_info     = f"사업자번호: {expert_d.get('biz_number') or expert_d.get('business_no', '-')}",
        service_type_label  = _expert_type_label(expert_type),
        article3            = claude_sections.get("article3", ""),
        start_date          = start_dt.strftime("%Y-%m-%d"),
        end_date            = end_dt.strftime("%Y-%m-%d"),
        duration_months     = duration_months,
        contract_amount_fmt = f"{contract_amount:,}",
        tai_fee_rate        = tai_fee_rate,
        tai_fee_amount_fmt  = f"{tai_fee_amount:,}",
        expert_amount_fmt   = f"{expert_amount:,}",
        article5            = claude_sections.get("article5", ""),
        article6            = claude_sections.get("article6", ""),
        article7            = claude_sections.get("article7", ""),
        client_signed_info  = "서명 대기",
        expert_signed_info  = "서명 대기",
    )

    # ── 4. matching_contracts INSERT ──────────────────────────────────
    contract_res = supabase.table("matching_contracts").insert({
        "request_id":       body.request_id,
        "result_id":        body.result_id,
        "status":           "DRAFT",
        "contract_title":   f"{_expert_type_label(expert_type)} 서비스 계약서",
        "contract_html":    html,
        "contract_version": 1,
        "revision_count":   0,
        "contract_amount":  contract_amount,
        "tai_fee_rate":     tai_fee_rate,
        "tai_fee_amount":   tai_fee_amount,
        "expert_amount":    expert_amount,
        "client_user_id":   req_data.get("user_id"),
        "expert_user_id":   result_data.get("expert_user_id"),
        "generated_at":     now,
        "created_at":       now,
        "updated_at":       now,
    }).execute()

    if not contract_res.data:
        raise HTTPException(status_code=500, detail="계약서 저장 실패")

    contract_id = contract_res.data[0]["id"]

    # contract_id를 HTML에 반영
    html_final   = html.replace("PENDING", contract_id[:8].upper())
    storage_path = f"{contract_id}/v1/contract.html"

    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=html_final.encode("utf-8"),
            file_options={"content-type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.warning(f"[CONTRACT GEN] Storage 업로드 실패 (DB는 유지): {e}")

    supabase.table("matching_contracts").update({
        "contract_html":    html_final,
        "contract_pdf_url": storage_path,
        "updated_at":       now,
    }).eq("id", contract_id).execute()

    # ── 5. matching_requests → CONTRACTING ────────────────────────────
    req_history = req_data.get("status_history") or []
    req_history.append({"status": "CONTRACTING", "at": now, "by": "system",
                        "memo": f"계약서 생성 contract_id={contract_id}"})
    supabase.table("matching_requests").update({
        "status":         "CONTRACTING",
        "status_history": req_history,
        "updated_at":     now,
    }).eq("id", body.request_id).execute()

    # ── 6. 양측 알림 ──────────────────────────────────────────────────
    for uid, msg in [
        (req_data.get("user_id"),           "계약서 초안이 작성되었습니다. 검토 후 서명해 주세요."),
        (result_data.get("expert_user_id"), "계약서 초안이 작성되었습니다. 내용을 확인해 주세요."),
    ]:
        if uid:
            supabase.table("notifications").insert({
                "user_id":    uid,
                "title":      "계약서 초안 완성",
                "body":       msg,
                "type":       "CONTRACT",
                "ref_id":     contract_id,
                "is_read":    False,
                "created_at": now,
            }).execute()

    log.info(f"[CONTRACT GEN] 생성 완료 contract_id={contract_id}")
    return {
        "status": "success",
        "data": {
            "contract_id": contract_id,
            "status":      "DRAFT",
            "view_url":    f"/matching/contracts/{contract_id}/view",
        },
    }


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
    res = (
        supabase.table("matching_contracts")
        .select("id, contract_html, status, client_user_id, expert_user_id, "
                "client_signed, expert_signed, revision_count")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    contract = res.data[0]
    uid      = current_user["id"]
    is_admin = current_user.get("role_code") == "001"
    is_party = uid in (contract.get("client_user_id"), contract.get("expert_user_id"))

    if not (is_admin or is_party):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

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
    res = (
        supabase.table("matching_contracts")
        .select("*")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    contract  = res.data[0]
    uid       = current_user["id"]
    is_admin  = current_user.get("role_code") == "001"
    is_party  = uid in (contract.get("client_user_id"), contract.get("expert_user_id"))
    if not (is_admin or is_party):
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    revision_count = (contract.get("revision_count") or 0) + 1
    now            = _now_iso()

    # 3회 초과 → ADMIN_HOLD
    if revision_count > 3:
        supabase.table("matching_contracts").update({
            "status":        "ADMIN_HOLD",
            "revision_note": body.revision_note,
            "updated_at":    now,
        }).eq("id", contract_id).execute()
        return {
            "status": "success",
            "data": {
                "contract_id":    contract_id,
                "status":         "ADMIN_HOLD",
                "message":        "수정 횟수(3회)를 초과하여 어드민 검토가 필요합니다.",
                "revision_count": revision_count,
            },
        }

    # Claude API로 수정 반영
    old_html     = contract.get("contract_html", "")
    new_html     = await _revise_with_claude(old_html, body.revision_note)
    new_version  = (contract.get("contract_version") or 1) + 1
    storage_path = f"{contract_id}/v{new_version}/contract.html"

    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=new_html.encode("utf-8"),
            file_options={"content-type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.warning(f"[CONTRACT REVISE] Storage 업로드 실패: {e}")

    supabase.table("matching_contracts").update({
        "status":           "REVISING",
        "contract_html":    new_html,
        "contract_pdf_url": storage_path,
        "contract_version": new_version,
        "revision_count":   revision_count,
        "revision_note":    body.revision_note,
        "updated_at":       now,
    }).eq("id", contract_id).execute()

    # 상대방 알림
    notify_uid = (
        contract.get("expert_user_id") if uid == contract.get("client_user_id")
        else contract.get("client_user_id")
    )
    if notify_uid:
        supabase.table("notifications").insert({
            "user_id":    notify_uid,
            "title":      "계약서 수정 요청",
            "body":       f"상대방이 계약서 수정을 요청했습니다. ({revision_count}/3회)",
            "type":       "CONTRACT",
            "ref_id":     contract_id,
            "is_read":    False,
            "created_at": now,
        }).execute()

    return {
        "status": "success",
        "data": {
            "contract_id":      contract_id,
            "status":           "REVISING",
            "contract_version": new_version,
            "revision_count":   revision_count,
            "remaining":        3 - revision_count,
        },
    }


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
    res = (
        supabase.table("matching_contracts")
        .select("id, status, client_user_id, expert_user_id, client_signed, expert_signed")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    contract = res.data[0]
    uid      = current_user["id"]

    if uid not in (contract.get("client_user_id"), contract.get("expert_user_id")):
        raise HTTPException(status_code=403, detail="계약 당사자만 서명할 수 있습니다.")

    if contract.get("status") not in ("DRAFT", "REVISING", "REVIEWING"):
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태({contract['status']})에서는 서명할 수 없습니다.",
        )

    # identity_logs에 PENDING 기록 (contract_id를 request_id 필드로 추적)
    supabase.table("identity_logs").insert({
        "user_id":    uid,
        "method":     "KAKAO",
        "status":     "PENDING",
        "request_id": contract_id,
        "created_at": _now_iso(),
    }).execute()

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

    ci      = data.get("ci", data.get("CI", ""))
    user_id = data.get("user_id", "")
    now     = _now_iso()

    supabase = get_supabase()
    contract_res = (
        supabase.table("matching_contracts")
        .select("*")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not contract_res.data:
        return HTMLResponse("<script>window.close();</script>")

    c = contract_res.data[0]

    # 어느 쪽 서명인지 판단
    update_row: dict = {}
    if user_id == c.get("client_user_id"):
        update_row = {
            "client_signed":    True,
            "client_signed_at": now,
            "client_sign_ci":   ci,
        }
    elif user_id == c.get("expert_user_id"):
        update_row = {
            "expert_signed":    True,
            "expert_signed_at": now,
            "expert_sign_ci":   ci,
        }

    if not update_row:
        return HTMLResponse("<script>window.close();</script>")

    supabase.table("matching_contracts").update({
        **update_row, "updated_at": now,
    }).eq("id", contract_id).execute()

    # 양측 서명 완료 여부 재확인
    updated_res = (
        supabase.table("matching_contracts")
        .select("client_signed, expert_signed, request_id")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not updated_res.data:
        return HTMLResponse("<script>window.opener?.onSignComplete({success:true});window.close();</script>")

    updated    = updated_res.data[0]
    both_signed = updated.get("client_signed") and updated.get("expert_signed")

    if both_signed:
        supabase.table("matching_contracts").update({
            "status": "SIGNED", "updated_at": now,
        }).eq("id", contract_id).execute()

        # matching_requests → CONTRACTED
        request_id = updated.get("request_id")
        if request_id:
            req_res = (
                supabase.table("matching_requests")
                .select("status_history")
                .eq("id", request_id)
                .limit(1)
                .execute()
            )
            if req_res.data:
                history = req_res.data[0].get("status_history") or []
                history.append({"status": "CONTRACTED", "at": now, "by": "system",
                                "memo": "양측 서명 완료"})
                supabase.table("matching_requests").update({
                    "status":         "CONTRACTED",
                    "status_history": history,
                    "updated_at":     now,
                }).eq("id", request_id).execute()

        # 양측 알림
        for uid, msg in [
            (c.get("client_user_id"), "계약이 성사되었습니다! 계약금 입금 안내를 확인해 주세요."),
            (c.get("expert_user_id"), "계약이 성사되었습니다! 업무 시작을 준비해 주세요."),
        ]:
            if uid:
                supabase.table("notifications").insert({
                    "user_id":    uid,
                    "title":      "🎉 계약 성사",
                    "body":       msg,
                    "type":       "CONTRACT",
                    "ref_id":     contract_id,
                    "is_read":    False,
                    "created_at": now,
                }).execute()

    log.info(f"[CONTRACT SIGN] contract_id={contract_id} user={user_id} both_signed={both_signed}")
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
    res = (
        supabase.table("matching_contracts")
        .select(
            "id, status, contract_title, contract_version, revision_count, "
            "contract_amount, tai_fee_rate, tai_fee_amount, expert_amount, "
            "client_signed, client_signed_at, "
            "expert_signed, expert_signed_at, "
            "generated_at, updated_at"
        )
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    return {"status": "success", "data": res.data[0]}
