from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request

from schemas.legal_engine import DiagnoseStep1Body
from services.legal_rules import normalize_sector_db
from services.time import now_kst, serialize_external_utc

log = logging.getLogger(__name__)

_COMPILER_ALLOWED_SECTORS = frozenset(
    {"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"}
)


def run_step1_via_compiler(supabase, step1_body: DiagnoseStep1Body, allowed_sectors=None) -> Dict[str, Any]:
    """Consumer step1 via Compiler Core temp-factory path (Phase 2)."""
    from services.anonymous_factory_service import prepare_step1_body_for_compiler, run_anonymous_diagnosis

    sectors = allowed_sectors or _COMPILER_ALLOWED_SECTORS
    step1_body = prepare_step1_body_for_compiler(step1_body)
    result_data = run_anonymous_diagnosis(supabase, step1_body, sectors)
    return {"status": "success", "data": result_data}


def _save_diagnosis_purchase(
    supabase,
    *,
    auth_log_id: str,
    public_token: str,
    tier_code: str,
    paid_amount: int,
    payment_ref: Optional[str],
    invoice_requested: bool,
    invoice_biz_no: Optional[str],
    invoice_email: Optional[str],
) -> None:
    """유료 진단 결제 메타를 diagnosis_purchases에 기록한다."""
    try:
        supabase.table("diagnosis_purchases").insert(
            {
                "auth_log_id": auth_log_id,
                "public_token": public_token,
                "tier_code": tier_code,
                "paid_amount": paid_amount,
                "payment_ref": payment_ref,
                "invoice_requested": invoice_requested,
                "invoice_biz_no": invoice_biz_no,
                "invoice_email": invoice_email,
                "created_at": serialize_external_utc(now_kst()),
            }
        ).execute()
    except Exception as e:
        log.warning("[diagnosis_purchases] save failed: %s", e)


def sync_diagnosis_auth_log_from_inicis(supabase, mtx_id: str) -> None:
    """inicis_auth_requests(SUCCESS) → diagnosis_auth_log, auth_token=mtx_id (무료진단 호환)."""
    res = (
        supabase.table("inicis_auth_requests")
        .select("mtx_id, status, user_name, user_phone, user_ci")
        .eq("mtx_id", mtx_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return
    row = res.data[0]
    if row.get("status") != "SUCCESS":
        return
    ci = (row.get("user_ci") or "").strip()
    if not ci:
        log.warning("[diagnosis_auth] inicis SUCCESS but no CI mtx_id=%s", mtx_id)
        return

    ci_hash = hashlib.sha256(ci.encode("utf-8")).hexdigest()
    name = row.get("user_name") or ""
    phone = row.get("user_phone") or ""
    now = serialize_external_utc(now_kst())

    existing = (
        supabase.table("diagnosis_auth_log")
        .select("id, free_count, free_limit")
        .eq("ci_hash", ci_hash)
        .limit(1)
        .execute()
    )
    payload = {
        "name": name,
        "phone": phone,
        "verified_at": now,
        "updated_at": now,
        "auth_token": mtx_id,
        "status": "ACTIVE",
    }
    if existing.data:
        supabase.table("diagnosis_auth_log").update(payload).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("diagnosis_auth_log").insert({
            **payload,
            "ci": "",
            "ci_hash": ci_hash,
            "free_count": 0,
            "free_limit": 3,
            "created_at": now,
        }).execute()


def resolve_auth_log(supabase, auth_token: str) -> dict:
    res = (
        supabase.table("diagnosis_auth_log")
        .select("id, ci_hash, name, phone, free_count, free_limit, status, linked_user_id")
        .eq("auth_token", auth_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=401, detail="인증 세션이 유효하지 않습니다. 본인인증을 다시 시도해 주세요.")
    row = res.data[0]
    if row.get("status") != "ACTIVE":
        raise HTTPException(status_code=403, detail="사용할 수 없는 인증 세션입니다.")
    return row


def resolve_member_auth_log(supabase, current_user: dict) -> dict:
    """WO-CST-PAID-MEMBER-RUNTIME-BRIDGE-006: 로그인 + 본인인증 완료 회원의 기존 diagnosis_auth_log 를
    서버 신원(current_user)으로 복원한다. body.auth_token 이 없는 유료 회원 fallback 전용.
    deterministic 규칙(임의 latest/first 금지): linked_user_id=current_user.id AND ci_hash=current_user.identity_ci(=이미 SHA256 저장)
    AND status='ACTIVE'. 결과가 '정확히 1건'일 때만 사용하고, 0/복수는 fail-closed.
    anonymous 인증 완화가 아니다 — verified persisted member 만 허용. client 전달 user_id/ci/linked 는 신뢰하지 않는다.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="유료 진단은 회원가입 후 이용 가능합니다.")
    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다. 본인인증 후 이용해 주세요.")
    uid = current_user.get("id")
    # CORRECTION-02: users.identity_ci 는 이미 SHA256(원문 CI)로 저장된다(inicis 본인인증 sync 규약).
    # diagnosis_auth_log.ci_hash 도 동일한 SHA256(원문 CI)다. 따라서 identity_ci 를 재해시하지 않고
    # 그대로 ci_hash 컬럼과 비교한다(double-hash 방지: SHA256(SHA256(CI)) 로 재해시하면 절대 매칭되지 않음).
    ci_hash = (current_user.get("identity_ci") or "").strip()
    if not ci_hash or not uid:
        raise HTTPException(status_code=403, detail="본인인증 정보가 없습니다. 본인인증을 다시 진행해 주세요.")
    res = (
        supabase.table("diagnosis_auth_log")
        .select("id, ci_hash, name, phone, free_count, free_limit, status, linked_user_id")
        .eq("linked_user_id", uid)
        .eq("ci_hash", ci_hash)
        .eq("status", "ACTIVE")
        .execute()
    )
    rows = res.data or []
    # 정확히 1건만 사용. 0(연결 없음)/복수(deterministic 규칙 부재)는 fail-closed.
    if len(rows) != 1:
        raise HTTPException(status_code=401, detail="인증 세션을 확인할 수 없습니다. 본인인증을 다시 시도해 주세요.")
    return rows[0]


def check_free_usage(supabase, auth_token: str) -> Dict[str, Any]:
    row = resolve_auth_log(supabase, auth_token)
    used = row.get("free_count") or 0
    limit_cnt = row.get("free_limit") or 3
    remaining = max(0, limit_cnt - used)
    return {
        "status": "success",
        "can_free": remaining > 0,
        "free_used": used,
        "free_limit": limit_cnt,
        "free_remaining": remaining,
        "name": row.get("name"),
    }


def get_price_tier_payload(
    sector: str,
    floor_area: float,
    contract_amount_eok: float,
    user_tier: Optional[str],
    auto_tier_func: Callable[[str, float, float, Optional[str]], str],
    paid_tier_prices: Dict[str, int],
    free_tier_codes,
) -> Dict[str, Any]:
    sector = normalize_sector_db(sector)
    tier_code = auto_tier_func(sector, floor_area, contract_amount_eok, user_tier)

    price = paid_tier_prices.get(tier_code, 0)
    is_free = tier_code in free_tier_codes
    auto_det = sector in ("BUILDING", "CONSTRUCTION")

    determination_note = ""
    if sector == "BUILDING":
        if floor_area >= 5000:
            determination_note = f"입력 면적 {floor_area:,.0f}㎡ ≥ 5,000㎡ → 대형건물로 자동 판정"
        else:
            determination_note = f"입력 면적 {floor_area:,.0f}㎡ < 5,000㎡ → 소형건물로 자동 판정"
    elif sector == "CONSTRUCTION":
        if contract_amount_eok >= 50:
            determination_note = f"공사금액 {contract_amount_eok}억 ≥ 50억 → 종합으로 자동 판정"
        else:
            determination_note = f"공사금액 {contract_amount_eok}억 < 50억 → 기본으로 자동 판정"
    else:
        determination_note = "산업 섹터는 사용자가 직접 등급을 선택합니다"

    return {
        "status": "success",
        "sector": sector,
        "tier_code": tier_code,
        "price_krw": price,
        "is_free": is_free,
        "auto_determined": auto_det,
        "determination_note": determination_note,
    }


def _ensure_disclaimer_for_paid_entry(supabase, auth_row: dict) -> str:
    """유료 결제 직입(runPaidDiagnosis) — disclaimer_log_id 없을 때 자동 기록."""
    from services.diagnosis_helpers import _now

    res = (
        supabase.table("diagnosis_disclaimer_log")
        .insert(
            {
                "ci_hash": auth_row["ci_hash"],
                "auth_log_id": auth_row["id"],
                "disclaimer_text": "유료 진단 결제 완료 후 자동 동의 처리",
                "agreed": True,
                "agreed_at": _now(),
            }
        )
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="면책 동의 저장에 실패했습니다.")
    return str(res.data[0]["id"])


def save_disclaimer(
    supabase,
    auth_token: str,
    agreed: bool,
    ip_address: Optional[str],
    user_agent: Optional[str],
    request: Request,
    disclaimer_text: str,
) -> Dict[str, Any]:
    if not agreed:
        raise HTTPException(status_code=400, detail="면책 동의를 체크해 주세요.")
    auth_row = resolve_auth_log(supabase, auth_token)

    ip = ip_address or (request.client.host if request.client else None)
    ua = user_agent or request.headers.get("user-agent", "")

    res = (
        supabase.table("diagnosis_disclaimer_log")
        .insert(
            {
                "ci_hash": auth_row["ci_hash"],
                "auth_log_id": auth_row["id"],
                "disclaimer_text": disclaimer_text,
                "agreed": True,
                "ip_address": ip,
                "user_agent": ua[:500] if ua else None,
            }
        )
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="동의 저장에 실패했습니다.")

    return {
        "status": "success",
        "disclaimer_log_id": res.data[0]["id"],
        "agreed_at": res.data[0].get("agreed_at"),
        "disclaimer_text": disclaimer_text,
    }


def _bind_linked_user_id(supabase, auth_row: dict, current_user: Optional[dict], now_iso: str) -> None:
    """유료 성공 시 diagnosis_auth_log.linked_user_id 바인딩. 다른 유저 연결이면 403."""
    if not current_user:
        return
    uid = current_user.get("id")
    if not uid:
        return
    existing = auth_row.get("linked_user_id")
    if existing:
        if str(existing) != str(uid):
            raise HTTPException(status_code=403, detail="이미 다른 계정에 연결된 인증입니다.")
        return
    supabase.table("diagnosis_auth_log").update(
        {"linked_user_id": uid, "updated_at": now_iso}
    ).eq("id", auth_row["id"]).execute()


def _assert_linkable(auth_row: dict, current_user: dict) -> None:
    existing = auth_row.get("linked_user_id")
    uid = current_user.get("id")
    if existing and uid and str(existing) != str(uid):
        raise HTTPException(status_code=403, detail="이미 다른 계정에 연결된 인증입니다.")


def run_diagnosis(
    supabase,
    body,
    run_step1_func: Callable[[Any, DiagnoseStep1Body], Dict[str, Any]],
    auto_tier_func: Callable[[str, float, float, Optional[str]], str],
    build_partial_func: Callable[[dict], dict],
    now_func: Callable[[], str],
    paid_tier_prices: Dict[str, int],
    free_tier_codes,
    engine_version: str,
    current_user: Optional[dict] = None,
    canonical_step1_factory_func: Optional[Callable[[Any], DiagnoseStep1Body]] = None,
) -> Dict[str, Any]:
    # WO-006: 인증 결정. explicit body.auth_token 우선(기존 무료/legacy 경로 보존).
    # member fallback 은 유료 진입(payment_ref 존재) 에서만 연다 — auth_token 없는 무료 회원이
    # member resolver 로 FREE 진단에 진입하는 경로를 차단(CORRECTION-02 BREAK-1: paid-only gate).
    if (getattr(body, "auth_token", None) or "").strip():
        auth_row = resolve_auth_log(supabase, body.auth_token)
    elif current_user and (getattr(body, "payment_ref", None) or "").strip():
        auth_row = resolve_member_auth_log(supabase, current_user)
    else:
        raise HTTPException(status_code=401, detail="인증이 필요합니다. 본인인증 후 이용해 주세요.")
    disclaimer_log_id = (body.disclaimer_log_id or "").strip()
    if not disclaimer_log_id:
        if body.payment_ref:
            disclaimer_log_id = _ensure_disclaimer_for_paid_entry(supabase, auth_row)
        else:
            raise HTTPException(status_code=400, detail="면책 동의가 필요합니다.")
    else:
        disc_res = (
            supabase.table("diagnosis_disclaimer_log")
            .select("id, ci_hash, agreed")
            .eq("id", disclaimer_log_id)
            .eq("ci_hash", auth_row["ci_hash"])
            .limit(1)
            .execute()
        )
        if not disc_res.data or not disc_res.data[0].get("agreed"):
            raise HTTPException(status_code=400, detail="면책 동의가 필요합니다.")

    sector = normalize_sector_db(body.sector)
    engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector

    _fd = getattr(body, "form_data", None) or {}

    def _fd_num(_key, _cast):
        _v = _fd.get(_key)
        if _v is None or _v == "":
            return None
        try:
            return _cast(float(_v))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="'{}' 값이 올바른 숫자가 아닙니다: {!r}".format(_key, _v))

    _is_construction = (engine_sector == "CONSTRUCTION")

    _contract_eok = body.contract_amount_eok
    if _contract_eok is None:
        if _is_construction:
            _contract_eok = _fd_num("project_amount", float)
        if _contract_eok is None:
            _contract_eok = _fd_num("contract_amount_eok", float)
    if body.region:
        _region_val = body.region
    elif _is_construction and _fd.get("project_address"):
        _region_val = _fd.get("project_address")
    else:
        _region_val = _fd.get("region")
    _worker_count = body.worker_count
    if _worker_count is None:
        _worker_count = _fd_num("worker_count", int)
        if _worker_count is None:
            _worker_count = _fd_num("workers", int)
    _construction_type_val = body.construction_type or _fd.get("construction_type")
    _ksic_major_val = body.ksic_major or _fd.get("ksic_major") or _fd.get("ksic_code")
    _process_list_val = body.process_list if body.process_list is not None else _fd.get("process_list")
    _equipment_list_val = body.equipment_list if body.equipment_list is not None else _fd.get("equipment_list")
    _ksic_list_val = body.ksic_list if body.ksic_list is not None else _fd.get("ksic_list")

    tier_code = auto_tier_func(
        sector,
        floor_area=body.floor_area or 0.0,
        contract_amount_eok=_contract_eok or 0.0,
        user_tier=body.user_tier,
    )
    if not body.payment_ref and tier_code not in free_tier_codes:
        _root = "INDUSTRY" if sector in ("INDUSTRIAL", "INDUSTRY") else sector
        _free_cand = "{}_FREE".format(_root)
        if _free_cand in free_tier_codes:
            tier_code = _free_cand
    is_free = tier_code in free_tier_codes

    if is_free:
        used = auth_row.get("free_count") or 0
        limit_cnt = auth_row.get("free_limit") or 3
        if used >= limit_cnt:
            raise HTTPException(status_code=402, detail=f"무료 진단 횟수({limit_cnt}회)를 모두 사용하셨습니다. 유료 진단을 이용해 주세요.")
    else:
        if current_user is None:
            raise HTTPException(status_code=401, detail="유료 진단은 회원가입 후 이용 가능합니다.")
        _assert_linkable(auth_row, current_user)
        if not body.payment_ref:
            price = paid_tier_prices.get(tier_code, 0)
            raise HTTPException(status_code=402, detail=f"유료 진단입니다. 결제 완료 후 payment_ref를 포함해 주세요. (가격: {price:,}원)")

    factory_id = (getattr(body, "factory_id", None) or "").strip() or None
    company_id = (getattr(body, "company_id", None) or "").strip() or None

    inp: dict = {"region": _region_val or "", "anonymous_flow": True, "tier_code": tier_code}
    if factory_id:
        inp["factory_id"] = factory_id
    if company_id:
        inp["company_id"] = company_id

    from services.canonical.materialization import canonical_applicability

    _available: dict = {f: getattr(body, f, None) for f in type(body).model_fields}
    _available.update(getattr(body, "form_data", None) or {})
    for _code, _val in canonical_applicability(_available).items():
        inp.setdefault(_code, _val)
    if _is_construction and not is_free and factory_id:
        from services.company_scope import _ensure_factory_own
        _ensure_factory_own(supabase, factory_id, current_user)
        _EQ_FACT = {"010": "has_emergency_gen", "014": "has_boiler", "023": "has_press",
                    "024": "has_conveyor", "038": "has_pressure_vessel"}
        try:
            _eq_res = (
                supabase.table("equipment_assets")
                .select("equipment_type_code")
                .eq("factory_id", factory_id)
                .eq("is_operating", True)
                .execute()
            )
        except Exception as _e:
            log.error("[equipment_materializer] source read failed factory=%s: %s", factory_id, _e)
            raise HTTPException(status_code=503, detail="설비 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        _eq_codes = {(_r.get("equipment_type_code") or "") for _r in (_eq_res.data or [])}
        for _c, _f in _EQ_FACT.items():
            if _c in _eq_codes:
                inp.setdefault(_f, True)
    if _worker_count is not None:
        workers = _worker_count
    elif body.direct_workers is not None:
        workers = body.direct_workers
    else:
        workers = 0
    employees = body.employee_count if body.employee_count is not None else workers
    floor_area = body.floor_area or 400.0
    total_floor_area = body.total_floor_area or floor_area
    contract_eok = _contract_eok if _contract_eok is not None else 1.0

    if canonical_step1_factory_func is not None and sector == "INDUSTRIAL":
        # GATE-2 Path A: WWW INDUSTRIAL LEG canonical path - legacy top-level default(400) bypass.
        step1_body = canonical_step1_factory_func(body)
    elif engine_sector == "CONSTRUCTION":
        _cst_fd = getattr(body, "form_data", None) or {}
        step1_body = DiagnoseStep1Body(
            factory_id=factory_id,
            sector=engine_sector,
            input=inp,
            construction_type=_construction_type_val or "건축",
            contract_amount_eok=float(contract_eok),
            worker_count=workers,
            direct_workers=body.direct_workers or workers,
            subcon_workers=body.subcon_workers or 0,
            has_chemical_substance=_cst_fd.get("has_chemical_substance"),
        )
    elif engine_sector == "BUILDING":
        # WP-1 BLOCKER-FIX: building_use_type/floor_count/total_floor_area 의 top-level default
        #   ('사무실'/5/400)를 제거한다. 이 default 는 build_facility precedence(top-level>input)로
        #   inp(canonical, 사용자 form_data 값)를 덮어써 사용자 입력이 유실되고 오판정을 유발했다.
        #   3축 모두 _LEG_INPUT_FIELDS 이므로 top-level 미지정 시 build_facility 가 inp(사용자값)를
        #   사용하며, 사용자 미입력이면 None → facility 미포함(None != 기본값 발명 금지).
        #   B5: elevator_count 는 canonical 미통과(_LEG_INPUT_FIELDS 밖)이므로 form_data 원본에서
        #   직접 전달해야 has_building_elevator 파생(elevator_count>0)이 실행된다.
        _bld_fd = getattr(body, "form_data", None) or {}
        _bld_elev = body.elevator_count
        if _bld_elev is None:
            _bld_elev = _bld_fd.get("elevator_count")
        step1_body = DiagnoseStep1Body(
            factory_id=factory_id,
            sector=engine_sector,
            input=inp,
            floor_area=float(floor_area),
            worker_count=workers,
            employee_count=employees,
            electric_capacity=body.electric_capacity,
            elevator_count=_bld_elev,
            has_high_pressure_gas=body.has_gas if body.has_gas is not None else None,
            has_hazardous_material=body.has_chemical if body.has_chemical is not None else None,
        )
    else:
        step1_body = DiagnoseStep1Body(
            factory_id=factory_id,
            sector=engine_sector,
            input=inp,
            worker_count=workers,
            employee_count=employees,
            floor_area=float(floor_area),
            total_floor_area=float(total_floor_area),
            ksic_major=_ksic_major_val or "",
            electric_capacity=body.electric_capacity,
            has_boiler=body.has_boiler,
            has_hazardous_material=body.has_hazardous_material,
            has_high_pressure_gas=body.has_high_pressure_gas,
            has_chemical_substance=body.has_chemical_substance,
        )

    eng = run_step1_func(supabase, step1_body)
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="진단 실행에 실패했습니다.")

    full_result = eng["data"]
    public_token = str(uuid.uuid4())
    expires_at = None
    if is_free:
        expires_at = (now_kst() + timedelta(days=7)).isoformat()

    # WP1-HOTFIX-001: form_data(field_code envelope, 유료 정본 소비자입력)를 저장에 보존.
    #   이전엔 input/process/equipment/ksic 만 담아 upgrade round-trip 시 form_data 유실.
    _raw_structured_input = {
        _k: _v
        for _k, _v in {
            "input": body.input,
            "form_data": getattr(body, "form_data", None),
            "process_list": _process_list_val,
            "equipment_list": _equipment_list_val,
            "ksic_list": _ksic_list_val,
        }.items()
        if _v is not None
    }

    row = {
        "public_token": public_token,
        "input_data": {
            "sector": sector,
            "tier_code": tier_code,
            "floor_area": floor_area,
            "contract_amount_eok": contract_eok,
            "workers": workers,
            **({"factory_id": factory_id} if factory_id else {}),
            **({"company_id": company_id} if company_id else {}),
            **(
                {"raw_structured_input": _raw_structured_input}
                if _raw_structured_input
                else {}
            ),
        },
        "partial_result": build_partial_func(full_result),
        "full_result": full_result,
        "expires_at": expires_at,
        "status": "ACTIVE",
        "source_type": "free_diag" if is_free else "paid_diag",
        "engine_version": engine_version,
        "ci_hash": auth_row["ci_hash"],
        "auth_log_id": auth_row["id"],
        "disclaimer_log_id": disclaimer_log_id,
        "tier_code": tier_code,
        "paid_amount": 0 if is_free else paid_tier_prices.get(tier_code, 0),
        "payment_ref": body.payment_ref,
    }

    ins = supabase.table("anonymous_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="결과 저장에 실패했습니다.")
    created = ins.data[0]

    if is_free:
        supabase.table("diagnosis_auth_log").update(
            {
                "free_count": (auth_row.get("free_count") or 0) + 1,
                "last_free_at": now_func(),
                "updated_at": now_func(),
            }
        ).eq("id", auth_row["id"]).execute()

    remaining_after = 0
    if is_free:
        remaining_after = max(0, (auth_row.get("free_limit") or 3) - ((auth_row.get("free_count") or 0) + 1))
    else:
        _save_diagnosis_purchase(
            supabase,
            auth_log_id=auth_row["id"],
            public_token=created.get("public_token") or public_token,
            tier_code=tier_code,
            paid_amount=paid_tier_prices.get(tier_code, 0),
            payment_ref=body.payment_ref,
            invoice_requested=bool(getattr(body, "invoice_requested", False)),
            invoice_biz_no=(getattr(body, "invoice_biz_no", None) or None),
            invoice_email=(getattr(body, "invoice_email", None) or None),
        )
        _bind_linked_user_id(supabase, auth_row, current_user, now_func())

    return {
        "status": "success",
        "public_token": public_token,
        "diagnosis_id": str(created.get("id") or ""),
        "tier_code": tier_code,
        "is_free": is_free,
        "expires_at": expires_at,
        "free_remaining_after": remaining_after if is_free else None,
        "result": full_result,
    }


def upgrade_diagnosis(
    supabase,
    body,
    run_step1_func: Callable[[Any, DiagnoseStep1Body], Dict[str, Any]],
    build_partial_func: Callable[[dict], dict],
    paid_tier_prices: Dict[str, int],
    current_user: Optional[dict] = None,
    now_func: Optional[Callable[[], str]] = None,
) -> Dict[str, Any]:
    auth_row = resolve_auth_log(supabase, body.auth_token)
    if current_user is None:
        raise HTTPException(status_code=401, detail="유료 진단은 회원가입 후 이용 가능합니다.")
    _assert_linkable(auth_row, current_user)
    existing = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, ci_hash, tier_code, input_data, paid_amount, status")
        .eq("public_token", body.public_token)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    rec = existing.data[0]
    if rec["ci_hash"] != auth_row["ci_hash"]:
        raise HTTPException(status_code=403, detail="자신의 진단만 업그레이드할 수 있습니다.")

    current_tier = rec.get("tier_code") or ""
    target_tier = body.target_tier_code
    current_price = paid_tier_prices.get(current_tier, 0)
    target_price = paid_tier_prices.get(target_tier)

    if target_price is None:
        raise HTTPException(status_code=422, detail=f"업그레이드 불가 티어: {target_tier}")
    if target_price <= current_price:
        raise HTTPException(status_code=422, detail="더 높은 등급으로만 업그레이드 가능합니다.")

    diff_price = target_price - current_price
    log.info("[UPGRADE] %s → %s, diff=%d, payment_ref=%s", current_tier, target_tier, diff_price, body.payment_ref)

    input_data = rec.get("input_data") or {}
    inp = {"tier_code": target_tier, "anonymous_flow": True, "upgrade": True}
    # WP-1 BLOCKER-FIX: 티어 업그레이드 재진단도 최초 저장된 소비자 원본
    #   (raw_structured_input.input)을 canonical 로 재적용해 사용자 입력을 살린다.
    #   (기존엔 building_use_type/floor_count 를 '사무실'/5 로 하드코딩해 원본을 유실).
    # WP1-HOTFIX-001: upgrade canonical source = form_data(유료 정본) 우선, 없으면 input.
    #   최초 저장이 form_data 를 보존하므로 유료 BUILDING 소비자입력이 round-trip 된다.
    _rsi_all = input_data.get("raw_structured_input") or {}
    # WP1-CORRECTION-002: form_data(유료 정본 canonical envelope)만 upgrade canonical source.
    #   RAW input 은 canonical 승격 금지(RAW→CANONICAL FIREWALL). form_data 키가 있으면
    #   그 값(빈 dict 포함)만 쓰고, 없으면 빈 dict — RAW input fallback 하지 않는다.
    if "form_data" in _rsi_all:
        _rsi = _rsi_all.get("form_data") or {}
    else:
        _rsi = {}
    if isinstance(_rsi, dict) and _rsi:
        from services.canonical.materialization import canonical_applicability
        for _c, _v in canonical_applicability(_rsi).items():
            inp.setdefault(_c, _v)
    sector = normalize_sector_db(str(input_data.get("sector") or ""))
    engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector
    workers = int(input_data.get("workers") or 0)
    floor_area = float(input_data.get("floor_area") or 400.0)
    contract_eok = float(input_data.get("contract_amount_eok") or 1.0)

    if engine_sector == "CONSTRUCTION":
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            construction_type="건축",
            contract_amount_eok=contract_eok,
            direct_workers=workers,
            subcon_workers=0,
        )
    elif engine_sector == "BUILDING":
        # WP-1 BLOCKER-FIX: building_use_type/floor_count/total_floor_area 하드코딩 default
        #   ('사무실'/5/floor_area) 제거. inp(canonical 재적용, 사용자 원본)를 사용한다.
        #   B5: elevator_count 는 canonical 밖이므로 raw_structured_input.input 에서 직접 전달.
        _up_elev = _rsi.get("elevator_count") if isinstance(_rsi, dict) else None
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            floor_area=floor_area,
            worker_count=workers,
            employee_count=workers,
            elevator_count=_up_elev,
        )
    else:
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            worker_count=workers,
            employee_count=workers,
            floor_area=floor_area,
            total_floor_area=floor_area,
            ksic_major="",
        )

    eng = run_step1_func(supabase, step1_body)
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="엔진 재실행에 실패했습니다.")

    new_full = eng["data"]
    supabase.table("anonymous_diagnosis_results").update(
        {
            "full_result": new_full,
            "partial_result": build_partial_func(new_full),
            "tier_code": target_tier,
            "paid_amount": int(rec.get("paid_amount") or 0) + diff_price,
            "payment_ref": body.payment_ref,
            "status": "ACTIVE",
            "expires_at": None,
        }
    ).eq("id", rec["id"]).execute()

    _save_diagnosis_purchase(
        supabase,
        auth_log_id=auth_row["id"],
        public_token=body.public_token,
        tier_code=target_tier,
        paid_amount=diff_price,
        payment_ref=body.payment_ref,
        invoice_requested=bool(getattr(body, "invoice_requested", False)),
        invoice_biz_no=(getattr(body, "invoice_biz_no", None) or None),
        invoice_email=(getattr(body, "invoice_email", None) or None),
    )
    _bind_linked_user_id(
        supabase,
        auth_row,
        current_user,
        (now_func or (lambda: serialize_external_utc(now_kst())))(),
    )

    return {
        "status": "success",
        "public_token": body.public_token,
        "prev_tier": current_tier,
        "new_tier": target_tier,
        "diff_paid_krw": diff_price,
        "result": new_full,
    }
