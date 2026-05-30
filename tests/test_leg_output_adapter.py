from services.leg_output_adapter import _clean_label, _resolve_title, adapt


def test_obligation_identity():
    """모든 obligation에 obligation_id, obligation_type 존재."""
    raw = _make_raw(
        [
            {
                "rule_id": "R1",
                "obligation_type": "APPOINT",
                "law_name": "산안법",
                "law_article": "제17조",
                "description": "선임",
            },
        ],
        bucket="appointment_required",
    )
    result = adapt(raw)
    ob = result["obligations"][0]
    assert ob["obligation_id"] == "R1"
    assert ob["obligation_type"] == "APPOINT"
    assert ob["title"]
    assert "law_name" in ob
    assert "schedule_info" in ob
    assert "executor" in ob
    assert "penalty_summary" in ob
    assert "submission" in ob
    assert "evidence" in ob


def test_unified_structure():
    """다른 bucket에서 와도 동일한 필드 구조."""
    raw = _make_raw_multi(
        appointment=[
            {
                "rule_id": "R1",
                "obligation_type": "APPOINT",
                "law_name": "산안법",
                "law_article": "제17조",
                "description": "선임",
            }
        ],
        inspection=[
            {
                "rule_id": "R2",
                "obligation_type": "INSPECT",
                "law_name": "소방법",
                "law_article": "제22조",
                "description": "점검",
            }
        ],
    )
    result = adapt(raw)
    fields_0 = set(result["obligations"][0].keys())
    fields_1 = set(result["obligations"][1].keys())
    assert fields_0 == fields_1


def test_dedup():
    raw = _make_raw(
        [
            {"rule_id": "R1", "law_name": "산안법", "description": "선임"},
            {"rule_id": "R1", "law_name": "산안법", "description": "선임"},
        ],
        bucket="appointment_required",
    )
    result = adapt(raw)
    assert len(result["obligations"]) == 1
    assert result["metadata"]["adapter_stats"]["duplicates_removed"] == 1


def test_grouped_by_type_ids():
    """grouped_by_type은 obligation_ids 참조."""
    raw = _make_raw_multi(
        appointment=[
            {
                "rule_id": "R1",
                "obligation_type": "APPOINT",
                "law_name": "산안법",
                "description": "선임",
            }
        ],
        inspection=[
            {
                "rule_id": "R2",
                "obligation_type": "INSPECT",
                "law_name": "산안법",
                "description": "점검",
            }
        ],
    )
    result = adapt(raw)
    assert "R1" in result["grouped_by_type"]["appointment"]["obligation_ids"]
    assert "R2" in result["grouped_by_type"]["inspection"]["obligation_ids"]


def test_grouped_by_law_sorted():
    """법령별 그룹은 count 역순."""
    raw = _make_raw_multi(
        inspection=[
            {
                "rule_id": f"R{i}",
                "obligation_type": "INSPECT",
                "law_name": "소방법",
                "description": f"점검{i}",
            }
            for i in range(5)
        ],
        action=[
            {
                "rule_id": "R10",
                "obligation_type": "ACTION",
                "law_name": "산안법",
                "description": "조치",
            }
        ],
    )
    result = adapt(raw)
    assert result["grouped_by_law"][0]["law_name"] == "소방법"
    assert result["grouped_by_law"][0]["count"] == 5


def test_clean_label():
    assert _clean_label("SAFETY_INSPECTION_TASK_CANDIDATE 점검") == "점검"
    assert _clean_label("정상") == "정상"
    assert _clean_label("") == ""


def test_title_fallback():
    item = {
        "description": "",
        "obligation_summary": "",
        "remarks": "",
        "law_name": "산업안전보건법",
        "law_article": "제36조",
    }
    assert _resolve_title(item) == "산업안전보건법 제36조 관련 의무"


def test_deterministic():
    raw = _make_raw(
        [
            {
                "rule_id": "R1",
                "law_name": "산안법",
                "description": "선임",
                "obligation_type": "APPOINT",
            },
        ],
        bucket="appointment_required",
    )
    assert adapt(raw) == adapt(raw)


def test_notify_separation():
    """report bucket에서 notify 분리."""
    raw = _make_raw(
        [
            {
                "rule_id": "R1",
                "obligation_type": "NOTIFY",
                "notify_required": True,
                "law_name": "중대재해법",
                "description": "신고",
            },
        ],
        bucket="report_required",
    )
    result = adapt(raw)
    assert result["obligations"][0]["obligation_type"] == "NOTIFY"
    assert result["grouped_by_type"]["notify"]["count"] == 1


def test_evidence_traceability():
    """원본 evidence 추적 가능."""
    raw = _make_raw(
        [
            {
                "rule_id": "R1",
                "rule_type": "001",
                "condition_code": "worker_gte_50",
                "condition_value": 50,
                "law_name": "산안법",
                "description": "선임",
                "obligation_type": "APPOINT",
            },
        ],
        bucket="appointment_required",
    )
    result = adapt(raw)
    ev = result["obligations"][0]["evidence"]
    assert ev["rule_id"] == "R1"
    assert ev["condition_code"] == "worker_gte_50"
    assert ev["source_bucket"] == "appointment_required"


def _make_raw(items, bucket="action_required"):
    base = {
        "engine_version": "v5.10",
        "mode": "BUILDING",
        "evaluated_at": "2026-05-30",
        "total_rules_checked": 100,
        "not_applicable_count": 90,
        "applicable_count": len(items),
        "appointment_required": [],
        "inspection_required": [],
        "action_required": [],
        "report_required": [],
        "summary": {
            "total": len(items),
            "appointment": 0,
            "inspection": 0,
            "action": 0,
            "report": 0,
            "notify": 0,
        },
    }
    base[bucket] = items
    return base


def _make_raw_multi(appointment=None, inspection=None, action=None, report=None):
    a = appointment or []
    i = inspection or []
    ac = action or []
    r = report or []
    total = len(a) + len(i) + len(ac) + len(r)
    return {
        "engine_version": "v5.10",
        "mode": "BUILDING",
        "evaluated_at": "2026-05-30",
        "total_rules_checked": 100,
        "not_applicable_count": 100 - total,
        "applicable_count": total,
        "appointment_required": a,
        "inspection_required": i,
        "action_required": ac,
        "report_required": r,
        "summary": {
            "total": total,
            "appointment": len(a),
            "inspection": len(i),
            "action": len(ac),
            "report": len(r),
            "notify": 0,
        },
    }
