"""CHEM-04 PATCH-3 Detail01 identity discovery. Mock transport only."""
from __future__ import annotations

import pathlib

import pytest

from services.kosha_msds.client import KoshaMsdsClient
from services.kosha_msds.contract import (
    BASE_URL,
    DISCOVERY_ABSENT,
    DISCOVERY_DISCOVERED,
    DISCOVERY_UNKNOWN,
    INITIAL_SEED_CANDIDATE_PASS,
)
from services.kosha_msds.discovery import (
    TAIL_EXTEND,
    TAIL_UPPER_BOUND_PASS,
    DiscoveryStore,
    evaluate_tail_block,
    initial_seed_candidate_status,
    range_complete,
    run_empirical_census,
)
from services.kosha_msds.identity import format_numeric_chem_id

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SECRET = "LIVE_SERVICE_KEY_MUST_NEVER_LEAK"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler, calls: list | None = None) -> KoshaMsdsClient:
    def fake_get(url, params=None, headers=None, timeout=25):
        if calls is not None:
            calls.append((url, dict(params or {})))
        return handler(url, params, timeout)

    return KoshaMsdsClient(
        get_fn=fake_get,
        service_key=SECRET,
        timeout_seconds=9,
        max_attempts=1,
    )


def _detail01_handler(by_id: dict[str, tuple[int, str] | Exception]):
    def handler(url, params, timeout):
        assert "getChemDetail01" in url
        assert "getChemDetail02" not in url
        chem_id = (params or {}).get("chemId")
        spec = by_id.get(chem_id) or by_id.get("*")
        if spec is None:
            return 200, fx("empty_success_section.xml")
        if isinstance(spec, Exception):
            raise spec
        return spec

    return handler


def test_000001_leading_zero_preserved(tmp_path):
    assert format_numeric_chem_id(1) == "000001"
    calls: list = []
    client = _client(
        _detail01_handler({"000001": (200, fx("benzene_detail_01.xml"))}),
        calls,
    )
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert calls[0][1]["chemId"] == "000001"
    assert calls[0][1]["chemId"] != "1"


def test_valid_detail01_discovered(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000001": (200, fx("benzene_detail_01.xml"))})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.discovered == 1
    assert summary.absent == 0
    assert summary.unknown == 0
    row = (tmp_path / "census.jsonl").read_text(encoding="utf-8")
    assert '"status": "DISCOVERED"' in row


def test_valid_empty_absent(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000002": (200, fx("empty_success_section.xml"))})),
        artifact_dir=tmp_path,
        range_start=2,
        range_end=2,
        stages=((2, 2),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.absent == 1
    assert summary.discovered == 0
    assert summary.unknown == 0


def test_http_429_unknown_not_absent(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000001": (429, "too many requests")})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.unknown == 1
    assert summary.absent == 0
    assert summary.http_429 == 1
    assert summary.quota_stop is True
    row = (tmp_path / "census.jsonl").read_text(encoding="utf-8")
    assert DISCOVERY_UNKNOWN in row
    assert DISCOVERY_ABSENT not in row


def test_quota_stops_submitting_remaining_ids(tmp_path):
    calls: list = []

    def handler(url, params, timeout):
        cid = (params or {}).get("chemId")
        if cid == "000001":
            return 429, "too many requests"
        return 200, fx("empty_success_section.xml")

    client = _client(handler, calls)
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=20,
        stages=((1, 20),),
        workers=4,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    chem_ids = [params["chemId"] for _, params in calls]
    assert "000001" in chem_ids
    assert len(chem_ids) <= 4
    assert "000020" not in chem_ids


def test_result_code_22_unknown(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000001": (200, fx("result_code_22.xml"))})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.unknown == 1
    assert summary.absent == 0
    assert summary.result_code_22 == 1
    assert summary.quota_stop is True


def test_timeout_unknown(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000001": TimeoutError("timed out")})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.unknown == 1
    assert summary.absent == 0
    assert summary.quota_stop is False


def test_5xx_unknown(tmp_path):
    summary = run_empirical_census(
        _client(_detail01_handler({"000001": (503, "upstream")})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.unknown == 1
    assert summary.absent == 0


def test_resume_skips_completed_ids(tmp_path):
    calls: list = []
    client = _client(
        _detail01_handler({"*": (200, fx("empty_success_section.xml"))}),
        calls,
    )
    artifact = tmp_path / "census.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=3,
        stages=((1, 3),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    first = len(calls)
    assert first == 3
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=5,
        stages=((1, 5),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    second_ids = [params["chemId"] for _, params in calls[first:]]
    assert second_ids == ["000004", "000005"]


def test_restart_resumes_from_checkpoint(tmp_path):
    artifact = tmp_path / "census.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    client = _client(_detail01_handler({"*": (200, fx("empty_success_section.xml"))}))
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=2,
        stages=((1, 2),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    store = DiscoveryStore(artifact, checkpoint, secret=SECRET)
    assert store.checkpoint.last_scanned_id == "000002"
    calls: list = []
    resumed = _client(
        _detail01_handler({"*": (200, fx("empty_success_section.xml"))}),
        calls,
    )
    run_empirical_census(
        resumed,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=4,
        stages=((1, 4),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    assert [params["chemId"] for _, params in calls] == ["000003", "000004"]
    store2 = DiscoveryStore(artifact, checkpoint, secret=SECRET)
    assert store2.checkpoint.last_scanned_id == "000004"


def test_duplicate_discovered_ids_impossible(tmp_path):
    calls: list = []
    client = _client(
        _detail01_handler({"000001": (200, fx("benzene_detail_01.xml"))}),
        calls,
    )
    artifact = tmp_path / "census.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    run_empirical_census(
        client,
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    ids = [params["chemId"] for _, params in calls]
    assert ids == ["000001"]
    rows = [json_line for json_line in artifact.read_text(encoding="utf-8").splitlines() if json_line]
    discovered = [line for line in rows if DISCOVERY_DISCOVERED in line]
    assert len(discovered) == 1


def test_artifact_contains_no_service_key(tmp_path):
    artifact = tmp_path / "census.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    run_empirical_census(
        _client(_detail01_handler({"000001": (200, fx("benzene_detail_01.xml"))})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=1,
        stages=((1, 1),),
        workers=1,
        tail=False,
        checkpoint_path=checkpoint,
        artifact_path=artifact,
    )
    for path in (artifact, checkpoint):
        text = path.read_text(encoding="utf-8")
        assert SECRET not in text
        assert "serviceKey" not in text


def test_unknown_gt_0_census_complete_false():
    assert range_complete(candidate_count=10, discovered=3, absent=6, unknown=1) is False
    assert range_complete(candidate_count=10, discovered=3, absent=7, unknown=0) is True
    assert range_complete(candidate_count=9, discovered=3, absent=7, unknown=0) is False


def test_10k_empty_tail_upper_bound_candidate_pass():
    assert evaluate_tail_block(discovered_count=0) == TAIL_UPPER_BOUND_PASS
    status = initial_seed_candidate_status(
        range_complete_ok=True,
        unknown=0,
        trailing_zero=True,
        checkpoint_ok=True,
        artifact_hash="abc",
        quota_stop=False,
    )
    assert status == INITIAL_SEED_CANDIDATE_PASS


def test_tail_hit_requires_next_10k_range():
    assert evaluate_tail_block(discovered_count=1) == TAIL_EXTEND
    assert evaluate_tail_block(discovered_count=3) == TAIL_EXTEND


def test_production_writer_never_called(tmp_path):
    src = pathlib.Path("services/kosha_msds/discovery.py").read_text(encoding="utf-8")
    assert "supabase" not in src.lower()
    assert "getChemDetail02" not in src
    assert "get_full_detail" not in src

    def boom(*_a, **_k):
        raise AssertionError("production writer called")

    summary = run_empirical_census(
        _client(_detail01_handler({"*": (200, fx("empty_success_section.xml"))})),
        artifact_dir=tmp_path,
        range_start=1,
        range_end=2,
        stages=((1, 2),),
        workers=1,
        tail=False,
        production_writer=boom,
        checkpoint_path=tmp_path / "checkpoint.json",
        artifact_path=tmp_path / "census.jsonl",
    )
    assert summary.absent == 2
