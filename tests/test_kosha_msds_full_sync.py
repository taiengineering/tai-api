"""CHEM-04 API-only full list census, incremental diff, resume. Mock transport only."""
from __future__ import annotations

import pathlib

import pytest

from services.kosha_msds.client import KoshaMsdsClient, redact_secret
from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    BASE_URL,
    DETAIL_INCOMPLETE,
    DIFF_CHANGED,
    DIFF_NEW,
    DIFF_UNCHANGED,
    FULL_LIST_API,
    LIST_OPERATION,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    REMOVED_CANDIDATE,
    SNAPSHOT_COMPLETED,
    SOURCE_ID,
)
from services.kosha_msds.snapshot import SnapshotSpec, new_full_official_spec
from services.kosha_msds.sync import (
    KoshaMsdsSyncError,
    SyncCheckpoint,
    collect_list_census,
    initial_sync_plan,
    plan_incremental,
    publish_full_allowed,
    run_hydration,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SECRET = "LIVE_SERVICE_KEY_MUST_NEVER_LEAK"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler) -> KoshaMsdsClient:
    def fake_get(url, params=None, headers=None, timeout=25):
        return handler(url, params, timeout)

    return KoshaMsdsClient(
        get_fn=fake_get,
        service_key=SECRET,
        timeout_seconds=9,
        max_attempts=1,
    )


def _list_handler(pages: dict[str, str], calls: list | None = None):
    def handler(url, params, timeout):
        if calls is not None:
            calls.append((url, dict(params)))
        assert url == f"{BASE_URL}/{LIST_OPERATION}"
        page = str(params.get("pageNo") or "1")
        if page not in pages:
            return 200, fx("empty_list.xml")
        return 200, pages[page]

    return handler


def _full_handler(list_pages: dict[str, str], *, fail_section_for: str | None = None, log: list | None = None):
    def handler(url, params, timeout):
        rec = {"url": url, "params": dict(params)}
        if log is not None:
            log.append(rec)
        if LIST_OPERATION in url:
            page = str(params.get("pageNo") or "1")
            return 200, list_pages[page]
        chem_id = params.get("chemId")
        section = url.rsplit("getChemDetail", 1)[1]
        if fail_section_for and chem_id == fail_section_for and section == "16":
            return 200, fx("error_result.xml")
        return 200, fx("empty_success_section.xml")

    return handler


CORPUS_PAGES = {"1": fx("full_list_page1.xml"), "2": fx("full_list_page2.xml")}


def test_full_list_first_page_omits_search_and_keeps_leading_zero():
    captured = []
    census = collect_list_census(
        _client(_list_handler({"1": fx("full_list_page1.xml"), "2": fx("full_list_page2.xml")}, captured)),
        num_of_rows=2,
    )
    first = captured[0][1]
    assert "searchCnd" not in first
    assert "searchWrd" not in first
    assert first["pageNo"] == "1"
    assert first["numOfRows"] == "2"
    assert census.rows[0].chem_id == "000001"
    assert census.chem_ids[0] == "000001"


def test_pagination_next_page_returns_different_rows():
    census = collect_list_census(_client(_list_handler(CORPUS_PAGES)), num_of_rows=2)
    page1 = {row.chem_id for row in census.rows[:2]}
    page2 = {row.chem_id for row in census.rows[2:]}
    assert page1 == {"000001", "001008"}
    assert page2 == {"047134", "009098"}
    assert page1.isdisjoint(page2)
    assert census.page_count == 2


def test_total_count_handling():
    census = collect_list_census(_client(_list_handler(CORPUS_PAGES)), num_of_rows=2)
    assert census.total_count == 4
    assert len(census.chem_ids) == 4
    assert census.total_count == len(census.chem_ids)


def test_leading_zero_chem_id_preservation():
    census = collect_list_census(_client(_list_handler(CORPUS_PAGES)), num_of_rows=2)
    assert "000001" in census.chem_ids
    assert "001008" in census.chem_ids
    assert all(cid == cid.strip() and not cid.startswith(" ") for cid in census.chem_ids)
    assert census.rows[0].chem_id == "000001"


def test_duplicate_chem_id_fail_closed():
    with pytest.raises(KoshaMsdsSyncError) as exc:
        collect_list_census(
            _client(_list_handler({"1": fx("full_list_duplicate.xml")})),
            num_of_rows=2,
        )
    assert exc.value.code == "DUPLICATE_IDENTITY"


def test_missing_chem_id_fail_closed():
    with pytest.raises(KoshaMsdsSyncError) as exc:
        collect_list_census(
            _client(_list_handler({"1": fx("full_list_missing_chemid.xml")})),
            num_of_rows=1,
        )
    assert exc.value.code == "MISSING_IDENTITY"


def test_collected_count_not_equal_total_count_fails():
    with pytest.raises(KoshaMsdsSyncError) as exc:
        collect_list_census(
            _client(
                _list_handler(
                    {
                        "1": fx("full_list_count_mismatch.xml"),
                        "2": fx("empty_list.xml"),
                        "3": fx("empty_list.xml"),
                    }
                )
            ),
            num_of_rows=1,
        )
    assert exc.value.code == "COUNT_MISMATCH"


def test_initial_diff_all_new():
    census = collect_list_census(_client(_list_handler(CORPUS_PAGES)), num_of_rows=2)
    plan = initial_sync_plan(census.identity_map)
    assert set(plan.diff.new) == set(census.chem_ids)
    assert plan.diff.changed == ()
    assert plan.diff.unchanged == ()
    assert plan.diff.removed == ()
    assert set(plan.hydration_targets) == set(census.chem_ids)
    assert plan.detail_calls_planned == 16 * 4


def test_plus_one_chem_id_is_new_one():
    previous = {"000001": "2024-01-01", "001008": "2025-09-17"}
    current = {**previous, "009098": "2024-12-31"}
    plan = plan_incremental(previous, current)
    assert plan.diff.new == ("009098",)
    assert plan.labels["009098"] == DIFF_NEW
    assert set(plan.diff.unchanged) == {"000001", "001008"}


def test_last_date_change_is_changed_one():
    previous = {"001008": "2025-09-17", "000001": "2024-01-01"}
    current = {"001008": "2026-01-01", "000001": "2024-01-01"}
    plan = plan_incremental(previous, current)
    assert plan.diff.changed == ("001008",)
    assert plan.labels["001008"] == DIFF_CHANGED
    assert plan.diff.unchanged == ("000001",)


def test_identical_list_all_unchanged():
    previous = {"000001": "2024-01-01", "001008": "2025-09-17"}
    plan = plan_incremental(previous, dict(previous))
    assert plan.diff.unchanged == ("000001", "001008")
    assert plan.diff.new == ()
    assert plan.diff.changed == ()
    assert plan.hydration_targets == ()
    assert plan.unchanged_detail_calls == 0
    assert plan.detail_calls_planned == 0
    assert all(plan.labels[cid] == DIFF_UNCHANGED for cid in previous)


def test_removed_chem_id_is_removed_candidate():
    previous = {"000001": "2024-01-01", "001008": "2025-09-17"}
    current = {"000001": "2024-01-01"}
    plan = plan_incremental(previous, current)
    assert plan.diff.removed == ("001008",)
    assert plan.labels["001008"] == REMOVED_CANDIDATE
    assert "001008" not in plan.hydration_targets


def test_unchanged_makes_zero_detail_calls():
    log: list = []
    census = collect_list_census(_client(_full_handler(CORPUS_PAGES, log=log)), num_of_rows=2)
    plan = plan_incremental(census.identity_map, census.identity_map)
    assert plan.unchanged_detail_calls == 0
    assert plan.detail_calls_planned == 0
    checkpoint = SyncCheckpoint()
    records = run_hydration(_client(_full_handler(CORPUS_PAGES, log=log)), census, plan.hydration_targets, checkpoint)
    assert records == []
    assert checkpoint.detail_calls == 0
    assert not any("getChemDetail" in rec["url"] for rec in log if "getChemDetail" in rec["url"])


def test_new_triggers_detail16():
    log: list = []
    client = _client(_full_handler(CORPUS_PAGES, log=log))
    census = collect_list_census(client, num_of_rows=2)
    plan = initial_sync_plan({"000001": census.last_dates["000001"]})
    # only hydrate the one NEW in this isolated map
    one = collect_list_census(client, num_of_rows=2)
    subset_plan = initial_sync_plan({"000001": one.last_dates["000001"]})
    checkpoint = SyncCheckpoint()
    log.clear()
    run_hydration(client, one, subset_plan.hydration_targets, checkpoint)
    details = [rec for rec in log if "getChemDetail" in rec["url"]]
    assert len(details) == 16
    assert {rec["url"].rsplit("getChemDetail", 1)[1] for rec in details} == {f"{n:02d}" for n in ALLOWED_SECTIONS}
    assert all(rec["params"]["chemId"] == "000001" for rec in details)
    assert subset_plan.detail_calls_planned == 16
    assert checkpoint.detail_calls == 16


def test_changed_triggers_detail16():
    log: list = []
    client = _client(_full_handler(CORPUS_PAGES, log=log))
    census = collect_list_census(client, num_of_rows=2)
    previous = dict(census.identity_map)
    previous["001008"] = "1999-01-01"
    plan = plan_incremental(previous, census.identity_map)
    assert plan.diff.changed == ("001008",)
    log.clear()
    checkpoint = SyncCheckpoint()
    run_hydration(client, census, plan.hydration_targets, checkpoint)
    details = [rec for rec in log if "getChemDetail" in rec["url"]]
    assert len(details) == 16
    assert all(rec["params"]["chemId"] == "001008" for rec in details)
    assert plan.labels["001008"] == DIFF_CHANGED


def test_retry_resume_is_idempotent():
    log: list = []
    client = _client(_full_handler(CORPUS_PAGES, log=log))
    census = collect_list_census(client, num_of_rows=2)
    targets = ("000001", "001008")
    checkpoint = SyncCheckpoint()
    log.clear()
    with pytest.raises(KoshaMsdsSyncError) as exc:
        run_hydration(client, census, targets, checkpoint, fail_chem_id="001008")
    assert exc.value.code == "HYDRATION_INTERRUPTED"
    assert checkpoint.last_completed_chem_id == "000001"
    assert checkpoint.completed_chem_ids == ["000001"]
    first_details = [rec for rec in log if "getChemDetail" in rec["url"]]
    assert all(rec["params"]["chemId"] == "000001" for rec in first_details)
    assert len(first_details) == 16
    log.clear()
    run_hydration(client, census, targets, checkpoint)
    second = [rec for rec in log if "getChemDetail" in rec["url"]]
    assert all(rec["params"]["chemId"] == "001008" for rec in second)
    assert len(second) == 16
    assert checkpoint.completed_chem_ids == ["000001", "001008"]
    assert checkpoint.detail_calls == 32


def test_incomplete_detail_does_not_publish():
    client = _client(_full_handler(CORPUS_PAGES, fail_section_for="000001"))
    census = collect_list_census(client, num_of_rows=2)
    checkpoint = SyncCheckpoint()
    records = run_hydration(client, census, ("000001",), checkpoint)
    assert records[0].detail.detail_status == DETAIL_INCOMPLETE
    spec = new_full_official_spec(census.total_count)
    spec_completed = SnapshotSpec(
        enumeration_mode=spec.enumeration_mode,
        status=SNAPSHOT_COMPLETED,
        publish_state=PUBLISH_PUBLISHED_FULL,
        expected_count=census.total_count,
    )
    assert publish_full_allowed(spec_completed, census, records, publish_state=PUBLISH_PUBLISHED_FULL) is False
    assert publish_full_allowed(spec, census, records, publish_state=PUBLISH_NOT_PUBLISHED) is False


def test_service_key_leakage_is_zero():
    for path in FIXTURES.glob("full_list_*.xml"):
        text = path.read_text(encoding="utf-8")
        assert "serviceKey" not in text
        assert SECRET not in text
    captured = []
    collect_list_census(_client(_list_handler(CORPUS_PAGES, captured)), num_of_rows=2)
    blob = redact_secret(str(captured), SECRET)
    assert SECRET not in blob
    assert FULL_LIST_API == "BLOCKED"
    assert SOURCE_ID == "KOSHA_MSDS"
    with pytest.raises(KoshaMsdsSyncError) as exc:
        collect_list_census(_client(_list_handler({"1": fx("empty_list.xml")})), num_of_rows=1)
    assert exc.value.code == "FULL_LIST_BLOCKED"
    assert SECRET not in str(exc.value)


def test_cas_null_is_not_identity():
    census = collect_list_census(_client(_list_handler(CORPUS_PAGES)), num_of_rows=2)
    row = next(r for r in census.rows if r.chem_id == "047134")
    assert row.cas_no is None
    assert row.chem_id == "047134"
