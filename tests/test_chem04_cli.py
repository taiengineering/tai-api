"""CHEM-04 local CLIs: fixture/small-probe only. No live HF download, no live KOSHA crawl."""
from __future__ import annotations

import json
import pathlib

import pytest

from services.kosha_msds.contract import (
    CURSOR_FULL_DATA_EXECUTION,
    LOCAL_FULL_DATA_EXECUTION,
    PRODUCTION_INGEST_UNTIL_GPT_APPROVAL,
)
from services.kosha_msds.current_index import parse_list_html
from tools.chem04 import (
    audit_secondary_content,
    bootstrap_seed,
    collect_current_index,
    join_current_identity,
    live_sample_compare,
    report,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "kosha_msds"
SAMPLE = FIXTURES / "secondary_seed_sample.jsonl"


def test_role_split_constants():
    assert CURSOR_FULL_DATA_EXECUTION is False
    assert LOCAL_FULL_DATA_EXECUTION is True
    assert PRODUCTION_INGEST_UNTIL_GPT_APPROVAL is False


def test_bootstrap_refuses_bare_invocation():
    with pytest.raises(SystemExit):
        bootstrap_seed.main([])


def test_content_audit_refuses_bare_invocation():
    with pytest.raises(SystemExit):
        audit_secondary_content.main([])


def test_live_sample_refuses_bare_invocation():
    with pytest.raises(SystemExit):
        live_sample_compare.main([])


def test_collect_refuses_bare_invocation():
    with pytest.raises(SystemExit):
        collect_current_index.main([])


def test_bootstrap_fixture_probe(tmp_path):
    dest = tmp_path / "seed.jsonl"
    manifest = tmp_path / "manifest.json"
    rc = bootstrap_seed.main(
        [
            "--local-jsonl",
            str(SAMPLE),
            "--max-rows",
            "10",
            "--out",
            str(dest),
            "--manifest",
            str(manifest),
        ]
    )
    assert rc == 0
    rows = [json.loads(line) for line in dest.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {row["chemId"] for row in rows} == {"000001", "001008", "047134"}
    assert all("sections" not in row for row in rows)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["executor"] == "CURSOR_PROBE"
    assert payload["stats"]["invalid_skipped"] == 1
    assert payload["production_content"] == "BLOCKED"


def test_join_cli_fixture(tmp_path):
    html = (FIXTURES / "chemlist_page1.html").read_text(encoding="utf-8")
    official_rows, *_ = parse_list_html(html, page=1)
    official = tmp_path / "official.jsonl"
    official.write_text(
        "\n".join(json.dumps(row.as_row(), ensure_ascii=False) for row in official_rows) + "\n",
        encoding="utf-8",
    )
    seed = tmp_path / "seed.jsonl"
    bootstrap_seed.main(
        [
            "--local-jsonl",
            str(SAMPLE),
            "--out",
            str(seed),
            "--manifest",
            str(tmp_path / "m.json"),
        ]
    )
    dest = tmp_path / "join.jsonl"
    rc = join_current_identity.main(
        ["--official", str(official), "--seed", str(seed), "--out", str(dest)]
    )
    assert rc == 0
    joined = [json.loads(line) for line in dest.read_text(encoding="utf-8").splitlines()]
    assert len(joined) == 3
    assert {row["match_method"] for row in joined} == {"DIRECT_OFFICIAL_ID"}
    assert all(row["present_in_secondary"] is True for row in joined)
    assert all(row["resolved_chem_id"] == row["secondary_chemId"] for row in joined)
    assert "serviceKey" not in dest.read_text(encoding="utf-8")


def test_report_secret_free(capsys):
    rc = report.main([])
    assert rc == 0
    text = capsys.readouterr().out
    assert "serviceKey" not in text
    assert "LOCAL" in text
    payload = json.loads(text)
    assert payload["production_ingest"] == "NO"


def test_report_seed_path_arg(tmp_path, capsys):
    seed = tmp_path / "secondary_identity_seed.jsonl"
    seed.write_text(json.dumps({"chemId": "000001"}) + "\n", encoding="utf-8")
    official = tmp_path / "official.jsonl"
    official.write_text("{}\n", encoding="utf-8")
    join = tmp_path / "join.jsonl"
    join.write_text("{}\n", encoding="utf-8")
    rc = report.main(
        [
            "--seed",
            str(seed),
            "--official",
            str(official),
            "--join",
            str(join),
            "--manifest",
            str(tmp_path / "missing.json"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["secondary_seed_rows"] == 1
    assert payload["manifest_present"] is False
    assert payload["secondary_seed_sha256"]
