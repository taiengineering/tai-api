"""WO-RISK-KALIS-MAP-001-R1 KALIS source→canonical mapping review evidence.

Deterministic, read-only. Derives the KALIS TASK review universe from the
frozen KALIS CSV via the existing risk02 ingest logic, attaches existing
CIC_W (1139) + KOSHA (46) APPROVED mapping evidence per candidate
canonical, and emits the review-pack TSVs for downstream GPT semantic
review.

NO LLM. NO embedding. NO fuzzy. NO Kiwi. NO synonym expansion. NO DB write.
NO canonical mutation. NO mapping mutation.

Layer A retrieval : exact name_normalized match against 554 TASK canonicals
Layer B retrieval : controlled lexical variants (drop terminal '작업',
                    substring, token overlap) — retrieval only, never a
                    semantic decision
Layer C evidence  : for each candidate canonical, attach the CIC_W /
                    KOSHA source names that already APPROVED-map to it

Identity contract (locked in from KOSHA B07 §2 onward):
  * review_key = review artifact identity
  * source_key = KALIS source-node identity (from risk02.identity)
  * family_key = normalized task-name grouping aid — NOT canonical identity
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools.risk01.analyze_3way import read_csv_rows
from tools.risk02.plan_source_core import _c_plan
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

WO_ID = "WO-RISK-KALIS-MAP-001-R1"

SOURCE_ID = "KALIS_RISK_PROFILE"

# ---------------------------------------------------------------------------
# Frozen input anchors
# ---------------------------------------------------------------------------

_ROOT = Path("docs/knowledge/risk")
_ARTIFACTS_ROOT = Path("artifacts/risk01")

KALIS_CSV_PATH = _ARTIFACTS_ROOT / "source_c/kalis_risk_profile.csv"

CANONICAL_TASK_REFERENCE_PATH = _ROOT / "RISK_KOSHA_B01_CANONICAL_TASK_REFERENCE_v1.tsv"
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

CICW_PROPOSAL_PATH = _ROOT / "RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv"
KOSHA_APPROVAL_BINDING_PATH = _ROOT / "RISK_KOSHA_MAP_APPROVE001_OWNER_APPROVAL_BINDING_v1.tsv"

# Expected census (WO §6). Any deviation → INPUT_DRIFT / BLOCKED.
EXPECTED_TOTAL_NODES = 816
EXPECTED_WORK_BIG = 7
EXPECTED_WORK_MID = 48
EXPECTED_TASK = 761
EXPECTED_DISTINCT_TASK_NAMES = 40

CANDIDATE_CAP = 10

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

REVIEW_UNIVERSE_PATH = _ROOT / "RISK_KALIS_MAP001_REVIEW_UNIVERSE_v1.tsv"
REVIEW_SUMMARY_PATH = _ROOT / "RISK_KALIS_MAP001_REVIEW_SUMMARY_v1.tsv"
REPORT_PATH = _ROOT / "OBJ_risk-kalis-map001-review-evidence_v1.md"


REVIEW_UNIVERSE_FIELDS: tuple[str, ...] = (
    "review_key",
    "source_key",
    "family_key",
    "parent_source_key",
    "work_big",
    "work_mid",
    "name_raw",
    "name_normalized",
    "path_raw",
    "candidate_count",
    "candidate_canonical_ids",
    "candidate_canonical_names",
    "candidate_cic_w_evidence",
    "candidate_kosha_evidence",
    "gpt_semantic_decision",
    "gpt_target_canonical_id",
    "gpt_mapping_type",
    "gpt_confidence_class",
    "gpt_reason",
)

REVIEW_SUMMARY_FIELDS: tuple[str, ...] = (
    "family_key",
    "task_name",
    "task_name_normalized",
    "occurrence_count",
    "distinct_work_big_count",
    "work_big_values",
    "distinct_work_mid_count",
    "work_mid_values",
    "paths",
    "source_keys",
    "candidate_count",
    "candidate_canonical_ids",
    "candidate_canonical_names",
    "candidate_cic_w_evidence",
    "candidate_kosha_evidence",
    "gpt_family_decision",
    "gpt_mapping_type",
    "gpt_target_canonical_id",
    "gpt_context_split_rule",
    "gpt_confidence",
    "gpt_reason",
)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _sha256_join(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _review_key(source_key: str) -> str:
    return _sha256_join(SOURCE_ID, "REVIEW", source_key)


def _family_key(name_normalized: str) -> str:
    return _sha256_join(SOURCE_ID, "FAMILY", name_normalized)


# ---------------------------------------------------------------------------
# Load KALIS source universe (deterministic, from frozen CSV)
# ---------------------------------------------------------------------------


def _load_kalis_task_nodes() -> list[dict]:
    if not KALIS_CSV_PATH.exists():
        raise SystemExit(f"MISSING_KALIS_SOURCE_CSV {KALIS_CSV_PATH}")
    enc, header, rows, _stats = read_csv_rows(KALIS_CSV_PATH)
    _records, nodes, _meta = _c_plan(header, rows)

    by_type: Counter[str] = Counter(n["node_type"] for n in nodes)
    if len(nodes) != EXPECTED_TOTAL_NODES:
        raise SystemExit(
            f"INPUT_DRIFT nodes={len(nodes)} expected={EXPECTED_TOTAL_NODES}"
        )
    if by_type.get("WORK_BIG", 0) != EXPECTED_WORK_BIG:
        raise SystemExit(f"INPUT_DRIFT work_big={by_type.get('WORK_BIG')}")
    if by_type.get("WORK_MID", 0) != EXPECTED_WORK_MID:
        raise SystemExit(f"INPUT_DRIFT work_mid={by_type.get('WORK_MID')}")
    if by_type.get("TASK", 0) != EXPECTED_TASK:
        raise SystemExit(f"INPUT_DRIFT task={by_type.get('TASK')}")

    node_by_key = {n["source_key"]: n for n in nodes}
    tasks = [n for n in nodes if n["node_type"] == "TASK"]

    # Attach work_big / work_mid via parent chain.
    enriched: list[dict] = []
    for t in tasks:
        mid = node_by_key.get(t["parent_source_key"])
        if not mid or mid["node_type"] != "WORK_MID":
            raise SystemExit(f"BROKEN_PARENT_MID {t['source_key']}")
        big = node_by_key.get(mid["parent_source_key"])
        if not big or big["node_type"] != "WORK_BIG":
            raise SystemExit(f"BROKEN_PARENT_BIG {t['source_key']}")
        enriched.append(
            {
                "source_key": t["source_key"],
                "parent_source_key": t["parent_source_key"],
                "work_big": big["name_raw"],
                "work_mid": mid["name_raw"],
                "name_raw": t["name_raw"],
                "name_normalized": t["name_normalized"],
                "path_raw": t["path_raw"],
            }
        )

    # Sort deterministically by (name_normalized, path_raw, source_key).
    enriched.sort(key=lambda r: (r["name_normalized"], r["path_raw"], r["source_key"]))

    distinct_names = {t["name_normalized"] for t in enriched}
    if len(distinct_names) != EXPECTED_DISTINCT_TASK_NAMES:
        raise SystemExit(
            f"DISTINCT_TASK_NAME_DRIFT {len(distinct_names)} expected={EXPECTED_DISTINCT_TASK_NAMES}"
        )

    return enriched


# ---------------------------------------------------------------------------
# Canonical + existing APPROVED mapping evidence
# ---------------------------------------------------------------------------


def _load_canonical_reference() -> list[dict]:
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    # Reference is TASK-only by construction; anchor SHA is enforced by
    # kosha_b01_semantic_evidence.canonical_task_reference_sha but we import
    # a lighter check to avoid cross-module coupling here.
    from tools.risk_map.kosha_b01_semantic_evidence import canonical_task_reference_sha
    got = canonical_task_reference_sha(ref)
    if got != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit(f"CANONICAL_TASK_REFERENCE_SHA_DRIFT {got}")
    return ref


def _load_existing_mapping_evidence() -> dict[str, dict[str, list[str]]]:
    """canonical_id → {'cic_w': [source_names…], 'kosha': [source_names…]}."""
    evidence: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"cic_w": [], "kosha": []}
    )

    cicw = load_tsv(CICW_PROPOSAL_PATH)
    if len(cicw) != 1139:
        raise SystemExit(f"CICW_PROPOSAL_ROW_DRIFT {len(cicw)}")
    for r in cicw:
        cid = r["canonical_id"]
        name = r["source_name"]
        if name and name not in evidence[cid]["cic_w"]:
            evidence[cid]["cic_w"].append(name)

    kosha = load_tsv(KOSHA_APPROVAL_BINDING_PATH)
    if len(kosha) != 75:
        raise SystemExit(f"KOSHA_BINDING_ROW_DRIFT {len(kosha)}")
    approved_kosha = [r for r in kosha if r["owner_decision"] == "APPROVE"]
    if len(approved_kosha) != 46:
        raise SystemExit(f"KOSHA_APPROVED_ROW_DRIFT {len(approved_kosha)}")
    for r in approved_kosha:
        cid = r["target_canonical_id"]
        name = r["source_name"]
        if name and name not in evidence[cid]["kosha"]:
            evidence[cid]["kosha"].append(name)

    return dict(evidence)


# ---------------------------------------------------------------------------
# Candidate retrieval (mechanical only)
# ---------------------------------------------------------------------------


def _retrieval_token(name_normalized: str) -> str:
    """Strip terminal '작업' for retrieval only (never rewrites source name)."""
    if name_normalized.endswith("작업") and len(name_normalized) > 2:
        return name_normalized[:-2]
    return name_normalized


def _retrieve_candidates(
    task_name_normalized: str,
    canonical_ref: list[dict],
) -> list[dict]:
    """Return up to CANDIDATE_CAP TASK canonicals ranked mechanically.

    Ranking order (mechanical, deterministic, review-aid only):
      A. exact name_normalized match
      B. canonical.name_normalized contains retrieval_token
      C. canonical.name_normalized token overlap ≥ 1 with task_name_normalized
    """
    seen: dict[str, dict] = {}
    ordered: list[tuple[int, int, str, dict]] = []
    retrieval_token = _retrieval_token(task_name_normalized)
    task_tokens = set(task_name_normalized.split()) if task_name_normalized else set()

    for idx, c in enumerate(canonical_ref):
        cid = c["canonical_id"]
        cname_norm = c["name_normalized"]
        if not cname_norm:
            continue
        # A. exact
        if cname_norm == task_name_normalized:
            score = 0
        # B. substring
        elif retrieval_token and retrieval_token in cname_norm:
            score = 1
        # C. token overlap
        else:
            cand_tokens = set(cname_norm.split())
            if task_tokens and (task_tokens & cand_tokens):
                score = 2
            else:
                continue
        if cid in seen:
            continue
        seen[cid] = c
        ordered.append((score, idx, cid, c))

    ordered.sort(key=lambda x: (x[0], x[1]))
    return [c for _s, _i, _cid, c in ordered[:CANDIDATE_CAP]]


def _format_evidence(names: list[str]) -> str:
    if not names:
        return ""
    return "|".join(names)


# ---------------------------------------------------------------------------
# Build review universe + summary
# ---------------------------------------------------------------------------


def build_review_universe() -> list[dict]:
    tasks = _load_kalis_task_nodes()
    canonical_ref = _load_canonical_reference()
    evidence_map = _load_existing_mapping_evidence()

    # Family bookkeeping so identical (name_normalized) rows share the same
    # deterministic candidate list — retrieval depends only on name.
    family_candidates: dict[str, list[dict]] = {}

    out: list[dict] = []
    for t in tasks:
        name_norm = t["name_normalized"]
        if name_norm not in family_candidates:
            family_candidates[name_norm] = _retrieve_candidates(name_norm, canonical_ref)
        candidates = family_candidates[name_norm]

        cand_ids = "|".join(c["canonical_id"] for c in candidates)
        cand_names = "|".join(c["name"] for c in candidates)
        cic_w_evidence_parts: list[str] = []
        kosha_evidence_parts: list[str] = []
        for c in candidates:
            cid = c["canonical_id"]
            e = evidence_map.get(cid, {"cic_w": [], "kosha": []})
            cic_w_evidence_parts.append(
                f"{c['name']}:{_format_evidence(e['cic_w'])}"
            )
            kosha_evidence_parts.append(
                f"{c['name']}:{_format_evidence(e['kosha'])}"
            )

        out.append(
            {
                "review_key": _review_key(t["source_key"]),
                "source_key": t["source_key"],
                "family_key": _family_key(name_norm),
                "parent_source_key": t["parent_source_key"],
                "work_big": t["work_big"],
                "work_mid": t["work_mid"],
                "name_raw": t["name_raw"],
                "name_normalized": name_norm,
                "path_raw": t["path_raw"],
                "candidate_count": str(len(candidates)),
                "candidate_canonical_ids": cand_ids,
                "candidate_canonical_names": cand_names,
                "candidate_cic_w_evidence": "||".join(cic_w_evidence_parts),
                "candidate_kosha_evidence": "||".join(kosha_evidence_parts),
                # Semantic decision fields — deliberately blank; GPT fills.
                "gpt_semantic_decision": "",
                "gpt_target_canonical_id": "",
                "gpt_mapping_type": "",
                "gpt_confidence_class": "",
                "gpt_reason": "",
            }
        )

    # Deterministic total sort by review_key so SHA is stable.
    out.sort(key=lambda r: r["review_key"])
    _assert_universe_shape(out)
    return out


def _assert_universe_shape(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_TASK:
        raise SystemExit(f"REVIEW_ROW_DRIFT {len(rows)}")
    if len({r["review_key"] for r in rows}) != EXPECTED_TASK:
        raise SystemExit("REVIEW_KEY_NOT_UNIQUE")
    if len({r["source_key"] for r in rows}) != EXPECTED_TASK:
        raise SystemExit("SOURCE_KEY_NOT_UNIQUE")
    if len({(r["review_key"], r["source_key"]) for r in rows}) != EXPECTED_TASK:
        raise SystemExit("PAIR_NOT_UNIQUE")
    families = {r["family_key"] for r in rows}
    if len(families) != EXPECTED_DISTINCT_TASK_NAMES:
        raise SystemExit(
            f"FAMILY_KEY_COUNT_DRIFT {len(families)} expected={EXPECTED_DISTINCT_TASK_NAMES}"
        )
    for r in rows:
        for f in (
            "gpt_semantic_decision",
            "gpt_target_canonical_id",
            "gpt_mapping_type",
            "gpt_confidence_class",
            "gpt_reason",
        ):
            if r[f]:
                raise SystemExit(f"SEMANTIC_DECISION_PREMATURE {r['review_key']} {f}")
        n = int(r["candidate_count"])
        if n < 0 or n > CANDIDATE_CAP:
            raise SystemExit(f"CANDIDATE_COUNT_OUT_OF_RANGE {r['review_key']} {n}")


def build_review_summary(universe: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in universe:
        grouped[r["family_key"]].append(r)
    out: list[dict] = []
    for fkey, rows in grouped.items():
        head = rows[0]
        work_big_values = sorted({r["work_big"] for r in rows})
        work_mid_values = sorted({r["work_mid"] for r in rows})
        paths = sorted({r["path_raw"] for r in rows})
        source_keys = sorted({r["source_key"] for r in rows})
        # Candidates are identical across a family (retrieval depends only on
        # name_normalized), so borrow from the head row.
        out.append(
            {
                "family_key": fkey,
                "task_name": head["name_raw"],
                "task_name_normalized": head["name_normalized"],
                "occurrence_count": str(len(rows)),
                "distinct_work_big_count": str(len(work_big_values)),
                "work_big_values": "|".join(work_big_values),
                "distinct_work_mid_count": str(len(work_mid_values)),
                "work_mid_values": "|".join(work_mid_values),
                "paths": "|".join(paths),
                "source_keys": "|".join(source_keys),
                "candidate_count": head["candidate_count"],
                "candidate_canonical_ids": head["candidate_canonical_ids"],
                "candidate_canonical_names": head["candidate_canonical_names"],
                "candidate_cic_w_evidence": head["candidate_cic_w_evidence"],
                "candidate_kosha_evidence": head["candidate_kosha_evidence"],
                "gpt_family_decision": "",
                "gpt_mapping_type": "",
                "gpt_target_canonical_id": "",
                "gpt_context_split_rule": "",
                "gpt_confidence": "",
                "gpt_reason": "",
            }
        )
    # Sort by (occurrence_count desc, task_name_normalized) for review ergonomics.
    out.sort(key=lambda r: (-int(r["occurrence_count"]), r["task_name_normalized"]))
    if sum(int(r["occurrence_count"]) for r in out) != EXPECTED_TASK:
        raise SystemExit("SUMMARY_OCCURRENCE_SUM_DRIFT")
    if len(out) != EXPECTED_DISTINCT_TASK_NAMES:
        raise SystemExit(f"SUMMARY_FAMILY_COUNT_DRIFT {len(out)}")
    return out


# ---------------------------------------------------------------------------
# SHAs
# ---------------------------------------------------------------------------


def review_universe_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *REVIEW_UNIVERSE_FIELDS)


def review_summary_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *REVIEW_SUMMARY_FIELDS)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    universe: list[dict],
    summary: list[dict],
    shas: dict[str, str],
) -> str:
    cand_dist = Counter(int(r["candidate_count"]) for r in universe)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MAP-001-R1 KALIS mapping review evidence
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KALIS TASK Review Evidence (Delta-Only)

## THIS IS EVIDENCE PREPARATION ONLY

```text
THIS IS NOT SEMANTIC DECISION
THIS IS NOT OWNER APPROVAL
THIS IS NOT PRODUCTION MAPPING
THIS DOES NOT LIFT KALIS IDENTITY HOLD

FAMILY IS REVIEW COMPRESSION AID
FAMILY IS NOT CANONICAL IDENTITY
```

## Inputs (frozen)

```text
KALIS source CSV               = {KALIS_CSV_PATH}
canonical TASK reference SHA   = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
CIC_W mapping proposal         = {CICW_PROPOSAL_PATH.name}
KOSHA owner approval binding   = {KOSHA_APPROVAL_BINDING_PATH.name}
```

Frozen production totals reused verbatim (not reverified this WO):

```text
CIC_W approved mappings   = 1139
KOSHA approved mappings   =   46
existing total mappings   = 1185
KALIS production mappings =    0
canonical                 = 1110 (DRAFT 1110 / ACTIVE 0)
sectors                   =    0
```

## KALIS census

```text
KALIS_RISK_PROFILE source nodes = 816
  WORK_BIG                       =   7
  WORK_MID                       =  48
  TASK                           = 761

distinct TASK name (normalized)  =  40
review families                  =  40
review rows                      = 761
unique review_key                = 761
unique source_key                = 761
```

## Candidate retrieval

Mechanical only — no LLM, no fuzzy, no embedding, no Kiwi, no
synonym expansion. Candidate cap = {CANDIDATE_CAP} / family.

Layer A : exact name_normalized against 554 TASK canonicals
Layer B : substring match on retrieval token (terminal '작업' dropped for retrieval only)
Layer C : token overlap ≥ 1

Per-candidate evidence attaches CIC_W + KOSHA APPROVED source_names
already mapped to that canonical target.

### Candidate distribution across 761 review rows

```text
{chr(10).join(f'  candidates = {n}   rows = {c}' for n, c in sorted(cand_dist.items()))}
```

## Frozen output SHAs

```text
RISK KALIS MAP001 REVIEW UNIVERSE SHA = {shas["universe"]}
RISK KALIS MAP001 REVIEW SUMMARY SHA  = {shas["summary"]}
```

## Reused frozen evidence (not reverified)

```text
FROZEN EVIDENCE REUSED =
PR #362  (RISK-01)
PR #363  (RISK-02)
PR #364  (RISK-03)
PR #366  (CIC_W)
PR #374  (KOSHA)

FROZEN EVIDENCE REVERIFIED =
NO
```

## Verdict

```text
{WO_ID} = PASS / GPT_REVIEW_READY
KALIS TASK = 761 / 761
review families = 40
SEMANTIC DECISION = NOT EXECUTED
OWNER APPROVAL = NOT OPENED
KALIS PRODUCTION MAPPING = 0
CANONICAL MUTATION = 0
MAPPING WRITE = 0
MERGE = NOT AUTHORIZED
NEXT = GPT DELTA-ONLY VERIFY → GPT KALIS SEMANTIC REVIEW
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def write_all() -> dict:
    universe_a = build_review_universe()
    universe_b = build_review_universe()
    if universe_a != universe_b:
        raise SystemExit("REVIEW_UNIVERSE_ROW_ORDER_DRIFT")
    sha_u_a = review_universe_sha(universe_a)
    sha_u_b = review_universe_sha(universe_b)
    if sha_u_a != sha_u_b:
        raise SystemExit(f"REVIEW_UNIVERSE_SHA_DRIFT {sha_u_a} vs {sha_u_b}")

    summary_a = build_review_summary(universe_a)
    summary_b = build_review_summary(universe_a)
    if summary_a != summary_b:
        raise SystemExit("REVIEW_SUMMARY_ROW_ORDER_DRIFT")
    sha_s_a = review_summary_sha(summary_a)
    sha_s_b = review_summary_sha(summary_b)
    if sha_s_a != sha_s_b:
        raise SystemExit(f"REVIEW_SUMMARY_SHA_DRIFT {sha_s_a} vs {sha_s_b}")

    shas = {"universe": sha_u_a, "summary": sha_s_a}

    write_tsv(universe_a, REVIEW_UNIVERSE_PATH, REVIEW_UNIVERSE_FIELDS)
    write_tsv(summary_a, REVIEW_SUMMARY_PATH, REVIEW_SUMMARY_FIELDS)
    REPORT_PATH.write_text(render_report(universe_a, summary_a, shas), encoding="utf-8")

    return {
        "review_rows": len(universe_a),
        "review_families": len(summary_a),
        "review_universe_sha_run1": sha_u_a,
        "review_universe_sha_run2": sha_u_b,
        "review_summary_sha_run1": sha_s_a,
        "review_summary_sha_run2": sha_s_b,
        "review_universe_path": str(REVIEW_UNIVERSE_PATH),
        "review_summary_path": str(REVIEW_SUMMARY_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} evidence generator")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
