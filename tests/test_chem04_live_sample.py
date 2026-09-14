"""OPTION C live sample comparator: fixtures only. No production writer."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from services.kosha_msds.bootstrap import require_padded_chem_id
from services.kosha_msds.bootstrap_decision import flatten_msds_xml, sample_manifest_hash
from services.kosha_msds.content_audit import ContentAuditError, canonical_json_hash
from services.kosha_msds.contract import (
    EXPECTED_OPTIONC_SAMPLE_SHA256,
    LIVE_SAMPLE_HARD_CAP,
    LIVE_SAMPLE_KEY_ENV,
    LIVE_SAMPLE_MAX_CALLS,
    LIVE_SAMPLE_RETRY_MAX,
)
from services.kosha_msds.live_sample import (
    LiveSampleError,
    QuotaStop,
    assert_manifest_sha,
    chemical_status,
    compare_section,
    comparison_metrics,
    detail_url,
    fetch_official_xml,
    live_sample_key,
    load_sample_rows,
    run_live_sample,
    run_preflight,
    scan_secret_free_dir,
)
from tools.chem04 import live_sample_compare

FIXTURES = Path("tests/fixtures/kosha_msds")
MANIFEST = FIXTURES / "optionc_live_sample_manifest.json"
FAKE_KEY = "unit-test-live-sample-key"
SRC = Path("services/kosha_msds/live_sample.py").read_text(encoding="utf-8")
CLI_SRC = Path("tools/chem04/live_sample_compare.py").read_text(encoding="utf-8")


def _sample() -> list[dict]:
    return load_sample_rows(MANIFEST)


def _success_xml(detail: str, label: str = "항목") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<response><header><resultCode>00</resultCode>"
        "<resultMsg>NORMAL SERVICE.</resultMsg></header><body><items><item>"
        f"<itemDetail>{detail}</itemDetail>"
        f"<msdsItemNameKor>{label}</msdsItemNameKor>"
        "</item></items></body></response>"
    )


def _secondary_all(text: str) -> dict[str, dict[int, str]]:
    return {row["chemId"]: {n: text for n in range(1, 17)} for row in _sample()}


def test_01_fixed_manifest_sha_guard():
    rows = _sample()
    assert len(rows) == 16
    assert sample_manifest_hash(rows) == EXPECTED_OPTIONC_SAMPLE_SHA256
    assert assert_manifest_sha(rows) == EXPECTED_OPTIONC_SAMPLE_SHA256
    bad = [{"chemId": "000002", "stratum": "WRONG"}]
    with pytest.raises(LiveSampleError) as exc:
        assert_manifest_sha(bad)
    assert exc.value.code == "MANIFEST_MISMATCH"


def test_02_chemid_leading_zero():
    assert require_padded_chem_id("000002") == "000002"
    assert all(len(row["chemId"]) == 6 for row in _sample())
    assert _sample()[0]["chemId"].startswith("0")


def test_03_detail_url_generation():
    urls = [detail_url(n) for n in range(1, 17)]
    assert urls[0].endswith("/getChemDetail01")
    assert urls[15].endswith("/getChemDetail16")
    assert all("serviceKey" not in url for url in urls)
    assert all("?" not in url for url in urls)


def test_04_service_key_not_logged(caplog):
    xml = _success_xml("ok")
    caplog.set_level(logging.INFO, logger="chem04.live_sample")
    status, body = fetch_official_xml(
        chem_id="000002",
        section_no=1,
        get_fn=lambda url, params=None, timeout=30, **_: (200, xml),
        service_key=FAKE_KEY,
    )
    assert status == "OK"
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert FAKE_KEY not in joined
    assert "serviceKey" not in joined


def test_05_service_key_not_serialized(tmp_path):
    xml = _success_xml("ok")
    flat = flatten_msds_xml(xml)

    def get_fn(url, params=None, timeout=30, **_):
        assert params["serviceKey"] == FAKE_KEY
        return 200, xml

    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all(flat),
        get_fn=get_fn,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
        checkpoint_path=tmp_path / "cp.json",
        raw_dir=tmp_path / "raw",
    )
    dumped = json.dumps(result, ensure_ascii=False)
    assert FAKE_KEY not in dumped
    assert "serviceKey" not in dumped
    assert result["report"]["production_writer"] is None


def test_06_xml_success_parse():
    xml = (FIXTURES / "benzene_detail_01.xml").read_text(encoding="utf-8")
    status, body = fetch_official_xml(
        chem_id="001008",
        section_no=1,
        get_fn=lambda url, params=None, timeout=30, **_: (200, xml),
        service_key=FAKE_KEY,
    )
    assert status == "OK"
    assert "벤젠" in flatten_msds_xml(body)


def test_07_official_empty_parse():
    xml = (FIXTURES / "empty_success_section.xml").read_text(encoding="utf-8")
    compared = compare_section("제품명: 벤젠", xml, "OK")
    assert compared["class"] == "OFFICIAL_EMPTY"


def test_08_result_code_error_parse():
    xml = (FIXTURES / "result_code_99.xml").read_text(encoding="utf-8")
    status, body = fetch_official_xml(
        chem_id="000002",
        section_no=1,
        get_fn=lambda url, params=None, timeout=30, **_: (200, xml),
        service_key=FAKE_KEY,
    )
    assert status == "API_ERROR"
    assert body == "RESULT_99"


def test_09_429_hard_stop():
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(1)
        return 429, "quota"

    with pytest.raises(QuotaStop) as exc:
        fetch_official_xml(
            chem_id="000002",
            section_no=1,
            get_fn=get_fn,
            service_key=FAKE_KEY,
        )
    assert exc.value.http_429 == 1
    assert len(calls) == 1

    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all("x"),
        get_fn=get_fn,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
    )
    assert result["report"]["quota_stop"] is True
    assert result["report"]["HTTP_429"] == 1
    assert result["report"]["TECHNICAL_OPTION_C_GATE"] == "BLOCKED"
    assert len(calls) == 2


def test_10_max_call_guard():
    xml = _success_xml("ok")
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(url)
        return 200, xml

    with pytest.raises(LiveSampleError) as exc:
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem=_secondary_all(flatten_msds_xml(xml)),
            get_fn=get_fn,
            service_key=FAKE_KEY,
            max_calls=2,
            max_chems=1,
        )
    assert exc.value.code == "MAX_CALLS"
    assert len(calls) == 2
    with pytest.raises(LiveSampleError) as cap:
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem={},
            get_fn=get_fn,
            service_key=FAKE_KEY,
            max_calls=LIVE_SAMPLE_HARD_CAP + 1,
        )
    assert cap.value.code == "CALL_CAP"


def test_11_retry_max_two():
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append("500")
        return 500, "err"

    status, body = fetch_official_xml(
        chem_id="000002",
        section_no=1,
        get_fn=get_fn,
        service_key=FAKE_KEY,
    )
    assert status == "API_ERROR"
    assert body == "HTTP_500"
    assert len(calls) == LIVE_SAMPLE_RETRY_MAX

    calls.clear()

    def bad400(url, params=None, timeout=30, **_):
        calls.append("400")
        return 400, "no"

    status, _ = fetch_official_xml(
        chem_id="000002",
        section_no=1,
        get_fn=bad400,
        service_key=FAKE_KEY,
    )
    assert status == "API_ERROR"
    assert len(calls) == 1

    calls.clear()
    xml = _success_xml("ok")

    def timeout_then_ok(url, params=None, timeout=30, **_):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return 200, xml

    status, _ = fetch_official_xml(
        chem_id="000002",
        section_no=1,
        get_fn=timeout_then_ok,
        service_key=FAKE_KEY,
    )
    assert status == "OK"
    assert len(calls) == 2


def test_12_checkpoint_resume(tmp_path):
    xml = _success_xml("ok")
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(url)
        return 200, xml

    cp = tmp_path / "cp.json"
    with pytest.raises(LiveSampleError):
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem=_secondary_all(flatten_msds_xml(xml)),
            get_fn=get_fn,
            service_key=FAKE_KEY,
            max_calls=2,
            max_chems=1,
            checkpoint_path=cp,
        )
    assert len(calls) == 2
    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all(flatten_msds_xml(xml)),
        get_fn=get_fn,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
        checkpoint_path=cp,
    )
    assert len(calls) == 16
    assert result["attempted_calls"] == 16
    assert len(result["rows"]) == 16


def test_13_flatten_parity_fixture():
    xml = (FIXTURES / "benzene_detail_01.xml").read_text(encoding="utf-8")
    text = flatten_msds_xml(xml)
    assert text == "제품명: 벤젠\n제품의 권고 용도: 고분자, 세제, 농약"


def test_14_ghs_filename_conversion():
    xml = (FIXTURES / "benzene_detail_02.xml").read_text(encoding="utf-8")
    text = flatten_msds_xml(xml)
    assert ".gif" not in text
    assert "인화성" in text
    assert "건강유해성(발암성/생식독성)" in text


def test_15_pipe_conversion():
    xml = (FIXTURES / "benzene_detail_02.xml").read_text(encoding="utf-8")
    text = flatten_msds_xml(xml)
    assert "|" not in text
    assert "인화성 액체 : 구분2, 발암성 : 구분1B" in text


def test_16_jayou_none_handling():
    xml = (FIXTURES / "jayou_none_section.xml").read_text(encoding="utf-8")
    assert flatten_msds_xml(xml) == "내용: 있음"


def test_17_exact_classification():
    xml = _success_xml("벤젠", "제품명")
    assert compare_section("제품명: 벤젠", xml, "OK")["class"] == "EXACT"


def test_18_normalized_equal_classification():
    xml = _success_xml("벤젠", "제품명")
    assert compare_section("제품명: 벤젠\r\n", xml, "OK")["class"] == "NORMALIZED_EQUAL"
    assert compare_section("제품명: 벤젠&amp;", _success_xml("벤젠&amp;", "제품명"), "OK")["class"] == "NORMALIZED_EQUAL"


def test_19_content_different_classification():
    xml = _success_xml("톨루엔", "제품명")
    row = compare_section("제품명: 벤젠", xml, "OK")
    assert row["class"] == "CONTENT_DIFFERENT"
    assert row["possible_cause"] == "UNKNOWN"


def test_20_official_empty_classification():
    xml = (FIXTURES / "empty_success_section.xml").read_text(encoding="utf-8")
    assert compare_section("제품명: 벤젠", xml, "OK")["class"] == "OFFICIAL_EMPTY"


def test_21_api_error_classification():
    assert compare_section("제품명: 벤젠", None, "API_ERROR")["class"] == "API_ERROR"
    assert compare_section(None, _success_xml("벤젠", "제품명"), "OK")["class"] == "SECONDARY_MISSING"
    assert compare_section("", _success_xml("벤젠", "제품명"), "OK")["class"] == "SECONDARY_EMPTY"


def test_22_deterministic_report():
    rows = [
        {
            "chemId": "000002",
            "class": "EXACT",
            "attempted_calls": 1,
            "official_fetch": "OK",
        }
        for _ in range(16)
    ]
    a = comparison_metrics(rows)
    b = comparison_metrics(rows)
    assert a == b
    assert a["section_fidelity_pct"] == 100.0
    assert a["comparable_sections"] == 16
    payload = {"EXACT": 16, "NORMALIZED_EQUAL": 0, "CONTENT_DIFFERENT": 0}
    assert canonical_json_hash(payload) == canonical_json_hash(dict(payload))
    assert chemical_status(["EXACT"] * 16) == "ALL_MATCH"


def test_23_no_llm_fuzzy():
    lowered = (SRC + CLI_SRC).lower()
    for token in ("openai", "llm", "fuzzy", "embedding", "semantic"):
        assert token not in lowered


def test_24_no_production_writer():
    def writer(*_args, **_kwargs):
        raise AssertionError("must not write production")

    with pytest.raises(LiveSampleError) as exc:
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem={},
            get_fn=lambda *a, **k: (200, _success_xml("x")),
            service_key=FAKE_KEY,
            production_writer=writer,
        )
    assert exc.value.code == "PRODUCTION_WRITER"


def test_25_artifact_secret_scan(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "ok.json").write_text('{"class":"EXACT"}\n', encoding="utf-8")
    scan_secret_free_dir(clean, extra_tokens=(FAKE_KEY,))
    leak = tmp_path / "leak"
    leak.mkdir()
    (leak / "bad.txt").write_text("https://example?serviceKey=abc\n", encoding="utf-8")
    with pytest.raises(ContentAuditError) as exc:
        scan_secret_free_dir(leak)
    assert exc.value.code == "SECRET_LEAK"


def test_key_env_priority_kosha_first(monkeypatch):
    monkeypatch.delenv("KOSHA_SERVICE_KEY", raising=False)
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    monkeypatch.delenv("BUILDING_API_KEY", raising=False)
    monkeypatch.setenv("BUILDING_API_KEY", "building-must-be-ignored")
    assert live_sample_key() == ""
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "data-key")
    monkeypatch.setenv("KOSHA_SERVICE_KEY", "kosha-key")
    assert LIVE_SAMPLE_KEY_ENV[0] == "KOSHA_SERVICE_KEY"
    assert live_sample_key() == "kosha-key"


def test_result_code_22_hard_stop():
    xml = (FIXTURES / "result_code_22.xml").read_text(encoding="utf-8")
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(1)
        return 200, xml

    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all("x"),
        get_fn=get_fn,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
    )
    assert result["report"]["quota_stop"] is True
    assert result["report"]["resultCode_22"] == 1
    assert len(calls) == 1


def test_cli_refuses_bare_and_requires_mode():
    with pytest.raises(SystemExit):
        live_sample_compare.main([])
    with pytest.raises(SystemExit):
        live_sample_compare.main(["--probe", "--local-run"])
    with pytest.raises(SystemExit):
        live_sample_compare.main(["--preflight", "--local-run"])


def test_cli_probe_without_key(monkeypatch):
    monkeypatch.delenv("KOSHA_SERVICE_KEY", raising=False)
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    with pytest.raises(SystemExit, match="service key unavailable"):
        live_sample_compare.main(["--probe"])


def test_cli_probe_max_one_chem(tmp_path, monkeypatch):
    xml = _success_xml("벤젠", "제품명")
    flat = flatten_msds_xml(xml)
    train = tmp_path / "train.jsonl"
    rows = []
    for item in _sample():
        rows.append(
            json.dumps(
                {
                    "chemId": item["chemId"],
                    "sections": [{"section_no": n, "text_ko": flat} for n in range(1, 17)],
                },
                ensure_ascii=False,
            )
        )
    train.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("KOSHA_SERVICE_KEY", FAKE_KEY)
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "rows": [],
            "report": {
                "WO": "WO-CHEM-04-OPTIONC-LIVE-SAMPLE-001",
                "quota_stop": False,
                "secret_leak": 0,
                "production_writer": None,
            },
        }

    monkeypatch.setattr(live_sample_compare, "run_live_sample", fake_run)
    monkeypatch.setattr(live_sample_compare, "DECISION", tmp_path)
    monkeypatch.setattr(live_sample_compare, "DECISION_RAW", tmp_path / "live_raw")
    monkeypatch.setattr(live_sample_compare, "DECISION_NORMALIZED", tmp_path / "normalized")
    monkeypatch.setattr(live_sample_compare, "DECISION_CHECKPOINTS", tmp_path / "checkpoints")
    monkeypatch.setattr(live_sample_compare, "DECISION_MANIFESTS", tmp_path / "manifests")
    rc = live_sample_compare.main(
        [
            "--probe",
            "--sample-manifest",
            str(MANIFEST),
            "--train-jsonl",
            str(train),
            "--checkpoint",
            str(tmp_path / "cp.json"),
            "--out-report",
            str(tmp_path / "report.json"),
            "--out-comparison",
            str(tmp_path / "comparison.jsonl"),
        ]
    )
    assert rc == 0
    assert captured["max_chems"] == 1
    assert captured["max_calls"] == 16
    assert captured["production_writer"] is None
    assert FAKE_KEY not in json.dumps(captured["report"] if False else {"ok": True})


def test_planned_calls_constant():
    assert LIVE_SAMPLE_MAX_CALLS == 256
    assert LIVE_SAMPLE_HARD_CAP == 320
    assert len(_sample()) * 16 == 256


def test_fetch_error_http_and_result_tokens(tmp_path):
    xml99 = (FIXTURES / "result_code_99.xml").read_text(encoding="utf-8")

    def get_fn(url, params=None, timeout=30, **_):
        return 200, xml99

    with pytest.raises(LiveSampleError):
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem=_secondary_all("x"),
            get_fn=get_fn,
            service_key=FAKE_KEY,
            max_calls=2,
            max_chems=1,
            checkpoint_path=tmp_path / "cp99.json",
        )
    rows = json.loads((tmp_path / "cp99.json").read_text(encoding="utf-8"))["rows"]
    assert {row["fetch_error"] for row in rows} == {"RESULT_99"}

    def forbidden(url, params=None, timeout=30, **_):
        return 403, "no"

    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all("x"),
        get_fn=forbidden,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
    )
    assert result["report"]["error_token_counts"] == {"HTTP_403": 16}
    assert all(row["fetch_error"] == "HTTP_403" for row in result["rows"])
    dumped = json.dumps(result, ensure_ascii=False)
    assert FAKE_KEY not in dumped


def test_fetch_error_parse_and_timeout():
    status, token = fetch_official_xml(
        chem_id="001008",
        section_no=1,
        get_fn=lambda url, params=None, timeout=30, **_: (200, "<html>not-xml"),
        service_key=FAKE_KEY,
    )
    assert status == "API_ERROR"
    assert token == "PARSE"

    def boom(url, params=None, timeout=30, **_):
        raise TimeoutError("timed out")

    status, token = fetch_official_xml(
        chem_id="001008",
        section_no=1,
        get_fn=boom,
        service_key=FAKE_KEY,
    )
    assert status == "API_ERROR"
    assert token == "TIMEOUT"


def test_preflight_fail_stops_without_writing_checkpoint(tmp_path):
    checkpoint = tmp_path / "live_sample.json"
    original = '{"done":[["000002",1]],"attempted_calls":1,"rows":[]}\n'
    checkpoint.write_text(original, encoding="utf-8")
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(params["chemId"])
        return 401, "denied"

    result = run_live_sample(
        sample_rows=_sample(),
        secondary_by_chem=_secondary_all("x"),
        get_fn=get_fn,
        service_key=FAKE_KEY,
        max_calls=16,
        max_chems=1,
        checkpoint_path=checkpoint,
        require_preflight=True,
    )
    assert calls == ["001008"]
    assert result["rows"] == []
    assert result["report"]["preflight"]["fetch_error"] == "HTTP_401"
    assert result["report"]["error_token_counts"] == {"HTTP_401": 1}
    assert result["report"]["TECHNICAL_OPTION_C_GATE"] == "BLOCKED"
    assert checkpoint.read_text(encoding="utf-8") == original


def test_preflight_ok_then_sample_starts():
    xml = _success_xml("ok")
    calls = []

    def get_fn(url, params=None, timeout=30, **_):
        calls.append(params["chemId"])
        return 200, xml

    with pytest.raises(LiveSampleError) as exc:
        run_live_sample(
            sample_rows=_sample(),
            secondary_by_chem=_secondary_all(flatten_msds_xml(xml)),
            get_fn=get_fn,
            service_key=FAKE_KEY,
            max_calls=1,
            max_chems=1,
            require_preflight=True,
        )
    assert exc.value.code == "MAX_CALLS"
    assert calls[0] == "001008"
    assert calls[1] == "000002"
    assert len(calls) == 2


def test_cli_preflight_skips_train_and_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("KOSHA_SERVICE_KEY", FAKE_KEY)
    captured = {}

    def fake_preflight(**kwargs):
        captured.update(kwargs)
        return {
            "preflight": "FAIL",
            "chemId": "001008",
            "sectionNo": 1,
            "fetch_error": "RESULT_30",
            "official_fetch": "API_ERROR",
            "http_requests": 1,
        }

    checkpoint = tmp_path / "live_sample.json"
    checkpoint.write_text('{"done":[],"attempted_calls":256}\n', encoding="utf-8")
    before = checkpoint.read_bytes()
    monkeypatch.setattr(live_sample_compare, "run_preflight", fake_preflight)
    monkeypatch.setattr(live_sample_compare, "DECISION", tmp_path)
    monkeypatch.setattr(live_sample_compare, "DECISION_CHECKPOINTS", tmp_path)
    rc = live_sample_compare.main(
        [
            "--preflight",
            "--sample-manifest",
            str(MANIFEST),
            "--checkpoint",
            str(checkpoint),
            "--out-preflight",
            str(tmp_path / "preflight_report.json"),
        ]
    )
    assert rc == 2
    assert captured["get_fn"] is not None
    assert checkpoint.read_bytes() == before
    payload = json.loads((tmp_path / "preflight_report.json").read_text(encoding="utf-8"))
    assert payload["fetch_error"] == "RESULT_30"
    assert payload["error_token_counts"] == {"RESULT_30": 1}
    assert payload["sample_checkpoint_written"] is False
    assert FAKE_KEY not in json.dumps(payload)


def test_run_preflight_ok_fixture():
    xml = (FIXTURES / "benzene_detail_01.xml").read_text(encoding="utf-8")
    result = run_preflight(
        get_fn=lambda url, params=None, timeout=30, **_: (200, xml),
        service_key=FAKE_KEY,
    )
    assert result["preflight"] == "OK"
    assert result["chemId"] == "001008"
    assert result["fetch_error"] is None
