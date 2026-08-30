"""tests/test_paid_result_contract_v1.py — STEP3B-A B1~B12.

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

    assert set(out) == {"contract_version", "diagnosis", "paid_result_materials_v1"}
    assert out["contract_version"] == 1

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
# B5 / B6 — 회사정보 생성 금지 · input_data 미노출
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_FIELDS = ("company_name", "business_no", "ceo_name", "address")


def test_b5_company_data_is_never_invented():
    out = build_paid_result_contract_v1(_row())
    flat = json.dumps(out, ensure_ascii=False)
    for field in COMPANY_FIELDS:
        assert field not in flat, field
    # 빈 문자열/추정 라벨도 없다.
    assert "고객 사업장" not in flat
    assert "사업장명" not in flat


def test_b6_input_data_is_not_passed_through_even_when_populated():
    row = _row(input_data={
        "sector": "INDUSTRIAL",
        "company_name": "(주)테스트",
        "business_no": "123-45-67890",
        "ceo_name": "홍길동",
        "address": "서울시 강남구",
        "workers": 45,
    })
    out = build_paid_result_contract_v1(row)

    assert "input_data" not in out
    assert "input_data" not in out["diagnosis"]
    flat = json.dumps(out, ensure_ascii=False)
    for value in ("(주)테스트", "123-45-67890", "홍길동", "서울시 강남구"):
        assert value not in flat, value
    for field in COMPANY_FIELDS:
        assert field not in flat, field


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
