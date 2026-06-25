"""Tests for obligation_instance_adapter glue (CURSOR-TASK-001)."""

from services.obligation_instance_adapter import (
    obligation_instances_to_candidates,
    obligation_instances_to_trigger_candidates,
)
from services.obligation_adapter_service import (
    build_obligations_from_trigger_candidates,
)


def test_obligation_instances_to_candidates_shape():
    rows = [
        {
            "source_clause_id": "clause-1",
            "source_article_id": "art-1",
            "source_part_id": "part-1",
            "trigger_type": "WORK",
            "trigger_l2": "CONFINED_SPACE",
            "executor_text": "사업주",
            "condition_text": "밀폐공간",
            "action_text": "사업주는 환기를 해야 한다.",
            "content_type": "OBLIGATION",
            "applicable_sectors": ["INDUSTRIAL"],
            "confidence": 0.95,
        }
    ]
    out = obligation_instances_to_candidates(rows)
    assert len(out) == 1
    c = out[0]
    assert c["clause_id"] == "clause-1"
    assert c["trigger_code"] == "WORK:CONFINED_SPACE"
    assert c["confidence"] == "HIGH"
    assert c["sector"] == "INDUSTRIAL"


def test_build_obligations_from_instance_candidates():
    candidates = obligation_instances_to_candidates([
        {
            "source_clause_id": "c1",
            "source_article_id": "a1",
            "source_part_id": "p1",
            "trigger_type": "BUSINESS",
            "trigger_l2": "REGISTERED",
            "executor_text": "사업주",
            "condition_text": None,
            "action_text": "사업주는 안전조치를 해야 한다.",
            "content_type": "OBLIGATION",
            "applicable_sectors": [],
            "confidence": 0.85,
        }
    ])
    result = build_obligations_from_trigger_candidates(
        candidates, "factory-1", trigger_codes=[]
    )
    assert result["verdict"] == "APPLICABLE"
    assert result["obligation_count"] == 1
    assert result["obligations"][0]["trigger_code"] == "BUSINESS:REGISTERED"


def test_integration_live_factory_e9c56af6():
    """Live DB: WO-MVP-001-LIVE test factory (skip if no env)."""
    import os
    if not os.getenv("SUPABASE_URL"):
        return
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not key:
        return
    sb = create_client(url, key)
    factory_id = "e9c56af6-5de7-487d-bd2e-0d452291a562"
    candidates = obligation_instances_to_trigger_candidates(factory_id, sb)
    assert len(candidates) == 95
    null_fields = sum(
        1 for c in candidates
        for k in (
            "clause_id", "source_article_id", "trigger_code",
            "executor_text", "action_text", "content_type",
        )
        if not c.get(k)
    )
    assert null_fields == 0
    result = build_obligations_from_trigger_candidates(
        candidates, factory_id, trigger_codes=[]
    )
    assert result["verdict"] == "APPLICABLE"
    assert result["obligation_count"] >= 93
