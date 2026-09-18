"""WO-CHEM-05 build materialize plan (Phase B: local terminal only).

Reads:
    - artifacts/chem04/official_v12/responses.jsonl   (KOSHA hydration runner output)
    - optional census JSONL keyed by chem_id

Writes (all gitignored under artifacts/chem05/):
    - materialize_plan.jsonl      one JSONL row per chemId (chemical + sections)
    - materialize_manifest.json   provenance and SHA256s
    - materialize_report.json     dry-run summary (execute_eligible + counts)

No DB I/O. No live API calls. No hydration mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Iterator

from services.kosha_msds import materialize as m

DEFAULT_RESPONSES = Path("artifacts/chem04/official_v12/responses.jsonl")
DEFAULT_OUT_DIR = Path("artifacts/chem05")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"BLOCKED: {path}:{lineno} is not valid JSON: {exc}"
                ) from exc


def _load_census(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    if not path.exists():
        raise SystemExit(f"BLOCKED: census path not found: {path}")
    out: dict[str, dict] = {}
    for row in _iter_jsonl(path):
        chem_id = row.get("chem_id") or row.get("chemId")
        if not isinstance(chem_id, str) or not chem_id:
            raise SystemExit(f"BLOCKED: census row missing chem_id: {row!r}")
        out[chem_id] = {
            "chemical_name_ko": row.get("chemical_name_ko") or row.get("chemNameKor"),
            "chemical_name_en": row.get("chemical_name_en") or row.get("chemNameEng"),
            "cas_no": row.get("cas_no") or row.get("casNo"),
            "ke_no": row.get("ke_no") or row.get("keNo"),
            "en_no": row.get("en_no") or row.get("enNo"),
            "un_no": row.get("un_no") or row.get("unNo"),
            "last_date": row.get("last_date") or row.get("lastDate"),
            "open_yn": row.get("open_yn") or row.get("openYn"),
            "kosha_confirm": row.get("kosha_confirm") or row.get("koshaConfirm"),
        }
    return out


def _write_plan_jsonl(plan: m.MaterializePlan, path: Path) -> str:
    """Write plan.jsonl deterministically. Return its raw file SHA256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as fh:
        for c in sorted(plan.chemicals, key=lambda x: x.chem_id):
            line = json.dumps(
                c.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            )
            fh.write(line + "\n")
            h.update((line + "\n").encode("utf-8"))
    return h.hexdigest()


def _canonical_json_sha256(obj: object) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(
    *,
    responses_path: Path,
    census_path: Path | None,
    out_dir: Path,
) -> dict:
    if not responses_path.exists():
        raise SystemExit(f"BLOCKED: responses.jsonl not found at {responses_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "materialize_plan.jsonl"
    manifest_path = out_dir / "materialize_manifest.json"
    report_path = out_dir / "materialize_report.json"

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    responses_sha = _file_sha256(responses_path)

    census = _load_census(census_path)
    plan = m.build_plan(
        artifact_records=_iter_jsonl(responses_path),
        census=census,
        artifact_responses_sha256=responses_sha,
    )

    plan_file_sha = _write_plan_jsonl(plan, plan_path)

    manifest = {
        "wo": "WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001",
        "adapter_version": m.ADAPTER_VERSION,
        "responses_path": str(responses_path),
        "responses_sha256": responses_sha,
        "census_path": str(census_path) if census_path else None,
        "census_size": len(census),
        "plan_path": str(plan_path),
        "plan_file_sha256": plan_file_sha,
        "plan_semantic_sha256": plan.plan_sha256,
        "snapshot": plan.snapshot.to_dict(),
        "counts": dict(plan.counts),
        "execute_eligible": plan.execute_eligible,
        "execute_block_reasons": list(plan.execute_block_reasons),
        "started_at": started_at,
        "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    manifest["manifest_sha256"] = _canonical_json_sha256(
        {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = plan.to_report()
    report["responses_path"] = str(responses_path)
    report["responses_sha256"] = responses_sha
    report["plan_file_sha256"] = plan_file_sha
    report["manifest_sha256"] = manifest["manifest_sha256"]
    report["adapter_version"] = m.ADAPTER_VERSION
    report["started_at"] = started_at
    report["ended_at"] = manifest["ended_at"]
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-CHEM-05 build materialize plan (dry-run planner)."
    )
    parser.add_argument("--responses", default=str(DEFAULT_RESPONSES))
    parser.add_argument("--census", default=None,
                        help="Optional census JSONL keyed by chem_id.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    report = run(
        responses_path=Path(args.responses),
        census_path=Path(args.census) if args.census else None,
        out_dir=Path(args.out_dir),
    )
    # Print a compact summary; not the whole plan.
    summary = {
        "counts": report["counts"],
        "execute_eligible": report["execute_eligible"],
        "execute_block_reasons": report["execute_block_reasons"],
        "plan_semantic_sha256": report["plan_sha256"],
        "plan_file_sha256": report["plan_file_sha256"],
        "manifest_sha256": report["manifest_sha256"],
        "responses_sha256": report["responses_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
