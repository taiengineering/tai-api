from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request

from schemas.legal_engine import DiagnoseStep1Body
from services.legal_rules import normalize_sector_db

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
                "created_at": datetime.now(timezone.utc).isoformat(),
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
    now = datetime.now(timezone.utc).isoformat()

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
) -> Dict[str, Any]:
    auth_row = resolve_auth_log(supabase, body.auth_token)
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
    tier_code = auto_tier_func(
        sector,
        floor_area=body.floor_area or 0.0,
        contract_amount_eok=body.contract_amount_eok or 0.0,
        user_tier=body.user_tier,
    )
    # 무료 진단 정합: 결제 없는 요청은 무료 의도이므로 섹터별 무료 tier_code 로 확정한다.
    # 프론트가 tier="FREE" 로 신호하나 nexas 어댑터가 이를 소비하므로, 여기서는 payment_ref
    # 부재를 무료 의도로 본다(유료는 payment_ref 필수 → 영향 없음). tier_code 는 inp["tier_code"]
    # 로 엔진 scope 에도 반영되므로 코드 자체를 무료로 교정한다.
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

    inp: dict = {"region": body.region or "", "anonymous_flow": True, "tier_code": tier_code}
    if factory_id:
        inp["factory_id"] = factory_id
    if company_id:
        inp["company_id"] = company_id

    # Phase 1 lossless canonical materialization
    # (WO-GATE8-CANONICAL-LOSSLESS-MATERIALIZATION-IMPLEMENT-01):
    # consumer 가 실제 제공한 RTM-vocab applicability(선언 attr + 보존된 form_data)를
    # DiagnoseStep1Body.input 으로 손실 없이 전달한다. build_facility 가 input[code]
    # 로 사영하므로 스키마/매핑 확장 불요. alias/derivation/값 생성 없음.
    # setdefault 로 기존 inp 키(region/tier_code 등)는 덮어쓰지 않는다. FREE 경로 미영향.
    from services.canonical.materialization import canonical_applicability

    _available: dict = {f: getattr(body, f, None) for f in type(body).model_fields}
    _available.update(getattr(body, "form_data", None) or {})
    # WO-FE-CST-GAP-IMPL-001 FIX-B1: CONSTRUCTION 전용 CODE-C1(body.input→canonical 우회) 제거.
    # primary paid path(free-diagnosis runPaidDiagnosis)는 form_data 로 applicability 를 전달하므로
    # 위 _available.update(form_data) → canonical_applicability(_LEG_INPUT_FIELDS exact) 공통 배선으로
    # 10 fact 가 그대로 materialize 된다(중복 배선 제거). has_chemical_substance 는 FIX-B2 step1 bridge 로 처리.
    for _code, _val in canonical_applicability(_available).items():
        inp.setdefault(_code, _val)
    workers = body.worker_count or body.direct_workers or 0
    employees = body.employee_count or workers
    floor_area = body.floor_area or 400.0
    total_floor_area = body.total_floor_area or floor_area
    contract_eok = body.contract_amount_eok or 1.0

    if engine_sector == "CONSTRUCTION":
        # WO-FE-CST-GAP-IMPL-001 FIX-B2: CONSTRUCTION chemical step1 bridge.
        # has_chemical_substance 는 _LEG_INPUT_FIELDS 미등록(has_chemical + alias)이라 canonical 로는
        # inp 에 실리지 않는다. form_data.has_chemical_substance 를 step1_body 로 전달하면 build_facility 의
        # 기존 alias(_LEG_CODE_TO_CONSUMER: has_chemical→has_chemical_substance)가 facility[has_chemical] 을
        # 생성하고, CODE-C2(build_facility CONSTRUCTION rename)가 facility.has_chemical_substance 로 교정한다.
        # else(산업) 분기가 이미 쓰는 방식과 동일. 새 alias engine 없음.
        _cst_fd = getattr(body, "form_data", None) or {}
        step1_body = DiagnoseStep1Body(
            factory_id=factory_id,
            sector=engine_sector,
            input=inp,
            construction_type=body.construction_type or "건축",
            contract_amount_eok=float(contract_eok),
            worker_count=workers,
            direct_workers=body.direct_workers or workers,
            subcon_workers=body.subcon_workers or 0,
            has_chemical_substance=_cst_fd.get("has_chemical_substance"),
        )
    elif engine_sector == "BUILDING":
        step1_body = DiagnoseStep1Body(
            factory_id=factory_id,
            sector=engine_sector,
            input=inp,
            building_use_type=body.building_use_type or "사무실",
            floor_area=float(floor_area),
            total_floor_area=float(total_floor_area),
            worker_count=workers,
            employee_count=employees,
            floor_count=body.floor_count or 5,
            electric_capacity=body.electric_capacity,
            elevator_count=body.elevator_count,
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
            ksic_major=body.ksic_major or "",
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
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    # WO-FE-IND-GAP-051-TRANSPORT-001 (CORRECTION-01): raw envelope 은 `is not None` 기준으로만
    # 필터한다. {} / [] 는 "전송했고 0건" 이라는 사실값이므로 verbatim 보존(truthiness 로 버리지 않음).
    _raw_structured_input = {
        _k: _v
        for _k, _v in {
            "input": body.input,
            "process_list": body.process_list,
            "equipment_list": body.equipment_list,
            "ksic_list": body.ksic_list,
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
            # WO-FE-IND-GAP-051-TRANSPORT-001: paid RAW structured input 을 verbatim 보존.
            # RAW ENVELOPE 전용 — canonical_applicability/build_facility 로는 주입하지 않는다.
            # 보존 판정은 truthiness 가 아니라 `is not None` 기준이다(CORRECTION-01):
            #   None → 미보존 / {} 또는 [] → 그대로 보존(전송했고 0건이라는 사실 보존).
            #   comprehension 결과가 비면(=4개 모두 None) raw_structured_input 자체를 생략한다.
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
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            building_use_type="사무실",
            floor_area=floor_area,
            total_floor_area=floor_area,
            worker_count=workers,
            employee_count=workers,
            floor_count=5,
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
        (now_func or (lambda: datetime.now(timezone.utc).isoformat()))(),
    )

    return {
        "status": "success",
        "public_token": body.public_token,
        "prev_tier": current_tier,
        "new_tier": target_tier,
        "diff_paid_krw": diff_price,
        "result": new_full,
    }
