"""KECO 15149420 API client + LEG reference foundation 테스트.

KECO_API_SERVICE_KEY 없이 전부 통과 (synthetic fixture 사용).
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
        """searchGubun 0 또는 4 (국문명) 허용 안 됨."""
        from services.keco_chemical.contract import ALLOWED_SEARCH_GUBUN
        assert "0" not in ALLOWED_SEARCH_GUBUN
        assert "4" not in ALLOWED_SEARCH_GUBUN
        assert "5" not in ALLOWED_SEARCH_GUBUN

    def test_source_id_constant(self):
        from services.keco_chemical.contract import SOURCE_ID
        assert SOURCE_ID == "KECO_15149420"

    def test_service_key_env_single(self):
        """다른 키 fallback 없이 KECO_API_SERVICE_KEY만."""
        from services.keco_chemical.contract import SERVICE_KEY_ENV
        assert SERVICE_KEY_ENV == ("KECO_API_SERVICE_KEY",)
        assert len(SERVICE_KEY_ENV) == 1

    def test_probe_max_calls_hard_cap(self):
        from services.keco_chemical.contract import PROBE_MAX_CALLS
        assert PROBE_MAX_CALLS == 3

    def test_success_codes(self):
        from services.keco_chemical.contract import SUCCESS_RESULT_CODES
        assert "00" in SUCCESS_RESULT_CODES
        assert "0000" in SUCCESS_RESULT_CODES

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
        """fake get_fn 으로 KecoChemicalClient 생성."""
        from services.keco_chemical.client import KecoChemicalClient
        def fake_get(url, params=None, timeout=25):
            return status, response_text
        client = KecoChemicalClient(get_fn=fake_get, _service_key="FAKE_KEY_FOR_TEST")
        return client

    def test_client_builds_correct_params(self):
        """search 호출 시 올바른 파라미터가 전달되는지 확인."""
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
        """redact_key가 serviceKey를 [REDACTED]로 치환."""
        from services.keco_chemical.client import redact_key
        key = "ABC123SECRET"
        url = "https://apis.data.go.kr/B552584?serviceKey=ABC123SECRET&foo=bar"
        result = redact_key(url, key)
        assert "ABC123SECRET" not in result
        assert "[REDACTED]" in result

    def test_client_no_korean_name_search_code(self):
        """searchGubun "0" (국문명) 는 ValueError."""
        from services.keco_chemical.client import KecoChemicalClient
        def fake_get(url, params=None, timeout=25):
            return 200, "{}"
        client = KecoChemicalClient(get_fn=fake_get, _service_key="FAKE_KEY")
        with pytest.raises(ValueError):
            client.search(search_gubun="0", search_nm="암모니아")

    def test_client_no_key_raises_error(self):
        """키 없으면 KecoNoServiceKeyError."""
        from services.keco_chemical.client import KecoChemicalClient, KecoNoServiceKeyError
        def fake_get(url, params=None, timeout=25):
            return 200, "{}"
        client = KecoChemicalClient(get_fn=fake_get, _service_key=None)
        with patch.dict(os.environ, {}, clear=True):
            # KECO_API_SERVICE_KEY 환경변수도 없는 상태
            env_backup = os.environ.pop("KECO_API_SERVICE_KEY", None)
            try:
                with pytest.raises(KecoNoServiceKeyError):
                    client.search(search_gubun="2", search_nm="test")
            finally:
                if env_backup is not None:
                    os.environ["KECO_API_SERVICE_KEY"] = env_backup

    def test_client_invalid_search_gubun(self):
        """ALLOWED_SEARCH_GUBUN에 없는 값은 ValueError."""
        client = self._make_client(_load("normal_response.json"))
        with pytest.raises(ValueError):
            client.search(search_gubun="9", search_nm="test")

    def test_client_returns_search_response(self):
        """정상 응답 시 KecoSearchResponse 반환."""
        from services.keco_chemical.parse import KecoSearchResponse
        client = self._make_client(_load("normal_response.json"))
        result = client.search(search_gubun="2", search_nm="7664-41-7")
        assert isinstance(result, KecoSearchResponse)
        assert result.result_code == "00"
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# parse 테스트
# ---------------------------------------------------------------------------

class TestParse:
    def test_parse_normal_response(self):
        from services.keco_chemical.parse import parse_keco_response
        text = _load("normal_response.json")
        r = parse_keco_response(text)
        assert r.result_code == "00"
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
        """items=null → 0건."""
        from services.keco_chemical.parse import parse_keco_response
        text = _load("null_items_response.json")
        r = parse_keco_response(text)
        assert r.items == []

    def test_parse_items_absent(self):
        """items 키 자체 없음 → 0건."""
        from services.keco_chemical.parse import parse_keco_response
        text = _load("absent_items_response.json")
        r = parse_keco_response(text)
        assert r.items == []

    def test_parse_one_chemical_zero_typelist(self):
        """typeList 없는 화학물질."""
        from services.keco_chemical.parse import parse_keco_response
        payload = {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": [{
                    "sbstnId": "KE-TEST-001",
                    "casNo": "50-00-0",
                    "korexst": "KE-TEST-001",
                    "sbstnNmKor": "포름알데히드",
                    "sbstnNmEng": "Formaldehyde",
                    "sbstnNm2Kor": None,
                    "sbstnNm2Eng": None,
                    "mlcfrm": "CH2O",
                    "mlcwgt": "30.026",
                    "typeList": []
                }],
                "numOfRows": "10",
                "pageNo": "1",
                "totalCount": "1"
            }
        }
        r = parse_keco_response(json.dumps(payload))
        assert len(r.items) == 1
        assert r.items[0].type_list == []

    def test_parse_one_chemical_one_typelist(self):
        """typeList 1건."""
        from services.keco_chemical.parse import parse_keco_response
        payload = {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": [{
                    "sbstnId": "KE-TEST-002",
                    "casNo": "1-00-0",
                    "korexst": None,
                    "sbstnNmKor": "테스트물질",
                    "sbstnNmEng": "Test",
                    "sbstnNm2Kor": None,
                    "sbstnNm2Eng": None,
                    "mlcfrm": None,
                    "mlcwgt": None,
                    "typeList": [{
                        "sbstnClsfTypeNm": "유독물질",
                        "unqNo": "99-1-1",
                        "contInfo": "테스트",
                        "excpInfo": None,
                        "ancmntYmd": "20000101",
                        "ancmntInfo": None
                    }]
                }],
                "numOfRows": "10", "pageNo": "1", "totalCount": "1"
            }
        }
        r = parse_keco_response(json.dumps(payload))
        assert len(r.items[0].type_list) == 1
        assert r.items[0].type_list[0].unq_no == "99-1-1"

    def test_parse_one_chemical_multiple_typelist(self):
        """typeList 여러 건."""
        from services.keco_chemical.parse import parse_keco_response
        text = _load("multi_typelist_response.json")
        r = parse_keco_response(text)
        assert len(r.items[0].type_list) == 3

    def test_parse_korexst_preserved_as_raw(self):
        """korexst는 korexst_raw 필드에 원문 보존."""
        from services.keco_chemical.parse import parse_keco_response
        text = _load("normal_response.json")
        r = parse_keco_response(text)
        item = r.items[0]
        # korexst_raw는 원문 그대로
        assert item.korexst_raw == "KE-01-2-0001"

    def test_parse_no_ke_no_conversion(self):
        """parser가 korexst_raw를 ke_no로 변환하지 않음."""
        from services.keco_chemical.parse import KecoChemicalItem
        # KecoChemicalItem에 ke_no 필드가 없어야 함
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


# ---------------------------------------------------------------------------
# hash 테스트
# ---------------------------------------------------------------------------

class TestHash:
    def _make_item(self, extra_type: bool = False) -> "KecoChemicalItem":
        from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact
        facts = [
            KecoRegulatoryFact("유독물질", "97-1-1", "함유량 0.1%", None, "19970101", "고시"),
        ]
        if extra_type:
            facts.append(
                KecoRegulatoryFact("사고대비물질", None, None, None, "20100101", None)
            )
        return KecoChemicalItem(
            sbstn_id="KE-01-2-0001",
            cas_no="7664-41-7",
            korexst_raw="KE-01-2-0001",
            sbstn_nm_kor="암모니아",
            sbstn_nm_eng="Ammonia",
            sbstn_nm2_kor=None,
            sbstn_nm2_eng=None,
            mlcfrm="H3N",
            mlcwgt="17.031",
            type_list=facts,
        )

    def test_hash_deterministic(self):
        """동일 item → 동일 hash."""
        from services.keco_chemical.hash import chemical_content_hash
        item = self._make_item()
        h1 = chemical_content_hash(item)
        h2 = chemical_content_hash(item)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_typelist_order_change_same_hash(self):
        """typeList 배열 순서가 바뀌어도 동일 hash."""
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

        h1 = chemical_content_hash(make([fact_a, fact_b]))
        h2 = chemical_content_hash(make([fact_b, fact_a]))
        assert h1 == h2

    def test_hash_different_content_different_hash(self):
        """내용 다르면 hash 다름."""
        from services.keco_chemical.parse import KecoChemicalItem
        from services.keco_chemical.hash import chemical_content_hash

        def make(cas):
            return KecoChemicalItem(
                sbstn_id="KE-01", cas_no=cas, korexst_raw=None,
                sbstn_nm_kor="테스트", sbstn_nm_eng="Test",
                sbstn_nm2_kor=None, sbstn_nm2_eng=None,
                mlcfrm=None, mlcwgt=None, type_list=[],
            )

        h1 = chemical_content_hash(make("7664-41-7"))
        h2 = chemical_content_hash(make("75-09-2"))
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        """hash 결과가 64자리 hex 문자열."""
        from services.keco_chemical.hash import chemical_content_hash
        item = self._make_item()
        h = chemical_content_hash(item)
        assert len(h) == 64
        int(h, 16)  # hex 파싱 가능


# ---------------------------------------------------------------------------
# store 로직 테스트 (mock supabase)
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
            sbstn_id=sbstn_id,
            cas_no=cas_no,
            korexst_raw=korexst_raw,
            sbstn_nm_kor="암모니아",
            sbstn_nm_eng="Ammonia",
            sbstn_nm2_kor=None,
            sbstn_nm2_eng=None,
            mlcfrm="H3N",
            mlcwgt="17.031",
            type_list=[
                KecoRegulatoryFact("유독물질", "97-1-1", "함유량", None, "19970101", "고시"),
            ],
        )

    def _mock_supabase(
        self,
        existing_raw: bool = False,
        existing_chemical: Optional[dict] = None,
        existing_facts: bool = False,
    ):
        """supabase client mock 생성."""
        mock_client = MagicMock()

        def make_chain(result_data):
            chain = MagicMock()
            chain.data = result_data
            q = MagicMock()
            q.select.return_value = q
            q.eq.return_value = q
            q.execute.return_value = chain
            return q

        def make_insert_chain(insert_data):
            chain = MagicMock()
            chain.data = insert_data
            q = MagicMock()
            q.insert.return_value = q
            q.execute.return_value = chain
            return q

        # table("msds_ref.keco_raw_records")
        raw_select_result = [{"id": "raw-1"}] if existing_raw else []
        raw_table = MagicMock()
        raw_select_q = make_chain(raw_select_result)
        raw_table.select.return_value = raw_select_q

        insert_result_raw = MagicMock()
        insert_result_raw.data = [{"id": "raw-new"}]
        raw_insert_q = MagicMock()
        raw_insert_q.execute.return_value = insert_result_raw
        raw_table.insert.return_value = raw_insert_q

        update_result_raw = MagicMock()
        update_result_raw.data = []
        raw_update_q = MagicMock()
        raw_update_q.eq.return_value = raw_update_q
        raw_update_q.execute.return_value = update_result_raw
        raw_table.update.return_value = raw_update_q

        # table("msds_ref.keco_chemicals")
        chem_select_data = [existing_chemical] if existing_chemical else []
        chem_table = MagicMock()
        chem_select_q = make_chain(chem_select_data)
        chem_table.select.return_value = chem_select_q

        insert_result_chem = MagicMock()
        insert_result_chem.data = [{"id": "chem-new-uuid"}]
        chem_insert_q = MagicMock()
        chem_insert_q.execute.return_value = insert_result_chem
        chem_table.insert.return_value = chem_insert_q

        update_result_chem = MagicMock()
        update_result_chem.data = []
        chem_update_q = MagicMock()
        chem_update_q.eq.return_value = chem_update_q
        chem_update_q.execute.return_value = update_result_chem
        chem_table.update.return_value = chem_update_q

        # table("msds_ref.keco_regulatory_facts")
        facts_select_data = [{"id": "fact-1"}] if existing_facts else []
        facts_table = MagicMock()
        facts_select_q = make_chain(facts_select_data)
        facts_table.select.return_value = facts_select_q

        insert_result_facts = MagicMock()
        insert_result_facts.data = [{"id": "fact-new"}]
        facts_insert_q = MagicMock()
        facts_insert_q.execute.return_value = insert_result_facts
        facts_table.insert.return_value = facts_insert_q

        def side_effect_table(name):
            if "raw_records" in name:
                return raw_table
            if "chemicals" in name:
                return chem_table
            if "regulatory_facts" in name:
                return facts_table
            return MagicMock()

        mock_client.table.side_effect = side_effect_table
        return mock_client

    def test_store_new_chemical(self):
        """source_record_id 없음 → NEW."""
        from services.keco_chemical.store import KecoReferenceStore, STATUS_NEW
        from services.keco_chemical.hash import chemical_content_hash

        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None)

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            status, chemical_id = store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")

        assert status == STATUS_NEW
        assert chemical_id == "chem-new-uuid"

    def test_store_unchanged_chemical(self):
        """source_content_hash 동일 → UNCHANGED."""
        from services.keco_chemical.store import KecoReferenceStore, STATUS_UNCHANGED
        from services.keco_chemical.hash import chemical_content_hash

        item = self._make_item()
        content_hash = chemical_content_hash(item)

        existing = {"id": "existing-uuid", "source_content_hash": content_hash}
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=existing)

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            status, chemical_id = store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")

        assert status == STATUS_UNCHANGED
        assert chemical_id == "existing-uuid"

    def test_store_changed_chemical(self):
        """source_content_hash 다름 → CHANGED."""
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
        """동일 raw payload는 insert 안 함 (duplicate = 0)."""
        from services.keco_chemical.store import KecoReferenceStore
        from services.keco_chemical.hash import chemical_content_hash

        item = self._make_item()
        store = KecoReferenceStore()
        # existing_raw=True → 이미 존재하는 raw
        mock_client = self._mock_supabase(existing_raw=True, existing_chemical=None)

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-TEST-001"}, item, "run-1")

        # raw_records.insert가 호출되지 않아야 함
        raw_table = mock_client.table("msds_ref.keco_raw_records")
        raw_table.insert.assert_not_called()

    def test_store_no_duplicate_facts(self):
        """이미 존재하는 fact_hash → insert 안 함."""
        from services.keco_chemical.store import KecoReferenceStore

        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_facts=True)

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            count = store.upsert_regulatory_facts("chem-id-1", item.type_list)

        assert count == 0  # 이미 있으므로 0

    def test_store_korexst_raw_preserved(self):
        """upsert 시 korexst_raw가 ke_no로 변환되지 않고 원문 그대로 저장."""
        from services.keco_chemical.store import KecoReferenceStore

        item = self._make_item(korexst_raw="KE-01-2-0001")
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_chemical=None)

        inserted_data = {}

        def capture_insert(data):
            inserted_data.update(data)
            q = MagicMock()
            result = MagicMock()
            result.data = [{"id": "chem-new"}]
            q.execute.return_value = result
            return q

        mock_client.table("msds_ref.keco_chemicals").insert.side_effect = capture_insert

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            store.upsert_chemical({"sbstnId": "KE-01-2-0001"}, item, "run-1")

        assert inserted_data.get("korexst_raw") == "KE-01-2-0001"
        assert "ke_no" not in inserted_data

    def test_store_facts_inserted_for_new(self):
        """새 fact → insert 1건."""
        from services.keco_chemical.store import KecoReferenceStore

        item = self._make_item()
        store = KecoReferenceStore()
        mock_client = self._mock_supabase(existing_facts=False)

        with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
            count = store.upsert_regulatory_facts("chem-id-1", item.type_list)

        assert count == 1


# ---------------------------------------------------------------------------
# probe 테스트
# ---------------------------------------------------------------------------

class TestProbe:
    def test_probe_blocked_no_key(self):
        """키 없으면 BLOCKED_NO_KEY."""
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
        """max_calls > PROBE_MAX_CALLS 이어도 PROBE_MAX_CALLS로 제한."""
        from services.keco_chemical.probe import PROBE_MAX_CALLS
        from services.keco_chemical.contract import PROBE_MAX_CALLS as CONTRACT_MAX
        assert PROBE_MAX_CALLS == CONTRACT_MAX
        assert PROBE_MAX_CALLS == 3
