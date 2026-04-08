"""
이니시스 INIStdPay 표준결제 라우터 — v1.1.0

v1.1.0 (2026-04-08):
  [ADD] POST /payments/{id}/cancel   결제 취소 (이니시스 환불 미지원, DB 상태만 CANCELLED)
  [FIX] POST /payments/inicis/return 이니시스 returnUrl 로직 수정
         · 사용자 브라우저가 returnUrl로 이동 → 서버에서 승인 후 프론트 redirect
         · redirect 목적지: safe.taieng.co.kr/html/payment-return.html
  [FIX] prepare returnUrl 기본값 백엔드 자체 URL로 유지

API:
  POST /payments/inicis/prepare        결제창 파라미터 생성
  POST /payments/inicis/return         이니시스 returnUrl (승인 + 프론트 redirect)
  POST /payments/inicis/noti           이니시스 noti (서버→서버)
  GET  /payments                       결제 이력 조회
  POST /payments/manual/confirm        수동 확인
  POST /payments/{id}/cancel           취소 ← v1.1.0
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import requests as _requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────

INICIS_MID          = os.getenv("INICIS_MID", "taieng4350")
INICIS_KEY_PATH     = os.getenv("INICIS_KEY_PATH", "/app/key/taieng4350")
INICIS_KEY_PASSWORD = os.getenv("INICIS_KEY_PASSWORD", "1111")
INICIS_AUTH_URL     = "https://inipayas.inicis.com/api/payAuth/v1"

# returnUrl: 이니시스가 사용자 브라우저를 보내는 URL (= 이 백엔드 엔드포인트)
DEFAULT_RETURN_URL = os.getenv(
    "INICIS_RETURN_URL",
    "https://api.taieng.co.kr/payments/inicis/return"
)
DEFAULT_CLOSE_URL  = os.getenv(
    "INICIS_CLOSE_URL",
    "https://safe.taieng.co.kr/html/payment-return.html?resultCode=CLOSE"
)

# 승인 후 redirect 목적지 (프론트 결과 페이지)
FRONT_RETURN_URL = os.getenv(
    "INICIS_FRONT_RETURN_URL",
    "https://safe.taieng.co.kr/html/payment-return.html"
)


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _ts_ms() -> str:
    return str(int(time.time() * 1000))

def _load_sign_key() -> str:
    keypass_path = os.path.join(INICIS_KEY_PATH, "keypass.enc")
    try:
        with open(keypass_path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except Exception as e:
        log.warning(f"[INICIS] keypass.enc 로드 실패: {e}")
    return os.getenv("INICIS_SIGN_KEY") or INICIS_KEY_PASSWORD

def _load_mpriv_pem() -> Optional[bytes]:
    try:
        with open(os.path.join(INICIS_KEY_PATH, "mpriv.pem"), "rb") as f:
            return f.read()
    except Exception as e:
        log.warning(f"[INICIS] mpriv.pem 로드 실패: {e}")
        return None

def _rsa_sign_sha256(data: str, pem_bytes: bytes, password: str) -> Optional[str]:
    try:
        from Crypto.PublicKey import RSA
        from Crypto.Signature import pkcs1_15
        from Crypto.Hash import SHA256 as _SHA256
        import base64
        key = RSA.import_key(pem_bytes, passphrase=password)
        h   = _SHA256.new(data.encode("utf-8"))
        sig = pkcs1_15.new(key).sign(h)
        return base64.b64encode(sig).decode("utf-8")
    except Exception as e:
        log.error(f"[INICIS] RSA 서명 실패: {e}")
        return None

def _make_order_id() -> str:
    return f"TAI{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────
# 승인 API 호출
# ──────────────────────────────────────────────

def _call_pay_auth(auth_token: str, mid: str, sign_key: str) -> Dict[str, Any]:
    timestamp = _ts_ms()
    signature = _sha256(auth_token + mid + sign_key + timestamp)
    params: Dict[str, str] = {
        "mid":       mid,
        "signKey":   sign_key,
        "authToken": auth_token,
        "timestamp": timestamp,
        "charset":   "UTF-8",
        "format":    "JSON",
        "signature": signature,
    }
    pem = _load_mpriv_pem()
    if pem:
        rsa_sig = _rsa_sign_sha256(auth_token, pem, INICIS_KEY_PASSWORD)
        if rsa_sig:
            params["signData"] = rsa_sig
    try:
        resp = _requests.post(
            INICIS_AUTH_URL, data=params, timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return resp.json()
    except Exception as e:
        log.error(f"[INICIS] 승인 API 호출 실패: {e}")
        raise


# ──────────────────────────────────────────────
# Pydantic 모델
# ──────────────────────────────────────────────

class PrepareBody(BaseModel):
    company_id:    str
    contract_id:   Optional[str] = None
    quote_id:      Optional[str] = None
    amount:        int
    goodname:      str
    buyername:     str
    buyertel:      str
    buyeremail:    Optional[str] = None
    return_url:    Optional[str] = None
    close_url:     Optional[str] = None
    plan_code:     Optional[str] = None
    period_months: Optional[int] = None
    payment_type:  Optional[str] = "CARD"
    created_by:    Optional[str] = None

class ManualConfirmBody(BaseModel):
    payment_id:  str
    contract_id: str

class CancelBody(BaseModel):
    reason:       Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None


# ──────────────────────────────────────────────
# 1. POST /payments/inicis/prepare
# ──────────────────────────────────────────────

@router.post("/inicis/prepare")
def inicis_prepare(body: PrepareBody):
    """
    이니시스 결제창 호출 전 준비.
    payments 테이블에 PENDING 레코드 생성 후 결제창 파라미터 반환.
    signature = SHA256(oid + price + timestamp)
    mKey      = SHA256(signKey)
    """
    supabase  = get_supabase()
    sign_key  = _load_sign_key()
    order_id  = _make_order_id()
    timestamp = _ts_ms()
    price_str = str(body.amount)

    mKey      = _sha256(sign_key)
    signature = _sha256(order_id + price_str + timestamp)

    supply_amount = round(body.amount / 1.1)
    vat_amount    = body.amount - supply_amount

    now = _now_iso()
    row = {
        "company_id":      body.company_id,
        "contract_id":     body.contract_id,
        "quote_id":        body.quote_id,
        "payment_method":  "INICIS",
        "payment_type":    body.payment_type or "CARD",
        "plan_code":       body.plan_code,
        "period_months":   body.period_months,
        "supply_amount":   supply_amount,
        "vat_amount":      vat_amount,
        "total_amount":    body.amount,
        "inicis_order_id": order_id,
        "status_code":     "PENDING",
        "created_by":      body.created_by,
        "created_at":      now,
        "updated_at":      now,
    }
    res = supabase.table("payments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="결제 레코드 생성 실패")

    payment_id = res.data[0]["id"]
    return_url = body.return_url or DEFAULT_RETURN_URL
    close_url  = body.close_url  or DEFAULT_CLOSE_URL

    return {
        "status": "success",
        "data": {
            "payment_id": payment_id,
            "mid":         INICIS_MID,
            "mKey":        mKey,
            "oid":         order_id,
            "price":       price_str,
            "goodname":    body.goodname,
            "buyername":   body.buyername,
            "buyertel":    body.buyertel,
            "buyeremail":  body.buyeremail or "",
            "timestamp":   timestamp,
            "signature":   signature,
            "returnUrl":   return_url,
            "closeUrl":    close_url,
            "charset":     "UTF-8",
            "gopaymethod": "Card",
        },
    }


# ──────────────────────────────────────────────
# 2. POST /payments/inicis/return
#    v1.1.0: 승인 처리 후 프론트 redirect
# ──────────────────────────────────────────────

@router.post("/inicis/return", include_in_schema=True)
async def inicis_return(request: Request):
    """
    v1.1.0: 이니시스 returnUrl 수신 → 승인 처리 → 프론트 redirect.

    이니시스 흐름:
    1. 사용자가 결제 완료
    2. 이니시스가 returnUrl(= 이 엔드포인트)에 form POST
    3. 서버가 승인 API 호출
    4. 결과에 따라 payment-return.html로 302 redirect
       성공: ?resultCode=00&oid=...&goodname=...&price=...
       실패: ?resultCode=FAIL&msg=...
    """
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return RedirectResponse(
                f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=파싱실패",
                status_code=302
            )

    result_code  = str(data.get("resultCode") or data.get("P_STATUS", ""))
    auth_token   = data.get("authToken", "")
    auth_sig_got = data.get("authSignature", "")
    timestamp    = data.get("timestamp", "")
    order_id     = data.get("oid", "")
    tid          = data.get("tid", "")
    goodname     = data.get("goodname", "TAI Safe 이용권")
    price        = data.get("price", "")
    paymethod    = data.get("paymethod", "카드")

    log.info(f"[INICIS return] oid={order_id} resultCode={result_code}")

    supabase = get_supabase()

    pay_res = supabase.table("payments").select("*") \
        .eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        log.warning(f"[INICIS return] order_id 미발견: {order_id}")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=주문번호미확인&oid={order_id}",
            status_code=302
        )

    payment     = pay_res.data[0]
    payment_id  = payment["id"]
    contract_id = payment.get("contract_id")

    # authSignature 검증
    sign_key     = _load_sign_key()
    expected_sig = _sha256(auth_token + timestamp)
    if auth_sig_got and auth_sig_got.lower() != expected_sig.lower():
        log.error(f"[INICIS return] authSignature 불일치 oid={order_id}")
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": "authSignature 검증 실패",
            "inicis_raw": data, "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=서명검증실패&oid={order_id}",
            status_code=302
        )

    # 승인 API 호출
    try:
        auth_result = _call_pay_auth(auth_token, INICIS_MID, sign_key)
    except Exception as e:
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": f"승인 API 실패: {e}",
            "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=승인API오류&oid={order_id}",
            status_code=302
        )

    log.info(f"[INICIS return] 승인결과: {auth_result}")
    res_code = str(auth_result.get("resultCode") or auth_result.get("P_STATUS", ""))
    is_ok    = res_code in ("00", "0000")

    if is_ok:
        now       = _now_iso()
        apply_num = auth_result.get("applNum") or auth_result.get("authCode", "")
        supabase.table("payments").update({
            "status_code":      "SUCCESS",
            "inicis_tid":       auth_result.get("tid") or tid,
            "inicis_auth_code": apply_num,
            "inicis_card_name": auth_result.get("CARD_NM") or auth_result.get("cardName", ""),
            "inicis_raw":       auth_result,
            "paid_at":          now,
            "updated_at":       now,
        }).eq("id", payment_id).execute()

        if contract_id:
            supabase.table("contracts").update({
                "is_active": True, "updated_at": now,
            }).eq("id", contract_id).execute()
            log.info(f"[INICIS return] 계약 활성화 contract_id={contract_id}")

        qs = urllib.parse.urlencode({
            "resultCode": "00",
            "oid":        order_id,
            "goodname":   goodname,
            "price":      price,
            "paymethod":  paymethod,
            "applnum":    apply_num,
            "payment_id": payment_id,
        })
        return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

    else:
        fail_msg = auth_result.get("resultMsg") or auth_result.get("P_RMESG1", "승인 실패")
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": fail_msg,
            "inicis_raw": auth_result, "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(fail_msg)}&oid={order_id}",
            status_code=302
        )


# ──────────────────────────────────────────────
# 3. POST /payments/inicis/noti
# ──────────────────────────────────────────────

@router.post("/inicis/noti", include_in_schema=True)
async def inicis_noti(request: Request):
    """이니시스 노티 URL (서버→서버, 백그라운드 검증). 응답: "OK" """
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return "OK"

    auth_token   = data.get("authToken", "")
    auth_sig_got = data.get("authSignature", "")
    timestamp    = data.get("timestamp", "")
    order_id     = data.get("oid", "")

    log.info(f"[INICIS noti] oid={order_id}")
    supabase = get_supabase()
    sign_key = _load_sign_key()

    expected_sig = _sha256(auth_token + timestamp)
    if auth_sig_got and auth_sig_got.lower() != expected_sig.lower():
        log.warning(f"[INICIS noti] authSignature 불일치 oid={order_id}")
        return "OK"

    pay_res = supabase.table("payments").select("id, status_code, contract_id") \
        .eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        return "OK"

    payment     = pay_res.data[0]
    payment_id  = payment["id"]
    contract_id = payment.get("contract_id")

    if payment["status_code"] == "SUCCESS":
        return "OK"

    try:
        auth_result = _call_pay_auth(auth_token, INICIS_MID, sign_key)
    except Exception:
        return "OK"

    res_code = str(auth_result.get("resultCode", ""))
    is_ok    = res_code in ("00", "0000")

    if is_ok:
        now = _now_iso()
        supabase.table("payments").update({
            "status_code":      "SUCCESS",
            "inicis_tid":       auth_result.get("tid", ""),
            "inicis_auth_code": auth_result.get("applNum", ""),
            "inicis_card_name": auth_result.get("CARD_NM", ""),
            "inicis_raw":       auth_result,
            "paid_at":          now,
            "updated_at":       now,
        }).eq("id", payment_id).execute()
        if contract_id:
            supabase.table("contracts").update({
                "is_active": True, "updated_at": now,
            }).eq("id", contract_id).execute()
    return "OK"


# ──────────────────────────────────────────────
# 4. GET /payments
# ──────────────────────────────────────────────

@router.get("")
def list_payments(
    company_id:   Optional[str] = Query(None),
    contract_id:  Optional[str] = Query(None),
    status_code:  Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("payments").select(
        "id, company_id, contract_id, payment_method, payment_type, "
        "plan_code, period_months, total_amount, inicis_order_id, "
        "inicis_tid, inicis_card_name, status_code, paid_at, created_at",
        count="exact"
    )
    if company_id:  q = q.eq("company_id",  company_id)
    if contract_id: q = q.eq("contract_id", contract_id)
    if status_code: q = q.eq("status_code", status_code)
    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


# ──────────────────────────────────────────────
# 5. POST /payments/manual/confirm
# ──────────────────────────────────────────────

@router.post("/manual/confirm")
def manual_confirm(body: ManualConfirmBody):
    supabase = get_supabase()
    now = _now_iso()
    pay_res = supabase.table("payments").select("id, status_code") \
        .eq("id", body.payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    if pay_res.data[0]["status_code"] == "SUCCESS":
        raise HTTPException(status_code=409, detail="이미 성공 처리된 결제입니다.")
    supabase.table("payments").update({
        "status_code": "SUCCESS", "paid_at": now,
        "memo": "계좌이체 수동 확인", "updated_at": now,
    }).eq("id", body.payment_id).execute()
    supabase.table("contracts").update({
        "is_active": True, "updated_at": now,
    }).eq("id", body.contract_id).execute()
    log.info(f"[MANUAL] 확인 payment_id={body.payment_id} contract_id={body.contract_id}")
    return {
        "status":  "success",
        "message": "수동 활성화 완료",
        "data":    {"payment_id": body.payment_id, "contract_id": body.contract_id},
    }


# ──────────────────────────────────────────────
# 6. POST /payments/{id}/cancel  ← v1.1.0
# ──────────────────────────────────────────────

@router.post("/{payment_id}/cancel")
def cancel_payment(payment_id: str, body: CancelBody):
    """
    v1.1.0: 결제 취소.

    주의: 이니시스 환불 API는 별도 연동 필요 (미구현).
    현재 DB status_code만 CANCELLED로 변경.
    실제 환불은 이니시스 관리자 페이지 또는 다빈채 API를 통해 직접 요청.
    """
    supabase = get_supabase()
    now = _now_iso()

    pay_res = supabase.table("payments").select("id, status_code, contract_id") \
        .eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")

    payment = pay_res.data[0]
    if payment["status_code"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 결제입니다.")

    supabase.table("payments").update({
        "status_code":   "CANCELLED",
        "cancel_reason": body.reason,
        "cancelled_at":  now,
        "updated_at":    now,
    }).eq("id", payment_id).execute()

    contract_id = payment.get("contract_id")
    if contract_id:
        supabase.table("contracts").update({
            "is_active": False, "updated_at": now,
        }).eq("id", contract_id).execute()

    log.info(f"[CANCEL] payment_id={payment_id} reason={body.reason}")
    return {
        "status":  "success",
        "message": "취소 처리되었습니다.",
        "data":    {"payment_id": payment_id, "status_code": "CANCELLED"},
    }
