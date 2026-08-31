"""STEP E static oracle — artifacts that do not require live DB or the missing json_agg SoT."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TIME = ROOT / "docs" / "time"
SQL = ROOT / "docs" / "sql"
sys.path.insert(0, str(ROOT / "scripts"))


def _j(name: str):
    return json.loads((TIME / name).read_text(encoding="utf-8"))


def test_step_c_baseline_and_allowlist_empty():
    baseline = json.loads((ROOT / "time_debt_baseline.json").read_text(encoding="utf-8"))
    allow = json.loads((ROOT / "time_exception_allowlist.json").read_text(encoding="utf-8"))
    assert baseline == {}
    assert allow == {}


def test_partition_manifest_hash_16_children():
    m = _j("TAI_TIME_PARTITION_MANIFEST.json")
    assert m["partition_strategy"] == "HASH"
    assert m["partition_key"] == "factory_id"
    assert m["altered_column"] == "reviewed_at"
    assert m["altered_column_is_partition_key"] is False
    assert m["migration_group"] == "WORK_SCHEDULES_PARTITION"
    assert m["child_alter_count"] == 0
    assert len(m["children"]) == 16
    assert [c["remainder"] for c in m["children"]] == list(range(16))


def test_cron_manifest_12_jobs_schedule_map():
    m = _j("TAI_TIME_CRON_MANIFEST.json")
    assert m["alter_job_available"] is True
    assert m["job_count"] == 12
    jobs = {j["job_id"]: j for j in m["jobs"]}
    assert sorted(jobs) == list(range(1, 13))
    assert jobs[1]["schedule"] == "10 9 * * *"
    assert jobs[2]["schedule"] == "0 9 * * *"
    assert jobs[5]["schedule"] == "0 6 * * *"
    assert jobs[6]["schedule"] == "0 12 * * *"
    assert jobs[7]["schedule"] == "0 18 * * *"
    assert jobs[8]["schedule"] == "0 2 * * *"
    assert jobs[9]["schedule"] == "0 3 * * 1"
    assert jobs[10]["schedule"] == "0 12 * * *"
    assert jobs[12]["schedule"] == "27 3 * * *"
    assert jobs[3]["schedule_changed"] is False
    assert jobs[4]["schedule_changed"] is False
    assert jobs[11]["schedule_changed"] is False
    assert jobs[11]["command_changed"] is True
    assert "now() - interval '30 days'" in jobs[11]["command_predicate"]
    assert "now() - interval '90 days'" in jobs[12]["command_predicate"]
    assert all(j["active_preserved"] for j in m["jobs"])
    assert jobs[1]["active"] is False
    assert jobs[3]["active"] is False
    assert jobs[4]["active"] is False
    assert m["inactive_job_ids"] == [1, 3, 4]


def test_routine_manifest_writers_now_no_change():
    m = _j("TAI_TIME_DB_ROUTINE_MANIFEST.json")
    assert m["localtimestamp_in_tai_functions"] == 0
    assert m["tai_naive_ts_functions"] == 0
    assert m["time_writer_trigger_count"] == 12
    assert m["active_triggers_expected"] == 30
    assert {t["name"] for t in m["time_writer_triggers"]} >= {
        "tai_set_updated_at",
        "fn_set_updated_at",
        "update_timestamp",
        "sync_construction_worker_to_registry",
    }
    assert all(t["clock"] == "now()" and t["change"] == "NO CHANGE" for t in m["time_writer_triggers"])


def test_timezone_and_cron_sql_not_executed_markers():
    tz = (SQL / "20260831_tai_time_database_timezone_cutover.sql").read_text(encoding="utf-8")
    cron = (SQL / "20260831_tai_time_cron_kst_cutover.sql").read_text(encoding="utf-8")
    up = (SQL / "20260831_tai_time_kst_cutover_up.sql").read_text(encoding="utf-8")
    down = (SQL / "20260831_tai_time_kst_cutover_down.sql").read_text(encoding="utf-8")
    assert "ALTER DATABASE postgres SET timezone TO 'Asia/Seoul'" in tz
    assert "EXECUTE = 0" in tz
    assert "cron.alter_job(1, '10 9 * * *'" in cron
    assert cron.count("SELECT cron.alter_job(") == 12
    assert "localtimestamp" in cron.lower()  # mentioned as removed for job 11
    assert "now() - interval '30 days'" in cron
    assert "now() - interval '90 days'" in cron
    assert "DROP VIEW public.v_demo_buildings" in up
    assert "DROP VIEW public.v_equipment_unified" in up
    assert "DROP VIEW public.v_files_unified" in up
    assert "CASCADE" not in up.split("DROP VIEW")[1].split("\n")[0]
    assert "work_schedules" in up and "reviewed_at" in up
    assert "timestamp without time zone" in down
    assert "AT TIME ZONE 'Asia/Seoul'" in up and "AT TIME ZONE 'Asia/Seoul'" in down


def test_postmaster_md_not_executed():
    md = (TIME / "TAI_TIME_CRON_POSTMASTER_CUTOVER.md").read_text(encoding="utf-8")
    assert "cron.timezone" in md
    assert "GMT" in md
    assert "Asia/Seoul" in md
    assert "Restart required" in md
    assert "NOT EXECUTED" in md
    assert "ALTER SYSTEM" in md


def test_generator_isolated_hard_fail():
    """isolated (object, column) in ALTER set must abort, not skip."""
    import generate_time_kst_migration as gen

    views = {
        "views": [
            {
                "name": n,
                "owner": "postgres",
                "definition": f"SELECT 1 AS {n}",
                "comment": None,
            }
            for n in (
                "v_demo_buildings",
                "v_equipment_unified",
                "v_files_unified",
                "v_payments_list",
                "v_process_unified",
            )
        ]
    }
    active = [
        {
            "object_name": "synthetic_clock",
            "column_name": "ticked_at",
            "migration_action": "ALTER_TYPE_USING_KST",
        }
    ]
    isolated = {
        "columns": [{"object_name": "synthetic_clock", "column_name": "ticked_at"}]
    }
    with pytest.raises(SystemExit, match="HARD FAIL isolated"):
        gen.generate(active, isolated, views)


def test_sot_attached_260():
    """Live catalog json_agg is materialized (260). Isolated 20/13. Views have definitions."""
    active = _j("TAI_TIME_ACTIVE_COLUMN_MANIFEST.json")
    isolated = _j("TAI_TIME_ISOLATED_ASSETS.json")
    views = _j("TAI_TIME_VIEW_MANIFEST.json")
    cols = active if isinstance(active, list) else (active.get("columns") or [])
    iso = isolated if isinstance(isolated, list) else (isolated.get("columns") or [])
    assert len(cols) == 260
    assert len(iso) == 20
    assert len({r["object_name"] for r in iso}) == 13
    assert len(views["views"]) == 5
    assert all(v.get("definition") for v in views["views"])
