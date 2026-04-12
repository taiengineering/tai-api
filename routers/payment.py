"""
이니시스 INIStdPay 표준결제 라우터 — v3.2.0

v3.2.0 (2026-04-12)
  [FEAT] VBANK(가상계좌) 결제 지원 — 연결 서비스 전용
         - POST /payments/vbank/prepare   : 가상계좌 발급
         - POST /payments/vbank/noti      : 입금 확인 웹훅
         - GET  /payments/{id}/vbank-status : 입금 현황 조회
         - /inicis/return VBANK 분기 처리 추가
         - matching_contracts.paid_confirmed_at / 상태 자동 업데이트
         - matching_requests IN_PROGRESS 자동 전이

v3.1.0 (2026-04-12)
  [FEAT] service_status 추가 — PAID / ACTIVE / ENDED
  [FEAT] list_payments → v_payments_list 뷰 사용

v3.0.0 (2026-04-12)
  [FEAT] user_id 필수값, product_type 필수값, expired_at(SaaS), pg_method
"""
from __future__ import annotations

import base64 as _base64
import hashlib
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests as _requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, field_validator

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])

INICIS_MID          = os.getenv("INICIS_MID", "taieng4350")
INICIS_KEY_PATH     = os.getenv("INICIS_KEY_PATH", "/app/key/taieng4350")
INICIS_KEY_PASSWORD = os.getenv("INICIS_KEY_PASSWORD", "1111")

DEFAULT_RETURN_URL = "https://api.taieng.co.kr/payments/inicis/return"
DEFAULT_CLOSE_URL  = "https://api.taieng.co.kr/payments/result?resultCode=CLOSE"
FRONT_RETURN_URL   = "https://api.taieng.co.kr/payments/result"

# SaaS 상품 — 결제 후 expired_at 계산 대상
SAAS_PRODUCT_TYPES: List[str] = [
    "SAAS_CONSTRUCTION",
    "SAAS_FACILITY",
    "SAAS_BUILDING",
]


# ── 유틸 ──────────────────────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _ts_ms() -> str:
    return str(int(time.time() * 1000))

def _make_order_id() -> str:
    return f"TAI{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _calc_expired_at(paid_at_iso: str, period_months: int) -> str:
    base = datetime.fromisoformat(paid_at_iso.replace("Z", "+00:00"))
    return (base + relativedelta(months=period_months)).isoformat()

def _load_sign_key() -> str:
    env_key = os.getenv("INICIS_SIGN_KEY", "").strip()
    if env_key:
        return env_key
    try:
        with open(os.path.join(INICIS_KEY_PATH, "keypass.enc"), "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except Exception as e:
        log.warning(f"[INICIS] keypass.enc 로드 실패: {e}")
    return INICIS_KEY_PASSWORD

def _load_mpriv_pem() -> Optional[bytes]:
    b64 = os.getenv("INICIS_MPRIV_PEM_B64", "").strip()
    if b64:
        try:
            return _base64.b64decode(b64)
        except Exception as e:
            log.error(f"[INICIS] INICIS_MPRIV_PEM_B64 디코딩 실패: {e}")
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
        key = RSA.import_key(pem_bytes, passphrase=password)
        h   = _SHA256.new(data.encode("utf-8"))
        sig = pkcs1_15.new(key).sign(h)
        return _base64.b64encode(sig).decode("utf-8")
    except Exception as e:
        log.error(f"[INICIS] RSA 서명 실패: {e}")
        return None

def _call_pay_auth(auth_token: str, auth_url: str, sign_key: str) -> Dict[str, Any]:
    timestamp    = _ts_ms()
    sig_data     = f"authToken={auth_token}&timestamp={timestamp}"
    veri_data    = f"authToken={auth_token}&signKey={sign_key}&timestamp={timestamp}"
    signature    = _sha256(sig_data)
    verification = _sha256(veri_data)
    params: Dict[str, str] = {
        "mid":          INICIS_MID,
        "authToken":    auth_token,
        "timestamp":    timestamp,
        "signature":    signature,
        "verification": verification,
        "charset":      "UTF-8",
        "format":       "JSON",
    }
    pem = _load_mpriv_pem()
    if pem:
        rsa_sig = _rsa_sign_sha256(auth_token, pem, INICIS_KEY_PASSWORD)
        if rsa_sig:
            params["signData"] = rsa_sig
    try:
        resp = _requests.post(auth_url, data=params, timeout=30,
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
        result = resp.json()
        log.info(f"[INICIS STEP3] resultCode={result.get('resultCode')} resultMsg={result.get('resultMsg')}")
        return result
    except Exception as e:
        log.error(f"[INICIS] 승인 API 실패: {e}")
        raise


# ── Pydantic 모델 ─────────────────────────────────────────────────────

class PrepareBody(BaseModel):
    user_id:       str
    product_type:  str
    amount:        int
    goodname:      str
    company_id:    Optional[str] = None
    contract_id:   Optional[str] = None
    quote_id:      Optional[str] = None
    plan_code:     Optional[str] = None
    period_months: Optional[int] = None
    payment_type:  Optional[str] = "CARD"
    buyername:     Optional[str] = "고객"
    buyertel:      Optional[str] = "00000000000"
    buyeremail:    Optional[str] = None
    return_url:    Optional[str] = None
    close_url:     Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def user_id_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id는 필수값입니다. 로그인 후 결제해주세요.")
        return v.strip()

    @field_validator("product_type")
    @classmethod
    def product_type_valid(cls, v: str) -> str:
        allowed = {
            "DIAGNOSIS", "SAAS_CONSTRUCTION", "SAAS_FACILITY", "SAAS_BUILDING",
            "EXPERT", "REPAIR", "CONSULTING", "INAPP",
        }
        if v not in allowed:
            raise ValueError(f"product_type 값이 유효하지 않습니다. 허용: {allowed}")
        return v


class VbankPrepareBody(BaseModel):
    """VBANK 전용 결제 준비 Body — 연결 서비스(선임/컨설팅/수선) 전용"""
    user_id:              str
    product_type:         str                    # EXPERT / CONSULTING / REPAIR
    amount:               int                    # 계약 전체 금액
    goodname:             str                    # 상품명
    matching_contract_id: str                    # matching_contracts.id (필수)

    company_id:          Optional[str] = None
    buyername:           Optional[str] = "고객"
    buyertel:            Optional[str] = "00000000000"
    buyeremail:          Optional[str] = None
    vbank_expire_min:    int = 4320              # 가상계좌 유효시간 (분, 기본 3일)

    @field_validator("product_type")
    @classmethod
    def validate_vbank_product(cls, v: str) -> str:
        allowed = {"EXPERT", "CONSULTING", "REPAIR"}
        if v not in allowed:
            raise ValueError(f"VBANK는 연결 서비스만 가능합니다: {allowed}")
        return v


class ManualConfirmBody(BaseModel):
    payment_id:  str
    contract_id: str


class CancelBody(BaseModel):
    reason:       Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None


# ── HTML 페이지 ───────────────────────────────────────────────────────

_PRICING_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TAI Safe 요금제 | 산업안전 플랫폼</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
  <link href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css" rel="stylesheet" />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <style>
    * { font-family: 'Noto Sans KR', sans-serif; } body { background: #f8fafc; }
    .hero { background: linear-gradient(135deg,#1a1f36 0%,#0d6efd 60%,#0a58ca 100%); color:#fff; padding:3.5rem 0 3rem; text-align:center; }
    .hero h1 { font-size:2.2rem; font-weight:800; margin-bottom:.5rem; }
    .plan-card { border-radius:1.25rem; border:2px solid #dee2e6; background:#fff; box-shadow:0 6px 30px rgba(0,0,0,.07); transition:transform .18s,border-color .18s; cursor:pointer; overflow:hidden; }
    .plan-card:hover { transform:translateY(-4px); border-color:#0d6efd; }
    .plan-card.selected { border-color:#0d6efd; box-shadow:0 0 0 3px rgba(13,110,253,.18); }
    .plan-card .plan-header { padding:1.75rem 1.5rem 1.25rem; border-bottom:1px solid #f0f0f0; }
    .plan-card.premium .plan-header { background:linear-gradient(135deg,#0d6efd 0%,#6610f2 100%); color:#fff; }
    .plan-name { font-size:1.4rem; font-weight:800; }
    .plan-badge { font-size:.72rem; padding:.25em .65em; border-radius:.5em; background:rgba(255,255,255,.25); color:#fff; vertical-align:middle; margin-left:.4rem; }
    .plan-price { font-size:2.2rem; font-weight:800; margin:.75rem 0 .25rem; }
    .plan-desc { font-size:.88rem; color:#6c757d; margin-top:.25rem; }
    .plan-features { padding:1.25rem 1.5rem 1.5rem; }
    .plan-features li { font-size:.88rem; padding:.3rem 0; border-bottom:1px solid #f5f5f5; display:flex; align-items:center; gap:.5rem; }
    .plan-features li:last-child { border-bottom:none; }
    .btn-pay { background:linear-gradient(90deg,#0d6efd,#6610f2); color:#fff; border:none; border-radius:.75rem; padding:.85rem 2rem; font-size:1rem; font-weight:700; width:100%; cursor:pointer; }
    .btn-pay:disabled { opacity:.55; cursor:not-allowed; }
    .select-indicator { width:22px; height:22px; border-radius:50%; border:2px solid #dee2e6; flex-shrink:0; display:flex; align-items:center; justify-content:center; }
    .plan-card.selected .select-indicator { background:#0d6efd; border-color:#0d6efd; color:#fff; }
  </style>
</head>
<body>
<div class="hero"><div class="container">
  <div class="badge bg-white bg-opacity-25 text-white mb-3" style="font-size:.85rem;padding:.45em 1em;"><i class="ti ti-shield-check me-1"></i>TAI Safe 요금제</div>
  <h1>안전관리를 더 스마트하게</h1>
  <p>산업안전보건법 의무를 자동으로 파악하고, 일정·업무를 분배하세요.</p>
</div></div>
<div class="container py-5" style="max-width:900px">
  <div class="row g-4 mb-4">
    <div class="col-md-6">
      <div class="plan-card selected" id="card-basic" onclick="selectPlan('basic')">
        <div class="plan-header">
          <div class="d-flex align-items-center justify-content-between">
            <div><div class="plan-name">베이직</div><div class="plan-desc">소규모 사업장에 최적</div></div>
            <div class="select-indicator" id="ind-basic"><i class="ti tabler-check" style="font-size:.85rem;"></i></div>
          </div>
          <div class="plan-price" id="price-basic">&#8361;79,000</div>
        </div>
        <div class="plan-features"><ul class="list-unstyled mb-0">
          <li><i class="ti ti-check"></i>법령 의무 자동 분석</li>
          <li><i class="ti ti-check"></i>점검 일정 자동 생성</li>
          <li><i class="ti ti-check"></i>업무 배분 기능</li>
          <li><i class="ti ti-check"></i>모바일 앱 (작업자용)</li>
          <li><i class="ti ti-check"></i>이메일 지원</li>
        </ul></div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="plan-card premium" id="card-premium" onclick="selectPlan('premium')">
        <div class="plan-header">
          <div class="d-flex align-items-center justify-content-between">
            <div><div class="plan-name">프리미엄<span class="plan-badge">추천</span></div><div class="plan-desc" style="color:rgba(255,255,255,.75)">중·대규모 현장 최적</div></div>
            <div class="select-indicator" id="ind-premium" style="border-color:rgba(255,255,255,.5)"></div>
          </div>
          <div class="plan-price" id="price-premium">&#8361;149,000</div>
        </div>
        <div class="plan-features"><ul class="list-unstyled mb-0">
          <li><i class="ti ti-check" style="color:#6610f2"></i>베이직 모든 기능 포함</li>
          <li><i class="ti ti-check" style="color:#6610f2"></i>건설현장 TBM·위험성평가</li>
          <li><i class="ti ti-check" style="color:#6610f2"></i>법령 진단 (3회 제공)</li>
          <li><i class="ti ti-check" style="color:#6610f2"></i>안전보건 교육 관리</li>
          <li><i class="ti ti-check" style="color:#6610f2"></i>신고서식 자동화</li>
          <li><i class="ti ti-check" style="color:#6610f2"></i>전담 CS 지원</li>
        </ul></div>
      </div>
    </div>
  </div>
  <div class="card border-0 shadow-sm rounded-3 p-4">
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-3">
      <div><div class="fw-bold mb-1" id="summaryText">베이직</div><div class="text-body-secondary small">부가세 포함 · 월 단위 결제</div></div>
      <div class="text-end"><div class="fw-bold fs-4" id="summaryPrice">&#8361;79,000</div></div>
    </div>
    <hr class="my-3" />
    <button class="btn-pay" id="btnPay" onclick="startPayment()">
      <span class="spinner-border spinner-border-sm d-none me-1" id="paySpinner"></span>
      <i class="ti ti-credit-card me-1" id="payIcon"></i>지금 결제하기
    </button>
    <div class="text-center mt-2"><small class="text-body-secondary"><i class="ti ti-lock me-1"></i>이니시스 안전결제 · SSL 암호화</small></div>
  </div>
</div>
<form id="inicisForm" method="POST" accept-charset="euc-kr" style="display:none">
  <input type="hidden" name="version" value="1.0" /><input type="hidden" name="gopaymethod" value="Card" />
  <input type="hidden" name="mid" id="f_mid" /><input type="hidden" name="oid" id="f_oid" />
  <input type="hidden" name="price" id="f_price" /><input type="hidden" name="timestamp" id="f_timestamp" />
  <input type="hidden" name="use_chkfake" value="Y" /><input type="hidden" name="signature" id="f_signature" />
  <input type="hidden" name="verification" id="f_verification" /><input type="hidden" name="mKey" id="f_mKey" />
  <input type="hidden" name="goodname" id="f_goodname" /><input type="hidden" name="buyername" id="f_buyername" />
  <input type="hidden" name="buyertel" id="f_buyertel" /><input type="hidden" name="buyeremail" id="f_buyeremail" />
  <input type="hidden" name="returnUrl" id="f_returnUrl" /><input type="hidden" name="closeUrl" id="f_closeUrl" />
  <input type="hidden" name="currency" value="WON" /><input type="hidden" name="langtype" value="KO" />
  <input type="hidden" name="acceptmethod" value="CARDONLY:CARDPOINT:centerCd(Y)" />
</form>
<script src="https://stdpay.inicis.com/stdjs/INIStdPay.js" charset="utf-8"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
'use strict';
var API='https://api.taieng.co.kr',BASE={basic:79000,premium:149000},PNAME={basic:'TAI Safe 베이직',premium:'TAI Safe 프리미엄'},_plan='basic';
function selectPlan(p){_plan=p;['basic','premium'].forEach(function(x){document.getElementById('card-'+x).classList.toggle('selected',x===p);var ind=document.getElementById('ind-'+x);if(x===p){ind.innerHTML='<i class="ti tabler-check" style="font-size:.85rem;"></i>';ind.style.background='#0d6efd';ind.style.borderColor='#0d6efd';ind.style.color='#fff';}else{ind.innerHTML='';ind.style.background='';ind.style.borderColor=x==='premium'?'rgba(255,255,255,.5)':'';ind.style.color='';}});updatePrices();}
function updatePrices(){document.getElementById('price-basic').innerHTML='&#8361;'+BASE.basic.toLocaleString();document.getElementById('price-premium').innerHTML='&#8361;'+BASE.premium.toLocaleString();document.getElementById('summaryText').textContent=_plan==='basic'?'베이직':'프리미엄';document.getElementById('summaryPrice').innerHTML='&#8361;'+BASE[_plan].toLocaleString();}
function startPayment(){var token=localStorage.getItem('access_token')||'',userId=localStorage.getItem('user_id')||'';if(!token||!userId){alert('로그인 후 결제해주세요.');return;}var btn=document.getElementById('btnPay'),sp=document.getElementById('paySpinner'),icon=document.getElementById('payIcon');if(btn.disabled)return;btn.disabled=true;sp.classList.remove('d-none');icon.classList.add('d-none');var total=BASE[_plan],goodname=PNAME[_plan],companyId=localStorage.getItem('company_id')||'',RETURN_URL=API+'/payments/inicis/return',CLOSE_URL=API+'/payments/result?resultCode=CLOSE';var payload=JSON.stringify({user_id:userId,product_type:'SAAS_FACILITY',company_id:companyId||undefined,amount:total,goodname:goodname,buyername:'고객',buyertel:'00000000000',plan_code:_plan.toUpperCase(),period_months:1,payment_type:'CARD',return_url:RETURN_URL,close_url:CLOSE_URL});var xhr=new XMLHttpRequest();xhr.open('POST',API+'/payments/inicis/prepare',true);xhr.setRequestHeader('Content-Type','application/json');if(token)xhr.setRequestHeader('Authorization','Bearer '+token);xhr.onload=function(){try{var d=JSON.parse(xhr.responseText);if(xhr.status<200||xhr.status>=300)throw new Error(d.detail||d.message||'결제 준비 실패');var p=d.data||d;document.getElementById('f_mid').value=p.mid||'';document.getElementById('f_oid').value=p.oid||'';document.getElementById('f_price').value=p.price||String(total);document.getElementById('f_timestamp').value=p.timestamp||'';document.getElementById('f_signature').value=p.signature||'';document.getElementById('f_verification').value=p.verification||'';document.getElementById('f_mKey').value=p.mKey||'';document.getElementById('f_goodname').value=p.goodname||goodname;document.getElementById('f_buyername').value='고객';document.getElementById('f_buyertel').value='00000000000';document.getElementById('f_buyeremail').value='';document.getElementById('f_returnUrl').value=RETURN_URL;document.getElementById('f_closeUrl').value=CLOSE_URL;INIStdPay.pay('inicisForm');}catch(e){alert('오류: '+e.message);}finally{btn.disabled=false;sp.classList.add('d-none');icon.classList.remove('d-none');}};xhr.onerror=function(){alert('네트워크 오류. 다시 시도해 주세요.');btn.disabled=false;sp.classList.add('d-none');icon.classList.remove('d-none');};xhr.send(payload);}
updatePrices();(function(){var p=new URLSearchParams(location.search).get('plan');if(p==='premium')selectPlan('premium');})();
</script>
</body></html>"""


_RESULT_HTML = """<!doctype html>
<html lang="ko"><head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>결제 결과 | TAI Safe</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
  <link href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css" rel="stylesheet" />
  <style>*{font-family:sans-serif;}body{background:#f8fafc;min-height:100vh;display:flex;align-items:center;justify-content:center;}.result-card{background:#fff;border-radius:1.5rem;box-shadow:0 8px 40px rgba(0,0,0,.1);max-width:480px;width:100%;padding:3rem 2.5rem;text-align:center;}.icon-wrap{width:96px;height:96px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2.8rem;margin:0 auto 1.75rem;}.icon-wrap.success{background:#e8f5e9;color:#198754;}.icon-wrap.fail{background:#fef2f2;color:#dc3545;}.detail-table{background:#f8fafc;border-radius:.75rem;padding:1rem 1.25rem;text-align:left;font-size:.88rem;}.detail-row{display:flex;justify-content:space-between;padding:.35rem 0;border-bottom:1px solid #f0f0f0;}.detail-row:last-child{border-bottom:none;}.btn-action{border-radius:.75rem;padding:.75rem 1.5rem;font-size:.95rem;font-weight:700;}.countdown{font-size:.82rem;color:#adb5bd;margin-top:.5rem;}</style>
</head><body>
<div class="result-card" id="rc">
  <div class="d-flex justify-content-center mb-4"><div class="spinner-border text-primary" style="width:3rem;height:3rem;"></div></div>
  <h5 class="fw-bold mb-2">결제 정보 확인 중...</h5><p class="text-body-secondary mb-0">잠시만 기다려 주세요.</p>
</div>
<script>
'use strict';
function getParams(){var p={};new URLSearchParams(location.search).forEach(function(v,k){p[k]=v;});return p;}
function fmt(n){return n?Number(n).toLocaleString()+'원':'-';}
function goHome(){location.href='https://taieng.co.kr';}
function renderOk(p){var rc=document.getElementById('rc'),sec=5,ti;rc.innerHTML='<div class="icon-wrap success"><i class="ti tabler-circle-check"></i></div><h4 class="fw-bold mb-2">결제가 완료됐습니다.</h4><p class="text-body-secondary mb-4">서비스가 시작됩니다.</p><div class="detail-table mb-4"><div class="detail-row"><span style="color:#6c757d">상품명</span><span style="font-weight:600">'+(p.goodname||'TAI Safe')+'</span></div><div class="detail-row"><span style="color:#6c757d">결제금액</span><span style="font-weight:600">'+fmt(p.price)+'</span></div><div class="detail-row"><span style="color:#6c757d">결제수단</span><span style="font-weight:600">'+(p.paymethod||'카드')+'</span></div>'+(p.applnum?'<div class="detail-row"><span style="color:#6c757d">승인번호</span><span style="font-weight:600">'+p.applnum+'</span></div>':'')+(p.expired_at?'<div class="detail-row"><span style="color:#6c757d">서비스 만료일</span><span style="font-weight:600">'+p.expired_at.slice(0,10)+'</span></div>':'')+'</div><button class="btn btn-primary btn-action w-100" onclick="goHome()">서비스 시작하기 →</button><div class="countdown" id="cd">'+sec+'초 후 자동 이동</div>';ti=setInterval(function(){sec--;var e=document.getElementById('cd');if(e)e.textContent=sec+'초 후 자동 이동';if(sec<=0){clearInterval(ti);goHome();}},1000);}
function renderFail(msg,oid){var rc=document.getElementById('rc');rc.innerHTML='<div class="icon-wrap fail"><i class="ti tabler-circle-x"></i></div><h4 class="fw-bold mb-2">결제에 실패했습니다.</h4><p class="text-body-secondary mb-3">다시 시도해 주세요.</p><div class="detail-table mb-4"><div class="detail-row"><span style="color:#6c757d">사유</span><span style="color:#dc3545;font-weight:600">'+(msg||'오류')+'</span></div>'+(oid?'<div class="detail-row"><span style="color:#6c757d">주문번호</span><span style="font-size:.8rem">'+oid+'</span></div>':'')+'</div><div class="d-flex gap-2"><a href="https://api.taieng.co.kr/payments/pricing" class="btn btn-primary btn-action flex-grow-1">다시 시도</a><a href="https://taieng.co.kr" class="btn btn-outline-secondary btn-action">홈으로</a></div>';}
(function(){var p=getParams();if(!p.resultCode){renderFail('파라미터 없음');return;}if(p.resultCode==='00'||p.resultCode==='0000')renderOk(p);else renderFail(decodeURIComponent(p.msg||'오류코드 '+p.resultCode),p.oid);})();
</script>
</body></html>"""


# ── 라우터 ────────────────────────────────────────────────────────────

@router.get("/pricing", response_class=HTMLResponse, include_in_schema=True)
def payment_pricing_page():
    return HTMLResponse(content=_PRICING_HTML, status_code=200)


@router.get("/result", response_class=HTMLResponse, include_in_schema=True)
def payment_result_page():
    return HTMLResponse(content=_RESULT_HTML, status_code=200)


@router.post("/inicis/prepare")
def inicis_prepare(body: PrepareBody):
    """결제 준비 — STEP1 (user_id, product_type 필수)"""
    if body.product_type in SAAS_PRODUCT_TYPES and not body.period_months:
        raise HTTPException(status_code=400, detail=f"SaaS 상품은 period_months가 필수입니다.")

    supabase  = get_supabase()
    sign_key  = _load_sign_key()
    order_id  = _make_order_id()
    timestamp = _ts_ms()
    price_str = str(body.amount)
    mKey      = _sha256(sign_key)
    sig_data   = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data  = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature    = _sha256(sig_data)
    verification = _sha256(veri_data)
    log.info(f"[INICIS STEP1] oid={order_id} user={body.user_id} product={body.product_type}")

    supply_amount = round(body.amount / 1.1)
    vat_amount    = body.amount - supply_amount
    now = _now_iso()

    row: dict = {
        "user_id":         body.user_id,
        "product_type":    body.product_type,
        "payment_method":  "INICIS",
        "payment_type":    body.payment_type or "CARD",
        "supply_amount":   supply_amount,
        "vat_amount":      vat_amount,
        "total_amount":    body.amount,
        "inicis_order_id": order_id,
        "status_code":     "PENDING",
        "service_status":  None,   # 결제 완료 후 설정
        "created_at":      now,
        "updated_at":      now,
    }
    if body.company_id:    row["company_id"]   = body.company_id
    if body.contract_id:   row["contract_id"]  = body.contract_id
    if body.quote_id:      row["quote_id"]      = body.quote_id
    if body.plan_code:     row["plan_code"]     = body.plan_code
    if body.period_months: row["period_months"] = body.period_months

    res = supabase.table("payments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="결제 레코드 생성 실패")

    return {
        "status": "success",
        "data": {
            "payment_id":   res.data[0]["id"],
            "mid":          INICIS_MID,
            "mKey":         mKey,
            "oid":          order_id,
            "price":        price_str,
            "goodname":     body.goodname,
            "buyername":    body.buyername or "고객",
            "buyertel":     body.buyertel  or "00000000000",
            "buyeremail":   body.buyeremail or "",
            "timestamp":    timestamp,
            "signature":    signature,
            "verification": verification,
            "use_chkfake":  "Y",
            "returnUrl":    DEFAULT_RETURN_URL,
            "closeUrl":     DEFAULT_CLOSE_URL,
            "charset":      "UTF-8",
            "gopaymethod":  "Card",
        },
    }


@router.post("/inicis/return", include_in_schema=True)
async def inicis_return(request: Request):
    """결제 인증 콜백 — STEP2→STEP3"""
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=파싱실패", status_code=302)

    result_code = data.get("resultCode", "")
    auth_token  = data.get("authToken", "")
    auth_url    = data.get("authUrl", "")
    idc_name    = data.get("idc_name", "")
    order_id    = data.get("orderNumber") or data.get("oid", "")
    goodname    = data.get("goodname", "TAI Safe")
    price       = data.get("price", "")
    paymethod   = data.get("paymethod", "")
    log.info(f"[INICIS STEP2] resultCode={result_code} oid={order_id} paymethod={paymethod}")

    supabase = get_supabase()

    if result_code and result_code != "0000":
        result_msg = data.get("resultMsg", "인증 실패")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(result_msg)}&oid={order_id}",
            status_code=302
        )

    pay_res = supabase.table("payments").select("*").eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=주문번호미확인&oid={order_id}", status_code=302)

    payment       = pay_res.data[0]
    payment_id    = payment["id"]
    contract_id   = payment.get("contract_id")
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")

    if not auth_url:
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=authUrl없음&oid={order_id}", status_code=302)

    supabase.table("payments").update({
        "memo": f"authToken_prefix={auth_token[:32]} idc={idc_name} authUrl={auth_url[:50]}",
        "updated_at": _now_iso(),
    }).eq("id", payment_id).execute()

    sign_key = _load_sign_key()
    try:
        auth_result = _call_pay_auth(auth_token, auth_url, sign_key)
    except Exception as e:
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": f"승인 API 실패: {e}", "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=승인API오류&oid={order_id}", status_code=302)

    is_ok = str(auth_result.get("resultCode", "")) == "0000"

    if is_ok:
        now       = _now_iso()
        apply_num = auth_result.get("applNum", "")
        pg_method = auth_result.get("payMethod", paymethod) or paymethod

        # ── VBANK: 가상계좌 발급 완료 (아직 입금 전) ─────────────────
        if pg_method == "Vbank" or pg_method == "VBANK":
            vbank_number = auth_result.get("vbankNum", "")
            vbank_bank   = auth_result.get("vbankBankName", "")
            vbank_expire = auth_result.get("vbankExpireDate", "")

            supabase.table("payments").update({
                "status_code":     "PENDING",    # 입금 전이므로 PENDING 유지
                "pg_method":       "VBANK",
                "vbank_number":    vbank_number,
                "vbank_bank":      vbank_bank,
                "inicis_order_id": order_id,
                "inicis_raw":      auth_result,
                "memo":            f"가상계좌 발급완료 | {vbank_bank} {vbank_number}",
                "updated_at":      now,
            }).eq("id", payment_id).execute()

            qs = urllib.parse.urlencode({
                "resultCode":    "00",
                "oid":           order_id,
                "goodname":      goodname,
                "price":         price,
                "paymethod":     "VBANK",
                "vbank_number":  vbank_number,
                "vbank_bank":    vbank_bank,
                "vbank_expire":  vbank_expire,
                "payment_id":    payment_id,
            })
            return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

        # ── 카드/기타: 기존 로직 ───────────────────────────────────────

        expired_at = None
        if product_type in SAAS_PRODUCT_TYPES and period_months:
            expired_at = _calc_expired_at(now, period_months)

        # service_status: 계약 연결 → ACTIVE(서비스중), 미연결 → PAID(결제완료)
        service_status = "ACTIVE" if contract_id else "PAID"

        update_row: dict = {
            "status_code":      "SUCCESS",
            "service_status":   service_status,
            "pg_method":        pg_method,
            "inicis_tid":       auth_result.get("tid", ""),
            "inicis_auth_code": apply_num,
            "inicis_card_name": auth_result.get("P_FN_NM") or auth_result.get("CARD_Num", ""),
            "inicis_raw":       auth_result,
            "paid_at":          now,
            "updated_at":       now,
        }
        if expired_at:
            update_row["expired_at"] = expired_at

        supabase.table("payments").update(update_row).eq("id", payment_id).execute()

        if contract_id:
            supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()

        qs = urllib.parse.urlencode({
            "resultCode":  "00",
            "oid":         order_id,
            "goodname":    auth_result.get("goodName", goodname),
            "price":       auth_result.get("TotPrice", price),
            "paymethod":   pg_method,
            "applnum":     apply_num,
            "payment_id":  payment_id,
            "expired_at":  expired_at or "",
        })
        return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)
    else:
        fail_msg = auth_result.get("resultMsg", "승인 실패")
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": fail_msg,
            "inicis_raw": auth_result, "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(fail_msg)}&oid={order_id}",
            status_code=302
        )


@router.post("/inicis/noti", include_in_schema=True)
async def inicis_noti(request: Request):
    """이니시스 서버 노티 — STEP2 백업"""
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return "OK"

    auth_token   = data.get("authToken", "")
    auth_url     = data.get("authUrl", "")
    order_id     = data.get("orderNumber") or data.get("oid", "")
    paymethod    = data.get("paymethod", "")
    supabase     = get_supabase()
    sign_key     = _load_sign_key()

    pay_res = supabase.table("payments").select(
        "id, status_code, contract_id, product_type, period_months"
    ).eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        return "OK"

    payment       = pay_res.data[0]
    payment_id    = payment["id"]
    contract_id   = payment.get("contract_id")
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")

    if payment["status_code"] == "SUCCESS" or not auth_url:
        return "OK"

    try:
        auth_result = _call_pay_auth(auth_token, auth_url, sign_key)
    except Exception:
        return "OK"

    if auth_result.get("resultCode") == "0000":
        now = _now_iso()
        pg_method  = auth_result.get("payMethod", paymethod) or paymethod
        expired_at = None
        if product_type in SAAS_PRODUCT_TYPES and period_months:
            expired_at = _calc_expired_at(now, period_months)
        service_status = "ACTIVE" if contract_id else "PAID"

        update_row: dict = {
            "status_code":      "SUCCESS",
            "service_status":   service_status,
            "pg_method":        pg_method,
            "inicis_tid":       auth_result.get("tid", ""),
            "inicis_auth_code": auth_result.get("applNum", ""),
            "inicis_card_name": auth_result.get("P_FN_NM", ""),
            "inicis_raw":       auth_result,
            "paid_at":          now,
            "updated_at":       now,
        }
        if expired_at:
            update_row["expired_at"] = expired_at

        supabase.table("payments").update(update_row).eq("id", payment_id).execute()
        if contract_id:
            supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()
    return "OK"


@router.get("")
def list_payments(
    user_id:        Optional[str] = Query(None),
    company_id:     Optional[str] = Query(None),
    status_code:    Optional[str] = Query(None),
    service_status: Optional[str] = Query(None),
    product_type:   Optional[str] = Query(None),
    plan_code:      Optional[str] = Query(None),
    pg_method:      Optional[str] = Query(None),
    keyword:        Optional[str] = Query(None, description="회원명 또는 회사명 검색"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    결제 목록 조회 — v_payments_list 뷰 사용
    (user_name, company_name, user_email 포함)
    """
    supabase = get_supabase()
    q = supabase.table("v_payments_list").select("*", count="exact")

    if user_id:        q = q.eq("user_id",        user_id)
    if company_id:     q = q.eq("company_id",      company_id)
    if status_code:    q = q.eq("status_code",     status_code)
    if service_status: q = q.eq("service_status",  service_status)
    if product_type:   q = q.eq("product_type",    product_type)
    if plan_code:      q = q.eq("plan_code",        plan_code)
    if pg_method:      q = q.eq("pg_method",        pg_method)

    # keyword: user_name OR company_name (Supabase는 OR 필터를 지원)
    if keyword:
        q = q.or_(f"user_name.ilike.%{keyword}%,company_name.ilike.%{keyword}%")

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


@router.get("/expiring")
def list_expiring_payments(
    days: int = Query(30, ge=1, le=90),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """SaaS 만료 임박 목록 — 어드민 관제용"""
    supabase = get_supabase()
    now      = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=days)).isoformat()
    q = supabase.table("v_payments_list").select(
        "id, user_id, user_name, company_name, product_type, plan_code, "
        "period_months, total_amount, status_code, service_status, paid_at, expired_at",
        count="exact"
    ).eq("status_code", "SUCCESS").lte("expired_at", deadline).gte("expired_at", now.isoformat())
    offset = (page - 1) * size
    res    = q.order("expired_at", desc=False).range(offset, offset + size - 1).execute()
    total  = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":          res.data or [],
            "total":          total,
            "page":           page,
            "size":           size,
            "days_threshold": days,
        },
    }


@router.post("/manual/confirm")
def manual_confirm(body: ManualConfirmBody):
    """수동 활성화 — 계좌이체 입금 확인 또는 webhook 실패 복구"""
    supabase = get_supabase()
    now = _now_iso()
    pay_res = supabase.table("payments").select(
        "id, status_code, product_type, period_months"
    ).eq("id", body.payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "SUCCESS":
        raise HTTPException(status_code=409, detail="이미 성공 처리된 결제입니다.")

    update_row: dict = {
        "status_code":    "SUCCESS",
        "service_status": "ACTIVE",   # 수동 활성화 → 서비스중
        "paid_at":        now,
        "memo":           "수동 활성화 처리",
        "updated_at":     now,
    }
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")
    if product_type in SAAS_PRODUCT_TYPES and period_months:
        update_row["expired_at"] = _calc_expired_at(now, period_months)

    supabase.table("payments").update(update_row).eq("id", body.payment_id).execute()
    supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", body.contract_id).execute()

    return {
        "status":  "success",
        "message": "수동 활성화 완료",
        "data":    {"payment_id": body.payment_id, "contract_id": body.contract_id},
    }


@router.post("/{payment_id}/cancel")
def cancel_payment(payment_id: str, body: CancelBody):
    """결제 취소 — 이니시스 실결제 취소는 별도 PG 취소 API 연동 필요"""
    supabase = get_supabase()
    now = _now_iso()
    pay_res = supabase.table("payments").select(
        "id, status_code, contract_id"
    ).eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 결제입니다.")

    supabase.table("payments").update({
        "status_code":    "CANCELLED",
        "service_status": "ENDED",    # 취소 → 계약종결
        "cancel_reason":  body.reason,
        "cancelled_at":   now,
        "expired_at":     None,       # 만료일 초기화
        "updated_at":     now,
    }).eq("id", payment_id).execute()

    contract_id = payment.get("contract_id")
    if contract_id:
        supabase.table("contracts").update({"is_active": False, "updated_at": now}).eq("id", contract_id).execute()

    return {
        "status":  "success",
        "message": "취소 처리되었습니다.",
        "data":    {"payment_id": payment_id, "status_code": "CANCELLED"},
    }


# ════════════════════════════════════════════════════════════════════════
# VBANK (가상계좌) 결제 — 연결 서비스 전용  (v3.2.0)
# ════════════════════════════════════════════════════════════════════════

@router.post("/vbank/prepare")
def vbank_prepare(body: VbankPrepareBody):
    """
    연결 서비스 가상계좌 발급
    POST /payments/vbank/prepare

    이니시스 INIStdPay gopaymethod="Vbank"
    발급 즉시 가상계좌번호를 반환 → 고객에게 입금 안내.

    ⚠️ 이니시스 카드심사 완료 후 실제 가동 (현재는 구조 완성)
    """
    supabase  = get_supabase()
    sign_key  = _load_sign_key()
    order_id  = _make_order_id()
    timestamp = _ts_ms()
    price_str = str(body.amount)
    mKey      = _sha256(sign_key)

    sig_data   = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data  = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature    = _sha256(sig_data)
    verification = _sha256(veri_data)

    supply_amount = round(body.amount / 1.1)
    vat_amount    = body.amount - supply_amount
    now           = _now_iso()

    vbank_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=body.vbank_expire_min)
    ).isoformat()

    row: dict = {
        "user_id":              body.user_id,
        "product_type":         body.product_type,
        "payment_method":       "INICIS",
        "pg_method":            "VBANK",
        "payment_type":         "VBANK",
        "supply_amount":        supply_amount,
        "vat_amount":           vat_amount,
        "total_amount":         body.amount,
        "inicis_order_id":      order_id,
        "status_code":          "PENDING",       # 입금 전
        "service_status":       "PAID",
        "vbank_expires_at":     vbank_expires_at,
        "matching_contract_id": body.matching_contract_id,
        "created_at":           now,
        "updated_at":           now,
    }
    if body.company_id:
        row["company_id"] = body.company_id

    res = supabase.table("payments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="결제 레코드 생성 실패")

    payment_id = res.data[0]["id"]

    # matching_contracts에 payment_id 연결
    supabase.table("matching_contracts").update({
        "payment_id": payment_id,
        "updated_at": now,
    }).eq("id", body.matching_contract_id).execute()

    log.info(f"[VBANK PREPARE] oid={order_id} contract={body.matching_contract_id}")

    return {
        "status": "success",
        "data": {
            "payment_id":    payment_id,
            "mid":           INICIS_MID,
            "mKey":          mKey,
            "oid":           order_id,
            "price":         price_str,
            "goodname":      body.goodname,
            "buyername":     body.buyername or "고객",
            "buyertel":      body.buyertel  or "00000000000",
            "buyeremail":    body.buyeremail or "",
            "timestamp":     timestamp,
            "signature":     signature,
            "verification":  verification,
            "use_chkfake":   "Y",
            "returnUrl":     DEFAULT_RETURN_URL,
            "closeUrl":      DEFAULT_CLOSE_URL,
            "charset":       "UTF-8",
            "gopaymethod":   "Vbank",
            "vbankexpire":   body.vbank_expire_min,
        },
    }


@router.post("/vbank/noti", include_in_schema=True)
async def vbank_noti(request: Request):
    """
    이니시스 VBANK 입금 확인 노티 (웹훅)
    POST /payments/vbank/noti

    고객 입금 → 이니시스 → 이 URL로 POST.
    처리 순서:
      1. payments → SUCCESS 업데이트
      2. matching_contracts → paid_confirmed_at / ACTIVE
      3. matching_requests → IN_PROGRESS 자동 전이
      4. 신청자 알림 발송

    이니시스 설정에 등록 필요:
      https://api.taieng.co.kr/payments/vbank/noti
    """
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return "OK"

    order_id    = data.get("orderNumber") or data.get("oid", "")
    result_code = data.get("resultCode", "")
    depositor   = data.get("vbankInputName", "")   # 실제 입금자명

    log.info(f"[VBANK NOTI] oid={order_id} resultCode={result_code}")

    supabase = get_supabase()

    pay_res = (
        supabase.table("payments")
        .select("id, status_code, user_id, company_id, total_amount, product_type, matching_contract_id")
        .eq("inicis_order_id", order_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        log.warning(f"[VBANK NOTI] 주문번호 미확인: {order_id}")
        return "OK"

    payment              = pay_res.data[0]
    payment_id           = payment["id"]
    matching_contract_id = payment.get("matching_contract_id")

    # 이미 처리된 경우 스킵 (멱등성)
    if payment["status_code"] == "SUCCESS":
        return "OK"

    # 입금 취소/실패
    if result_code not in ("", "00", "0000"):
        log.info(f"[VBANK NOTI] 입금 취소: resultCode={result_code}")
        supabase.table("payments").update({
            "status_code": "FAILED",
            "fail_reason": f"VBANK 입금 취소 (resultCode={result_code})",
            "updated_at":  _now_iso(),
        }).eq("id", payment_id).execute()
        return "OK"

    # ── 입금 성공 처리 ──────────────────────────────────────────────
    now = _now_iso()

    # 1. payments → SUCCESS
    supabase.table("payments").update({
        "status_code":        "SUCCESS",
        "service_status":     "ACTIVE",
        "vbank_depositor":    depositor,
        "vbank_confirmed_at": now,
        "paid_at":            now,
        "inicis_raw":         data,
        "updated_at":         now,
    }).eq("id", payment_id).execute()
    log.info(f"[VBANK NOTI] 입금 확인 — payment_id={payment_id}")

    # 2. matching_contracts → paid_confirmed_at / ACTIVE
    if matching_contract_id:
        supabase.table("matching_contracts").update({
            "paid_confirmed_at": now,
            "status":            "ACTIVE",
            "updated_at":        now,
        }).eq("id", matching_contract_id).execute()

        # 3. matching_requests → CONTRACTED → IN_PROGRESS 자동 전이
        contract_res = (
            supabase.table("matching_contracts")
            .select("request_id")
            .eq("id", matching_contract_id)
            .limit(1)
            .execute()
        )
        if contract_res.data:
            request_id = contract_res.data[0].get("request_id")
            if request_id:
                req_res = (
                    supabase.table("matching_requests")
                    .select("id, status, status_history")
                    .eq("id", request_id)
                    .limit(1)
                    .execute()
                )
                if req_res.data and req_res.data[0]["status"] == "CONTRACTED":
                    history = req_res.data[0].get("status_history") or []
                    history.append({
                        "status": "IN_PROGRESS",
                        "at":     now,
                        "by":     "system",
                        "memo":   "가상계좌 입금 확인 → 서비스 시작",
                    })
                    supabase.table("matching_requests").update({
                        "status":         "IN_PROGRESS",
                        "status_history": history,
                        "updated_at":     now,
                    }).eq("id", request_id).execute()
                    log.info(f"[VBANK NOTI] 매칭 → IN_PROGRESS request_id={request_id}")

    # 4. 신청자 알림 발송
    if payment.get("user_id"):
        supabase.table("notifications").insert({
            "user_id":    payment["user_id"],
            "title":      "계약금 입금 확인",
            "body":       f"계약금 {int(payment['total_amount']):,}원 입금이 확인되었습니다. 서비스가 시작됩니다.",
            "type":       "PAYMENT",
            "is_read":    False,
            "created_at": now,
        }).execute()

    return "OK"


@router.get("/{payment_id}/vbank-status")
def get_vbank_status(payment_id: str):
    """
    VBANK 입금 대기 현황 조회
    GET /payments/{payment_id}/vbank-status

    프론트 결제 완료 화면에서 폴링 또는 현황 확인용.
    """
    supabase = get_supabase()
    res = (
        supabase.table("payments")
        .select(
            "id, status_code, total_amount, "
            "vbank_number, vbank_bank, vbank_expires_at, "
            "vbank_depositor, vbank_confirmed_at, paid_at"
        )
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="결제 정보를 찾을 수 없습니다.")

    p = res.data[0]
    return {
        "status": "success",
        "data": {
            "payment_id":       payment_id,
            "status_code":      p["status_code"],
            "is_paid":          p["status_code"] == "SUCCESS",
            "total_amount":     p["total_amount"],
            "vbank_number":     p.get("vbank_number"),
            "vbank_bank":       p.get("vbank_bank"),
            "vbank_expires_at": p.get("vbank_expires_at"),
            "vbank_depositor":  p.get("vbank_depositor"),
            "confirmed_at":     p.get("vbank_confirmed_at"),
        },
    }
