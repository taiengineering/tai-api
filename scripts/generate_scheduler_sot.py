"""Emit TAI scheduler SoT JSON from the locked census. stdlib only."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIME = ROOT / "docs" / "time"

# Live catalog 2026-08-31 (read-only SELECT). DOW after-state uses named weekdays.
MASTER = [
    {"job_code":"ALERT_EVALUATE","cron_expression":"*/5 * * * *","is_active":True,"endpoint":"direct://alert_evaluate","command_type":"DIRECT","handler":"direct://alert_evaluate"},
    {"job_code":"AUTO_PARSE_NEW","cron_expression":"0 4 * * mon","is_active":False,"endpoint":"/law-rule-generator/auto-parse-and-approve","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"CONTROL_BRIDGE_EVALUATE","cron_expression":"*/3 * * * *","is_active":True,"endpoint":"direct://control_bridge_evaluate","command_type":"DIRECT","handler":"direct://control_bridge_evaluate"},
    {"job_code":"DB_STATS_COLLECT","cron_expression":"0 0 * * *","is_active":True,"endpoint":"/admin/stats","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"DUE_ALERT_DAILY","cron_expression":"0 8 * * *","is_active":True,"endpoint":"/notifications/trigger-due-alerts","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"EDU_EXPIRE_DAILY","cron_expression":"0 1 * * *","is_active":True,"endpoint":"direct://education_assignment_expire","command_type":"DIRECT","handler":"direct://education_assignment_expire"},
    {"job_code":"INCIDENT_REPEATED","cron_expression":"*/5 * * * *","is_active":True,"endpoint":"direct://incident_repeated","command_type":"DIRECT","handler":"direct://incident_repeated"},
    {"job_code":"INTEGRITY_EVALUATE","cron_expression":"*/5 * * * *","is_active":True,"endpoint":"direct://integrity_evaluate","command_type":"DIRECT","handler":"direct://integrity_evaluate"},
    {"job_code":"KCSC_SYNC","cron_expression":"0 5 1 * *","is_active":True,"endpoint":"/kcsc/sync","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"LAW_COLLECT_MISSING","cron_expression":"0 4 * * sun","is_active":False,"endpoint":"/law-collector/collect-missing","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"LAW_RECOLLECT_15D","cron_expression":"0 3 1,16 * *","is_active":False,"endpoint":"/law-collector/check-updates-v2","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"LAW_UPDATE_CHECK","cron_expression":"0 3 * * *","is_active":False,"endpoint":"/law-collector/check-updates","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"NOTIFICATION_METRICS","cron_expression":"*/10 * * * *","is_active":True,"endpoint":"direct://notification_collect_metrics","command_type":"DIRECT","handler":"direct://notification_collect_metrics"},
    {"job_code":"NOTIFICATION_QUEUE_WORKER","cron_expression":"* * * * *","is_active":True,"endpoint":"direct://notification_queue_worker","command_type":"DIRECT","handler":"direct://notification_queue_worker"},
    {"job_code":"OVERDUE_DISPATCH","cron_expression":"*/10 5-10 * * *","is_active":False,"endpoint":"/overdue/dispatch","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"OVERDUE_PREPARE","cron_expression":"0 4 * * *","is_active":False,"endpoint":"/overdue/prepare","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"PATTERN_SYNC","cron_expression":"0 */6 * * *","is_active":True,"endpoint":"direct://pattern_sync","command_type":"DIRECT","handler":"direct://pattern_sync"},
    {"job_code":"PRECEDENT_COLLECT_WEEKLY","cron_expression":"0 5 * * mon","is_active":True,"endpoint":"/precedents/collect","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"REPORT_DAILY","cron_expression":"0 8 * * *","is_active":True,"endpoint":"/admin/stats","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"RULE_REPARSE","cron_expression":"0 4 * * wed","is_active":False,"endpoint":"/law-rule-generator/reparse-master","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"SCHEDULE_GENERATE_ALL","cron_expression":"0 7 * * mon","is_active":False,"endpoint":"/legal-engine/generate-schedules","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"SITUATION_RETENTION_POLICY","cron_expression":"0 3 * * *","is_active":True,"endpoint":"direct://situation_retention_policy","command_type":"DIRECT","handler":"direct://situation_retention_policy"},
    {"job_code":"SITUATION_SNAPSHOT_GENERATE","cron_expression":"*/5 * * * *","is_active":True,"endpoint":"direct://situation_snapshot_generate","command_type":"DIRECT","handler":"direct://situation_snapshot_generate"},
    {"job_code":"SYNTHETIC_BROWSER_LOGIN","cron_expression":"*/15 * * * *","is_active":True,"endpoint":"direct://browser_synthetic_login","command_type":"DIRECT","handler":"direct://browser_synthetic_login"},
    {"job_code":"SYNTHETIC_BROWSER_PROCESS","cron_expression":"*/15 * * * *","is_active":True,"endpoint":"direct://browser_synthetic_process","command_type":"DIRECT","handler":"direct://browser_synthetic_process"},
    {"job_code":"SYNTHETIC_CHAOS_INJECTION","cron_expression":"*/5 * * * *","is_active":False,"endpoint":"direct://synthetic_chaos_injection","command_type":"DIRECT","handler":"direct://synthetic_chaos_injection"},
    {"job_code":"SYNTHETIC_CLEANUP","cron_expression":"0 3 * * *","is_active":True,"endpoint":"direct://synthetic_cleanup","command_type":"DIRECT","handler":"direct://synthetic_cleanup"},
    {"job_code":"SYNTHETIC_LOGIN","cron_expression":"*/5 * * * *","is_active":True,"endpoint":"direct://synthetic_login","command_type":"DIRECT","handler":"direct://synthetic_login"},
    {"job_code":"SYNTHETIC_PROCESS_REG","cron_expression":"*/15 * * * *","is_active":True,"endpoint":"direct://synthetic_process_reg","command_type":"DIRECT","handler":"direct://synthetic_process_reg"},
    {"job_code":"SYNTHETIC_RUNTIME_TICK","cron_expression":"*/3 * * * *","is_active":False,"endpoint":"direct://synthetic_runtime_tick","command_type":"DIRECT","handler":"direct://synthetic_runtime_tick"},
    {"job_code":"SYSTEM_HEALTH_CHECK","cron_expression":"*/10 * * * *","is_active":True,"endpoint":"/health","command_type":"HTTP","handler":"HTTP"},
    {"job_code":"VALIDATE_MASTER","cron_expression":"0 6 * * fri","is_active":False,"endpoint":"/law-rule-generator/validate-master","command_type":"HTTP","handler":"HTTP"},
]

CONFIG_JOB_CODES = [
    "CONTROL_BRIDGE_EVALUATE","DB_STATS_COLLECT","INTEGRITY_EVALUATE","KCSC_SYNC",
    "LAW_COLLECT_MISSING","LAW_UPDATE_CHECK","REPORT_DAILY","RULE_REPARSE",
    "SYNTHETIC_CHAOS_INJECTION","SYNTHETIC_RUNTIME_TICK","SYSTEM_HEALTH_CHECK",
]

PGCRON = [
    {"jobid":1,"jobname":"daily_assignments","active_old":False,"command_type":"DB_FUNCTION","kst_schedule":"10 9 * * *","handler":"direct://generate_daily_assignments","command":"SELECT generate_daily_assignments()"},
    {"jobid":2,"jobname":"daily_health","active_old":True,"command_type":"DB_FUNCTION","kst_schedule":"0 9 * * *","handler":"direct://daily_health_check","command":"SELECT daily_health_check()"},
    {"jobid":3,"jobname":"qa_send","active_old":False,"command_type":"DB_FUNCTION","kst_schedule":"0,30 * * * *","handler":"direct://send_auto_qa_requests","command":"SELECT send_auto_qa_requests()"},
    {"jobid":4,"jobname":"qa_collect","active_old":False,"command_type":"DB_FUNCTION","kst_schedule":"2,32 * * * *","handler":"direct://collect_auto_qa_results","command":"SELECT collect_auto_qa_results()"},
    {"jobid":5,"jobname":"kosha_construction_21","active_old":True,"command_type":"HTTP","kst_schedule":"0 6 * * *","handler":"direct://kosha_construction_safety_light","command":"POST /kosha-collect/construction-safety-light"},
    {"jobid":6,"jobname":"kosha_construction_03","active_old":True,"command_type":"HTTP","kst_schedule":"0 12 * * *","handler":"direct://kosha_construction_safety_light","command":"POST /kosha-collect/construction-safety-light"},
    {"jobid":7,"jobname":"kosha_construction_09","active_old":True,"command_type":"HTTP","kst_schedule":"0 18 * * *","handler":"direct://kosha_construction_safety_light","command":"POST /kosha-collect/construction-safety-light"},
    {"jobid":8,"jobname":"kosha_accidents","active_old":True,"command_type":"HTTP","kst_schedule":"0 2 * * *","handler":"direct://kosha_accident_cases","command":"POST /kosha-collect/accident-cases"},
    {"jobid":9,"jobname":"kosha_weekly","active_old":True,"command_type":"HTTP","kst_schedule":"0 3 * * mon","handler":"direct://kosha_safety_materials","command":"POST /kosha-collect/run?target=safety-materials"},
    {"jobid":10,"jobname":"health_cleanup","active_old":True,"command_type":"CLEANUP","kst_schedule":"0 12 * * *","handler":"direct://health_cleanup","command":"DELETE health_checks/health_alerts now()-30d"},
    {"jobid":11,"jobname":"cron_job_log_retention","active_old":True,"command_type":"CLEANUP","kst_schedule":"17 * * * *","handler":"direct://cron_job_log_retention","command":"cron_job_log started_at < now() - interval '30 days'"},
    {"jobid":12,"jobname":"business_event_retention","active_old":True,"command_type":"CLEANUP","kst_schedule":"27 3 * * *","handler":"direct://business_event_retention","command":"business_event created_at < now() - interval '90 days'"},
]

CODE = [
    {"job_code":"holiday_sync_annual","cron_expression":"10 3 1 12 *","is_active":True,"endpoint":"direct://holiday_sync","command_type":"DIRECT","handler":"direct://holiday_sync"},
    {"job_code":"holiday_sync_quarterly","cron_expression":"10 3 1 1,4,7,10 *","is_active":True,"endpoint":"direct://holiday_sync","command_type":"DIRECT","handler":"direct://holiday_sync"},
]

DOW = [
    {"job_code":"SCHEDULE_GENERATE_ALL","before":"0 7 * * 1","after":"0 7 * * mon","dow":"mon","schedule_desc":"매주 월요일 오전 7시"},
    {"job_code":"PRECEDENT_COLLECT_WEEKLY","before":"0 5 * * 1","after":"0 5 * * mon","dow":"mon","schedule_desc":None},
    {"job_code":"AUTO_PARSE_NEW","before":"0 4 * * 1","after":"0 4 * * mon","dow":"mon","schedule_desc":"매주 월요일 04:00 — 미파싱 조문 AI 파싱 + 자동승인"},
    {"job_code":"LAW_COLLECT_MISSING","before":"0 4 * * 0","after":"0 4 * * sun","dow":"sun","schedule_desc":"매주 일요일 새벽 4시"},
    {"job_code":"RULE_REPARSE","before":"0 4 * * 3","after":"0 4 * * wed","dow":"wed","schedule_desc":"매주 수요일 04:00 — 기존 master 룰 빈칸 AI 보강 (Sonnet)"},
    {"job_code":"VALIDATE_MASTER","before":"0 6 * * 5","after":"0 6 * * fri","dow":"fri","schedule_desc":"매주 금요일 06:00 — 판정룰 무결성 검증 리포트"},
]


def main() -> None:
    jobs = []
    for m in MASTER:
        jobs.append({**m, "source": "master"})
    for p in PGCRON:
        jobs.append({
            "job_code": p["jobname"],
            "source": "pgcron",
            "cron_expression": p["kst_schedule"],
            "is_active": p["active_old"],
            "endpoint": p["handler"],
            "command_type": p["command_type"],
            "handler": p["handler"],
        })
    for c in CODE:
        jobs.append({**c, "source": "code"})
    universe = {
        "universe_count": 46,
        "master_count": 32,
        "master_active": 21,
        "config_count": 11,
        "master_without_config": 21,
        "config_without_master": 0,
        "pgcron_count": 12,
        "pgcron_active": 9,
        "code_only_count": 2,
        "jobs": jobs,
    }
    TIME.mkdir(parents=True, exist_ok=True)
    (TIME / "TAI_SCHEDULER_UNIVERSE_MANIFEST.json").write_text(
        json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    retirement = {
        "mapped": 12,
        "active_old": 9,
        "inactive_old": 3,
        "delete_unschedule": False,
        "jobs": PGCRON,
    }
    (TIME / "TAI_PGCRON_RETIREMENT_MAP.json").write_text(
        json.dumps(retirement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    contradictions = []
    for row in DOW:
        desc = (row["schedule_desc"] or "").lower()
        if not desc:
            continue
        expected = {"mon": "월", "sun": "일", "wed": "수", "fri": "금"}[row["dow"]]
        if expected not in (row["schedule_desc"] or ""):
            contradictions.append(row["job_code"])
    dow_doc = {
        "numeric_before": 6,
        "numeric_after": 0,
        "contradiction_count": len(contradictions),
        "contradictions": contradictions,
        "mappings": DOW,
    }
    (TIME / "TAI_CRON_DOW_NORMALIZATION.json").write_text(
        json.dumps(dow_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote 3 manifests", len(jobs))


if __name__ == "__main__":
    main()
