"""KECO 15149420 API client + LEG reference foundation 테스트.

KECO_API_SERVICE_KEY 없이 전부 통과 (synthetic fixture 사용).
PATCH-001 생성 테스트 포함.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# fixture 로더
# ---------------------------------------------------------------------------
FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "keco"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# contract 테스트
# ---------------------------------------------------------------------------

class TestContract:
    def test_base_url_is_official(self):
        from services.keco_chemical.contract import BASE_URL
        assert BASE_URL == "https://apis.data.go.kr/B552584/kecoapi/ncissbstn"

    def test_allowed_search_gubun_exact(self):
        from services.keco_chemical.contract import ALLOWED_SEARCH_GUBUN
        assert ALLOWED_SEARCH_GUBUN == frozenset({"1", "2", "3"})

    def test_unknown_search_gubun_rejected(self):
        from services.keco_chemical.contract import ALLOWED_SEARCH_GUBUN
        assert "0" not in ALLOWED_SEARCH_GUBUN
        assert "4" not in ALLOWED_SEARCH_GUBUN
        assert "5" not in ALLOWED_SEARCH_GUBUN

    def test_source_id_constant(self):
        from services.keco_chemical.contract import SOURCE_ID
        assert SOURCE_ID == "KECO_15149420"

    def test_service_key_env_single(self):
        from services.keco_chemical.contract import SERVICE_KEY_ENV
        assert SERVICE_KEY_ENV == ("KECO_API_SERVICE_KEY",)
        assert len(SERVICE_KEY_ENV) == 1

    def test_probe_max_calls_hard_cap(self):
        from services.keco_chemical.contract import PROBE_MAX_CALLS
        assert PROBE_MAX_CALLS == 3

    def test_success_codes_official_200(self):
        """P001: 공식 Swagger 성공 코드 = 200."""
        from services.keco_chemical.contract import SUCCESS_RESULT_CODES
        assert "200" in SUCCESS_RESULT_CODES
        assert "00" not in SUCCESS_RESULT_CODES
        assert "0000" not in SUCCESS_RESULT_CODES

    def test_retry_codes(self):
        from services.keco_chemical.contract import RETRY_CODES
        assert "22" in RETRY_CODES
        assert "23" in RETRY_CODES
        assert "05" in RETRY_CODES


# ---------------------------------------------------------------------------
# client 테스트
# ---------------------------------------------------------------------------

class TestClient:
    def _make_client(self, response_text: str, status: int = 200):
        from services.keco_chemical.client import KecoChemicalClient
        def fake_get(url, params=None, timeout=25):
            return status, response_text
        return KecoChemicalClient(get_fn=fake_get, _service_key="FAKE_KEY_FOR_TEST")

    def test_client_builds_correct_params(self):
        captured = {}
        from services.keco_chemical.client import KecoChemicalClient
        normal_text = _load("normal_response.json")

        def fake_get(url, params=None, timeout=25):
            captured["url"] = url
            captured["params"] = dict(params or {})
            return 200, normal_text

        client = KecoChemicalClient(get_fn=fake_get, _service_key="FAKE_KEY")
        client.search(search_gubun="2", search_nm="7664-41-7")
        assert "serviceKey" in captured["params"]
        assert captured["params"]["searchGubun"] == "2"
        assert captured["params"]["searchNm"] == "7664-41-7"
        assert captured["params"]["returnType"] == "JSON"
        assert "/chemSbstnList" in captured["url"]

    def test_client_redacts_servicekey_in_logs(self):
        from services.keco_chemical.client import redact_key
        key = "ABC123SECRET"
        url = "https://apis.data.go.kr/B552584?serviceKey=ABC123SECRET&foo=bar"
        result = redact_key(url, key)
        assert "ABC123SECRET" not in result
        assert "[REDACTED]" in result

    def test_client_no_korean_name_search_code(self):
        from services.keco_chemical.client import KecoChemicalClient
        def fake_get(url, params=None, timeout=25):
            return 200, "{}"
        client = KecoChemicalClient(get_fn=fake_get, _service_key="FAKE_KEY")
        with pytest.raises(ValueError):
            client.search(search_gubun="0", search_nm="암모니아")

    def test_client_no_key_raises_error(self):
        from services.keco_chemical.client import KecoChemicalClient, KecoNoServiceKeyError
        def fake_get(url, params=None, timeout=25):
            return 200, "{}"
        client = KecoChemicalClient(get_fn=fake_get, _service_key=None)
        with patch.dict(os.environ, {}, clear=True):
            env_backup = os.environ.pop("KECO_API_SERVICE_KEY", None)
            try:
                with pytest.raises(KecoNoServiceKeyError):
                    client.search(search_gubun="2", search_nm="test")
            finally:
                if env_backup is not None:
                    os.environ["KECO_API_SERVICE_KEY"] = env_backup

    def test_client_invalid_search_gubun(self):
        client = self._make_client(_load("normal_response.json"))
        with pytest.raises(ValueError):
            client.search(search_gubun="9", search_nm="test")

    def test_client_returns_search_response(self):
        """P001: resultCode 200 → 성공 KecoSearchResponse."""
        from services.keco_chemical.parse import KecoSearchResponse
        client = self._make_client(_load("normal_response.json"))
        result = client.search(search_gubun="2", search_nm="7664-41-7")
        assert isinstance(result, KecoSearchResponse)
        assert result.result_code == "200"
        assert len(result.items) == 1

    # --- P001: resultCode 00 성공으로 임의 처리 안 함 ---
    def test_result_code_00_is_error(self):
        """P001: 00은 공식 성공 코드 아님 → 에러 발생."""
        from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
        payload = json.dumps({
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": [], "numOfRows": "10", "pageNo": "1", "totalCount": "0"}
        })
        client = KecoChemicalClient(get_fn=lambda url, params=None, timeout=25: (200, payload),
                                     _service_key="FAKE")
        with pytest.raises(KecoChemicalClientError):
            client.search(search_gubun="2", search_nm="test")

    # --- P002: 에러 코드 분류 ---
    def _make_error_response(self, code: str, msg: str = "error") -> str:
        return json.dumps({"header": {"resultCode": code, "resultMsg": msg}})

    def _check_error_class(self, code: str, expected_class: str):
        from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
        payload = self._make_error_response(code)
        client = KecoChemicalClient(
            get_fn=lambda url, params=None, timeout=25: (200, payload),
            _service_key="FAKE",
        )
        with pytest.raises(KecoChemicalClientError) as exc_info:
            client.search(search_gubun="2", search_nm="test")
        assert exc_info.value.code == expected_class, f"code={code} expected={expected_class} got={exc_info.value.code}"

    def test_error_91_is_validation(self):
        """P002: 91 → VALIDATION."""
        self._check_error_class("91", "VALIDATION")

    def test_error_93_is_validation(self):
        """P002: 93 → VALIDATION."""
        self._check_error_class("93", "VALIDATION")

    def test_error_95_is_validation(self):
        """P002: 95 → VALIDATION."""
        self._check_error_class("95", "VALIDATION")

    def test_error_10_is_validation(self):
        """P002: 10 → VALIDATION."""
        self._check_error_class("10", "VALIDATION")

    def test_error_97_is_auth(self):
        """P002: 97 → AUTH (not VALIDATION)."""
        self._check_error_class("97", "AUTH")

    def test_error_20_is_auth(self):
        """P002: 20 → AUTH."""
        self._check_error_class("20", "AUTH")

    def test_error_30_is_auth(self):
        """P002: 30 → AUTH."""
        self._check_error_class("30", "AUTH")

    def test_error_31_is_auth(self):
        """P002: 31 → AUTH."""
        self._check_error_class("31", "AUTH")

    def test_error_22_is_rate_limit(self):
        """P002: 22 → RATE_LIMIT."""
        self._check_error_class("22", "RATE_LIMIT")

    def test_error_23_is_rate_limit(self):
        """P002: 23 → RATE_LIMIT."""
        self._check_error_class("23", "RATE_LIMIT")

    def test_error_12_is_upstream(self):
        """P002: 12 → UPSTREAM."""
        self._check_error_class("12", "UPSTREAM")

    # --- P003: blank searchNm ---
    def test_blank_search_nm_rejected(self):
        """P003: blank searchNm → VALIDATION 에러 (API 호출 전 차단)."""
        from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
        called = []
        def fake_get(url, params=None, timeout=25):
            called.append(True)
            return 200, "{}"
        client = KecoChemicalClient(get_fn=fake_get, _service_key="FAKE")
        with pytest.raises(KecoChemicalClientError) as exc_info:
            client.search(search_gubun="2", search_nm="")
        assert exc_info.value.code == "VALIDATION"
        assert not called  # API 호출 전에 차단

    def test_whitespace_search_nm_rejected(self):
        """P003: 공백만 있는 searchNm 도 차단."""
        from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
        client = KecoChemicalClient(
            get_fn=lambda url, params=None, timeout=25: (200, "{}"),
            _service_key="FAKE",
        )
        with pytest.raises(KecoChemicalClientError) as exc_info:
            client.search(search_gubun="2", search_nm="   ")
        assert exc_info.value.code == "VALIDATION"

    # --- P004: JSON-only ---
    def test_xml_return_type_rejected(self):
        """P004: returnType XML → VALIDATION 에러."""
        from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
        client = KecoChemicalClient(
            get_fn=lambda url, params=None, timeout=25: (200, "{}"),
            _service_key="FAKE",
        )
        with pytest.raises(KecoChemicalClientError) as exc_info:
            client.search(search_gubun="2", search_nm="test", return_type="XML")
        assert exc_info.value.code == "VALIDATION"


# ---------------------------------------------------------------------------
# parse 테스트
# ---------------------------------------------------------------------------

class TestParse:
    def test_parse_normal_response(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("normal_response.json")
        r = parse_keco_response(text)
        assert r.result_code == "200"
        assert r.total_count == "1"
        assert len(r.items) == 1
        item = r.items[0]
        assert item.sbstn_id == "KE-01-2-0001"
        assert item.cas_no == "7664-41-7"
        assert len(item.type_list) == 2

    def test_parse_items_empty_list(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("empty_response.json")
        r = parse_keco_response(text)
        assert r.items == []
        assert r.total_count == "0"

    def test_parse_items_null(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("null_items_response.json")
        r = parse_keco_response(text)
        assert r.items == []

    def test_parse_items_absent(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("absent_items_response.json")
        r = parse_keco_response(text)
        assert r.items == []

    def test_parse_one_chemical_zero_typelist(self):
        from services.keco_chemical.parse import parse_keco_response
        payload = {
            "header": {"resultCode": "200", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": [{
                    "sbstnId": "KE-TEST-001", "casNo": "50-00-0",
                    "korexst": "KE-TEST-001", "sbstnNmKor": "폴름알데히드",
                    "sbstnNmEng": "Formaldehyde", "sbstnNm2Kor": None, "sbstnNm2Eng": None,
                    "mlcfrm": "CH2O", "mlcwgt": "30.026", "typeList": []
                }],
                "numOfRows": "10", "pageNo": "1", "totalCount": "1"
            }
        }
        r = parse_keco_response(json.dumps(payload))
        assert len(r.items) == 1
        assert r.items[0].type_list == []

    def test_parse_one_chemical_one_typelist(self):
        from services.keco_chemical.parse import parse_keco_response
        payload = {
            "header": {"resultCode": "200", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": [{
                    "sbstnId": "KE-TEST-002", "casNo": "1-00-0", "korexst": None,
                    "sbstnNmKor": "테스트물질", "sbstnNmEng": "Test",
                    "sbstnNm2Kor": None, "sbstnNm2Eng": None, "mlcfrm": None, "mlcwgt": None,
                    "typeList": [{
                        "sbstnClsfTypeNm": "유독물질", "unqNo": "99-1-1",
                        "contInfo": "테스트", "excpInfo": None,
                        "ancmntYmd": "20000101", "ancmntInfo": None
                    }]
                }],
                "numOfRows": "10", "pageNo": "1", "totalCount": "1"
            }
        }
        r = parse_keco_response(json.dumps(payload))
        assert len(r.items[0].type_list) == 1
        assert r.items[0].type_list[0].unq_no == "99-1-1"

    def test_parse_one_chemical_multiple_typelist(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("multi_typelist_response.json")
        r = parse_keco_response(text)
        assert len(r.items[0].type_list) == 3

    def test_parse_korexst_preserved_as_raw(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("normal_response.json")
        r = parse_keco_response(text)
        assert r.items[0].korexst_raw == "KE-01-2-0001"

    def test_parse_no_ke_no_conversion(self):
        from services.keco_chemical.parse import KecoChemicalItem
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(KecoChemicalItem)}
        assert "ke_no" not in field_names
        assert "korexst_raw" in field_names

    def test_parse_error_on_empty_body(self):
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response("")
        assert exc_info.value.code == "JSON_EMPTY"

    def test_parse_error_on_malformed_json(self):
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response("{not valid json")
        assert exc_info.value.code == "JSON_MALFORMED"

    # --- P005: header fail-closed ---
    def test_parse_missing_header_raises(self):
        """P005: header 필드 없으면 KecoParseError."""
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        payload = json.dumps({"body": {"items": []}})
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response(payload)
        assert exc_info.value.code == "JSON_HEADER_MISSING"

    def test_parse_null_header_raises(self):
        """P005: header=null → KecoParseError."""
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        payload = json.dumps({"header": None, "body": {}})
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response(payload)
        assert exc_info.value.code == "JSON_HEADER_MISSING"

    def test_parse_missing_result_code_raises(self):
        """P005: resultCode 없으면 KecoParseError."""
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        payload = json.dumps({"header": {"resultMsg": "OK"}})
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response(payload)
        assert exc_info.value.code == "RESULT_CODE_MISSING"

    def test_parse_blank_result_code_raises(self):
        """P005: resultCode blank → KecoParseError."""
        from services.keco_chemical.parse import parse_keco_response, KecoParseError
        payload = json.dumps({"header": {"resultCode": "", "resultMsg": "OK"}})
        with pytest.raises(KecoParseError) as exc_info:
            parse_keco_response(payload)
        assert exc_info.value.code == "RESULT_CODE_MISSING"


# ---------------------------------------------------------------------------
# hash 테스트
# ---------------------------------------------------------------------------

class TestHash:
    def _make_item(self, extra_type: bool = False):
        from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact
        facts = [
            KecoRegulatoryFact("유독물질", "97-1-1", "함유량 0.1%", None, "19970101", "고시"),
        ]
        if extra_type:
            facts.append(KecoRegulatoryFact("사고대비물질", None, None, None, "20100101", None))
        return KecoChemicalItem(
            sbstn_id="KE-01-2-0001", cas_no="7664-41-7", korexst_raw="KE-01-2-0001",
            sbstn_nm_kor="암모니아", sbstn_nm_eng="Ammonia",
            sbstn_nm2_kor=None, sbstn_nm2_eng=None,
            mlcfrm="H3N", mlcwgt="17.031", type_list=facts,
        )

    def test_hash_deterministic(self):
        from services.keco_chemical.hash import chemical_content_hash
        item = self._make_item()
        assert chemical_content_hash(item) == chemical_content_hash(item)
        assert len(chemical_content_hash(item)) == 64

    def test_hash_typelist_order_change_same_hash(self):
        from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact
        from services.keco_chemical.hash import chemical_content_hash
        fact_a = KecoRegulatoryFact("유독물질", "97-1-1", "함유량 0.1%", None, "19970101", "고시")
        fact_b = KecoRegulatoryFact("사고대비물질", None, None, None, "20100101", None)
        def make(facts):
            return KecoChemicalItem(
                sbstn_id="KE-01-2-0001", cas_no="7664-41-7", korexst_raw="KE",
                sbstn_nm_kor="암모니아", sbstn_nm_eng="Ammonia",
                sbstn_nm2_kor=None, sbstn_nm2_eng=None,
                mlcfrm="H3N", mlcwgt="17.031", type_list=facts,
            )
        assert chemical_content_hash(make([fact_a, fact_b])) == chemical_content_hash(make([fact_b, fact_a]))

    def test_hash_different_content_different_hash(self):
        from services.keco_chemical.parse import KecoChemicalItem
        from services.keco_chemical.hash import chemical_content_hash
        def make(cas):
            return KecoChemicalItem(
                sbstn_id="KE-01", cas_no=cas, korexst_raw=None,
                sbstn_nm_kor="테스트", sbstn_nm_eng="Test",
                sbstn_nm2_kor=None, sbstn_nm2_eng=None,
                mlcfrm=None, mlcwgt=None, type_list=[],
            )
        assert chemical_content_hash(make("7664-41-7")) != chemical_content_hash(make("75-09-2"))

    def test_hash_is_sha256_hex(self):
        from services.keco_chemical.hash import chemical_content_hash
        h = chemical_content_hash(self._make_item())
        assert len(h) == 64
        int(h, 16)

    def test_hash_fact_excp_info_ancmnt_info_tie_invariant(self):
        """P010: excp_info / ancmnt_info만 다른 두 fact — 배열 순서 없이 hash 동일."""
        from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact
        from services.keco_chemical.hash import chemical_content_hash
        # 두 fact: sbstn_clsf_type_nm/unq_no/ancmnt_ymd/cont_info 모두 동일
        # excp_info 또는 ancmnt_info만 다름
        fact_a = KecoRegulatoryFact("유독체", "X-1", "내용A", "예외A", "20200101", "안내A")
        fact_b = KecoRegulatoryFact("유독체", "X-1", "내용A", "예외B", "20200101", "안내B")
        def make(facts):
            return KecoChemicalItem(
                sbstn_id="KE-HASH-TEST", cas_no="1-1-1", korexst_raw=None,
                sbstn_nm_kor=None, sbstn_nm_eng=None,
                sbstn_nm2_kor=None, sbstn_nm2_eng=None,
                mlcfrm=None, mlcwgt=None, type_list=facts,
            )
        # [a, b] vs [b, a] — hash 다름 (excp_info가 다른 별도 항목이므로 이 두는 다른 hash)
        # 판정: fact_a != fact_b이면 set이 다르면 hash 다름, 순서만 다르면 hash 동일
        h_ab = chemical_content_hash(make([fact_a, fact_b]))
        h_ba = chemical_content_hash(make([fact_b, fact_a]))
        # 배열 순서만 바본 것이므로 hash 동일
        assert h_ab == h_ba


# ---------------------------------------------------------------------------
# store 로직 테스트 (mock supabase — schema selector 패턴)
# ---------------------------------------------------------------------------

class TestStore:
    def _make_item(
        self,
        sbstn_id: str = "KE-TEST-001",
        cas_no: str = "7664-41-7",
        korexst_raw: str = "KE-TEST-001",
    ):
        from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact
        return KecoChemicalItem(
            sbstn_id=sbstn_id, cas_no=cas_no, korexst_raw=korexst_raw,
            sbstn_nm_kor="암모니아", sbstn_nm_eng="Ammonia",
            sbstn_nm2_kor=None, sbstn_nm2_eng=None,
            mlcfrm="H3N", mlcwgt="17.031",
            type_list=[
                __import__("services.keco_chemical.parse", fromlist=["KecoRegulatoryFact"]).KecoRegulatoryFact(
                    "유독물질", "97-1-1", "함유량", None, "19970101", "고시"
                ),
            ],
        )

    def _mock_supabase(
        self,
        existing_raw: bool = False,
        existing_chemical: Optional[dict] = None,
        existing_facts: bool = False,
    ):
        """P006: schema('msds_ref').table(...) 패턴 mock."""
        mock_client = MagicMock()
        mock_schema = MagicMock()
        mock_client.schema.return_value = mock_schema

        def make_chain(result_data):
            chain = MagicMock()
            chain.data = result_data
            q = MagicMock()
            q.select.return_value = q
            q.eq.return_value = q
            q.execute.return_value = chain
            return q

        raw_select_result = [{"id": "raw-1"}] if existing_raw else []
        raw_table = MagicMock()
        raw_table.select.return_value = make_chain(raw_select_result)
        insert_raw = MagicMock(); insert_raw.data = [{"id": "raw-new"}]
        raw_ins_q = MagicMock(); raw_ins_q.execute.return_value = insert_raw
        raw_table.insert.return_value = raw_ins_q
        update_raw = MagicMock(); update_raw.data = []
        raw_upd_q = MagicMock(); raw_upd_q.eq.return_value = raw_upd_q; raw_upd_q.execute.return_value = update_raw
        raw_table.update.return_value = raw_upd_q

        chem_select_data = [existing_chemical] if existing_chemical else []
        chem_table = MagicMock()
        chem_table.select.return_value = make_chain(chem_select_data)
        insert_chem = MagicMock(); insert_chem.data = [{"id": "chem-new-uuid"}]
        chem_ins_q = MagicMock(); chem_ins_q.execute.return_value = insert_chem
        chem_table.insert.return_value = chem_ins_q
        update_chem = MagicMock(); update_chem.data = []
        chem_upd_q = MagicMock(); chem_upd_q.eq.return_value = chem_upd_q; chem_upd_q.execute.return_value = update_chem
        chem_table.update.return_value = chem_upd_q

        facts_select_data = [{"id": "fact-1"}] if existing_facts else []
        facts_table = MagicMock()
        facts_table.select.return_value = make_chain(facts_select_data)
        insert_fact = MagicMock(); insert_fact.data = [{"id": "fact-new"}]
        fact_ins_q = MagicMock(); fact_ins_q.execute.return_value = insert_fact
        facts_table.insert.return_value = fact_ins_q

        run_table = MagicMock()
        run_insert_result = MagicMock(); run_insert_result.data = [{"id": "run-uuid-001"}]
        run_ins_q = MagicMock(); run_ins_q.execute.return_value = run_insert_result
        run_table.insert.return_value = run_ins_q
        run_upd_q = MagicMock(); run_upd_q.eq.return_value = run_upd_q; run_upd_q.execute.return_value = MagicMock()
        run_table.update.return_value = run_upd_q

        def side_effect_table(name):
            if name == "keco_raw_records":
                return raw_table
            if name == "keco_chemicals":
                return chem_table
            if name == "keco_regulatory_facts":
                return facts_table
            if name == "keco_ingestion_runs":
                return run_table
            return MagicMock()

        mock_schema.table.side_effect = side_effect_table
        return mock_client

    def test_store_new_chemical(self):
        from services.keco_chemical.store import KecoReferenceStore, STATUS_NEW
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            status, chemical_id = store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")
        assert status == STATUS_NEW
        assert chemical_id == "chem-new-uuid"

    def test_store_unchanged_chemical(self):
        from services.keco_chemical.store import KecoReferenceStore, STATUS_UNCHANGED
        from services.keco_chemical.hash import chemical_content_hash
        item = self._make_item()
        existing = {"id": "existing-uuid", "source_content_hash": chemical_content_hash(item)}
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=existing)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            status, chemical_id = store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")
        assert status == STATUS_UNCHANGED
        assert chemical_id == "existing-uuid"

    def test_store_changed_chemical(self):
        from services.keco_chemical.store import KecoReferenceStore, STATUS_CHANGED
        item = self._make_item()
        existing = {"id": "existing-uuid", "source_content_hash": "OLD_HASH_000"}
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=existing)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            status, chemical_id = store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")
        assert status == STATUS_CHANGED
        assert chemical_id == "existing-uuid"

    def test_store_no_duplicate_raw(self):
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_raw=True, existing_chemical=None)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")
        raw_table = mock_client.schema("msds_ref").table("keco_raw_records")
        raw_table.insert.assert_not_called()

    def test_store_no_duplicate_facts(self):
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_facts=True)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            count = store.upsert_regulatory_facts("chem-id-1", item.type_list)
        assert count == 0

    def test_store_korexst_raw_preserved(self):
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item(korexst_raw="KE-01-2-0001")
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None)
        inserted_data = {}
        def capture_insert(data):
            inserted_data.update(data)
            q = MagicMock()
            result = MagicMock(); result.data = [{"id": "chem-new"}]
            q.execute.return_value = result
            return q
        mock_client.schema("msds_ref").table("keco_chemicals").insert.side_effect = capture_insert
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-01-2-0001"}, item, "run-1")
        assert inserted_data.get("korexst_raw") == "KE-01-2-0001"
        assert "ke_no" not in inserted_data

    def test_store_facts_inserted_for_new(self):
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_facts=False)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            count = store.upsert_regulatory_facts("chem-id-1", item.type_list)
        assert count == 1

    # --- P006: schema selector used ---
    def test_store_uses_schema_selector(self):
        """P006: client.schema('msds_ref').table() 패턴 사용. qualified 문자열 미사용."""
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")
        # schema("msds_ref")이 호출되었어야 함
        mock_client.schema.assert_called_with("msds_ref")
        # client.table() 직접 호출되면 안 됨 (자격을 갼친 문자열 미사용 확인)
        mock_client.table.assert_not_called()

    # --- P009: blank source_record_id ---
    def test_store_blank_sbstn_id_raises(self):
        """P009: sbstnId blank → KecoStoreSourceRecordIdError."""
        from services.keco_chemical.store import KecoReferenceStore, KecoStoreSourceRecordIdError
        item = self._make_item(sbstn_id="")
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            with pytest.raises(KecoStoreSourceRecordIdError):
                store.upsert_chemical({"sbstnId": ""}, item, "run-1")

    def test_store_none_sbstn_id_raises(self):
        """P009: sbstnId None → KecoStoreSourceRecordIdError."""
        from services.keco_chemical.store import KecoReferenceStore, KecoStoreSourceRecordIdError
        item = self._make_item(sbstn_id=None)
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            with pytest.raises(KecoStoreSourceRecordIdError):
                store.upsert_chemical({}, item, "run-1")

    # --- P011: ingestion run lifecycle ---
    def test_start_run_returns_id(self):
        """P011: start_run → run_id 반환."""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            run_id = store.start_run(run_type="PROBE")
        assert run_id == "run-uuid-001"
        mock_client.schema.assert_called_with("msds_ref")

    def test_complete_run_calls_update(self):
        """P011: complete_run → COMPLETED status 업데이트."""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.complete_run("run-uuid-001", request_count=3, record_count=1)
        run_table = mock_client.schema("msds_ref").table("keco_ingestion_runs")
        run_table.update.assert_called_once()
        update_args = run_table.update.call_args[0][0]
        assert update_args["status"] == "COMPLETED"
        assert update_args["request_count"] == 3
        assert update_args["record_count"] == 1

    def test_fail_run_calls_update(self):
        """P011: fail_run → FAILED status 업데이트."""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.fail_run("run-uuid-001", error_code="TIMEOUT", error_message="timed out")
        run_table = mock_client.schema("msds_ref").table("keco_ingestion_runs")
        run_table.update.assert_called_once()
        update_args = run_table.update.call_args[0][0]
        assert update_args["status"] == "FAILED"
        assert update_args["error_code"] == "TIMEOUT"

    def test_fail_run_no_service_key_in_message(self):
        """P011: fail_run error_message에 serviceKey 포함 금지 (호출자 속성)."""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()
        mock_client = self._mock_supabase()
        stored_msg = {}
        run_table = mock_client.schema("msds_ref").table("keco_ingestion_runs")
        def capture_update(data):
            stored_msg.update(data)
            q = MagicMock(); q.eq.return_value = q; q.execute.return_value = MagicMock()
            return q
        run_table.update.side_effect = capture_update
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.fail_run("run-1", error_code="ERR", error_message="generic error, no key here")
        # serviceKey 대신 error_message는 caller가 직접 제어하므로 store는 포워드만
        assert stored_msg.get("error_message") == "generic error, no key here"

    # --- P012: raw last_seen_at ---
    def test_raw_last_seen_at_updated_on_reseen(self):
        """P012: 동일 raw payload 재조회 시 last_seen_at 갱신."""
        from services.keco_chemical.store import KecoReferenceStore
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_raw=True, existing_chemical=None)
        updated_data = {}
        raw_table = mock_client.schema("msds_ref").table("keco_raw_records")
        def capture_update(data):
            updated_data.update(data)
            q = MagicMock(); q.eq.return_value = q; q.execute.return_value = MagicMock()
            return q
        raw_table.update.side_effect = capture_update
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-2")
        assert "last_seen_at" in updated_data
        assert updated_data["last_seen_run_id"] == "run-2"

    # --- persist_item orchestration ---
    def test_persist_item_returns_result(self):
        from services.keco_chemical.store import KecoReferenceStore, PersistItemResult, STATUS_NEW
        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None, existing_facts=False)
        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            result = store.persist_item({"sbstnId": "KE-TEST-001"}, item, "run-1")
        assert isinstance(result, PersistItemResult)
        assert result.status == STATUS_NEW
        assert result.chemical_id == "chem-new-uuid"
        assert result.inserted_fact_count == 1


# ---------------------------------------------------------------------------
# probe 테스트
# ---------------------------------------------------------------------------

class TestProbe:
    def test_probe_blocked_no_key(self):
        from services.keco_chemical.probe import run_probe, PROBE_BLOCKED_NO_KEY
        from services.keco_chemical.client import KecoChemicalClient
        client = MagicMock(spec=KecoChemicalClient)
        with patch.dict(os.environ, {}, clear=True):
            env_backup = os.environ.pop("KECO_API_SERVICE_KEY", None)
            try:
                result = run_probe(client)
            finally:
                if env_backup is not None:
                    os.environ["KECO_API_SERVICE_KEY"] = env_backup
        assert result.status == PROBE_BLOCKED_NO_KEY

    def test_probe_max_calls_cap(self):
        from services.keco_chemical.probe import PROBE_MAX_CALLS
        from services.keco_chemical.contract import PROBE_MAX_CALLS as CONTRACT_MAX
        assert PROBE_MAX_CALLS == CONTRACT_MAX
        assert PROBE_MAX_CALLS == 3
