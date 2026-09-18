"""WO-CHEM-FULL-READINESS-004 — MSDS ops status CLI.

Read-only. No production mutation, no publish, no env change, no
KOSHA API call, no deploy. Uses stdlib urllib for live GETs.

Usage:

    railway run --service tai-api-prod \\
        python3 -m tools.chem_ops.status \\
        --artifact-dir artifacts/chem04/official_v12 \\
        --live-base-url https://api.taieng.co.kr

The `railway run --service tai-api-prod` prefix injects the same
production env vars the SEO preview daily sync uses; the CLI itself
never reads secrets.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from services.kosha_msds import ops


def _git_main_sha(repo_root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _build_stores(no_db: bool):
    """Return (publish_store, read_store).

    In production, calls into `services.kosha_msds.production_store`
    (Supabase-backed) and `services.kosha_msds.read` (Supabase-backed
    for the read side). Tests should NOT use this — they pass their
    own store objects via `collect_status(publish_store=..., read_store=...)`.

    `--no-db` forces empty in-memory stores so the CLI stays useful
    even without a Supabase connection (dev / offline). The output
    will show all production_db counts as None with an explanatory
    note.
    """
    if no_db:
        from services.kosha_msds.publish import MemoryPublishStore
        from services.kosha_msds.read import MemoryMsdsReadStore
        return MemoryPublishStore(), MemoryMsdsReadStore()
    from services.kosha_msds.production_store import SupabasePublishStore
    from services.kosha_msds.read import SupabaseMsdsReadStore
    return SupabasePublishStore(), SupabaseMsdsReadStore()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MSDS ops observability (read-only).")
    p.add_argument("--artifact-dir", default="artifacts/chem04/official_v12",
                   help="Path to CHEM-04 official_v12 artifact directory.")
    p.add_argument("--live-base-url", default=None,
                   help="Base URL for live /search-dict/* GETs. Omit to skip.")
    p.add_argument("--no-db", action="store_true", default=False,
                   help="Skip Supabase connection (in-memory placeholder stores).")
    p.add_argument("--no-deep-scan", action="store_true", default=False,
                   help="Skip the responses.jsonl full-scan (unique_chemicals / "
                        "complete_chemicals / incomplete_chemicals will be None).")
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    git_main = _git_main_sha(repo_root)

    publish_store, read_store = _build_stores(no_db=args.no_db)

    status = ops.collect_status(
        artifact_dir=args.artifact_dir,
        live_base_url=args.live_base_url,
        publish_store=publish_store,
        read_store=read_store,
        deep_scan=not args.no_deep_scan,
        git_main=git_main,
    )

    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_text(status)

    # Exit 0 always — this is a read-only status tool, not a health check.
    # Alerts are surfaced in the payload; downstream tooling decides
    # what to do with them.
    return 0


def _print_text(s: dict) -> None:
    def _line(k, v):
        print(f"  {k:34s} = {v}")

    print("CHEM OPS STATUS")
    r = s["repository"]
    print("[repository]")
    _line("git_main", r["git_main"])
    _line("contract_version", r["contract_version"])
    h = s["hydration"]
    print("[hydration]")
    _line("status", h["status"])
    _line("queue_total", h["queue_total"])
    _line("completed", h["completed"])
    _line("remaining", h["remaining"])
    _line("unique_chemicals", h["unique_chemicals"])
    _line("complete_chemicals", h["complete_chemicals"])
    _line("incomplete_chemicals", h["incomplete_chemicals"])
    _line("next_pending",
          f"{h['next_pending_chem_id']}/{h['next_pending_section']}")
    _line("last_terminal_reason", h["last_terminal_reason"])
    _line("responses_sha256", h["responses_sha256"])
    prod = s["production_db"]
    print("[production_db]")
    _line("chemicals", prod["chemicals"])
    _line("sections", prod["sections"])
    _line("preview_current", prod["preview_current"])
    _line("full_current", prod["full_current"])
    _line("running_snapshots", prod["running_snapshots"])
    _line("failed_snapshots", prod["failed_snapshots"])
    pub = s["publication"]
    print("[publication]")
    _line("preview_count", pub["preview_count"])
    _line("full_count", pub["full_count"])
    _line("latest_preview_snapshot", (pub["latest_preview_snapshot"] or {}).get("id"))
    _line("latest_full_snapshot", (pub["latest_full_snapshot"] or {}).get("id"))
    pr = s["public_runtime"]
    print("[public_runtime]")
    _line("resolved_mode", pr["resolved_mode"])
    _line("effective_scope", pr["effective_scope"])
    _line("is_failsafe_off", pr["is_failsafe_off"])
    d = s["search_dictionary"]
    print("[search_dictionary]")
    _line("runtime_snapshot", d["runtime_snapshot"])
    _line("subjects", d["subjects"])
    _line("indexed_terms", d["indexed_terms"])
    _line("CHEM_TERM MSDS", d["chem_term_msds_matched"])
    _line("CHEM_TERM SDS", d["chem_term_sds_matched"])
    _line("binding", d["binding"])
    fr = s["full_readiness"]
    print("[full_readiness]")
    _line("ready", fr["ready"])
    _line("reason", fr["reason"])
    _line("snapshot_id", fr["snapshot_id"])
    print("[alerts]")
    for a in s["alerts"]:
        print(f"  {a['severity']:4s} {a['code']:36s} {a['evidence']}")


if __name__ == "__main__":
    sys.exit(main())
