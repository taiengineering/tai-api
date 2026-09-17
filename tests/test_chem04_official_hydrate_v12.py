"""WO-CHEM-04-OFFICIAL-HYDRATE-V12-001 runner + rate-limit tests.

All tests use fake handlers — no live KOSHA API calls.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from services.kosha_msds.client import (
    KoshaMsdsClient,
    KoshaMsdsClientError,
)
from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    detail_operation,
)
from tools.chem04 import official_hydrate_v12 as runner


FAKE_KEY = "TEST_HYDRATE_V12_KEY"


def _client_from_handler(handler):
    def get_fn(url, params=None, headers=None, timeout=25):
        return handler(url, params, timeout)

    return KoshaMsdsClient(
        get_fn=get_fn,
        service_key=FAKE_KEY,
        timeout_seconds=5,
        max_attempts=1,
    )


def _write_queue(tmp: Path, pairs: list[tuple[str, int]]) -> Path:
    p = tmp / "queue.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for chem, section in pairs:
            fh.write(json.dumps({"chemId": chem, "sectionNo": section}) + "\n")
    return p


def _success_xml(section_no: int = 1) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<response><header><resultCode>00</resultCode>"
        "<resultMsg>NORMAL SERVICE.</resultMsg></header>"
        "<body><items><item>"
        f"<msdsItemCode>C{section_no:02d}</msdsItemCode>"
        f"<msdsItemNameKor>테스트 항목 {section_no}</msdsItemNameKor>"
        "<itemDetail>내용</itemDetail>"
        "</item></items></body></response>"
    )


def _empty_success_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<response><header><resultCode>00</resultCode>"
        "<resultMsg>NORMAL SERVICE.</resultMsg></header>"
        "<body><items></items></body></response>"
    )


def _result_code_xml(code: str, msg: str = "err") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<response><header><resultCode>{code}</resultCode>"
        f"<resultMsg>{msg}</resultMsg></header>"
        "<body></body></response>"
    )


# ---------------------------------------------------------------------------
# WO §7  KoshaMsdsClient.get_detail_section must map rc22/23 → RATE_LIMIT
# ---------------------------------------------------------------------------


def test_get_detail_section_maps_rc22_to_rate_limit():
    def handler(url, params, timeout):
        return 200, _result_code_xml("22", "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS")

    client = _client_from_handler(handler)
    with pytest.raises(KoshaMsdsClientError) as exc:
        client.get_detail_section("000001", 1)
    assert exc.value.code == "RATE_LIMIT"


def test_get_detail_section_maps_rc23_to_rate_limit():
    def handler(url, params, timeout):
        return 200, _result_code_xml("23", "SERVICE REQUEST LIMIT EXCEEDED PER SECOND")

    client = _client_from_handler(handler)
    with pytest.raises(KoshaMsdsClientError) as exc:
        client.get_detail_section("000001", 1)
    assert exc.value.code == "RATE_LIMIT"


def test_get_detail_section_non_rate_limit_stays_result_code():
    def handler(url, params, timeout):
        return 200, _result_code_xml("99", "unexpected")

    client = _client_from_handler(handler)
    with pytest.raises(KoshaMsdsClientError) as exc:
        client.get_detail_section("000001", 1)
    assert exc.value.code == "RESULT_CODE"


# ---------------------------------------------------------------------------
# WO §14/§15/§16  runner completes small queue and skips already-done pairs
# ---------------------------------------------------------------------------


def _run_with_fake_client(tmp: Path, queue_path: Path, handler, hard_cap: int = 100):
    def factory(_key):
        return _client_from_handler(handler)

    os.environ["KOSHA_SERVICE_KEY"] = FAKE_KEY
    try:
        return runner.run(
            queue_path=queue_path,
            out_dir=tmp / "out",
            hard_cap=hard_cap,
            resume=True,
            expect_rows=0,       # disable queue-row guard for tiny fixtures
            expect_sha=None,     # disable queue-sha guard for tiny fixtures
            client_factory=factory,
        )
    finally:
        os.environ.pop("KOSHA_SERVICE_KEY", None)


def test_runner_full_small_queue_completes(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1), ("000001", 2), ("000002", 1)])
    section_counts = {}

    def handler(url, params, timeout):
        section = int(url.rsplit("getChemDetail", 1)[1][:-1])
        section_counts[section] = section_counts.get(section, 0) + 1
        return 200, _success_xml(section)

    report = _run_with_fake_client(tmp_path, queue, handler)
    assert report["stop_reason"] == runner.STOP_QUEUE_COMPLETE
    assert report["new_success"] == 3
    assert report["new_official_empty"] == 0
    assert report["new_errors"] == 0
    assert report["remaining"] == 0
    assert report["http_requests"] == 3
    assert section_counts == {1: 2, 2: 1}


def test_runner_resume_skips_already_done_pairs(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1), ("000001", 2), ("000002", 1)])

    def handler_success(url, params, timeout):
        section = int(url.rsplit("getChemDetail", 1)[1][:-1])
        return 200, _success_xml(section)

    def factory(_key):
        return _client_from_handler(handler_success)

    os.environ["KOSHA_SERVICE_KEY"] = FAKE_KEY
    out_dir = tmp_path / "out"
    try:
        # First run: complete 3.
        report1 = runner.run(
            queue_path=queue,
            out_dir=out_dir,
            hard_cap=100,
            resume=True,
            expect_rows=0,
            expect_sha=None,
            client_factory=factory,
        )
        assert report1["new_success"] == 3

        # Second run: everything is already recorded — must make 0 HTTP calls.
        called = {"n": 0}

        def handler_should_never_fire(url, params, timeout):
            called["n"] += 1
            return 200, _success_xml(1)

        def factory2(_key):
            return _client_from_handler(handler_should_never_fire)

        report2 = runner.run(
            queue_path=queue,
            out_dir=out_dir,
            hard_cap=100,
            resume=True,
            expect_rows=0,
            expect_sha=None,
            client_factory=factory2,
        )
        assert called["n"] == 0
        assert report2["http_requests"] == 0
        assert report2["new_success"] == 0
        assert report2["start_completed"] == 3
        assert report2["total_completed"] == 3
    finally:
        os.environ.pop("KOSHA_SERVICE_KEY", None)


def test_runner_official_empty_still_authoritative(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1)])

    def handler(url, params, timeout):
        return 200, _empty_success_xml()

    report = _run_with_fake_client(tmp_path, queue, handler)
    assert report["new_official_empty"] == 1
    assert report["new_success"] == 0
    responses = list(
        (tmp_path / "out" / "responses.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )
    assert len(responses) == 1
    row = json.loads(responses[0])
    assert row["status"] == "OFFICIAL_EMPTY"
    assert row["authoritative_verified"] is True


# ---------------------------------------------------------------------------
# WO §18/§19  quota-signal STOP
# ---------------------------------------------------------------------------


def test_runner_stops_on_rc22(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1), ("000001", 2), ("000001", 3)])
    called = {"n": 0}

    def handler(url, params, timeout):
        called["n"] += 1
        if called["n"] == 1:
            return 200, _success_xml(1)
        return 200, _result_code_xml("22", "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS")

    report = _run_with_fake_client(tmp_path, queue, handler)
    assert report["stop_reason"] == runner.STOP_QUOTA
    assert report["new_success"] == 1
    assert report["result_code_22"] == 1
    assert report["http_429"] == 0
    assert report["result_code_23"] == 0
    assert called["n"] == 2  # STOP immediately at first rc22, no further calls


def test_runner_stops_on_rc23(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1)])

    def handler(url, params, timeout):
        return 200, _result_code_xml("23", "SERVICE REQUEST LIMIT EXCEEDED PER SECOND")

    report = _run_with_fake_client(tmp_path, queue, handler)
    assert report["stop_reason"] == runner.STOP_QUOTA
    assert report["result_code_23"] == 1


def test_runner_stops_on_http_429(tmp_path):
    queue = _write_queue(tmp_path, [("000001", 1), ("000001", 2)])

    def handler(url, params, timeout):
        return 429, "quota exceeded"

    report = _run_with_fake_client(tmp_path, queue, handler)
    assert report["stop_reason"] == runner.STOP_QUOTA
    assert report["http_429"] == 1
    # first_quota_hit_operation must equal detail_operation(1)
    assert report["first_quota_hit_operation"] == detail_operation(1)


# ---------------------------------------------------------------------------
# WO §33  safety cap
# ---------------------------------------------------------------------------


def test_runner_safety_cap(tmp_path):
    queue = _write_queue(
        tmp_path,
        [("00000%d" % i, 1) for i in range(1, 6)],
    )

    def handler(url, params, timeout):
        return 200, _success_xml(1)

    report = _run_with_fake_client(tmp_path, queue, handler, hard_cap=3)
    assert report["stop_reason"] == runner.STOP_SAFETY_CAP
    assert report["http_requests"] == 3
    assert report["new_success"] == 3
    assert report["remaining"] == 2


# ---------------------------------------------------------------------------
# Queue guard  (frozen prod queue on disk)
# ---------------------------------------------------------------------------


def test_frozen_hydration_queue_sha_and_rows():
    queue = Path("artifacts/chem04/content/queues/hydration_queue.jsonl")
    if not queue.exists():
        pytest.skip("local frozen queue not available in this env")
    h = hashlib.sha256()
    n = 0
    with queue.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    with queue.open() as fh:
        for _ in fh:
            n += 1
    assert h.hexdigest() == runner.EXPECTED_QUEUE_SHA256
    assert n == runner.EXPECTED_QUEUE_ROWS
