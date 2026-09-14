"""CHEM-04 local content audit: fixture/unit only. No live HF, no live KOSHA API."""
from __future__ import annotations

import json
import pathlib

import pytest

from services.kosha_msds.contract import (
    ABSENT_SECONDARY_CONTENT_FIELDS,
    ALLOWED_SECTIONS,
    CONTENT_SECONDARY_COMPLETE,
    CONTENT_SECONDARY_EMPTY_VALID,
    CONTENT_SECONDARY_INVALID,
    CONTENT_SECONDARY_MISSING,
    CONTENT_SECONDARY_PARTIAL,
    FRESHNESS_CURRENT_CHANGED,
    FRESHNESS_CURRENT_MATCH,
    FRESHNESS_DATE_UNKNOWN,
    OBSERVED_SECONDARY_CONTENT_FIELDS,
    OBSERVED_SECONDARY_SECTION_FIELDS,
    REASON_OFFICIAL_ONLY,
    REASON_REVISION_CHANGED,
    REASON_REVISION_UNKNOWN,
    REASON_SECONDARY_MISSING_SECTION,
    SECONDARY_CONTENT_PRODUCTION_INGEST,
    SECONDARY_CONTENT_PRODUCTION_PUBLICATION,
    SECTION_EMPTY,
    SECTION_INVALID,
    SECTION_MISSING,
    SECTION_PRESENT,
)
from services.kosha_msds.content_audit import (
    ContentAuditError,
    assert_secret_free,
    canonical_content_hash,
    canonical_json_hash,
    coverage_metrics,
    delta_queue_rows,
    endpoint_counts,
    index_row_from_raw,
    join_coverage,
    observe_record_fields,
    parse_section_map,
    stream_index_from_path,
    stream_secondary_index,
)
from services.kosha_msds.current_index import OfficialCurrentRow
from tools.chem04 import (
    audit_secondary_content,
    build_content_coverage,
    build_hydration_queue,
    content_report,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SAMPLE = FIXTURES / "secondary_content_sample.jsonl"
REV = "testdatasetsha"
SRC = pathlib.Path("services/kosha_msds/content_audit.py").read_text(encoding="utf-8")


def _sections(*, missing=(), empty=(), invalid=(), text="body"):
    rows = []
    for n in ALLOWED_SECTIONS:
        if n in missing:
            continue
        if n in invalid:
            rows.append({"section_no": n, "title": f"s{n}", "text_ko": {"bad": True}, "braille": ""})
        elif n in empty:
            rows.append({"section_no": n, "title": f"s{n}", "text_ko": "", "braille": ""})
        else:
            rows.append({"section_no": n, "title": f"s{n}", "text_ko": text, "braille": ""})
    return rows


def _raw(chem_id, *, missing=(), empty=(), invalid=(), text="body", extra=None):
    rec = {
        "chem_id": chem_id,
        "name_ko": chem_id,
        "cas_no": "71-43-2",
        "name_en": "x",
        "sections": _sections(missing=missing, empty=empty, invalid=invalid, text=text),
    }
    if extra:
        rec.update(extra)
    return rec


def _off(chem_id, cas=None, name=None, rev="2026-01-01") -> OfficialCurrentRow:
    return OfficialCurrentRow(chem_id, name, cas, rev, 1)


def test_observed_secondary_schema_from_fixture():
    first = json.loads(SAMPLE.read_text(encoding="utf-8").splitlines()[0])
    observed = observe_record_fields(first)
    assert tuple(observed["top_keys"]) == tuple(sorted(OBSERVED_SECONDARY_CONTENT_FIELDS))
    assert set(observed["section_keys"]) == set(OBSERVED_SECONDARY_SECTION_FIELDS)
    for field in ABSENT_SECONDARY_CONTENT_FIELDS:
        assert field not in first


def test_chem_id_leading_zero_preserved():
    row = index_row_from_raw(_raw("000001"), source_revision=REV)
    assert row["chemId"] == "000001"
    assert row["chemId"] != "1"


def test_exact_chem_id_join_only():
    index = {"000001": index_row_from_raw(_raw("000001"), source_revision=REV)}
    coverage = join_coverage([_off("000001"), _off("999999")], index)
    by_id = {row["chemId"]: row for row in coverage}
    assert by_id["000001"]["secondary_present"] is True
    assert by_id["999999"]["content_status"] == CONTENT_SECONDARY_MISSING
    assert by_id["000001"]["match_method"] == "CHEMID_EXACT"


def test_secondary_missing_chemical():
    coverage = join_coverage([_off("047000")], {})
    assert coverage[0]["content_status"] == CONTENT_SECONDARY_MISSING
    queue = delta_queue_rows(coverage)
    assert len(queue) == 16
    assert {row["reason"] for row in queue} == {REASON_OFFICIAL_ONLY}


def test_sixteen_section_complete():
    row = index_row_from_raw(_raw("000001"), source_revision=REV)
    assert row["content_status"] == CONTENT_SECONDARY_COMPLETE
    assert row["section_count"] == 16
    assert all(row[f"section{n:02d}_present"] == SECTION_PRESENT for n in ALLOWED_SECTIONS)


def test_one_section_missing_is_partial():
    row = index_row_from_raw(_raw("001008", missing={4}), source_revision=REV)
    assert row["content_status"] == CONTENT_SECONDARY_PARTIAL
    assert row["section04_present"] == SECTION_MISSING
    coverage = join_coverage([_off("001008")], {"001008": row})
    queue = delta_queue_rows(coverage)
    assert [(q["chemId"], q["sectionNo"]) for q in queue] == [("001008", 4)]
    assert queue[0]["reason"] == REASON_SECONDARY_MISSING_SECTION


def test_explicit_empty_is_not_missing():
    row = index_row_from_raw(_raw("047134", empty={2}), source_revision=REV)
    assert row["section02_present"] == SECTION_EMPTY
    assert row["section02_present"] != SECTION_MISSING
    assert row["content_status"] == CONTENT_SECONDARY_COMPLETE


def test_all_empty_is_empty_valid():
    row = index_row_from_raw(_raw("047134", empty=set(ALLOWED_SECTIONS)), source_revision=REV)
    assert row["content_status"] == CONTENT_SECONDARY_EMPTY_VALID
    assert all(row[f"section{n:02d}_present"] == SECTION_EMPTY for n in ALLOWED_SECTIONS)


def test_invalid_section_status():
    row = index_row_from_raw(_raw("000003", invalid={7}), source_revision=REV)
    assert row["section07_present"] == SECTION_INVALID
    assert row["content_status"] == CONTENT_SECONDARY_INVALID
    queue = delta_queue_rows(join_coverage([_off("000003")], {"000003": row}))
    assert queue[0]["sectionNo"] == 7


def test_no_cas_name_fallback():
    secondary = index_row_from_raw(_raw("001008"), source_revision=REV)
    official = _off("999999", cas="71-43-2", name="벤젠")
    coverage = join_coverage([official], {"001008": secondary})
    assert coverage[0]["chemId"] == "999999"
    assert coverage[0]["content_status"] == CONTENT_SECONDARY_MISSING


def test_no_fuzzy_or_llm_matching():
    assert "fuzzy" not in SRC.lower()
    assert "llm" not in SRC.lower()
    assert "openai" not in SRC.lower()
    secondary = index_row_from_raw(_raw("001008"), source_revision=REV)
    official = _off("999998", name="벤젠류")
    coverage = join_coverage([official], {"001008": secondary})
    assert coverage[0]["secondary_present"] is False


def test_duplicate_chem_id_fail(tmp_path):
    src = tmp_path / "dup.jsonl"
    src.write_text(
        json.dumps(_raw("000001")) + "\n" + json.dumps(_raw("000001")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ContentAuditError) as exc:
        stream_index_from_path(src, tmp_path / "idx.jsonl", source_revision=REV)
    assert exc.value.code == "DUPLICATE_CHEM_ID"


def test_duplicate_section_fail():
    rec = _raw("000001")
    rec["sections"].append({"section_no": 1, "title": "dup", "text_ko": "x", "braille": ""})
    with pytest.raises(ContentAuditError) as exc:
        parse_section_map(rec["sections"])
    assert exc.value.code == "SECTION_DUPLICATE"


def test_unknown_section_number_fail():
    rec = _raw("000001")
    rec["sections"].append({"section_no": 17, "title": "bad", "text_ko": "x", "braille": ""})
    with pytest.raises(ContentAuditError) as exc:
        parse_section_map(rec["sections"])
    assert exc.value.code == "SECTION_NO_UNKNOWN"


def test_deterministic_section_ordering():
    row = index_row_from_raw(_raw("000001"), source_revision=REV)
    keys = [f"section{n:02d}_present" for n in ALLOWED_SECTIONS]
    assert keys == [key for key in row if key.startswith("section") and key.endswith("_present")]
    queue = delta_queue_rows(join_coverage([_off("999999")], {}))
    assert [q["sectionNo"] for q in queue] == list(ALLOWED_SECTIONS)


def test_deterministic_content_hash():
    a = index_row_from_raw(_raw("000001", text="same"), source_revision=REV)
    b = index_row_from_raw(_raw("000001", text="same"), source_revision=REV)
    assert a["content_hash"] == b["content_hash"]
    c = index_row_from_raw(_raw("000001", text="other"), source_revision=REV)
    assert a["content_hash"] != c["content_hash"]


def test_timestamps_excluded_from_canonical_hash():
    base = _raw("000001")
    hashed = canonical_content_hash(
        "000001",
        parse_section_map(base["sections"]),
        {n: SECTION_PRESENT for n in ALLOWED_SECTIONS},
    )
    stamped = dict(base)
    stamped["written_at"] = "2099-01-01T00:00:00Z"
    stamped["created_at"] = "2099-01-01T00:00:00Z"
    row = index_row_from_raw(stamped, source_revision=REV)
    assert row["content_hash"] == hashed
    payload = {"official_current": 1, "written_at": "2099-01-01T00:00:00Z"}
    assert canonical_json_hash(payload) == canonical_json_hash({"official_current": 1})


def test_strict_queue_count_not_materialized():
    coverage = join_coverage([_off("000001"), _off("999999")], {"000001": index_row_from_raw(_raw("000001"), source_revision=REV)})
    queue = delta_queue_rows(coverage)
    metrics = coverage_metrics(coverage, queue)
    assert metrics["STRICT_API_CALLS"] == 32
    assert metrics["DELTA_API_CALLS"] == 16
    assert len(queue) != metrics["STRICT_API_CALLS"]


def test_delta_queue_only_missing_or_changed():
    complete = index_row_from_raw(_raw("000001"), source_revision=REV)
    partial = index_row_from_raw(_raw("001008", missing={4}), source_revision=REV)
    coverage = join_coverage(
        [_off("000001"), _off("001008"), _off("999999")],
        {"000001": complete, "001008": partial},
    )
    queue = delta_queue_rows(coverage)
    keys = {(q["chemId"], q["sectionNo"], q["reason"]) for q in queue}
    assert ("000001", 1, REASON_REVISION_UNKNOWN) not in keys
    assert ("001008", 4, REASON_SECONDARY_MISSING_SECTION) in keys
    assert all(q["chemId"] != "000001" for q in queue)
    assert len([q for q in queue if q["chemId"] == "999999"]) == 16


def test_endpoint_call_counts():
    coverage = join_coverage(
        [_off("001008"), _off("999999")],
        {"001008": index_row_from_raw(_raw("001008", missing={4}), source_revision=REV)},
    )
    queue = delta_queue_rows(coverage)
    counts = endpoint_counts(queue)
    assert counts[4] == 2
    assert counts[1] == 1
    metrics = coverage_metrics(coverage, queue)
    assert metrics["DETAIL04_strict"] == 2
    assert metrics["DETAIL04_delta"] == 2
    assert metrics["DETAIL01_delta"] == 1


def test_revision_changed():
    row = index_row_from_raw(_raw("000002", extra={"lastDate": "2024-01-01"}), source_revision=REV)
    coverage = join_coverage([_off("000002", rev="2026-01-01")], {"000002": row})
    assert coverage[0]["freshness"] == FRESHNESS_CURRENT_CHANGED
    queue = delta_queue_rows(coverage)
    assert len(queue) == 16
    assert {q["reason"] for q in queue} == {REASON_REVISION_CHANGED}


def test_revision_match_and_unknown_preserved():
    matched = index_row_from_raw(_raw("000002", extra={"lastDate": "2026-01-01"}), source_revision=REV)
    unknown = index_row_from_raw(_raw("000001"), source_revision=REV)
    coverage = join_coverage(
        [_off("000002", rev="2026-01-01"), _off("000001", rev="2026-01-01")],
        {"000002": matched, "000001": unknown},
    )
    by_id = {row["chemId"]: row for row in coverage}
    assert by_id["000002"]["freshness"] == FRESHNESS_CURRENT_MATCH
    assert by_id["000001"]["freshness"] == FRESHNESS_DATE_UNKNOWN
    assert by_id["000001"]["needs_api"] == "unknown"
    assert by_id["000001"]["reason"] == REASON_REVISION_UNKNOWN
    queue = delta_queue_rows(coverage)
    assert all(q["chemId"] != "000001" for q in queue)
    assert all(q["chemId"] != "000002" for q in queue)


def test_streaming_full_reader(tmp_path):
    dest = tmp_path / "idx.jsonl"

    def lines():
        yield json.dumps(_raw("000001")) + "\n"
        yield json.dumps(_raw("001008", missing={4})) + "\n"

    result = stream_secondary_index(lines(), dest, source_revision=REV, production_writer=None)
    assert result["rows"] == 2
    rows = [json.loads(line) for line in dest.read_text(encoding="utf-8").splitlines()]
    assert [row["chemId"] for row in rows] == ["000001", "001008"]
    assert all("text_ko" not in row for row in rows)
    assert all("braille" not in json.dumps(row) for row in rows)


def test_checkpoint_resume(tmp_path):
    src = tmp_path / "src.jsonl"
    src.write_text(
        json.dumps(_raw("000001"))
        + "\n"
        + json.dumps(_raw("001008"))
        + "\n"
        + json.dumps(_raw("047134", empty=set(ALLOWED_SECTIONS)))
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / "idx.jsonl"
    checkpoint = tmp_path / "cp.json"
    first = stream_index_from_path(
        src,
        dest,
        source_revision=REV,
        max_rows=1,
        checkpoint_path=checkpoint,
    )
    assert first["rows"] == 1
    assert first["source_lines_consumed"] == 1
    second = stream_index_from_path(
        src,
        dest,
        source_revision=REV,
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert second["rows"] == 2
    assert second["rows_total"] == 3
    ids = [json.loads(line)["chemId"] for line in dest.read_text(encoding="utf-8").splitlines()]
    assert ids == ["000001", "001008", "047134"]


def test_artifact_secret_free(tmp_path):
    dest = tmp_path / "idx.jsonl"
    stream_secondary_index(
        [json.dumps(_raw("000001"))],
        dest,
        source_revision=REV,
        production_writer=None,
    )
    text = dest.read_text(encoding="utf-8")
    assert_secret_free(text)
    assert "serviceKey" not in text
    assert "LIVE_SERVICE_KEY" not in text


def test_production_writer_absent(tmp_path):
    assert SECONDARY_CONTENT_PRODUCTION_INGEST == "NO"
    assert SECONDARY_CONTENT_PRODUCTION_PUBLICATION == "NO"
    assert "import supabase" not in SRC.lower()
    assert "create_client" not in SRC.lower()
    assert "insert(" not in SRC.lower()
    assert "upsert(" not in SRC.lower()
    called = []

    def boom(*_a, **_k):
        called.append(True)
        raise AssertionError("production writer called")

    stream_secondary_index(
        [json.dumps(_raw("000001"))],
        tmp_path / "idx.jsonl",
        source_revision=REV,
        production_writer=boom,
    )
    assert called == []


def test_secondary_body_not_automatically_published(tmp_path):
    dest = tmp_path / "idx.jsonl"
    rec = _raw("000001", text="SECRET_BODY_MUST_NOT_PUBLISH")
    stream_secondary_index([json.dumps(rec)], dest, source_revision=REV, production_writer=None)
    text = dest.read_text(encoding="utf-8")
    assert "SECRET_BODY_MUST_NOT_PUBLISH" not in text
    row = json.loads(text.splitlines()[0])
    assert row["production_content"] == "NO"


def test_cli_probe_and_report(tmp_path, capsys):
    index = tmp_path / "idx.jsonl"
    rc = audit_secondary_content.main(
        [
            "--local-jsonl",
            str(SAMPLE),
            "--max-rows",
            "5",
            "--out",
            str(index),
            "--checkpoint",
            str(tmp_path / "cp.json"),
            "--manifest",
            str(tmp_path / "idx-manifest.json"),
        ]
    )
    assert rc == 0
    official = tmp_path / "official.jsonl"
    official.write_text(
        "\n".join(
            json.dumps(
                {
                    "chemId": cid,
                    "official_name": cid,
                    "official_cas": None,
                    "official_revision_date": "2026-01-01",
                    "official_page": 1,
                }
            )
            for cid in ("000001", "001008", "047134", "000002", "000003", "999999")
        )
        + "\n",
        encoding="utf-8",
    )
    coverage = tmp_path / "cov.jsonl"
    assert build_content_coverage.main(["--official", str(official), "--index", str(index), "--out", str(coverage)]) == 0
    queue = tmp_path / "q.jsonl"
    assert build_hydration_queue.main(["--coverage", str(coverage), "--out", str(queue)]) == 0
    report = tmp_path / "report.json"
    assert content_report.main(
        [
            "--index",
            str(index),
            "--coverage",
            str(coverage),
            "--queue",
            str(queue),
            "--out",
            str(report),
            "--manifest",
            str(tmp_path / "manifest.json"),
        ]
    ) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["metrics"]["STRICT_API_CALLS"] == 96
    assert payload["metrics"]["DELTA_API_CALLS"] == len(queue.read_text(encoding="utf-8").splitlines())
    assert payload["live_bulk_api_calls"] == 0
    assert "serviceKey" not in capsys.readouterr().out


def test_cli_refuses_bare_and_download_max_rows():
    with pytest.raises(SystemExit):
        audit_secondary_content.main([])
    with pytest.raises(SystemExit):
        audit_secondary_content.main(["--download", "--max-rows", "1"])
