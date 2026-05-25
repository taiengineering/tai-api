from services.diagnosis_nexas_adapter import (
    build_nexas_run_response,
    nexas_run_body_from_request,
    rules_table_to_obligations,
)


def test_nexas_form_data_maps_worker_count():
    body = nexas_run_body_from_request(
        {
            "auth_token": "t",
            "disclaimer_log_id": "d",
            "sector": "INDUSTRY",
            "tier": "FREE",
            "form_data": {"workers": 120, "total_floor_area": 3000},
        }
    )
    assert body.worker_count == 120
    assert body.total_floor_area == 3000.0


def test_rules_table_to_obligations():
    obs = rules_table_to_obligations(
        {
            "rules_table": [
                {
                    "law_name": "산업안전보건법",
                    "law_article": "제29조",
                    "obligation_summary": "교육 실시",
                    "who": "사업주",
                }
            ]
        }
    )
    assert len(obs) == 1
    assert obs[0]["title"] == "교육 실시"
    assert "산업안전보건법" in obs[0]["law_reference"]


def test_build_nexas_run_response_wraps_data():
    out = build_nexas_run_response(
        {
            "status": "success",
            "public_token": "tok-1",
            "result": {"risk_level": "HIGH", "rules_table": []},
        }
    )
    assert out["data"]["public_token"] == "tok-1"
    assert out["status"] == "success"
