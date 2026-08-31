"""tests/test_paid_result_contract_v1.py — STEP3B-A B1~B12 · STEP3B-A.1 P0~P20 · STEP4C-2 P21~P28c.

대상: services.paid_result_contract_svc.build_paid_result_contract_v1

fixture 는 저장된 row shape 기준(public.anonymous_diagnosis_results).
DB 접근 없음. 네트워크 없음. 시간 의존 없음. 공개 endpoint 무접촉.
"""
import copy
import json
import pathlib

from services.paid_result_contract_svc import build_paid_result_contract_v1
from services.paid_result_materializer import build_paid_result_materials_v1


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# fixture — 저장된 row shape 를 그대로 흉내낸다.
# ─────────────────────────────────────────────────────────────────────────────

def _obligation(law_name="산업안전보건기준에 관한 규칙", law_article="19",
                obligation_type="ACTION", content_type="OBLIGATION",
                check_result="VERIFIED", what="안전조치를 한다", who="사업주",
                when=None, condition=None, triggered_by=None, atom_id="atom-1"):
    detail = {"what": what, "who": who}
    if when is not None:
        detail["when"] = when
    if condition is not None:
        detail["condition"] = condition
    out = {
        "atom_id": atom_id,
        "source_atom_ids": [atom_id],
        "mapped_field": ",".join(triggered_by or []),
        "law_name": law_name,
        "law_article": law_article,
        "evidence": "사업주는 ... 하여야 한다.",
        "applicability": "APPLICABLE",
        "triggered_by": triggered_by if triggered_by is not None else [],
        "obligation_detail": detail,
        "enrichment": {
            "usable_for_evaluation": True,
            "completeness": "COMPLETE",
            "missing_fields": [],
            "needs_numeric_condition": None,
            "consumer_status": "applicable",
            "content_type": content_type,
            "obligation_type": obligation_type,
            "inspection_cycle": None,
        },
    }
    if check_result is not None:
        out["check_result"] = check_result
    return out


def _full_result(obligations=None, contract=None):
    out = {
        "engine_family": "LEG",
        "engine_version": "leg-runtime-v3",
        "rule_source": "leg-prod",
        "fallback_used": False,
        "leg_status": "OK",
        "leg_trace_id": "rtm-000000000000",
        "sector": "MANUFACTURING",
        "applicable_count": len(obligations or []),
        "key_obligations": [],
        "applicable_laws": [],
        "law_badges": [],
        "rules": [],
        "risk_level": None,
        "summary": None,
        "provenance": {"release_version": "SEMREPO-RC1-2026.07.20", "repository_size": 339},
        "obligations_raw": obligations if obligations is not None else [],
        "facility_used": {"worker_count": 45},
    }
    if contract is not None:
        out["contract"] = contract
    return out


_MISSING = object()


def _row(full_result=_MISSING, created_at="2026-08-28T14:17:15.585284+00:00",
         input_data=None, **overrides):
    """저장된 anonymous_diagnosis_results row 1건.

    full_result=None 은 "컬럼은 있으나 값이 null" 을 뜻하며 기본값으로 대체되지 않는다.
    """
    row = {
        "id": "6f2a1c94-0000-4000-8000-000000000001",
        "public_token": "0f1e2d3c-4b5a-4000-8000-000000000002",
        "tier_code": "INDUSTRY_V2",
        "status": "ACTIVE",
        "source_type": "paid_diag",
        "engine_version": "leg-runtime-v3",
        "paid_amount": 79000,
        "payment_ref": "oid-0001",
        "ci_hash": "hash",
        "auth_log_id": "auth-1",
        "disclaimer_log_id": "disc-1",
        "expires_at": None,
        "partial_result": {"message": "..."},
        "input_data": input_data if input_data is not None else {
            "sector": "INDUSTRIAL", "tier_code": "INDUSTRY_V2",
            "floor_area": 400.0, "contract_amount_eok": 1.0, "workers": 45,
        },
        "full_result": _full_result([_obligation()]) if full_result is _MISSING else full_result,
    }
    if created_at is not None:
        row["created_at"] = created_at
    row.update(overrides)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# B1 — 정상 stored row
# ─────────────────────────────────────────────────────────────────────────────

def test_b1_normal_row_produces_contract():
    out = build_paid_result_contract_v1(_row())

    assert set(out) == {
        "contract_version", "diagnosis", "diagnosis_profile", "paid_result_materials_v1",
    }
    assert out["contract_version"] == 1
    assert out["diagnosis_profile"]["profile_version"] == 1

    diagnosis = out["diagnosis"]
    assert set(diagnosis) == {
        "result_id", "public_token", "tier_code", "status", "diagnosed_at", "expires_at",
    }
    assert diagnosis["result_id"] == "6f2a1c94-0000-4000-8000-000000000001"
    assert diagnosis["public_token"] == "0f1e2d3c-4b5a-4000-8000-000000000002"
    assert diagnosis["tier_code"] == "INDUSTRY_V2"
    assert diagnosis["status"] == "ACTIVE"
    assert diagnosis["expires_at"] is None

    materials = out["paid_result_materials_v1"]
    assert materials["meta"]["material_version"] == 1
    assert materials["overview"]["total_obligation_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# B2 — Materializer 위임이 정확히 일치
# ─────────────────────────────────────────────────────────────────────────────

def test_b2_materials_are_exact_delegation():
    full_result = _full_result([
        _obligation(atom_id="a1", when="상시", triggered_by=["has_excavation"],
                    condition="굴착작업을 할 때"),
        _obligation(atom_id="a2", law_article="30", content_type="PROHIBITION",
                    obligation_type="PROHIBIT", check_result="NOT_APPLICABLE"),
    ], contract={"valid": True, "active_fields": ["worker_count"],
                 "missing_fields": ["total_floor_area"], "unknown_fields": [],
                 "invalid_fields": [], "accepted_count": 1})
    out = build_paid_result_contract_v1(_row(full_result=full_result))

    expected = build_paid_result_materials_v1(full_result)
    assert out["paid_result_materials_v1"] == expected
    assert json.dumps(out["paid_result_materials_v1"], ensure_ascii=False, sort_keys=True) == \
           json.dumps(expected, ensure_ascii=False, sort_keys=True)


# ─────────────────────────────────────────────────────────────────────────────
# B3 / B4 — created_at
# ─────────────────────────────────────────────────────────────────────────────

def test_b3_created_at_is_exact_passthrough():
    out = build_paid_result_contract_v1(_row(created_at="2026-08-09T00:26:15.852207+00:00"))
    assert out["diagnosis"]["diagnosed_at"] == "2026-08-09T00:26:15.852207+00:00"


def test_b4_missing_created_at_is_null_never_current_time():
    out = build_paid_result_contract_v1(_row(created_at=None))
    assert out["diagnosis"]["diagnosed_at"] is None

    # created_at 컬럼 자체가 없는 row 도 동일.
    row = _row()
    row.pop("created_at")
    assert build_paid_result_contract_v1(row)["diagnosis"]["diagnosed_at"] is None

    # 현재 시각 fallback 이 없다는 것을 두 번 호출로도 확인(시간 의존 0).
    a = build_paid_result_contract_v1(_row(created_at=None))
    b = build_paid_result_contract_v1(_row(created_at=None))
    assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# B5 / B6 — 회사정보 생성 금지 · raw input_data 미노출
#
# STEP3B-A.1 에서 의미가 바뀐 부분:
#   raw input_data 통째 pass-through   = 여전히 금지
#   whitelist diagnosis_profile        = 허용 (저장된 값이 있을 때만)
#   값 생성 · 추정 · 등급화             = 여전히 금지
# B6b 의 본질(허용목록 밖 필드는 절대 통과 0)은 그대로 유지한다.
# ─────────────────────────────────────────────────────────────────────────────

NEVER_CARRIED_COMPANY_FIELDS = ("business_no", "ceo_name")


def test_b5_company_data_is_never_invented():
    """저장돼 있지 않으면 만들지 않는다. key 는 있어도 값은 None 이다."""
    out = build_paid_result_contract_v1(_row())          # input_data 에 회사정보 없음
    profile = out["diagnosis_profile"]

    assert profile["company_name"] is None
    assert profile["address"] is None
    assert "company_name" not in profile["available_facts"]
    assert "address" not in profile["available_facts"]

    flat = json.dumps(out, ensure_ascii=False)
    for field in NEVER_CARRIED_COMPANY_FIELDS:
        assert field not in flat, field
    # 빈 문자열/추정 라벨도 없다.
    for label in ("고객 사업장", "사업장명", "OO회사", "(주)"):
        assert label not in flat, label


def test_b6_raw_input_data_is_not_passed_through_even_when_populated():
    """허용목록 밖 key 는 값이 저장돼 있어도 계약에 나타나지 않는다."""
    row = _row(input_data={
        "sector": "INDUSTRIAL",
        "company_name": "(주)테스트",
        "business_no": "123-45-67890",
        "ceo_name": "홍길동",
        "workers": 45,
        "factory_id": "FCT-0001",
        "company_id": "CMP-0001",
        "claimed_user_id": "USR-0001",
        "scale": "medium",
        "region": "서울특별시 테스트구 검증로 1",
        "raw_structured_input": {"anything": "at all"},
    })
    out = build_paid_result_contract_v1(row)

    # raw 컨테이너 자체가 어디에도 없다.
    assert "input_data" not in out
    assert "input_data" not in out["diagnosis"]
    assert "input_data" not in out["diagnosis_profile"]

    flat = json.dumps(out, ensure_ascii=False)
    for value in ("123-45-67890", "홍길동", "FCT-0001", "CMP-0001", "USR-0001",
                  "medium", "서울특별시 테스트구 검증로 1", "at all"):
        assert value not in flat, value
    for field in ("business_no", "ceo_name", "factory_id", "company_id",
                  "claimed_user_id", "scale", "region", "raw_structured_input"):
        assert field not in flat, field

    # 허용된 값은 그대로 실린다.
    assert out["diagnosis_profile"]["company_name"] == "(주)테스트"
    assert out["diagnosis_profile"]["sector"] == "INDUSTRIAL"
    assert out["diagnosis_profile"]["workers"] == 45


def test_b6b_other_row_columns_are_not_carried():
    out = build_paid_result_contract_v1(_row())
    flat = json.dumps(out, ensure_ascii=False)
    for column in ("payment_ref", "ci_hash", "auth_log_id", "disclaimer_log_id",
                   "paid_amount", "partial_result", "source_type"):
        assert column not in flat, column


# ─────────────────────────────────────────────────────────────────────────────
# B7 / B8 — determinism · mutation
# ─────────────────────────────────────────────────────────────────────────────

def test_b7_deterministic_output():
    row = _row(full_result=_full_result([
        _obligation(atom_id="a1"), _obligation(atom_id="a2", law_name="건축법", law_article="41"),
    ]))
    first = build_paid_result_contract_v1(row)
    second = build_paid_result_contract_v1(copy.deepcopy(row))
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
           json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_b8_input_row_is_not_mutated():
    row = _row(full_result=_full_result([_obligation(when="상시")]))
    before = copy.deepcopy(row)
    build_paid_result_contract_v1(row)
    assert row == before


def test_b8b_output_mutation_does_not_reach_input_row():
    row = _row()
    out = build_paid_result_contract_v1(row)
    out["paid_result_materials_v1"]["normalized_obligations"][0]["legal"]["law_name"] = "CHANGED"
    out["diagnosis"]["tier_code"] = "CHANGED"
    assert row["full_result"]["obligations_raw"][0]["law_name"] == "산업안전보건기준에 관한 규칙"
    assert row["tier_code"] == "INDUSTRY_V2"


# ─────────────────────────────────────────────────────────────────────────────
# B9 — full_result 없음 / null
# ─────────────────────────────────────────────────────────────────────────────

def test_b9_missing_or_null_full_result_yields_empty_materials():
    for row in (_row(full_result=None),
                {k: v for k, v in _row().items() if k != "full_result"},
                {},
                None):
        out = build_paid_result_contract_v1(row)
        assert out["contract_version"] == 1
        assert set(out["diagnosis"]) == {
            "result_id", "public_token", "tier_code", "status", "diagnosed_at", "expires_at",
        }
        materials = out["paid_result_materials_v1"]
        assert materials["overview"]["total_obligation_count"] == 0
        assert materials["normalized_obligations"] == []
        assert materials["execution_seed"] == []

    # 빈 row 는 metadata 가 전부 None 이며 값을 만들지 않는다.
    empty = build_paid_result_contract_v1({})
    assert all(value is None for value in empty["diagnosis"].values())


# ─────────────────────────────────────────────────────────────────────────────
# B10 — R06 raw 상태 보존 · 법 적용 재해석 0
# ─────────────────────────────────────────────────────────────────────────────

def test_b10_r06_raw_state_survives_and_is_not_relabelled():
    full_result = _full_result([
        _obligation(atom_id="a1", check_result="VERIFIED"),
        _obligation(atom_id="a2", law_article="30", check_result="NOT_APPLICABLE"),
        _obligation(atom_id="a3", law_article="31", check_result="BLOCKED"),
    ])
    out = build_paid_result_contract_v1(_row(full_result=full_result))
    materials = out["paid_result_materials_v1"]

    # 원본 상태명이 그대로 살아 있다.
    states = [o["verification"]["check_result"] for o in materials["normalized_obligations"]]
    assert states == ["VERIFIED", "NOT_APPLICABLE", "BLOCKED"]
    assert materials["verification_summary"]["counts"] == {
        "BLOCKED": 1, "NOT_APPLICABLE": 1, "VERIFIED": 1,
    }

    # NOT_APPLICABLE 인 의무도 모수에서 빠지지 않는다(법 적용 재해석 0).
    assert materials["overview"]["total_obligation_count"] == 3
    assert len(materials["execution_seed"]) == 3

    # 한국어 상태 label 을 만들지 않는다.
    flat = json.dumps(out, ensure_ascii=False)
    for label in ("법령 근거 확인됨", "추가 검증 필요", "근거 정보 보류",
                  "구조 정보 확인 필요", "적용되지 않음", "비적용", "적용 대상 아님"):
        assert label not in flat, label


# ─────────────────────────────────────────────────────────────────────────────
# B11 — assembler 안에 파생 재계산 없음 · import surface 고정
# ─────────────────────────────────────────────────────────────────────────────

def test_b11_assembler_has_no_derivation_logic_and_fixed_imports():
    import ast
    import inspect

    import services.paid_result_contract_svc as mod

    src = inspect.getsource(mod)

    # docstring·주석은 "금지사항을 선언하는 텍스트"이므로 코드 스캔에서 제외한다.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body.pop(0)
    src_body = ast.unparse(tree)

    banned = (
        "datetime", "time.time", "random", "uuid",
        "requests.", "httpx.", "open(", "os.getenv", "os.environ",
        "get_supabase", "supabase", "sqlalchemy", "psycopg",
        # 파생 재계산 흔적
        "Counter", "groupby", "sha256", "hashlib", "unicodedata",
        "law_portfolio", "duplicate", "fingerprint", "timing_character",
        "obligations_raw",
    )
    for token in banned:
        assert token not in src_body, "forbidden token in assembler: {}".format(token)

    imported = set()
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imported.add(stripped.split()[1].split(".")[0])
        elif stripped.startswith("from ") and " import " in stripped:
            imported.add(stripped.split()[1])
    assert imported == {"__future__", "copy", "typing",
                        "services.paid_result_materializer"}, imported


def test_b11b_materializer_is_the_only_derivation_source():
    """assembler 출력의 재료 부분은 Materializer 결과와 완전히 동일해야 한다."""
    full_result = _full_result([
        _obligation(atom_id="a1", when="6개월마다"),
        _obligation(atom_id="a2"),
        _obligation(atom_id="a3"),
    ])
    out = build_paid_result_contract_v1(_row(full_result=full_result))
    assert out["paid_result_materials_v1"] == build_paid_result_materials_v1(full_result)

    # material_version 을 assembler 가 덮어쓰지 않는다.
    assert out["paid_result_materials_v1"]["meta"]["material_version"] == \
           build_paid_result_materials_v1(full_result)["meta"]["material_version"]


# ─────────────────────────────────────────────────────────────────────────────
# B12 — 공개 라우터 무변경 / 응답 delta 0
# ─────────────────────────────────────────────────────────────────────────────

def test_b12_public_paid_result_router_does_not_reference_new_layers():
    """GET /diagnosis/paid-result/{public_token} 는 이번 STEP 에서 무접촉이어야 한다.

    공개 응답에 Product Contract / Materializer 가 실리지 않았음을 소스로 고정한다.
    (ACCESS GATE 가 닫힌 뒤 STEP3B-B 에서 다룬다.)
    """
    reader = (REPO_ROOT / "routers" / "diagnosis_result_web.py").read_text(encoding="utf-8")
    for token in ("paid_result_contract_svc", "build_paid_result_contract_v1",
                  "paid_result_materializer", "build_paid_result_materials_v1",
                  "paid_result_materials_v1"):
        assert token not in reader, "public reader references {}".format(token)


def test_b12b_no_router_imports_the_new_layers():
    routers_dir = REPO_ROOT / "routers"
    hits = []
    for path in sorted(routers_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "paid_result_contract_svc" in text or "paid_result_materializer" in text:
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], hits


# ─────────────────────────────────────────────────────────────────────────────
# STEP3B-A.1 — PRODUCT CONTRACT v1.1 DIAGNOSIS PROFILE (P1~P20)
#
# 경계: profile 은 법적 판정이 아니다. 저장된 사업장 사실의 표현용 snapshot 이며
#       Materializer 입력으로 되돌아가지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_KEYS = {
    "profile_version",
    "company_name", "sector", "workers", "floor_area", "contract_amount_eok",
    "site_kind", "construction_type", "building_use_type", "address",
    # STEP4C-2 PKG-0 — presence fact 2개 (additive)
    "has_excavation", "has_hazardous_material",
    "available_facts",
}


def _profile(input_data=None, facility_used=_MISSING):
    """profile 만 보기 위한 얇은 helper."""
    full_result = _full_result([_obligation()])
    if facility_used is not _MISSING:
        if facility_used is None:
            full_result.pop("facility_used", None)
        else:
            full_result["facility_used"] = facility_used
    row = _row(full_result=full_result, input_data=input_data)
    return build_paid_result_contract_v1(row)["diagnosis_profile"]


def test_p0_profile_shape_is_fixed():
    """값이 없어도 key 는 항상 나온다 — diagnosis metadata 와 같은 style."""
    profile = _profile(input_data={}, facility_used=None)
    assert set(profile) == PROFILE_KEYS
    assert profile["profile_version"] == 1
    assert profile["available_facts"] == []
    for key in PROFILE_KEYS - {"profile_version", "available_facts"}:
        assert profile[key] is None, key


# P1 ── company_name exact pass-through
def test_p1_company_name_exact_passthrough():
    assert _profile({"company_name": "(주)태왕엔지니어링"})["company_name"] == "(주)태왕엔지니어링"
    # 앞뒤 공백만 정리한다. 내용은 손대지 않는다.
    assert _profile({"company_name": "  대한산업  "})["company_name"] == "대한산업"
    # 빈 문자열은 값이 아니다 — 대체 문구를 만들지 않는다.
    assert _profile({"company_name": "   "})["company_name"] is None
    assert _profile({})["company_name"] is None
    # factory_id / company_id 로 회사명을 조회하거나 합성하지 않는다.
    assert _profile({"factory_id": "FCT-1", "company_id": "CMP-1"})["company_name"] is None


# P2 ── sector exact pass-through
def test_p2_sector_exact_passthrough_input_only():
    assert _profile({"sector": "CONSTRUCTION"})["sector"] == "CONSTRUCTION"

    # full_result.sector 로 대체하지 않는다.
    # 실데이터에 input INDUSTRIAL -> full_result MANUFACTURING 인 row 가 존재하므로
    # 두 어휘는 동일하지 않다. profile 은 "고객이 제공한 사실" 을 그대로 유지한다.
    profile = _profile({"sector": "INDUSTRIAL"})
    assert profile["sector"] == "INDUSTRIAL"

    row = _row(full_result=_full_result([_obligation()]), input_data={})
    assert row["full_result"]["sector"] == "MANUFACTURING"
    assert build_paid_result_contract_v1(row)["diagnosis_profile"]["sector"] is None


# P3 ── workers source priority
def test_p3_workers_source_priority():
    # 1순위 input_data.workers
    assert _profile({"workers": 86, "worker_count": 12},
                    facility_used={"worker_count": 999})["workers"] == 86
    # 2순위 input_data.worker_count
    assert _profile({"worker_count": 12},
                    facility_used={"worker_count": 999})["workers"] == 12
    # 3순위 facility_used.worker_count
    assert _profile({}, facility_used={"worker_count": 999})["workers"] == 999
    # 아무데도 없으면 None
    assert _profile({}, facility_used=None)["workers"] is None
    # 등급 라벨로 바꾸지 않는다.
    flat = json.dumps(_profile({"workers": 86}), ensure_ascii=False)
    for label in ("중규모", "대규모", "소규모", "중소", "대형", "소형"):
        assert label not in flat, label


# P4 ── floor_area source priority
def test_p4_floor_area_source_priority():
    assert _profile({"floor_area": 12400.0},
                    facility_used={"total_floor_area": 999.0})["floor_area"] == 12400.0
    assert _profile({}, facility_used={"total_floor_area": 999.0})["floor_area"] == 999.0
    assert _profile({}, facility_used=None)["floor_area"] is None
    # 실제로 0 이 저장된 row 가 있다. 0 은 값이며 "없음" 으로 바꾸지 않는다.
    profile = _profile({"floor_area": 0})
    assert profile["floor_area"] == 0
    assert "floor_area" in profile["available_facts"]


# P5 ── contract_amount exact
def test_p5_contract_amount_exact():
    profile = _profile({"contract_amount_eok": 53.0})
    assert profile["contract_amount_eok"] == 53.0
    flat = json.dumps(profile, ensure_ascii=False)
    for label in ("고액", "대형 공사", "소액", "억원 규모"):
        assert label not in flat, label
    assert _profile({})["contract_amount_eok"] is None


# P6 ── construction_type / building_use_type exact
def test_p6_facility_types_exact():
    profile = _profile({}, facility_used={"construction_type": "건축",
                                          "building_use_type": "사무실"})
    assert profile["construction_type"] == "건축"
    assert profile["building_use_type"] == "사무실"
    # input_data 쪽에 같은 이름이 있어도 facility_used 가 유일 source 다.
    profile = _profile({"construction_type": "토목", "building_use_type": "공장"},
                       facility_used={})
    assert profile["construction_type"] is None
    assert profile["building_use_type"] is None


# P7 ── address exact only
def test_p7_address_exact_only_and_never_synthesized():
    assert _profile({"address": "경기도 화성시"})["address"] == "경기도 화성시"
    # region 은 주소처럼 생긴 값이 저장돼 있어도 address 로 승격하지 않는다.
    profile = _profile({"region": "서울특별시 테스트구 검증로 CONV2-01895",
                        "sector": "CONSTRUCTION"})
    assert profile["address"] is None
    assert "서울특별시 테스트구 검증로 CONV2-01895" not in json.dumps(profile, ensure_ascii=False)
    # facility / 다른 값으로 주소를 합성하지 않는다.
    assert _profile({}, facility_used={"building_use_type": "사무실"})["address"] is None


# P8 ── missing field invention 0
def test_p8_missing_fields_are_never_invented():
    profile = _profile({"sector": "BUILDING"}, facility_used=None)
    assert profile["sector"] == "BUILDING"
    for key in ("company_name", "workers", "floor_area", "contract_amount_eok",
                "site_kind", "construction_type", "building_use_type", "address"):
        assert profile[key] is None, key
    flat = json.dumps(profile, ensure_ascii=False)
    for filler in ("미상", "정보 없음", "확인 필요", "N/A", "해당 없음", "-"):
        assert filler not in flat, filler


# P9 / P10 ── factory_id · company_id absent
def test_p9_p10_identifiers_absent_from_profile():
    profile = _profile({
        "factory_id": "FCT-0001", "company_id": "CMP-0001",
        "claimed_user_id": "USR-1", "auth_log_id": "AUTH-1",
        "payment_ref": "oid-1", "ci_hash": "hash-1",
        "sector": "MANUFACTURING",
    })
    flat = json.dumps(profile, ensure_ascii=False)
    for token in ("factory_id", "company_id", "claimed_user_id", "auth_log_id",
                  "payment_ref", "ci_hash",
                  "FCT-0001", "CMP-0001", "USR-1", "AUTH-1", "oid-1", "hash-1"):
        assert token not in flat, token
    assert set(profile) == PROFILE_KEYS
    # public_token 은 diagnosis metadata 에만 있고 profile 에는 없다.
    out = build_paid_result_contract_v1(_row())
    assert "public_token" in out["diagnosis"]
    assert "public_token" not in out["diagnosis_profile"]


# P11 ── raw_structured_input absent
def test_p11_raw_structured_input_is_never_carried():
    profile = _profile({
        "raw_structured_input": {"workers": 86, "company_name": "(주)통째로"},
        "sector": "MANUFACTURING",
    })
    flat = json.dumps(profile, ensure_ascii=False)
    assert "raw_structured_input" not in flat
    assert "(주)통째로" not in flat
    # 허용된 key 라도 값이 구조체이면 통과시키지 않는다.
    nested = _profile({"company_name": {"legal": "(주)중첩"}, "workers": [1, 2, 3]},
                      facility_used=None)
    assert nested["company_name"] is None
    assert nested["workers"] is None
    assert "(주)중첩" not in json.dumps(nested, ensure_ascii=False)
    # 구조체는 "값 없음" 으로 취급되므로 다음 source 로 넘어간다(생성이 아니라 우선순위).
    fell_through = _profile({"workers": [1, 2, 3]}, facility_used={"worker_count": 45})
    assert fell_through["workers"] == 45


# P12 ── input_data raw object absent
def test_p12_input_data_container_absent_everywhere():
    out = build_paid_result_contract_v1(_row(input_data={
        "sector": "CONSTRUCTION", "workers": 708, "unexpected_new_field": "X-9999",
    }))
    assert "input_data" not in out
    assert "input_data" not in out["diagnosis"]
    assert "input_data" not in out["diagnosis_profile"]
    flat = json.dumps(out, ensure_ascii=False)
    assert "unexpected_new_field" not in flat
    assert "X-9999" not in flat
    # whitelist 밖의 새 key 가 나중에 추가돼도 자동으로 새어 나가지 않는다.
    assert set(out["diagnosis_profile"]) == PROFILE_KEYS


# P13 / P14 ── scale · region absent
def test_p13_p14_scale_and_region_are_excluded():
    profile = _profile({
        "scale": "large", "region": "전남", "sector": "SPECIAL_FACILITY", "workers": 300,
    })
    flat = json.dumps(profile, ensure_ascii=False)
    for token in ("scale", "region", "large", "전남"):
        assert token not in flat, token
    assert profile["sector"] == "SPECIAL_FACILITY"
    assert profile["workers"] == 300
    assert profile["available_facts"] == ["sector", "workers"]


# P15 ── available_facts exact / deterministic
def test_p15_available_facts_is_exact_and_deterministic():
    profile = _profile(
        {"company_name": "(주)태왕", "sector": "CONSTRUCTION", "workers": 86,
         "contract_amount_eok": 53.0, "address": "경기도 화성시",
         "scale": "medium", "region": "경기"},
        facility_used={"total_floor_area": 12400.0, "construction_type": "건축"},
    )
    # 선언 순서 그대로. raw input inventory 가 아니라 실제 값이 있는 필드 key 만.
    assert profile["available_facts"] == [
        "company_name", "sector", "workers", "floor_area",
        "contract_amount_eok", "construction_type", "address",
    ]
    for field in profile["available_facts"]:
        assert profile[field] is not None, field
    for field in ("site_kind", "building_use_type"):
        assert field not in profile["available_facts"]

    # 빈 profile
    assert _profile({}, facility_used=None)["available_facts"] == []

    # 두 번 호출해도 동일
    assert _profile({"sector": "BUILDING"})["available_facts"] == \
           _profile({"sector": "BUILDING"})["available_facts"]


# P16 ── profile does not change Materializer result
def test_p16_profile_does_not_change_materializer_result():
    full_result = _full_result([
        _obligation(atom_id="a1", when="상시", triggered_by=["has_excavation"]),
        _obligation(atom_id="a2", law_name="건축법", law_article="41",
                    content_type="PROHIBITION", obligation_type="PROHIBIT"),
    ])
    expected = build_paid_result_materials_v1(full_result)

    rich = build_paid_result_contract_v1(_row(full_result=copy.deepcopy(full_result), input_data={
        "company_name": "(주)태왕", "sector": "CONSTRUCTION", "workers": 86,
        "floor_area": 12400.0, "contract_amount_eok": 53.0, "address": "경기도 화성시",
    }))
    bare = build_paid_result_contract_v1(_row(full_result=copy.deepcopy(full_result),
                                              input_data={}))

    assert rich["paid_result_materials_v1"] == expected
    assert bare["paid_result_materials_v1"] == expected
    assert rich["paid_result_materials_v1"] == bare["paid_result_materials_v1"]
    # profile 값이 법적 재료 안으로 흘러 들어가지 않는다.
    materials_flat = json.dumps(rich["paid_result_materials_v1"], ensure_ascii=False)
    for value in ("(주)태왕", "경기도 화성시", "12400", "53.0"):
        assert value not in materials_flat, value


# P17 ── same row same contract
def test_p17_same_row_same_contract():
    row = _row(input_data={"company_name": "(주)태왕", "sector": "CONSTRUCTION",
                           "workers": 86, "floor_area": 0})
    first = build_paid_result_contract_v1(row)
    second = build_paid_result_contract_v1(copy.deepcopy(row))
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
           json.dumps(second, ensure_ascii=False, sort_keys=True)


# P18 ── input mutation 0
def test_p18_profile_build_does_not_mutate_input_row():
    row = _row(input_data={"company_name": "  (주)태왕  ", "sector": "CONSTRUCTION",
                           "workers": 86, "scale": "medium"})
    before = copy.deepcopy(row)
    out = build_paid_result_contract_v1(row)
    assert row == before
    # trim 은 출력에만 적용된다.
    assert row["input_data"]["company_name"] == "  (주)태왕  "
    assert out["diagnosis_profile"]["company_name"] == "(주)태왕"
    # 출력 변형이 입력으로 되돌아가지 않는다.
    out["diagnosis_profile"]["company_name"] = "CHANGED"
    out["diagnosis_profile"]["available_facts"].append("CHANGED")
    assert row["input_data"]["company_name"] == "  (주)태왕  "
    assert row == before


# P19 ── existing diagnosis metadata unchanged
def test_p19_existing_contract_surface_is_unchanged():
    row = _row(input_data={"company_name": "(주)태왕", "workers": 86})
    out = build_paid_result_contract_v1(row)

    assert out["contract_version"] == 1
    assert set(out["diagnosis"]) == {
        "result_id", "public_token", "tier_code", "status", "diagnosed_at", "expires_at",
    }
    assert out["diagnosis"]["result_id"] == "6f2a1c94-0000-4000-8000-000000000001"
    assert out["diagnosis"]["tier_code"] == "INDUSTRY_V2"
    assert out["diagnosis"]["diagnosed_at"] == "2026-08-28T14:17:15.585284+00:00"
    assert out["paid_result_materials_v1"] == \
           build_paid_result_materials_v1(row["full_result"])

    # profile 이 없거나 비어도 기존 표면은 그대로다.
    for empty in (None, {}, _row(full_result=None, input_data={})):
        contract = build_paid_result_contract_v1(empty)
        assert contract["contract_version"] == 1
        assert set(contract["diagnosis"]) == {
            "result_id", "public_token", "tier_code", "status", "diagnosed_at", "expires_at",
        }
        assert contract["diagnosis_profile"]["profile_version"] == 1
        assert set(contract["diagnosis_profile"]) == PROFILE_KEYS


# P20 ── public router change 0
def test_p20_no_router_references_the_profile_layer():
    routers_dir = REPO_ROOT / "routers"
    hits = []
    for path in sorted(routers_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in ("diagnosis_profile", "paid_result_contract_svc",
                      "build_paid_result_contract_v1", "paid_result_materializer"):
            if token in text:
                hits.append("{}:{}".format(path.relative_to(REPO_ROOT), token))
    assert hits == [], hits

    reader = (REPO_ROOT / "routers" / "diagnosis_result_web.py").read_text(encoding="utf-8")
    assert "diagnosis_profile" not in reader


# ─────────────────────────────────────────────────────────────────────────────
# STEP4C-2 PKG-0 — PRODUCT CONTRACT PROFILE +2 (P21~P28)
#
# 경계: presence fact 는 저장된 값을 그대로 옮긴다.
#       true -> True · false -> False · 키 없음 -> None.
#       missing 을 False 로 만들지 않는다. 둘은 다른 사실이다.
#       source 는 facility_used 하나뿐이며 input_data fallback 은 없다.
# ─────────────────────────────────────────────────────────────────────────────

PRESENCE_FIELDS = ("has_excavation", "has_hazardous_material")


# P21 ── stored true 는 True 로 보존된다
def test_p21_presence_true_is_preserved():
    profile = _profile({}, facility_used={
        "has_excavation": True, "has_hazardous_material": True,
    })
    assert profile["has_excavation"] is True
    assert profile["has_hazardous_material"] is True
    # 1 / "true" 같은 다른 표현으로 바뀌지 않는다.
    for field in PRESENCE_FIELDS:
        assert isinstance(profile[field], bool), field


# P22 ── stored false 는 False 로 보존된다 (버리지 않는다)
def test_p22_presence_false_is_preserved_not_dropped():
    profile = _profile({}, facility_used={
        "has_excavation": False, "has_hazardous_material": False,
    })
    assert profile["has_excavation"] is False
    assert profile["has_hazardous_material"] is False
    # False 를 None 으로 접지 않는다. bool 타입 그대로여야 한다
    # (False == 0 이 참이므로 값 비교가 아니라 타입으로 확인한다).
    for field in PRESENCE_FIELDS:
        assert profile[field] is not None, field
        assert isinstance(profile[field], bool), field

    # true 와 false 가 섞여도 각각 보존된다.
    mixed = _profile({}, facility_used={
        "has_excavation": True, "has_hazardous_material": False,
    })
    assert mixed["has_excavation"] is True
    assert mixed["has_hazardous_material"] is False


# P23 ── key 가 없으면 None. False 를 만들어 넣지 않는다
def test_p23_missing_presence_key_is_none_never_false():
    profile = _profile({}, facility_used={"worker_count": 45})
    for field in PRESENCE_FIELDS:
        assert profile[field] is None, field
        assert profile[field] is not False, field
        assert field not in profile["available_facts"], field

    # facility_used 자체가 없는 row 도 같다.
    bare = _profile({}, facility_used=None)
    for field in PRESENCE_FIELDS:
        assert bare[field] is None, field
        assert field not in bare["available_facts"], field

    # 명시적 null 도 None 이며 False 가 되지 않는다.
    explicit_null = _profile({}, facility_used={
        "has_excavation": None, "has_hazardous_material": None,
    })
    for field in PRESENCE_FIELDS:
        assert explicit_null[field] is None, field
        assert field not in explicit_null["available_facts"], field


# P24 ── true 는 available_facts 에 들어간다
def test_p24_true_presence_is_in_available_facts():
    profile = _profile({}, facility_used={
        "has_excavation": True, "has_hazardous_material": True,
    })
    assert "has_excavation" in profile["available_facts"]
    assert "has_hazardous_material" in profile["available_facts"]
    # 선언 순서 그대로 — 두 필드는 address 뒤에 온다.
    assert profile["available_facts"] == ["has_excavation", "has_hazardous_material"]


# P25 ── false 도 available_facts 에 들어간다 (값이 있었으므로)
def test_p25_false_presence_is_in_available_facts():
    """available_facts 의 기준은 '값이 있었는가' 이지 '참인가' 가 아니다.

    truthiness 로 판정하면 저장된 False 가 사라진다.
    """
    profile = _profile({}, facility_used={
        "has_excavation": False, "has_hazardous_material": False,
    })
    assert profile["available_facts"] == ["has_excavation", "has_hazardous_material"]

    mixed = _profile({}, facility_used={
        "has_excavation": True, "has_hazardous_material": False,
    })
    assert mixed["available_facts"] == ["has_excavation", "has_hazardous_material"]

    # 0 도 같은 규칙이다 — 기존 숫자 필드에서 이미 지켜지던 원칙.
    zero = _profile({"workers": 0}, facility_used=None)
    assert zero["workers"] == 0
    assert "workers" in zero["available_facts"]


# P26 ── source 는 facility_used 뿐. input_data fallback = 0
def test_p26_presence_source_is_facility_used_only():
    """input_data 에 같은 key 가 있어도 읽지 않는다."""
    profile = _profile(
        {"has_excavation": True, "has_hazardous_material": True},
        facility_used={"worker_count": 45},
    )
    for field in PRESENCE_FIELDS:
        assert profile[field] is None, field
        assert field not in profile["available_facts"], field

    # facility_used 가 False 이고 input_data 가 True 여도 facility_used 가 이긴다.
    conflict = _profile(
        {"has_excavation": True},
        facility_used={"has_excavation": False},
    )
    assert conflict["has_excavation"] is False

    # 다른 필드로부터 추론하지 않는다: sector CONSTRUCTION 이라고 굴착이 되지 않는다.
    inferred = _profile({"sector": "CONSTRUCTION"}, facility_used={"construction_type": "건축"})
    assert inferred["has_excavation"] is None
    assert inferred["has_hazardous_material"] is None


# P27 ── non-scalar 는 통과하지 않는다
def test_p27_non_scalar_presence_value_is_rejected():
    profile = _profile({}, facility_used={
        "has_excavation": {"value": True},
        "has_hazardous_material": [True],
    })
    for field in PRESENCE_FIELDS:
        assert profile[field] is None, field
        assert field not in profile["available_facts"], field

    # 구조가 profile 로 새어 나가지 않는다.
    flat = json.dumps(profile, ensure_ascii=False)
    assert "value" not in flat


# P28 ── profile +2 이후에도 Materializer exact delegation 은 그대로
def test_p28_presence_fields_do_not_reach_legal_material():
    full_result = _full_result([
        _obligation(atom_id="a1", when="상시", triggered_by=["has_excavation"]),
        _obligation(atom_id="a2", law_name="건축법", law_article="41",
                    content_type="PROHIBITION", obligation_type="PROHIBIT"),
    ])
    full_result["facility_used"] = {
        "worker_count": 45, "has_excavation": True, "has_hazardous_material": False,
    }
    expected = build_paid_result_materials_v1(copy.deepcopy(full_result))

    contract = build_paid_result_contract_v1(
        _row(full_result=copy.deepcopy(full_result), input_data={"sector": "CONSTRUCTION"})
    )

    # 법적 재료는 profile 확장과 무관하게 동일하다.
    assert contract["paid_result_materials_v1"] == expected
    assert contract["diagnosis_profile"]["has_excavation"] is True
    assert contract["diagnosis_profile"]["has_hazardous_material"] is False

    # 계약 버전은 올리지 않는다 (미공개 v1 profile 의 additive 확장).
    assert contract["contract_version"] == 1
    assert contract["diagnosis_profile"]["profile_version"] == 1


# P28b ── 입력 row mutation 0 · 결정성 유지
def test_p28b_presence_extension_keeps_purity():
    facility = {"has_excavation": True, "has_hazardous_material": False}
    full_result = _full_result([_obligation()])
    full_result["facility_used"] = facility
    row = _row(full_result=full_result, input_data={"sector": "CONSTRUCTION"})
    snapshot = copy.deepcopy(row)

    first = build_paid_result_contract_v1(row)
    second = build_paid_result_contract_v1(row)

    assert row == snapshot                    # 입력 row 무변경
    assert first == second                    # 같은 row 이면 같은 출력
    assert first["diagnosis_profile"]["has_excavation"] is True
    assert first["diagnosis_profile"]["has_hazardous_material"] is False


# P28c ── 기존 9필드의 순서와 source priority 는 변하지 않았다
def test_p28c_existing_nine_fields_are_untouched():
    """확장은 append 다. 앞의 9개는 이름·순서·source 가 그대로여야 한다."""
    from services.paid_result_contract_svc import PROFILE_FIELDS

    assert PROFILE_FIELDS[:9] == (
        "company_name", "sector", "workers", "floor_area", "contract_amount_eok",
        "site_kind", "construction_type", "building_use_type", "address",
    )
    assert PROFILE_FIELDS[9:] == ("has_excavation", "has_hazardous_material")
    assert len(PROFILE_FIELDS) == 11

    # STEP3B-A.1 의 source priority 회귀 확인 (workers / floor_area).
    assert _profile({"workers": 7}, facility_used={"worker_count": 45})["workers"] == 7
    assert _profile({}, facility_used={"worker_count": 45})["workers"] == 45
    assert _profile({"floor_area": 400.0},
                    facility_used={"total_floor_area": 12400.0})["floor_area"] == 400.0
    assert _profile({}, facility_used={"total_floor_area": 12400.0})["floor_area"] == 12400.0

    # raw input_data passthrough 는 여전히 0 — presence key 를 넣어도 통과하지 않는다.
    leaky = _profile({"has_excavation": True, "raw_structured_input": {"x": 1}},
                     facility_used=None)
    assert set(leaky) == PROFILE_KEYS
    assert leaky["has_excavation"] is None
