"""OBJ-CHEM-FULL-READINESS-005 — FULL acceptance harness CLI.

Read-only composer. Never mutates a store, never publishes, never
changes env. Uses stdlib urllib for the live /search-dict/* GETs.

Usage:

    railway run --service tai-api-prod \\
        python3 -m tools.chem_full_acceptance.check \\
        --artifact-dir artifacts/chem04/official_v12 \\
        --queue artifacts/chem04/content/queues/hydration_queue.jsonl \\
        --plan-dir artifacts/chem05 \\
        --live-base-url https://api.taieng.co.kr

The railway prefix injects the same production env vars the SEO
preview daily sync uses; the CLI itself never reads secrets. Exit
code is always 0 — this is an evidence tool, not a health check;
downstream tooling decides what to do with the verdict.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from services.kosha_msds import full_acceptance as fa
from services.kosha_msds import ops
from services.kosha_msds.contract import PUBLIC_MODE_ENV_VAR


def _git_main_sha(repo_root: Path) -> Optional[str]:
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
    """Return (publish_store, materialize_store).

    Production paths return two distinct Supabase-backed stores.
    `--no-db` returns in-memory placeholders — the harness will still
    produce a verdict (WAIT_HYDRATION/BLOCKED) but the materialize/publish
    stages will be trivially not-ready.
    """
    if no_db:
        from services.kosha_msds.publish import MemoryPublishStore
        from services.kosha_msds.materialize_writer import MemoryMaterializeStore
        return MemoryPublishStore(), MemoryMaterializeStore()
    from services.kosha_msds.production_store import (
        SupabasePublishStore, SupabaseMaterializeStore,
    )
    return SupabasePublishStore(), SupabaseMaterializeStore()


def _load_plan_inputs(plan_dir: Optional[str]):
    """Return (plan_inputs, on_disk_plan_file_sha256) or (None, None)."""
    if not plan_dir:
        return None, None
    p = Path(plan_dir)
    plan_jsonl = p / "materialize_plan.jsonl"
    manifest_json = p / "materialize_manifest.json"
    report_json = p / "materialize_report.json"
    missing = [str(x) for x in (plan_jsonl, manifest_json, report_json) if not x.exists()]
    if missing:
        return None, None
    from services.kosha_msds.materialize_writer import load_plan_inputs

    # PATCH-1 §B1: recompute plan_file_sha256 from the actual bytes on
    # disk so the harness's Stage B can compare it against
    # manifest.plan_file_sha256. Never trust the manifest alone.
    import hashlib
    h = hashlib.sha256()
    with plan_jsonl.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    on_disk_plan_file_sha256 = h.hexdigest()

    inputs = load_plan_inputs(
        plan_jsonl=plan_jsonl,
        manifest_json=manifest_json,
        report_json=report_json,
    )
    return inputs, on_disk_plan_file_sha256


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        description="FULL acceptance harness (read-only composer).")
    p.add_argument("--artifact-dir", default="artifacts/chem04/official_v12",
                   help="CHEM-04 official_v12 artifact directory.")
    p.add_argument("--queue", default="artifacts/chem04/content/queues/hydration_queue.jsonl",
                   help="Frozen hydration queue file (identity gate).")
    p.add_argument("--plan-dir", default=None,
                   help="CHEM-05 plan artifact directory (materialize_plan.jsonl "
                        "+ manifest + report). Omit if no plan is present.")
    p.add_argument("--live-base-url", default=None,
                   help="Base URL for live /search-dict/* GETs. Omit to skip.")
    p.add_argument("--no-db", action="store_true", default=False,
                   help="Skip Supabase connection (empty in-memory placeholder).")
    p.add_argument("--no-deep-scan", action="store_true", default=False,
                   help="Skip responses.jsonl full-scan.")
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    git_main = _git_main_sha(repo_root)

    publish_store, materialize_store = _build_stores(no_db=args.no_db)

    # ── evidence collection (all read-only) ───────────────────────────────
    hydration_status = ops.collect_hydration_status(
        args.artifact_dir, deep_scan=not args.no_deep_scan,
    ).to_dict()
    dictionary_status = ops.collect_dictionary_runtime(
        args.live_base_url,
    ).to_dict()
    public_runtime = ops.collect_public_runtime()
    plan_inputs, on_disk_plan_file_sha256 = _load_plan_inputs(args.plan_dir)

    # Running-snapshot hold (WO §19).
    try:
        from services.kosha_msds.contract import SNAPSHOT_RUNNING
        running = publish_store.count_snapshots_by_status(SNAPSHOT_RUNNING)
    except Exception:
        running = 0

    # ── verdict ───────────────────────────────────────────────────────────
    queue_path = Path(args.queue) if args.queue else None
    report = fa.evaluate_full_acceptance(
        hydration_status=hydration_status,
        plan_inputs=plan_inputs,
        publish_store=publish_store,
        materialize_store=materialize_store,
        dictionary_status=dictionary_status,
        public_mode=public_runtime.resolved_mode,
        queue_path=queue_path,
        running_snapshots=int(running or 0),
        hydration_responses_sha256=hydration_status.get("responses_sha256"),
        on_disk_plan_file_sha256=on_disk_plan_file_sha256,
    )

    envelope = {
        "repository": {
            "git_main": git_main,
            "contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
        },
        "inputs": {
            "artifact_dir": args.artifact_dir,
            "queue": args.queue,
            "plan_dir": args.plan_dir,
            "live_base_url": args.live_base_url,
            "public_mode": public_runtime.resolved_mode,
            "public_mode_raw_env": public_runtime.raw_env_value,
            "public_mode_env_var": PUBLIC_MODE_ENV_VAR,
        },
        "acceptance": report.to_dict(),
    }

    if args.format == "json":
        print(json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_text(envelope)
    return 0


def _print_text(envelope: dict) -> None:
    def _line(k, v):
        print(f"  {k:34s} = {v}")
    print("CHEM FULL ACCEPTANCE HARNESS")
    r = envelope["repository"]
    print("[repository]")
    _line("git_main", r["git_main"])
    _line("contract_version", r["contract_version"])
    i = envelope["inputs"]
    print("[inputs]")
    for k, v in i.items():
        _line(k, v)
    a = envelope["acceptance"]
    print("[acceptance]")
    _line("verdict", a["verdict"])
    _line("overall_block_reasons", ", ".join(a["overall_block_reasons"]) or "—")
    for name, stage in a["stages"].items():
        ready = "READY" if stage["ready"] else "not ready"
        reasons = ", ".join(stage["block_reasons"]) or "—"
        _line(f"stage.{name}", f"{ready}  reasons={reasons}")


if __name__ == "__main__":
    sys.exit(main())
