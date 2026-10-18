"""CHEM-WO-LEG-INPUT-L2-TAI-API-CONSUMPTION-014B — L2 Reader 클라이언트 검증

Goal: G-mvdus6tg-8ef927

커버리지:
  B14-01  load_active_components 정상 수신
  B14-02  기밀 성분 원본 내부 보존 (is_confidential=True 그대로 반환)
  B14-03  load_consumption_lines 정상 수신
  B14-04  load_issue_lines 정상 수신
  B14-05  company_id + secret 전달 검증
  B14-06  factory_id 응답 불일치 차단
  B14-07  malformed JSON / 응답 구조 오류 차단
  B14-08  timeout / network error Fail Closed
  B14-09  HTTP error Fail Closed (403/404/422/5xx)
  B14-10  미설정 Secret / Base URL 차단
  B14-11  naive datetime 차단 (C1/C2)
  B14-12  역전 기간 차단 (from_at >= until_at_exclusive)
  B14-13  명시적 False / 0 / NULL 값 보존
  B14-14  기밀 원문 로그 미노출 (is_confidential=True 성분명 로그에 미포함)
  B14-15  기존 load_chemical_facts() 회귀 없음
  B14-16  SAFE / LEG 실행 경로 신규 호출 0
  B14-17  실제 LEG C4 호출 0

원칙:
  - 외부 CHEM API, 운영 DB, LEG Runtime 호출 모두 Mock
  - 빈 list 와 통신 실패 구분
  - False/0/None 임의 변환 금지
  - B1: is_confidential=True 외부 노출 금지
"""
from __future__ import annotations

import inspect
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────────────────────

_BASE = "http://chem-internal"
_SECRET = "test-secret-014b"
_FAC = "fac-014b"
_CO = "co-014b"
_TZ = timezone(timedelta(hours=9))
_FROM = datetime(2026, 10, 1, 0, 0, 0, tzinfo=_TZ)
_UNTIL = datetime(2026, 11, 1, 0, 0, 0, tzinfo=_TZ)


def _make_resp(status_code: int, json_body: Any, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = text or str(json_body)
    return resp


def _chem_env(monkeypatch):
    monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", _BASE)
    monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", _SECRET)


# ─────────────────────────────────────────────────────────────────────────────
# B14-01 — load_active_components 정상 수신
# ─────────────────────────────────────────────────────────────────────────────

class TestB1401ActiveComponentsOk:

    def test_b14_01_returns_components_list(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        components = [
            {
                "id": "comp-1", "msds_version_id": "mv-1", "company_id": _CO,
                "component_name_normalized": "Toluene", "cas_no_normalized": "108-88-3",
                "content_min_pct": 10.0, "content_max_pct": 20.0,
                "is_confidential": False, "sort_order": 1,
            }
        ]
        resp = _make_resp(200, {"factory_id": _FAC, "components": components})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result == components

    def test_b14_01_empty_list_is_valid(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        resp = _make_resp(200, {"factory_id": _FAC, "components": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# B14-02 — 기밀 성분 원본 내부 보존
# ─────────────────────────────────────────────────────────────────────────────

class TestB1402ConfidentialPreserved:

    def test_b14_02_confidential_row_returned_as_is(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        confidential_row = {
            "id": "comp-secret", "msds_version_id": "mv-2", "company_id": _CO,
            "component_name_normalized": "ProprietaryChemA", "cas_no_normalized": None,
            "content_min_pct": 5.0, "content_max_pct": 15.0,
            "is_confidential": True, "sort_order": 2,
        }
        resp = _make_resp(200, {"factory_id": _FAC, "components": [confidential_row]})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result[0]["is_confidential"] is True
        assert result[0]["component_name_normalized"] == "ProprietaryChemA"

    def test_b14_02_confidential_not_filtered(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        rows = [
            {"id": "c1", "is_confidential": False, "component_name_normalized": "A",
             "msds_version_id": "v1", "company_id": _CO, "cas_no_normalized": "1-1-1",
             "content_min_pct": 1.0, "content_max_pct": 5.0, "sort_order": 1},
            {"id": "c2", "is_confidential": True, "component_name_normalized": "B",
             "msds_version_id": "v1", "company_id": _CO, "cas_no_normalized": None,
             "content_min_pct": 1.0, "content_max_pct": 5.0, "sort_order": 2},
        ]
        resp = _make_resp(200, {"factory_id": _FAC, "components": rows})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# B14-03 — load_consumption_lines 정상 수신
# ─────────────────────────────────────────────────────────────────────────────

class TestB1403ConsumptionOk:

    def test_b14_03_returns_lines_list(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines
        lines = [
            {
                "document_id": "doc-1", "document_type": "CONSUMPTION",
                "document_no": "CSM-001", "occurred_at": "2026-10-15T09:00:00+09:00",
                "line_id": "ln-1", "line_no": 1, "material_code": "MAT-A",
                "quantity": 100.0, "uom_code": "KG", "base_quantity": 100.0,
                "base_uom_code": "KG", "conversion_factor_snapshot": 1.0, "lot_id": None,
            }
        ]
        resp = _make_resp(200, {"factory_id": _FAC, "lines": lines})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == lines

    def test_b14_03_empty_is_valid(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines
        resp = _make_resp(200, {"factory_id": _FAC, "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# B14-04 — load_issue_lines 정상 수신
# ─────────────────────────────────────────────────────────────────────────────

class TestB1404IssueOk:

    def test_b14_04_returns_lines_list(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines
        lines = [
            {
                "document_id": "doc-2", "document_type": "ISSUE",
                "document_no": "ISS-001", "occurred_at": "2026-10-16T10:00:00+09:00",
                "line_id": "ln-2", "line_no": 1, "material_code": "MAT-B",
                "quantity": 50.0, "uom_code": "L", "base_quantity": 50.0,
                "base_uom_code": "L", "conversion_factor_snapshot": 1.0, "lot_id": "lot-x",
            }
        ]
        resp = _make_resp(200, {"factory_id": _FAC, "lines": lines})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_issue_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == lines

    def test_b14_04_empty_is_valid(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines
        resp = _make_resp(200, {"factory_id": _FAC, "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_issue_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# B14-05 — company_id + secret 전달 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestB1405TransportContract:

    def test_b14_05_components_passes_company_id_and_secret(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        resp = _make_resp(200, {"factory_id": _FAC, "components": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp) as mock_get:
            load_active_components(_FAC, _CO)
        call = mock_get.call_args
        assert call.kwargs["params"]["company_id"] == _CO
        assert call.kwargs["headers"]["X-Internal-Secret"] == _SECRET

    def test_b14_05_consumption_passes_datetime_params(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines
        resp = _make_resp(200, {"factory_id": _FAC, "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp) as mock_get:
            load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)
        call = mock_get.call_args
        params = call.kwargs["params"]
        assert params["company_id"] == _CO
        assert params["from_at"] == _FROM.isoformat()
        assert params["until_at_exclusive"] == _UNTIL.isoformat()

    def test_b14_05_issue_passes_datetime_params(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines
        resp = _make_resp(200, {"factory_id": _FAC, "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp) as mock_get:
            load_issue_lines(_FAC, _CO, _FROM, _UNTIL)
        call = mock_get.call_args
        params = call.kwargs["params"]
        assert params["from_at"] == _FROM.isoformat()
        assert params["until_at_exclusive"] == _UNTIL.isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# B14-06 — factory_id 응답 불일치 차단
# ─────────────────────────────────────────────────────────────────────────────

class TestB1406FactoryIdMismatch:

    def test_b14_06_components_mismatch_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = _make_resp(200, {"factory_id": "OTHER-FAC", "components": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="factory_id mismatch"):
                load_active_components(_FAC, _CO)

    def test_b14_06_consumption_mismatch_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        resp = _make_resp(200, {"factory_id": "WRONG", "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="factory_id mismatch"):
                load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)

    def test_b14_06_issue_mismatch_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        resp = _make_resp(200, {"factory_id": "WRONG", "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="factory_id mismatch"):
                load_issue_lines(_FAC, _CO, _FROM, _UNTIL)


# ─────────────────────────────────────────────────────────────────────────────
# B14-07 — malformed JSON / 응답 구조 오류 차단
# ─────────────────────────────────────────────────────────────────────────────

class TestB1407MalformedResponse:

    def test_b14_07_invalid_json_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = Exception("not json")
        resp.text = "not json"
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="invalid JSON"):
                load_active_components(_FAC, _CO)

    def test_b14_07_components_not_list_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = _make_resp(200, {"factory_id": _FAC, "components": "bad"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="expected 'components' list"):
                load_active_components(_FAC, _CO)

    def test_b14_07_lines_not_list_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        resp = _make_resp(200, {"factory_id": _FAC, "lines": 123})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="expected 'lines' list"):
                load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)

    def test_b14_07_non_dict_response_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = _make_resp(200, ["not", "a", "dict"])
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="not a JSON object"):
                load_active_components(_FAC, _CO)


# ─────────────────────────────────────────────────────────────────────────────
# B14-08 — timeout / network error Fail Closed
# ─────────────────────────────────────────────────────────────────────────────

class TestB1408NetworkFailClosed:

    def test_b14_08_timeout_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        import httpx
        with patch("clients.chem_internal_client.httpx.get", side_effect=httpx.TimeoutException("t/o")):
            with pytest.raises(ChemicalSourceLoadError, match="timeout"):
                load_active_components(_FAC, _CO)

    def test_b14_08_network_error_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        import httpx
        with patch("clients.chem_internal_client.httpx.get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(ChemicalSourceLoadError, match="network"):
                load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)


# ─────────────────────────────────────────────────────────────────────────────
# B14-09 — HTTP error Fail Closed
# ─────────────────────────────────────────────────────────────────────────────

class TestB1409HttpErrorFailClosed:

    @pytest.mark.parametrize("status_code", [403, 404, 422, 500, 503])
    def test_b14_09_http_error_raises(self, status_code, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = _make_resp(status_code, {"detail": "error"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match=f"HTTP {status_code}"):
                load_active_components(_FAC, _CO)

    def test_b14_09_issue_403_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        resp = _make_resp(403, {"detail": "INVALID_INTERNAL_SECRET"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="HTTP 403"):
                load_issue_lines(_FAC, _CO, _FROM, _UNTIL)


# ─────────────────────────────────────────────────────────────────────────────
# B14-10 — 미설정 Secret / Base URL 차단
# ─────────────────────────────────────────────────────────────────────────────

class TestB1410EnvNotSet:

    def test_b14_10_no_base_url_raises(self, monkeypatch):
        monkeypatch.delenv("CHEM_INTERNAL_BASE_URL", raising=False)
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", _SECRET)
        from importlib import reload
        import clients.chem_internal_client as mod
        reload(mod)
        with pytest.raises(mod.ChemicalSourceLoadError, match="CHEM_INTERNAL_BASE_URL not set"):
            mod.load_active_components(_FAC, _CO)

    def test_b14_10_no_secret_raises(self, monkeypatch):
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", _BASE)
        monkeypatch.delenv("CHEM_INTERNAL_API_SECRET", raising=False)
        from importlib import reload
        import clients.chem_internal_client as mod
        reload(mod)
        with pytest.raises(mod.ChemicalSourceLoadError, match="CHEM_INTERNAL_API_SECRET not set"):
            mod.load_active_components(_FAC, _CO)

    def test_b14_10_no_base_url_consumption_raises(self, monkeypatch):
        monkeypatch.delenv("CHEM_INTERNAL_BASE_URL", raising=False)
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", _SECRET)
        from importlib import reload
        import clients.chem_internal_client as mod
        reload(mod)
        with pytest.raises(mod.ChemicalSourceLoadError, match="CHEM_INTERNAL_BASE_URL not set"):
            mod.load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)


# ─────────────────────────────────────────────────────────────────────────────
# B14-11 — naive datetime 차단
# ─────────────────────────────────────────────────────────────────────────────

class TestB1411NaiveDatetime:

    def test_b14_11_naive_from_at_consumption_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        naive = datetime(2026, 10, 1, 0, 0, 0)
        with pytest.raises(ChemicalSourceLoadError, match="timezone-aware"):
            load_consumption_lines(_FAC, _CO, naive, _UNTIL)

    def test_b14_11_naive_until_consumption_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        naive = datetime(2026, 11, 1, 0, 0, 0)
        with pytest.raises(ChemicalSourceLoadError, match="timezone-aware"):
            load_consumption_lines(_FAC, _CO, _FROM, naive)

    def test_b14_11_naive_from_at_issue_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        naive = datetime(2026, 10, 1, 0, 0, 0)
        with pytest.raises(ChemicalSourceLoadError, match="timezone-aware"):
            load_issue_lines(_FAC, _CO, naive, _UNTIL)


# ─────────────────────────────────────────────────────────────────────────────
# B14-12 — 역전 기간 차단
# ─────────────────────────────────────────────────────────────────────────────

class TestB1412ReversedRange:

    def test_b14_12_from_after_until_consumption_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        with pytest.raises(ChemicalSourceLoadError, match="strictly before"):
            load_consumption_lines(_FAC, _CO, _UNTIL, _FROM)

    def test_b14_12_from_equal_until_consumption_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        with pytest.raises(ChemicalSourceLoadError, match="strictly before"):
            load_consumption_lines(_FAC, _CO, _FROM, _FROM)

    def test_b14_12_reversed_issue_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        with pytest.raises(ChemicalSourceLoadError, match="strictly before"):
            load_issue_lines(_FAC, _CO, _UNTIL, _FROM)


# ─────────────────────────────────────────────────────────────────────────────
# B14-13 — 명시적 False / 0 / NULL 값 보존
# ─────────────────────────────────────────────────────────────────────────────

class TestB1413ZeroNullPreserved:

    def test_b14_13_zero_content_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        row = {
            "id": "c1", "msds_version_id": "v1", "company_id": _CO,
            "component_name_normalized": "X", "cas_no_normalized": "1-1-1",
            "content_min_pct": 0.0, "content_max_pct": 0.0,
            "is_confidential": False, "sort_order": 1,
        }
        resp = _make_resp(200, {"factory_id": _FAC, "components": [row]})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result[0]["content_min_pct"] == 0.0
        assert result[0]["content_max_pct"] == 0.0

    def test_b14_13_null_cas_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        row = {
            "id": "c1", "msds_version_id": "v1", "company_id": _CO,
            "component_name_normalized": "X", "cas_no_normalized": None,
            "content_min_pct": 5.0, "content_max_pct": 10.0,
            "is_confidential": False, "sort_order": 1,
        }
        resp = _make_resp(200, {"factory_id": _FAC, "components": [row]})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result[0]["cas_no_normalized"] is None

    def test_b14_13_zero_quantity_line_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines
        line = {
            "document_id": "d1", "document_type": "CONSUMPTION", "document_no": "C1",
            "occurred_at": "2026-10-10T00:00:00+09:00", "line_id": "l1", "line_no": 1,
            "material_code": "M1", "quantity": 0.0, "uom_code": "KG",
            "base_quantity": 0.0, "base_uom_code": "KG",
            "conversion_factor_snapshot": 1.0, "lot_id": None,
        }
        resp = _make_resp(200, {"factory_id": _FAC, "lines": [line]})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result[0]["quantity"] == 0.0
        assert result[0]["lot_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# B14-14 — 기밀 원문 로그 미노출
# ─────────────────────────────────────────────────────────────────────────────

class TestB1414ConfidentialNotLogged:

    def test_b14_14_confidential_name_not_in_log(self, monkeypatch, caplog):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        confidential_name = "ULTRA_SECRET_COMPOUND_XYZ"
        row = {
            "id": "cx", "msds_version_id": "vx", "company_id": _CO,
            "component_name_normalized": confidential_name, "cas_no_normalized": None,
            "content_min_pct": 1.0, "content_max_pct": 5.0,
            "is_confidential": True, "sort_order": 1,
        }
        resp = _make_resp(200, {"factory_id": _FAC, "components": [row]})
        with caplog.at_level(logging.DEBUG, logger="clients.chem_internal_client"):
            with patch("clients.chem_internal_client.httpx.get", return_value=resp):
                result = load_active_components(_FAC, _CO)
        assert result[0]["component_name_normalized"] == confidential_name
        assert confidential_name not in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# B14-15 — 기존 load_chemical_facts() 회귀 없음
# ─────────────────────────────────────────────────────────────────────────────

class TestB1415LoadChemicalFactsRegression:

    def test_b14_15_has_chemical_true_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts
        resp = _make_resp(200, {"factory_id": _FAC, "facts": {"has_chemical": True}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts(_FAC, _CO)
        assert result == {"has_chemical": True}

    def test_b14_15_has_chemical_false_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts
        resp = _make_resp(200, {"factory_id": _FAC, "facts": {"has_chemical": False}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts(_FAC, _CO)
        assert result == {"has_chemical": False}

    def test_b14_15_contract_gaps_stripped(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts
        resp = _make_resp(200, {
            "factory_id": _FAC,
            "facts": {"has_chemical": True},
            "contract_gaps": ["has_hazardous_material", "hazmat_designated_quantity_multiple"],
        })
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts(_FAC, _CO)
        assert "contract_gaps" not in result
        assert "has_hazardous_material" not in result

    def test_b14_15_timeout_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        import httpx
        with patch("clients.chem_internal_client.httpx.get", side_effect=httpx.TimeoutException("t/o")):
            with pytest.raises(ChemicalSourceLoadError, match="timeout"):
                load_chemical_facts(_FAC, _CO)


# ─────────────────────────────────────────────────────────────────────────────
# B14-16 — SAFE / LEG 실행 경로 신규 호출 0
# ─────────────────────────────────────────────────────────────────────────────

class TestB1416SafeLegNoNewCalls:

    def test_b14_16_chem_client_not_imported_in_safe_industrial(self):
        import importlib, ast, pathlib
        src = pathlib.Path("services/safe_industrial_leg_runtime.py").read_text()
        tree = ast.parse(src)
        imports = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        names = []
        for imp in imports:
            if isinstance(imp, ast.ImportFrom):
                names.append(imp.module or "")
            else:
                names.extend(alias.name for alias in imp.names)
        new_fns = {"load_active_components", "load_consumption_lines", "load_issue_lines"}
        src_text = pathlib.Path("services/safe_industrial_leg_runtime.py").read_text()
        for fn in new_fns:
            assert fn not in src_text, f"{fn} found in safe_industrial_leg_runtime.py"

    def test_b14_16_chem_client_not_imported_in_safe_building(self):
        import pathlib
        src = pathlib.Path("services/safe_building_leg_runtime.py").read_text()
        for fn in ["load_active_components", "load_consumption_lines", "load_issue_lines"]:
            assert fn not in src, f"{fn} found in safe_building_leg_runtime.py"

    def test_b14_16_chem_client_not_imported_in_safe_construction(self):
        import pathlib
        src = pathlib.Path("services/safe_construction_leg_runtime.py").read_text()
        for fn in ["load_active_components", "load_consumption_lines", "load_issue_lines"]:
            assert fn not in src, f"{fn} found in safe_construction_leg_runtime.py"

    def test_b14_16_saas_leg_source_adapter_no_new_reader(self):
        import pathlib
        src = pathlib.Path("services/canonical/saas_leg_source_adapter.py").read_text()
        for fn in ["load_active_components", "load_consumption_lines", "load_issue_lines"]:
            assert fn not in src, f"{fn} found in saas_leg_source_adapter.py"


# ─────────────────────────────────────────────────────────────────────────────
# B14-17 — 실제 LEG C4 호출 0
# ─────────────────────────────────────────────────────────────────────────────

class TestB1417NoC4Call:

    def test_b14_17_chem_client_does_not_call_evaluate(self):
        import pathlib
        src = pathlib.Path("clients/chem_internal_client.py").read_text()
        assert "evaluate_rtm" not in src
        assert "/rtm/evaluate" not in src
        assert "leg_runtime_client" not in src

    def test_b14_17_new_functions_not_in_leg_runtime_client(self):
        import pathlib
        src = pathlib.Path("clients/leg_runtime_client.py").read_text()
        for fn in ["load_active_components", "load_consumption_lines", "load_issue_lines"]:
            assert fn not in src, f"{fn} found in leg_runtime_client.py"


# ─────────────────────────────────────────────────────────────────────────────
# P14B-01 — HTTP 실패 응답 본문 예외·로그 미노출 (PATCH-A)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B01HttpErrorBodyRedacted:

    def test_p14b_01_confidential_name_in_error_body_not_in_exception(self, monkeypatch, caplog):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        secret_compound = "ULTRA_SECRET_COMPOUND_403"
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {"detail": f"component={secret_compound}"}
        resp.text = f'{{"detail": "component={secret_compound}"}}'
        import logging
        with caplog.at_level(logging.DEBUG, logger="clients.chem_internal_client"):
            with patch("clients.chem_internal_client.httpx.get", return_value=resp):
                with pytest.raises(ChemicalSourceLoadError) as exc_info:
                    load_active_components(_FAC, _CO)
        assert secret_compound not in str(exc_info.value)
        assert secret_compound not in caplog.text

    def test_p14b_01_http_error_message_contains_only_status_code(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        resp = _make_resp(500, {"detail": "internal error with sensitive data"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError) as exc_info:
                load_active_components(_FAC, _CO)
        msg = str(exc_info.value)
        assert "500" in msg
        assert "sensitive data" not in msg
        assert "internal error" not in msg


# ─────────────────────────────────────────────────────────────────────────────
# P14B-02 — 네트워크·JSON 오류 내부 원문 미노출 (PATCH-A)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B02NetworkJsonRedacted:

    def test_p14b_02_timeout_no_url_in_message(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        import httpx
        with patch("clients.chem_internal_client.httpx.get",
                   side_effect=httpx.TimeoutException(f"timed out connecting to http://chem-internal/{_FAC}")):
            with pytest.raises(ChemicalSourceLoadError) as exc_info:
                load_active_components(_FAC, _CO)
        msg = str(exc_info.value)
        assert "http://" not in msg
        assert "chem-internal" not in msg

    def test_p14b_02_json_error_no_body_content_in_message(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        secret_in_body = "CONFIDENTIAL_IN_JSON_BODY"
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = Exception(f"decode error: {secret_in_body}")
        resp.text = secret_in_body
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError) as exc_info:
                load_active_components(_FAC, _CO)
        assert secret_in_body not in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# P14B-03 — company_id 누락 시 HTTP 호출 0 (PATCH-B)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B03MissingCompanyId:

    @pytest.mark.parametrize("bad_company_id", ["", "   ", None])
    def test_p14b_03_empty_company_id_components_raises(self, bad_company_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="company_id"):
                load_active_components(_FAC, bad_company_id or "")
        mock_get.assert_not_called()

    @pytest.mark.parametrize("bad_company_id", ["", "   "])
    def test_p14b_03_empty_company_id_consumption_raises(self, bad_company_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="company_id"):
                load_consumption_lines(_FAC, bad_company_id, _FROM, _UNTIL)
        mock_get.assert_not_called()

    @pytest.mark.parametrize("bad_company_id", ["", "   "])
    def test_p14b_03_empty_company_id_issue_raises(self, bad_company_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="company_id"):
                load_issue_lines(_FAC, bad_company_id, _FROM, _UNTIL)
        mock_get.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# P14B-04 — factory_id 누락 시 HTTP 호출 0 (PATCH-B)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B04MissingFactoryId:

    @pytest.mark.parametrize("bad_factory_id", ["", "   "])
    def test_p14b_04_empty_factory_id_components_raises(self, bad_factory_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="factory_id"):
                load_active_components(bad_factory_id, _CO)
        mock_get.assert_not_called()

    @pytest.mark.parametrize("bad_factory_id", ["", "   "])
    def test_p14b_04_empty_factory_id_consumption_raises(self, bad_factory_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="factory_id"):
                load_consumption_lines(bad_factory_id, _CO, _FROM, _UNTIL)
        mock_get.assert_not_called()

    @pytest.mark.parametrize("bad_factory_id", ["", "   "])
    def test_p14b_04_empty_factory_id_issue_raises(self, bad_factory_id, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines, ChemicalSourceLoadError
        with patch("clients.chem_internal_client.httpx.get") as mock_get:
            with pytest.raises(ChemicalSourceLoadError, match="factory_id"):
                load_issue_lines(bad_factory_id, _CO, _FROM, _UNTIL)
        mock_get.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# P14B-05 — 세 Reader 정상 수신 및 빈 배열 계약 유지
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B05ReadersStillWork:

    def test_p14b_05_active_components_normal(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_active_components
        components = [{"id": "c1", "component_name_normalized": "X", "is_confidential": False}]
        resp = _make_resp(200, {"factory_id": _FAC, "components": components})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_active_components(_FAC, _CO)
        assert result == components

    def test_p14b_05_consumption_normal(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_consumption_lines
        lines = [{"document_id": "d1", "document_type": "CONSUMPTION"}]
        resp = _make_resp(200, {"factory_id": _FAC, "lines": lines})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_consumption_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == lines

    def test_p14b_05_issue_empty_valid(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_issue_lines
        resp = _make_resp(200, {"factory_id": _FAC, "lines": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_issue_lines(_FAC, _CO, _FROM, _UNTIL)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# P14B-06 — 기존 load_chemical_facts() 회귀 없음
# ─────────────────────────────────────────────────────────────────────────────

class TestP14B06LoadChemicalFactsRegression:

    def test_p14b_06_has_chemical_true(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts
        resp = _make_resp(200, {"factory_id": _FAC, "facts": {"has_chemical": True}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts(_FAC, _CO)
        assert result == {"has_chemical": True}

    def test_p14b_06_has_chemical_false_preserved(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts
        resp = _make_resp(200, {"factory_id": _FAC, "facts": {"has_chemical": False}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts(_FAC, _CO)
        assert result == {"has_chemical": False}

    def test_p14b_06_http_error_raises(self, monkeypatch):
        _chem_env(monkeypatch)
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        resp = _make_resp(403, {"detail": "INVALID_INTERNAL_SECRET"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="403"):
                load_chemical_facts(_FAC, _CO)
