"""OBJ-CHEM-02 contract tests: official MSDS adapter, identity, hash, snapshot, schema."""
from __future__ import annotations

import inspect
import os
import pathlib
import re
import uuid

import pytest

from services.knowledge_graph_rules import DISABLED_RELATIONS
from services.kosha_msds.client import (
    KoshaMsdsClient,
    KoshaMsdsClientError,
    KoshaMsdsTransportError,
    redact_secret,
)
from services.kosha_msds.contract import (
    BASE_URL,
    DATASET_ID,
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    ENUMERATION_PROBE,
    IDENTITY_HOLD,
    IDENTITY_READY,
    LIST_OPERATION,
    PUBLISH_PUBLISHED_FULL,
    SOURCE_ID,
)
from services.kosha_msds.hash import source_content_hash
from services.kosha_msds.identity import (
    candidate_from_list_item,
    identity_status_for_chem_id,
    is_chem_content_id,
    new_content_id,
)
from services.kosha_msds.parse import (
    KoshaMsdsParseError,
    KoshaMsdsResultError,
    parse_list_xml,
    parse_section_xml,
)
from services.kosha_msds.snapshot import (
    KoshaMsdsSnapshotError,
    SnapshotSpec,
    assert_probe_not_full,
    can_publish_global_current,
    new_probe_spec,
    validate_enumeration_mode,
)
import routers.kosha_apis as kosha_apis

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SQL = HERE.parent / "supabase" / "migrations" / "20260914_kosha_msds_catalog.sql"
SECRET = "LIVE_SERVICE_KEY_MUST_NEVER_LEAK"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).lower()


def _client(handler) -> KoshaMsdsClient:
    def fake_get(url, params=None, headers=None, timeout=25):
        return handler(url, params, timeout)

    return KoshaMsdsClient(
        get_fn=fake_get,
        service_key=SECRET,
        timeout_seconds=9,
        max_attempts=2,
    )


# ── Search ──────────────────────────────────────────────


def test_search_uses_official_parameter_names():
    captured = {}

    def handler(url, params, timeout):
        captured["url"] = url
        captured["params"] = dict(params)
        captured["timeout"] = timeout
        return 200, fx("benzene_list.xml")

    result = _client(handler).search(search_cnd=1, search_wrd="71-43-2", page_no=1, num_of_rows=10)
    assert captured["url"] == f"{BASE_URL}/{LIST_OPERATION}"
    assert captured["params"]["searchCnd"] == "1"
    assert captured["params"]["searchWrd"] == "71-43-2"
    assert captured["params"]["pageNo"] == "1"
    assert captured["params"]["numOfRows"] == "10"
    assert captured["params"]["serviceKey"] == SECRET
    assert "chemNm" not in captured["params"]
    assert "casNo" not in captured["params"]
    assert "kmcNo" not in captured["params"]
    assert captured["timeout"] == 9
    assert result.total_count == 1
    assert result.candidates[0].chem_id == "001008"


def test_pagination_and_total_count_preserved():
    result = parse_list_xml(fx("benzene_name_search.xml"))
    assert result.page_no == 1
    assert result.num_of_rows == 20
    assert result.total_count == 777
    assert len(result.items) == 3
    assert result.total_count != len(result.items)


def test_zero_results():
    result = parse_list_xml(fx("empty_list.xml"))
    assert result.ok
    assert result.total_count == 0
    assert result.items == []


def test_substring_results_not_exactified():
    parsed = parse_list_xml(fx("thinner_name_search.xml"))
    names = [item.get("chemNameKor") for item in parsed.items]
    assert "신나" not in names
    assert parsed.total_count == 2
    client = _client(lambda url, params, timeout: (200, fx("thinner_name_search.xml")))
    search = client.search(search_cnd=0, search_wrd="신나")
    assert len(search.candidates) == 2
    assert all(c.chem_id for c in search.candidates)
    assert not hasattr(search, "selected")
    assert search.candidates[0].chem_id != search.candidates[1].chem_id


def test_multiple_name_candidates_preserved():
    search = _client(lambda u, p, t: (200, fx("benzene_name_search.xml"))).search(
        search_cnd=0, search_wrd="벤젠"
    )
    ids = [c.chem_id for c in search.candidates]
    names = [c.chemical_name_ko for c in search.candidates]
    assert ids == ["001008", "001089", "001633"]
    assert names == ["벤젠", "에틸벤젠", "아조벤젠"]
    assert search.total_count == 777


# ── Identity ─────────────────────────────────────────────


def test_chem_id_is_stable_source_key():
    item = parse_list_xml(fx("benzene_list.xml")).items[0]
    cand = candidate_from_list_item(item)
    assert cand.chem_id == "001008"
    assert cand.source_key == "001008"
    assert cand.identity_status == IDENTITY_READY
    assert cand.cas_no == "71-43-2"


def test_cas_null_accepted_and_not_hold():
    item = parse_list_xml(fx("cas_null_047134_list.xml")).items[0]
    assert "casNo" not in item
    cand = candidate_from_list_item(item)
    assert cand.chem_id == "047134"
    assert cand.cas_no is None
    assert cand.identity_status == IDENTITY_READY
    assert identity_status_for_chem_id(None) == IDENTITY_HOLD
    assert identity_status_for_chem_id("047134") == IDENTITY_READY


def test_cas_never_primary_key_in_sql_and_model():
    sql = _norm(SQL.read_text(encoding="utf-8"))
    assert "cas_no text" in sql
    assert "unique (cas_no)" not in sql
    assert "cas_no not null" not in sql
    assert "unique (source_id, source_key)" in sql
    assert "chem_id text not null" in sql
    cand_a = candidate_from_list_item({"chemId": "1", "casNo": "71-43-2", "chemNameKor": "벤젠"})
    cand_b = candidate_from_list_item({"chemId": "2", "casNo": "71-43-2", "chemNameKor": "벤젠-별칭"})
    assert cand_a.cas_no == cand_b.cas_no
    assert cand_a.chem_id != cand_b.chem_id


def test_duplicate_names_preserved_as_separate_chem_ids():
    search = _client(lambda u, p, t: (200, fx("benzene_name_search.xml"))).search(
        search_cnd=0, search_wrd="벤젠"
    )
    assert search.candidates[0].chemical_name_ko.endswith("벤젠")
    assert search.candidates[1].chemical_name_ko.endswith("벤젠")
    assert search.candidates[0].chem_id != search.candidates[1].chem_id


def test_content_id_immutable_namespace():
    cid = new_content_id(lambda: uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
    assert cid == "CHEM:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert is_chem_content_id(cid)
    assert not is_chem_content_id("CSI:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert not is_chem_content_id("001008")


# ── Detail ───────────────────────────────────────────────


def test_sixteen_of_sixteen_complete():
    def handler(url, params, timeout):
        assert params["chemId"] == "001008"
        assert "kmcNo" not in params
        section = url.rsplit("getChemDetail", 1)[1]
        return 200, fx(f"benzene_detail_{section}.xml")

    detail = _client(handler).get_full_detail("001008")
    assert detail.detail_status == DETAIL_COMPLETE
    assert detail.failed_sections == ()
    assert len(detail.sections) == 16
    assert detail.sections["01"].status == DETAIL_COMPLETE
    assert detail.sections["04"].status == DETAIL_EMPTY_BUT_VALID
    assert detail.sections["08"].items[0].get("itemDetail") is None


def test_fifteen_of_sixteen_failure_incomplete():
    def handler(url, params, timeout):
        section = url.rsplit("getChemDetail", 1)[1]
        if section == "15":
            return 200, fx("error_result.xml")
        return 200, fx(f"benzene_detail_{section}.xml")

    detail = _client(handler).get_full_detail("001008")
    assert detail.detail_status == DETAIL_INCOMPLETE
    assert detail.failed_sections == (15,)
    assert "15" not in detail.sections
    assert len(detail.sections) == 15


def test_empty_but_success_section_valid():
    parsed = parse_section_xml(fx("benzene_detail_04.xml"))
    assert parsed.ok
    assert parsed.empty_but_valid
    fetched = _client(lambda u, p, t: (200, fx("benzene_detail_04.xml"))).get_detail_section("001008", 4)
    assert fetched.status == DETAIL_EMPTY_BUT_VALID


def test_result_code_not_success_fails():
    with pytest.raises(KoshaMsdsResultError) as exc:
        parse_list_xml(fx("error_result.xml"))
    assert exc.value.result_code == "10"
    with pytest.raises(KoshaMsdsClientError):
        _client(lambda u, p, t: (200, fx("error_result.xml"))).search(search_cnd=1, search_wrd="x")


def test_http_200_is_not_enough():
    with pytest.raises(KoshaMsdsClientError):
        _client(lambda u, p, t: (200, fx("error_result.xml"))).get_detail_section("001008", "01")


def test_malformed_xml_fails():
    with pytest.raises(KoshaMsdsParseError) as exc:
        parse_list_xml(fx("malformed.xml"))
    assert exc.value.code == "XML_MALFORMED"


def test_timeout_fails():
    def handler(url, params, timeout):
        raise TimeoutError("timed out")

    with pytest.raises(KoshaMsdsTransportError):
        _client(handler).search(search_cnd=1, search_wrd="71-43-2")


def test_unknown_section_rejected():
    client = _client(lambda u, p, t: (200, fx("benzene_detail_01.xml")))
    with pytest.raises(KoshaMsdsClientError) as exc:
        client.get_detail_section("001008", 17)
    assert exc.value.code == "SECTION_INVALID"
    with pytest.raises(KoshaMsdsClientError):
        client.get_detail_section("001008", "00")


def test_detail_requires_chem_id_not_search_row():
    client = _client(lambda u, p, t: (200, fx("benzene_detail_01.xml")))
    with pytest.raises(KoshaMsdsClientError) as exc:
        client.get_detail_section("  ", 1)
    assert exc.value.code == "CHEM_ID_REQUIRED"


# ── Hash ────────────────────────────────────────────────


def _benzene_sections():
    return {f"{n:02d}": parse_section_xml(fx(f"benzene_detail_{n:02d}.xml")).items for n in range(1, 17)}


def test_same_payload_same_hash():
    item = parse_list_xml(fx("benzene_list.xml")).items[0]
    sections = _benzene_sections()
    a = source_content_hash("001008", item, sections)
    b = source_content_hash("001008", item, sections)
    assert a == b
    assert len(a) == 64


def test_fetch_timestamp_change_same_hash():
    item = parse_list_xml(fx("benzene_list.xml")).items[0]
    sections = _benzene_sections()
    left = source_content_hash("001008", {**item, "fetched_at": "2026-01-01T00:00:00+09:00"}, sections)
    right = source_content_hash("001008", {**item, "fetched_at": "2026-09-13T00:00:00+09:00"}, sections)
    assert left == right


def test_source_field_change_changes_hash():
    item = parse_list_xml(fx("benzene_list.xml")).items[0]
    sections = _benzene_sections()
    base = source_content_hash("001008", item, sections)
    changed = source_content_hash("001008", {**item, "lastDate": "1999-01-01"}, sections)
    assert base != changed


def test_section_content_change_changes_hash():
    item = parse_list_xml(fx("benzene_list.xml")).items[0]
    sections = _benzene_sections()
    base = source_content_hash("001008", item, sections)
    mutated = dict(sections)
    mutated["02"] = [{**sections["02"][0], "itemDetail": "changed"}]
    assert source_content_hash("001008", item, mutated) != base


# ── Snapshot ─────────────────────────────────────────────


def test_probe_cannot_become_full_official():
    with pytest.raises(KoshaMsdsSnapshotError) as exc:
        validate_enumeration_mode(ENUMERATION_FULL_OFFICIAL, chem02=True)
    assert exc.value.code == "ENUMERATION_FORBIDDEN"
    spec = SnapshotSpec(
        enumeration_mode=ENUMERATION_PROBE,
        status="COMPLETED",
        publish_state=PUBLISH_PUBLISHED_FULL,
    )
    with pytest.raises(KoshaMsdsSnapshotError) as exc2:
        assert_probe_not_full(spec)
    assert exc2.value.code == "PROBE_CANNOT_PUBLISH_FULL"
    assert can_publish_global_current(spec) is False


def test_partial_snapshot_cannot_publish_global_current():
    probe = new_probe_spec()
    assert probe.enumeration_mode == ENUMERATION_PROBE
    assert probe.expected_count is None
    assert can_publish_global_current(probe) is False
    completed_probe = SnapshotSpec(
        enumeration_mode=ENUMERATION_PROBE,
        status="COMPLETED",
        publish_state="NOT_PUBLISHED",
    )
    assert can_publish_global_current(completed_probe) is False


def test_unofficial_expected_count_forbidden():
    spec = SnapshotSpec(
        enumeration_mode=ENUMERATION_PROBE,
        status="RUNNING",
        expected_count=20568,
    )
    with pytest.raises(KoshaMsdsSnapshotError) as exc:
        assert_probe_not_full(spec)
    assert exc.value.code == "EXPECTED_COUNT_FORBIDDEN"


# ── Schema ───────────────────────────────────────────────


def test_schema_sql_contract():
    sql = SQL.read_text(encoding="utf-8")
    n = _norm(sql)
    for table in (
        "kosha_msds_chemicals",
        "kosha_msds_sections",
        "kosha_msds_snapshots",
        "kosha_msds_snapshot_items",
    ):
        assert f"create table if not exists public.{table}" in n
    assert "create or replace view public.kosha_msds_current" in n
    assert "enumeration_mode = 'full_official'" in n
    assert "publish_state = 'published_full'" in n
    assert "check (section_no between 1 and 16)" in n
    assert "unique (chemical_id, section_no)" in n
    assert "alter table public.factory_materials" not in n
    assert "alter table public.master_dangerous_goods" not in n
    assert "create table if not exists public.factory_materials" not in n
    assert "knowledge_relation" not in n
    assert "csi_accident" not in n
    assert "drop table" not in n
    assert "enable row level security" in n
    assert "create policy" not in n
    assert "grant select on public.kosha_msds_current to service_role" in n
    assert "grant select on public.kosha_msds_current to anon" not in n
    assert "revoke delete" in n
    assert SOURCE_ID.lower() in n or "kosha_msds" in n
    assert "cas_no text," in n
    assert DATASET_ID in sql


def test_schema_file_location():
    rel = SQL.relative_to(HERE.parent)
    assert str(rel) == "supabase/migrations/20260914_kosha_msds_catalog.sql"


# ── Existing /kosha/msds audit freeze + Graph boundary ───


def test_existing_kosha_msds_route_found_and_not_rewritten():
    src = inspect.getsource(kosha_apis)
    assert 'prefix="/kosha"' in src or "prefix='/kosha'" in src
    assert "@router.get(\"/msds\")" in src
    assert 'params["chemNm"]' in src
    assert 'params["casNo"]' in src
    assert '{"kmcNo": kmc_no}' in src
    assert "searchCnd" not in src
    assert "searchWrd" not in src
    # new client is separate
    from services.kosha_msds.client import KoshaMsdsClient as _C

    assert inspect.getsource(_C.search).find("searchCnd") != -1


def test_graph_chemical_remains_disabled():
    assert "chemical" in DISABLED_RELATIONS
    rules = (HERE.parent / "services" / "knowledge_graph_rules.py").read_text(encoding="utf-8")
    assert 'DISABLED_RELATIONS = frozenset({"chemical", "legal_obligation"})' in rules


def test_service_key_never_in_fixtures_or_errors():
    for path in FIXTURES.glob("*"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "serviceKey" not in text
        assert SECRET not in text
    masked = redact_secret(f"{BASE_URL}/getChemList?serviceKey={SECRET}&searchCnd=1", SECRET)
    assert SECRET not in masked
    assert "[REDACTED]" in masked
