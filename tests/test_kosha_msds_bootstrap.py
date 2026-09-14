"""CHEM-04 PATCH-4 bootstrap seed, official current index, deterministic join. Mock only."""
from __future__ import annotations

import json
import pathlib

import pytest

from services.kosha_msds.api_validate import (
    ApiValidationError,
    assert_call_budget,
    assert_quota_window_open,
    run_identity_validation,
)
from services.kosha_msds.bootstrap import (
    BootstrapIdentity,
    BootstrapSeedError,
    crosscheck_live_discovered,
    extract_identity_jsonl,
    identity_from_raw,
    load_identity_rows,
    require_padded_chem_id,
)
from services.kosha_msds.client import KoshaMsdsClient
from services.kosha_msds.contract import (
    DISCOVERY_PRIMARY_ENUMERATION,
    MATCH_AMBIGUOUS,
    MATCH_CAS_EXACT,
    MATCH_DIRECT_OFFICIAL_ID,
    MATCH_NAME_EXACT,
    MATCH_UNMATCHED,
    SECONDARY_CONTENT_PRODUCTION_INGEST,
)
from services.kosha_msds.current_index import (
    CurrentIndexError,
    OfficialCurrentRow,
    collect_current_index,
    diff_current_snapshots,
    parse_list_html,
)
from services.kosha_msds.discovery import DiscoveryCheckpoint, main as discovery_main
from services.kosha_msds.identity_join import join_counts, join_official_to_secondary

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SECRET = "LIVE_SERVICE_KEY_MUST_NEVER_LEAK"
REV = "testdatasetsha"


def _seed(*rows: BootstrapIdentity) -> list[BootstrapIdentity]:
    return list(rows)


def _id(chem_id, cas=None, name_ko=None, name_en=None) -> BootstrapIdentity:
    return BootstrapIdentity(chem_id, cas, name_ko, name_en, REV)


def _off(chem_id=None, cas=None, name=None, rev="2026-01-01", page=1) -> OfficialCurrentRow:
    return OfficialCurrentRow(chem_id, name, cas, rev, page)


def test_secondary_6_digit_chem_id_leading_zero():
    ident = identity_from_raw({"chem_id": "000001", "name_ko": "염산 구아니딘"}, revision=REV)
    assert ident.chem_id == "000001"
    assert ident.chem_id != "1"
    assert require_padded_chem_id("001008") == "001008"


def test_secondary_duplicate_chem_id_fail(tmp_path):
    path = tmp_path / "seed.jsonl"
    path.write_text(
        json.dumps({"chem_id": "000001"}) + "\n" + json.dumps({"chem_id": "000001"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BootstrapSeedError) as exc:
        load_identity_rows(path, revision=REV)
    assert exc.value.code == "DUPLICATE_CHEM_ID"


def test_invalid_chem_id_fail():
    with pytest.raises(BootstrapSeedError) as exc:
        identity_from_raw({"chem_id": "1"}, revision=REV)
    assert exc.value.code == "CHEM_ID_INVALID"
    with pytest.raises(BootstrapSeedError):
        identity_from_raw({"chem_id": None}, revision=REV)


def test_cas_exact_unique_match():
    official = [_off(cas="71-43-2", name="벤젠")]
    secondary = [_id("001008", cas="71-43-2", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_CAS_EXACT
    assert joined[0].secondary_chem_id == "001008"


def test_duplicate_cas_ambiguous():
    official = [_off(cas="71-43-2", name="벤젠")]
    secondary = [
        _id("001008", cas="71-43-2", name_ko="벤젠"),
        _id("001009", cas="71-43-2", name_ko="벤젠혼합물"),
    ]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_AMBIGUOUS


def test_cas_null_fallback_to_name():
    official = [_off(cas=None, name="벤젠")]
    secondary = [_id("001008", cas=None, name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_NAME_EXACT
    assert joined[0].secondary_chem_id == "001008"


def test_normalized_exact_name_unique_match():
    official = [_off(cas=None, name="  벤젠  ")]
    secondary = [_id("001008", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_NAME_EXACT


def test_name_duplicate_ambiguous():
    official = [_off(cas=None, name="벤젠")]
    secondary = [_id("001008", name_ko="벤젠"), _id("009999", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_AMBIGUOUS


def test_fuzzy_similarity_not_auto_match():
    official = [_off(cas=None, name="벤젠류")]
    secondary = [_id("001008", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_UNMATCHED
    assert joined[0].secondary_chem_id is None


def test_official_id_precedes_secondary():
    official = [_off(chem_id="000001", cas="71-43-2", name="벤젠")]
    secondary = [_id("001008", cas="71-43-2", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_DIRECT_OFFICIAL_ID
    assert joined[0].secondary_chem_id == "000001"


def test_unmatched_preserved():
    official = [_off(cas="00-00-0", name="없는물질")]
    secondary = [_id("001008", cas="71-43-2", name_ko="벤젠")]
    joined = join_official_to_secondary(official, secondary)
    assert joined[0].match_method == MATCH_UNMATCHED


def test_current_row_count_reconciliation():
    html = (FIXTURES / "chemlist_page1.html").read_text(encoding="utf-8")
    rows, total, page_no, page_count = parse_list_html(html, page=1)
    assert page_no == 1
    assert page_count == 1
    assert total == 3
    assert len(rows) == 3
    assert len(rows) == total


def test_join_unique_chem_id():
    official = [
        _off(chem_id="000001", cas="50-01-1", name="염산 구아니딘"),
        _off(chem_id="001008", cas="71-43-2", name="벤젠"),
    ]
    secondary = [_id("000001"), _id("001008")]
    joined = join_official_to_secondary(official, secondary)
    counts = join_counts(joined)
    assert counts["mapped_unique_chemId"] == 2
    assert counts[MATCH_DIRECT_OFFICIAL_ID] == 2


def test_secondary_content_not_production_writer(tmp_path):
    assert SECONDARY_CONTENT_PRODUCTION_INGEST == "NO"
    src = tmp_path / "raw.jsonl"
    src.write_text(
        json.dumps(
            {
                "chem_id": "000001",
                "name_ko": "염산 구아니딘",
                "sections": [{"text_ko": "SECRET_BODY", "braille": "SECRET_BRAILLE"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / "seed.jsonl"

    def boom(*_a, **_k):
        raise AssertionError("production writer called")

    extract_identity_jsonl(src.read_text(encoding="utf-8").splitlines(), dest, revision=REV, production_writer=boom)
    text = dest.read_text(encoding="utf-8")
    assert "SECRET_BODY" not in text
    assert "braille" not in text
    assert "sections" not in text
    src_bootstrap = pathlib.Path("services/kosha_msds/bootstrap.py").read_text(encoding="utf-8")
    assert "supabase" not in src_bootstrap.lower()


def test_api_validation_max_call_guard():
    with pytest.raises(ApiValidationError) as exc:
        assert_call_budget(100, 1, max_calls=100)
    assert exc.value.code == "API_VALIDATION_BUDGET"
    assert_call_budget(99, 1, max_calls=100)


def test_http_429_stops_index_and_validation(tmp_path):
    def get_429(url, params):
        return 429, "too many requests"

    with pytest.raises(CurrentIndexError) as exc:
        collect_current_index(dest=tmp_path / "idx.jsonl", get_fn=get_429, delay_s=0)
    assert exc.value.code == "HTTP_429"

    def fake_get(url, params=None, headers=None, timeout=25):
        return 429, "too many"

    client = KoshaMsdsClient(get_fn=fake_get, service_key=SECRET, max_attempts=1)
    with pytest.raises(ApiValidationError) as exc2:
        run_identity_validation(client, [{"casNo": "71-43-2", "chemId": "001008"}])
    assert exc2.value.code == "HTTP_429"


def test_same_day_quota_stop_no_retry():
    cp = DiscoveryCheckpoint(quota_stop=True)
    with pytest.raises(ApiValidationError) as exc:
        assert_quota_window_open(cp)
    assert exc.value.code == "SAME_DAY_QUOTA_STOP"
    assert discovery_main([]) == 2
    assert DISCOVERY_PRIMARY_ENUMERATION is False


def test_artifacts_secret_free(tmp_path):
    html = (FIXTURES / "chemlist_page1.html").read_text(encoding="utf-8")

    def get_fn(url, params):
        return 200, html

    dest = tmp_path / "idx.jsonl"
    collect_current_index(dest=dest, get_fn=get_fn, delay_s=0)
    text = dest.read_text(encoding="utf-8")
    assert SECRET not in text
    assert "serviceKey" not in text
    join_path = tmp_path / "join.jsonl"
    rows, *_ = parse_list_html(html, page=1)
    joined = join_official_to_secondary(rows, [_id("000001"), _id("001008"), _id("047134")])
    join_path.write_text("\n".join(json.dumps(r.as_row(), ensure_ascii=False) for r in joined), encoding="utf-8")
    assert SECRET not in join_path.read_text(encoding="utf-8")


def test_official_snapshot_diff_new():
    prev = [_off(chem_id="000001", name="염산 구아니딘")]
    curr = prev + [_off(chem_id="001008", name="벤젠")]
    diff = diff_current_snapshots(prev, curr)
    assert diff["NEW_CURRENT"] == ("001008",)
    assert diff["REMOVED_CURRENT"] == ()


def test_revision_changed_detection():
    prev = [_off(chem_id="001008", name="벤젠", rev="2024-01-01")]
    curr = [_off(chem_id="001008", name="벤젠", rev="2026-01-01")]
    diff = diff_current_snapshots(prev, curr)
    assert diff["REVISION_CHANGED"] == ("001008",)
    assert diff["UNCHANGED"] == ()
