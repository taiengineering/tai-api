"""WP-DOCUMENT-ARCH-05A — schema-based deterministic renderer contract tests.

repository root 기준 실행(pytest). 순수 함수 테스트이며 DB/네트워크 접근 없음.
"""

import json
import re

import pytest

from services import document_schema_renderer as r
from services.document_schema_renderer import (
    SchemaRenderError,
    build_render_artifacts,
)
from services.document_snapshot_integrity import compute_confirmed_snapshot_hash

SCHEMA_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DOC_ID = "11111111-1111-1111-1111-111111111111"
BY = "22222222-2222-2222-2222-222222222222"
CHK_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def schema(**over):
    s = {"id": SCHEMA_ID, "form_name": "안전관리자선임보고서", "status": "CANDIDATE"}
    s.update(over)
    return s


def field(fid, key, label, order, input_type="text", **over):
    f = {
        "id": fid,
        "form_schema_id": SCHEMA_ID,
        "field_key": key,
        "field_label": label,
        "input_type": input_type,
        "field_order": order,
        "required_status": "CANDIDATE_ONLY",
        "status": "CANDIDATE",
        "created_at": "2026-01-01T00:00:00Z",
    }
    f.update(over)
    return f


def checklist(cid=CHK_ID, text="추락방호조치 확인", order=1, **over):
    c = {
        "id": cid,
        "form_schema_id": SCHEMA_ID,
        "raw_text": text,
        "input_type": "PASS_FAIL",
        "item_order": order,
        "status": "APPROVED_BY_HUMAN",
        "created_at": "2026-01-01T00:00:00Z",
    }
    c.update(over)
    return c


FIELDS = [
    field("f1", "company_name", "사업장명", 1),
    field("f2", "manager_name", "선임자", 2),
    field("f3", "appointed_at", "선임일", 3, input_type="date"),
]


def doc(**over):
    d = {
        "id": DOC_ID,
        "form_schema_id": SCHEMA_ID,
        "version": 1,
        "status": "REVIEW_PENDING",
        "runtime_data_json": {"company_name": "태왕엔지니어링", "manager_name": "홍길동"},
    }
    d.update(over)
    return d


def build(**over):
    kwargs = dict(document=doc(), schema=schema(), fields=FIELDS, checklists=[checklist()])
    kwargs.update(over)
    return build_render_artifacts(**kwargs)


# ── 결정성 ────────────────────────────────────────────────────────────────
def test_01_byte_identical_on_repeat():
    bodies = {build()["rendered_body"] for _ in range(50)}
    ids = {build()["template_identity"] for _ in range(50)}
    assert len(bodies) == 1
    assert len(ids) == 1


def test_02_data_key_insertion_order_irrelevant():
    a = build(document=doc(runtime_data_json={"company_name": "T", "manager_name": "H"}))
    b = build(document=doc(runtime_data_json={"manager_name": "H", "company_name": "T"}))
    assert a["rendered_body"] == b["rendered_body"]


def test_03_row_input_order_irrelevant_but_field_order_governs():
    shuffled = [FIELDS[2], FIELDS[0], FIELDS[1]]
    assert build(fields=shuffled)["rendered_body"] == build()["rendered_body"]
    body = build()["rendered_body"]
    assert body.index("사업장명") < body.index("선임자") < body.index("선임일")


def test_04_no_time_random_url_in_output():
    art = build()
    body = art["rendered_body"]
    # 현재 시각·연도·랜덤 id·URL·hostname 이 새어 들어가면 안 된다
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:", body)
    assert "http://" not in body and "https://" not in body
    assert "railway" not in body and "supabase" not in body
    # created_at 이 입력에 있어도 렌더/identity 어디에도 반영되지 않는다
    assert "2026-01-01T00:00:00Z" not in body


def test_05_order_none_and_ties_are_deterministic():
    fs = [
        field("fb", "b", "B", None),
        field("fa", "a", "A", None),
        field("f1", "one", "ONE", 1),
    ]
    one = build(fields=fs, document=doc(runtime_data_json={}))["rendered_body"]
    two = build(fields=list(reversed(fs)), document=doc(runtime_data_json={}))["rendered_body"]
    assert one == two
    # order 있는 행이 먼저, order 없는 행은 id 순으로 뒤에
    assert one.index("ONE") < one.index(">A<") < one.index(">B<")


# ── lossless / missing != omitted ────────────────────────────────────────
def test_06_unknown_keys_are_never_dropped():
    data = {"company_name": "T", "폐기되면안됨": "값", "extra": {"z": 1, "a": [1, 2]}}
    body = build(document=doc(runtime_data_json=data))["rendered_body"]
    assert "폐기되면안됨" in body and "값" in body
    assert "unmapped-values" in body
    # 중첩 구조도 canonical JSON 으로 보존
    assert '{&quot;a&quot;:[1,2],&quot;z&quot;:1}' in body


def test_07_unmapped_section_is_key_sorted():
    body = build(document=doc(runtime_data_json={"zz": "1", "aa": "2", "mm": "3"}))[
        "rendered_body"
    ]
    assert body.index('data-key="aa"') < body.index('data-key="mm"') < body.index('data-key="zz"')


def test_08_missing_is_explicit_not_omitted():
    body = build(document=doc(runtime_data_json={"company_name": "T"}))["rendered_body"]
    assert 'data-field-key="manager_name"' in body      # 행 자체는 존재
    assert 'data-state="missing"' in body
    assert "(미입력)" in body


def test_09_null_and_empty_are_missing_not_blank():
    body = build(document=doc(runtime_data_json={"company_name": None, "manager_name": ""}))[
        "rendered_body"
    ]
    assert body.count('data-state="missing"') >= 2
    assert body.count("(미입력)") >= 2


def test_10_field_without_key_is_unmappable_not_guessed():
    fs = [field("fx", None, "라벨만있는필드", 1)]
    body = build(fields=fs, document=doc(runtime_data_json={"any": "값"}))["rendered_body"]
    assert 'data-state="unmappable"' in body
    assert "라벨만있는필드" in body
    # 값을 추측해 채우지 않는다. 대신 그 값은 unmapped 영역에 보존된다.
    assert 'data-key="any"' in body


def test_11_checklist_response_only_by_item_id():
    body = build(document=doc(runtime_data_json={CHK_ID: "PASS"}))["rendered_body"]
    assert 'data-item-id="%s"' % CHK_ID in body
    assert "PASS" in body
    # 응답이 없으면 미입력으로 명시
    body2 = build(document=doc(runtime_data_json={}))["rendered_body"]
    assert 'data-item-id="%s"' % CHK_ID in body2 and "(미입력)" in body2


# ── 보안/escaping ─────────────────────────────────────────────────────────
def test_12_html_is_escaped():
    body = build(
        document=doc(runtime_data_json={"company_name": "<script>alert(1)</script>"}),
        schema=schema(form_name='<img src=x onerror="e">'),
    )["rendered_body"]
    # 위험 기준 = 실행 가능한 태그/속성 경계가 생성되는가. escape 된 평문은 위험이 아니다.
    assert "<script>" not in body and "</script>" not in body
    assert "<img" not in body
    assert "&lt;script&gt;" in body and "&lt;img" in body
    assert "&quot;" in body  # 속성 경계 문자도 escape
    # 주입값 앞뒤로 태그가 열리지 않았는지: 속성 안에서도 따옴표가 닫히지 않아야 한다
    assert 'onerror="' not in body


# ── template_identity ────────────────────────────────────────────────────
def test_13_identity_shape():
    tid = build()["template_identity"]
    assert tid.startswith("schema-renderer:%s:sha256:" % r.RENDERER_VERSION)
    digest = tid.rsplit(":", 1)[1]
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


def test_14_identity_changes_on_render_affecting_schema_change():
    base = build()["template_identity"]
    assert base != build(fields=[field("f1", "company_name", "사업장 이름", 1)] + FIELDS[1:])[
        "template_identity"
    ]  # label
    assert base != build(fields=[field("f1", "company", "사업장명", 1)] + FIELDS[1:])[
        "template_identity"
    ]  # field_key
    assert base != build(fields=[field("f1", "company_name", "사업장명", 9)] + FIELDS[1:])[
        "template_identity"
    ]  # order
    assert base != build(
        fields=[field("f1", "company_name", "사업장명", 1, input_type="number")] + FIELDS[1:]
    )["template_identity"]  # input_type
    assert base != build(checklists=[checklist(text="다른 점검항목")])["template_identity"]


def test_15_identity_stable_against_non_render_metadata_and_values():
    base = build()["template_identity"]
    # 저장 메타/계보/상태 변경은 identity 를 흔들지 않는다
    assert base == build(
        fields=[field("f1", "company_name", "사업장명", 1,
                      created_at="2099-12-31T00:00:00Z", status="ACTIVE",
                      field_candidate_id="x", source_trace={"a": 1})] + FIELDS[1:]
    )["template_identity"]
    # 렌더러가 소비하지 않는 속성(default_value/validation_rule/placeholder)도 무영향
    assert base == build(
        fields=[field("f1", "company_name", "사업장명", 1,
                      default_value="자동값", validation_rule={"max": 10},
                      placeholder="입력하세요")] + FIELDS[1:]
    )["template_identity"]
    # 입력 값이 달라져도 template identity 는 그대로(값은 rendered_body/hash 가 담당)
    assert base == build(document=doc(runtime_data_json={"company_name": "다른회사"}))[
        "template_identity"
    ]


def test_16_default_value_is_never_auto_filled():
    body = build(
        fields=[field("f1", "company_name", "사업장명", 1, default_value="자동채움")],
        document=doc(runtime_data_json={}),
    )["rendered_body"]
    assert "자동채움" not in body
    assert "(미입력)" in body


# ── 산출물 계약 ───────────────────────────────────────────────────────────
def test_17_source_trace_is_unknown_single_element():
    trace = build()["source_trace_snapshot"]
    assert isinstance(trace, list) and len(trace) == 1
    assert trace[0]["provenance"] == "UNKNOWN"
    assert trace[0]["source_id"] == DOC_ID
    assert isinstance(trace[0]["reason"], str) and trace[0]["reason"]


def test_18_evidence_manifest_is_empty_list_not_fake():
    art = build()
    assert art["evidence_manifest"] == []
    assert json.dumps(art["evidence_manifest"]) == "[]"


def test_19_artifacts_are_json_native_and_feed_q4_hash():
    """산출물이 Q4 hash 계약(JSON-native only)을 그대로 통과해야 한다."""
    art = build()
    for part in ("source_trace_snapshot", "evidence_manifest"):
        json.dumps(art[part], allow_nan=False)  # 예외 없이 직렬화 가능
    from datetime import datetime, timezone

    h = compute_confirmed_snapshot_hash(
        runtime_document_id=DOC_ID,
        document_version=1,
        snapshot_schema_version=1,
        runtime_values_snapshot=doc()["runtime_data_json"],
        source_trace_snapshot=art["source_trace_snapshot"],
        template_identity=art["template_identity"],
        confirmed_at=datetime(2026, 8, 23, 1, 30, 0, 123456, tzinfo=timezone.utc),
        confirmed_by=BY,
        evidence_manifest=art["evidence_manifest"],
        rendered_body=art["rendered_body"],
    )
    assert len(h) == 64


def test_20_hash_domain_is_separate_from_q4():
    """schema_structure_hash 는 Q4 snapshot hash 와 다른 도메인이어야 한다."""
    tid_digest = build()["template_identity"].rsplit(":", 1)[1]
    from datetime import datetime, timezone

    art = build()
    snap = compute_confirmed_snapshot_hash(
        runtime_document_id=DOC_ID,
        document_version=1,
        snapshot_schema_version=1,
        runtime_values_snapshot=doc()["runtime_data_json"],
        source_trace_snapshot=art["source_trace_snapshot"],
        template_identity=art["template_identity"],
        confirmed_at=datetime(2026, 8, 23, 1, 30, 0, 123456, tzinfo=timezone.utc),
        confirmed_by=BY,
        evidence_manifest=art["evidence_manifest"],
        rendered_body=art["rendered_body"],
    )
    assert tid_digest != snap


# ── 입력 계약 위반 = FAIL-CLOSED ─────────────────────────────────────────
def test_21_input_contract_violations_raise():
    with pytest.raises(SchemaRenderError):
        build(schema=schema(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))  # 다른 스키마
    with pytest.raises(SchemaRenderError):
        build(document=doc(runtime_data_json=["not", "an", "object"]))
    with pytest.raises(SchemaRenderError):
        build(fields=[field("f1", "k", "", 1)])                          # 빈 label
    with pytest.raises(SchemaRenderError):
        build(fields=[dict(field("f1", "k", "L", 1), form_schema_id="other")])
    with pytest.raises(SchemaRenderError):
        build(document=doc(runtime_data_json={"k": object()}))           # non-JSON-native
    with pytest.raises(SchemaRenderError):
        build(document=doc(runtime_data_json={"k": float("nan")}))


def test_22_module_does_not_touch_db_or_clock():
    src = open("services/document_schema_renderer.py", encoding="utf-8").read()
    for banned in ("get_supabase", "datetime.now", "utcnow", "random", "uuid4", "httpx"):
        assert banned not in src, "렌더러에 비결정/외부의존 요소: %s" % banned


# 23. form_name 은 렌더에 나타나므로 template_identity 에도 반드시 반영된다
def test_23_form_name_affects_template_identity():
    a = build(schema=schema(form_name="안전관리자선임보고서"))
    b = build(schema=schema(form_name="안전관리자 지정 보고서"))
    assert a["rendered_body"] != b["rendered_body"]
    assert a["template_identity"] != b["template_identity"]
    # form_name 이 None 인 경우도 별개 identity 로 구분된다
    assert build(schema=schema(form_name=None))["template_identity"] not in (
        a["template_identity"],
        b["template_identity"],
    )


# 24. nested non-JSON-native / non-string dict key 는 depth 와 무관하게 거부
def test_24_nested_type_boundary_matches_q4():
    from datetime import datetime, timezone
    from decimal import Decimal
    from uuid import UUID

    bads = (
        ("a", "b"),                                   # tuple
        Decimal("1.10"),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        UUID("33333333-3333-3333-3333-333333333333"),
        b"bytes",
        {1, 2},
        object(),
    )
    for bad in bads:
        with pytest.raises(SchemaRenderError):
            build(document=doc(runtime_data_json={"company_name": bad}))
        # 중첩 깊은 곳도 동일
        with pytest.raises(SchemaRenderError):
            build(document=doc(runtime_data_json={"nested": {"x": [{"y": bad}]}}))
    # non-string dict key
    with pytest.raises(SchemaRenderError):
        build(document=doc(runtime_data_json={"company_name": {1: "v"}}))
    # unmapped 영역으로 가는 값도 동일하게 검증된다
    with pytest.raises(SchemaRenderError):
        build(document=doc(runtime_data_json={"unmapped_key": ("t",)}))


# 25. document.version 은 int >= 1 만 허용 (ARCH-02/Q4 계약과 동일 경계)
def test_25_document_version_type_contract():
    ok = build(document=doc(version=1))
    assert "<dt>document_version</dt><dd>1</dd>" in ok["rendered_body"]
    assert ok["source_trace_snapshot"][0]["source_version"] == 1
    assert isinstance(ok["source_trace_snapshot"][0]["source_version"], int)

    for bad in (0, -1, "1", True, False, None, 1.0, "one"):
        with pytest.raises(SchemaRenderError):
            build(document=doc(version=bad))

    # version 이 다르면 body 도 달라진다(식별 헤더에 포함되므로)
    assert build(document=doc(version=1))["rendered_body"] != build(
        document=doc(version=2)
    )["rendered_body"]
