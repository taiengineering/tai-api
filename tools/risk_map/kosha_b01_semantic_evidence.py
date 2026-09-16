"""WO-RISK-KOSHA-B01-EVIDENCE-001 KOSHA B01 semantic review evidence pack.

Deterministic mechanical retrieval only. Evidence-only. Zero DB write surface.
Zero live-DB read: everything is derived from committed repository evidence, so
CI runs the tests with skip = 0.

Inputs (all frozen repository TSVs):
  * RISK_KOSHA_MAP001_GPT_REVIEW_PACK_v1.tsv        — filter to batch_no = B01
  * RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv — canonical TASK anchor
  * RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv        — CIC_W provenance
                                                     source_name enrichment
  * RISK_MAP001_MATERIALIZATION_RECEIPT_v1.tsv      — production APPROVED
                                                     gate for CIC_W provenance

No LLM. No embedding. No fuzzy. No Levenshtein. No synonym expansion.
No language-specific morphology. No semantic decision. Score is a
deterministic sort key, not a confidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools.risk04.identity import sha256_parts
from tools.risk04.materialize001_resume_effective_plan import (
    FROZEN_RECEIPT_SHA as FROZEN_CANONICAL_RECEIPT_SHA,
    RECEIPT_PATH as CANONICAL_RECEIPT_PATH,
    receipt_sha as canonical_receipt_sha,
)
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_map001_review_universe import (
    GPT_REVIEW_PACK_FIELDS,
    GPT_REVIEW_PACK_PATH,
)
from tools.risk_map.map_approve001_owner_binding import (
    FROZEN_PROPOSAL_SHA,
)
from tools.risk_map.map001_cicw_governance import (
    PROPOSAL_PATH as CICW_PROPOSAL_PATH,
    proposal_sha as cicw_proposal_sha,
)
from tools.risk_map.map_materialize001 import (
    RECEIPT_FIELDS as MATERIALIZATION_RECEIPT_FIELDS,
    RECEIPT_PATH as MATERIALIZATION_RECEIPT_PATH,
)

WO_ID = "WO-RISK-KOSHA-B01-EVIDENCE-001"
BATCH_ID = "B01"
BATCH_SIZE = 100
CANDIDATE_CAP = 10

CANONICAL_TASK_REFERENCE_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B01_CANONICAL_TASK_REFERENCE_v1.tsv"
)
B01_EVIDENCE_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B01_SEMANTIC_EVIDENCE_v1.tsv"
)
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk-kosha-b01-semantic-evidence_v1.md")

FROZEN_GPT_REVIEW_PACK_SHA = (
    "20bcdf3a7827a2446dae933a1d055463176478cccf86f7ad8c607c23fe29f9b5"
)
FROZEN_KOSHA_REVIEW_UNIVERSE_SHA = (
    "30a2762eec244518fd73eb53fb0c3e53f56e6a41669569d94ee570175cd0e04a"
)
FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA = (
    "8aa2efc056ac9873db108c07bce72ce691308badb7d413cc45cf306c110cc61b"
)

EXPECTED_B01_ROWS = 100
EXPECTED_EXACT_NAME_ROWS = 12
EXPECTED_SEMANTIC_SEARCH_ROWS = 88
EXPECTED_CANONICAL_TASK_ROWS = 554

# Deterministic tokenizer stopword list — intentionally empty per WO §13
# "가능하면 불용어 제거 없이 raw token overlap도 함께 보존한다."
STOPWORDS: frozenset[str] = frozenset()

# WO §14 mechanical score weights (sort key only, NOT a semantic score).
SCORE_EXACT_NORMALIZED_NAME = 1000
SCORE_SOURCE_IN_CANONICAL_SUBSTRING = 300
SCORE_CANONICAL_IN_SOURCE_SUBSTRING = 300
SCORE_SHARED_NAME_TOKEN = 50
SCORE_SHARED_WORK_TYPE_PATH_TOKEN = 20
SCORE_SHARED_PROJECT_KIND_PATH_TOKEN = 10

CANONICAL_TASK_REFERENCE_FIELDS: tuple[str, ...] = (
    "canonical_id",
    "name",
    "name_normalized",
    "parent_canonical_id",
    "parent_name",
    "canonical_path",
    "origin_type",
    "status",
    "cicw_approved_mapping_count",
    "cicw_source_names",
)


def _candidate_fields() -> tuple[str, ...]:
    fields: list[str] = []
    for i in range(1, CANDIDATE_CAP + 1):
        fields.extend(
            [
                f"candidate_{i}_canonical_id",
                f"candidate_{i}_name",
                f"candidate_{i}_parent",
                f"candidate_{i}_path",
                f"candidate_{i}_origin_type",
                f"candidate_{i}_cicw_mapping_count",
                f"candidate_{i}_mechanical_score",
                f"candidate_{i}_reasons",
            ]
        )
    return tuple(fields)


B01_EVIDENCE_FIELDS: tuple[str, ...] = (
    # 10 preserved source-side fields (WO §10)
    "review_key",
    "source_key",
    "project_kind",
    "work_type",
    "detail_process",
    "source_name",
    "source_name_normalized",
    "source_path",
    "source_path_normalized",
    "source_occurrence_count",
    "duplicate_occurrence_flag",
    "candidate_class",
    "exact_name_hit_count",
    "exact_name_canonical_id",
    # aggregate mechanical retrieval
    "mechanical_candidate_count",
    "evidence_state",
) + _candidate_fields() + (
    # GPT decision holders — blank in this WO (§20-22)
    "gpt_semantic_decision",
    "gpt_target_canonical_id",
    "gpt_mapping_type",
    "gpt_reason",
    "gpt_confidence_class",
)


# ---------------------------------------------------------------------------
# Deterministic normalization + tokenization
# ---------------------------------------------------------------------------


_PUNCT_SPLIT_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


def _norm(value: str) -> str:
    """Lightweight normalization: NFC + collapse-whitespace-and-common-separators."""
    text = unicodedata.normalize("NFC", value or "")
    text = text.replace("　", " ").replace("\xa0", " ")
    text = re.sub(r"[\s/·ㆍ・,]+", " ", text)
    return text.strip()


def _tokens(value: str) -> tuple[str, ...]:
    """Deterministic tokenization: NFC-normalize → split on any non-\\w unicode boundary → filter empty + stopwords."""
    normalized = _norm(value)
    parts = [p for p in _PUNCT_SPLIT_RE.split(normalized) if p]
    return tuple(p for p in parts if p not in STOPWORDS)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _load_gpt_pack_b01() -> list[dict]:
    all_rows = load_tsv(GPT_REVIEW_PACK_PATH)
    if universe_sha(all_rows, *GPT_REVIEW_PACK_FIELDS) != FROZEN_GPT_REVIEW_PACK_SHA:
        raise SystemExit("GPT_REVIEW_PACK_SHA_DRIFT")
    b01 = [r for r in all_rows if r["batch_no"] == BATCH_ID]
    if len(b01) != EXPECTED_B01_ROWS:
        raise SystemExit(f"B01_ROW_COUNT_DRIFT {len(b01)}")
    if len({r["review_key"] for r in b01}) != EXPECTED_B01_ROWS:
        raise SystemExit("B01_REVIEW_KEY_DUPLICATE")
    if len({r["source_key"] for r in b01}) != EXPECTED_B01_ROWS:
        raise SystemExit("B01_SOURCE_KEY_DUPLICATE")
    exact = sum(1 for r in b01 if r["candidate_class"] == "EXACT_NAME_CANDIDATE")
    semantic = sum(1 for r in b01 if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED")
    if exact != EXPECTED_EXACT_NAME_ROWS:
        raise SystemExit(f"B01_EXACT_NAME_COUNT_DRIFT {exact}")
    if semantic != EXPECTED_SEMANTIC_SEARCH_ROWS:
        raise SystemExit(f"B01_SEMANTIC_SEARCH_COUNT_DRIFT {semantic}")
    return b01


def _load_canonical_receipt() -> list[dict]:
    rows = load_tsv(CANONICAL_RECEIPT_PATH)
    if len(rows) != 1110:
        raise SystemExit(f"CANONICAL_RECEIPT_ROWS {len(rows)}")
    if canonical_receipt_sha(rows) != FROZEN_CANONICAL_RECEIPT_SHA:
        raise SystemExit("CANONICAL_RECEIPT_SHA_DRIFT")
    return rows


def _load_cicw_evidence() -> list[dict]:
    """Return CIC_W (source_name, canonical_id) pairs, gated by the frozen
    materialization receipt so we only trust proven-in-production provenance."""
    proposal = load_tsv(CICW_PROPOSAL_PATH)
    if cicw_proposal_sha(proposal) != FROZEN_PROPOSAL_SHA:
        raise SystemExit("CICW_PROPOSAL_SHA_DRIFT")
    if len(proposal) != 1139:
        raise SystemExit(f"CICW_PROPOSAL_ROWS {len(proposal)}")

    mat = load_tsv(MATERIALIZATION_RECEIPT_PATH)
    if universe_sha(mat, *MATERIALIZATION_RECEIPT_FIELDS) != FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA:
        raise SystemExit("MAP_MATERIALIZATION_RECEIPT_SHA_DRIFT")
    if len(mat) != 1139:
        raise SystemExit(f"MAP_MATERIALIZATION_RECEIPT_ROWS {len(mat)}")

    materialized_keys = {(r["source_id"], r["source_key"], r["canonical_id"]) for r in mat}
    proven = [
        p
        for p in proposal
        if (p["source_id"], p["source_key"], p["canonical_id"]) in materialized_keys
    ]
    if len(proven) != 1139:
        raise SystemExit(f"CICW_PROVEN_ROW_COUNT_DRIFT {len(proven)}")
    return proven


# ---------------------------------------------------------------------------
# Canonical TASK reference
# ---------------------------------------------------------------------------


def build_canonical_task_reference() -> list[dict]:
    receipt = _load_canonical_receipt()
    by_id = {r["canonical_id"]: r for r in receipt}

    def _resolve_path(canonical: dict) -> tuple[str, str]:
        """Return (canonical_path, parent_name). Fails loudly if a declared parent is unresolvable."""
        chain: list[str] = [canonical["name"]]
        parent_name = ""
        cur = canonical
        seen: set[str] = {canonical["canonical_id"]}
        while cur.get("parent_canonical_id") and cur["parent_canonical_id"] != "EMPTY":
            parent = by_id.get(cur["parent_canonical_id"])
            if parent is None:
                raise SystemExit(
                    f"PARENT_RESOLUTION_ERROR canonical={canonical['canonical_id']} "
                    f"missing_parent={cur['parent_canonical_id']}"
                )
            if parent["canonical_id"] in seen:
                raise SystemExit(
                    f"PARENT_CYCLE canonical={canonical['canonical_id']}"
                )
            seen.add(parent["canonical_id"])
            if cur is canonical:
                parent_name = parent["name"]
            chain.insert(0, parent["name"])
            cur = parent
        return " > ".join(chain), parent_name

    cicw_evidence = _load_cicw_evidence()
    by_canonical_source_names: dict[str, list[str]] = defaultdict(list)
    by_canonical_count: Counter[str] = Counter()
    for row in cicw_evidence:
        by_canonical_source_names[row["canonical_id"]].append(row["source_name"])
        by_canonical_count[row["canonical_id"]] += 1

    tasks = [r for r in receipt if r["node_kind"] == "TASK"]
    if len(tasks) != EXPECTED_CANONICAL_TASK_ROWS:
        raise SystemExit(f"CANONICAL_TASK_COUNT_DRIFT {len(tasks)}")

    rows: list[dict] = []
    for t in tasks:
        path, parent_name = _resolve_path(t)
        source_names = sorted(set(by_canonical_source_names.get(t["canonical_id"], [])))
        rows.append(
            {
                "canonical_id": t["canonical_id"],
                "name": t["name"],
                "name_normalized": t["name_normalized"],
                "parent_canonical_id": t["parent_canonical_id"],
                "parent_name": parent_name,
                "canonical_path": path,
                "origin_type": t["origin_type"],
                "status": t["status"],
                "cicw_approved_mapping_count": str(by_canonical_count.get(t["canonical_id"], 0)),
                "cicw_source_names": " | ".join(source_names),
            }
        )
    rows.sort(key=lambda r: (r["canonical_path"], r["canonical_id"]))
    return rows


def canonical_task_reference_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CANONICAL_TASK_REFERENCE_FIELDS)


# ---------------------------------------------------------------------------
# Mechanical candidate discovery
# ---------------------------------------------------------------------------


def _canonical_index(reference_rows: list[dict]) -> list[dict]:
    """Pre-compute normalized surfaces + token sets for each canonical TASK."""
    index = []
    for r in reference_rows:
        name_norm = r["name_normalized"]
        name_tokens = set(_tokens(r["name"]))
        path_tokens = set(_tokens(r["canonical_path"]))
        index.append(
            {
                "canonical_id": r["canonical_id"],
                "name": r["name"],
                "name_normalized": name_norm,
                "parent_name": r["parent_name"],
                "canonical_path": r["canonical_path"],
                "origin_type": r["origin_type"],
                "status": r["status"],
                "cicw_mapping_count": r["cicw_approved_mapping_count"],
                "name_tokens": name_tokens,
                "path_tokens": path_tokens,
            }
        )
    return index


def _score_candidate(source: dict, canonical: dict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0

    src_norm = source["source_name_normalized"]
    can_norm = canonical["name_normalized"]

    if src_norm and can_norm and src_norm == can_norm:
        score += SCORE_EXACT_NORMALIZED_NAME
        reasons.append("EXACT_NORMALIZED_NAME")
    else:
        if src_norm and can_norm and src_norm in can_norm:
            score += SCORE_SOURCE_IN_CANONICAL_SUBSTRING
            reasons.append("SOURCE_IN_CANONICAL_SUBSTRING")
        if src_norm and can_norm and can_norm in src_norm:
            score += SCORE_CANONICAL_IN_SOURCE_SUBSTRING
            reasons.append("CANONICAL_IN_SOURCE_SUBSTRING")

    shared_name = source["name_tokens"] & canonical["name_tokens"]
    if shared_name:
        score += SCORE_SHARED_NAME_TOKEN * len(shared_name)
        reasons.append(f"SHARED_NAME_TOKENS({len(shared_name)})")

    shared_work = source["work_type_tokens"] & canonical["path_tokens"]
    if shared_work:
        score += SCORE_SHARED_WORK_TYPE_PATH_TOKEN * len(shared_work)
        reasons.append(f"SHARED_WORK_TYPE_PATH_TOKENS({len(shared_work)})")

    shared_project = source["project_kind_tokens"] & canonical["path_tokens"]
    if shared_project:
        score += SCORE_SHARED_PROJECT_KIND_PATH_TOKEN * len(shared_project)
        reasons.append(f"SHARED_PROJECT_KIND_PATH_TOKENS({len(shared_project)})")

    return score, reasons


def _build_source(row: dict) -> dict:
    return {
        "source_name_normalized": row["source_name_normalized"],
        "name_tokens": set(_tokens(row["source_name"])),
        "work_type_tokens": set(_tokens(row["work_type"])),
        "project_kind_tokens": set(_tokens(row["project_kind"])),
    }


def _preserve_exact_first(candidates: list[dict], forced_canonical_id: str) -> list[dict]:
    """WO §16: if the source had an exact-name candidate, it must be #1."""
    if not forced_canonical_id:
        return candidates
    exact = [c for c in candidates if c["canonical_id"] == forced_canonical_id]
    others = [c for c in candidates if c["canonical_id"] != forced_canonical_id]
    if not exact:
        return candidates
    return exact + others


def build_b01_evidence() -> tuple[list[dict], list[dict]]:
    b01 = _load_gpt_pack_b01()
    reference_rows = build_canonical_task_reference()
    canonical_index = _canonical_index(reference_rows)

    out: list[dict] = []
    for row in b01:
        src = _build_source(row)
        scored: list[dict] = []
        for canonical in canonical_index:
            score, reasons = _score_candidate(src, canonical)
            if score <= 0:
                continue
            scored.append(
                {
                    "canonical_id": canonical["canonical_id"],
                    "name": canonical["name"],
                    "parent": canonical["parent_name"],
                    "path": canonical["canonical_path"],
                    "origin_type": canonical["origin_type"],
                    "cicw_mapping_count": canonical["cicw_mapping_count"],
                    "score": score,
                    "reasons": ",".join(reasons),
                }
            )
        scored.sort(key=lambda c: (-c["score"], c["path"], c["canonical_id"]))

        forced = row.get("exact_name_canonical_id", "") or ""
        scored = _preserve_exact_first(scored, forced)

        capped = scored[:CANDIDATE_CAP]

        evidence: dict[str, str] = {
            "review_key": row["review_key"],
            "source_key": row["source_key"],
            "project_kind": row["project_kind"],
            "work_type": row["work_type"],
            "detail_process": row["detail_process"],
            "source_name": row["source_name"],
            "source_name_normalized": row["source_name_normalized"],
            "source_path": row["source_path"],
            "source_path_normalized": row["source_path_normalized"],
            "source_occurrence_count": row["source_occurrence_count"],
            "duplicate_occurrence_flag": row["duplicate_occurrence_flag"],
            "candidate_class": row["candidate_class"],
            "exact_name_hit_count": row["exact_name_hit_count"],
            "exact_name_canonical_id": row["exact_name_canonical_id"],
            "mechanical_candidate_count": str(len(capped)),
            "evidence_state": "CANDIDATES_FOUND" if capped else "NO_MECHANICAL_CANDIDATE",
        }
        for i in range(1, CANDIDATE_CAP + 1):
            if i <= len(capped):
                c = capped[i - 1]
                evidence[f"candidate_{i}_canonical_id"] = c["canonical_id"]
                evidence[f"candidate_{i}_name"] = c["name"]
                evidence[f"candidate_{i}_parent"] = c["parent"]
                evidence[f"candidate_{i}_path"] = c["path"]
                evidence[f"candidate_{i}_origin_type"] = c["origin_type"]
                evidence[f"candidate_{i}_cicw_mapping_count"] = c["cicw_mapping_count"]
                evidence[f"candidate_{i}_mechanical_score"] = str(c["score"])
                evidence[f"candidate_{i}_reasons"] = c["reasons"]
            else:
                for suffix in (
                    "canonical_id",
                    "name",
                    "parent",
                    "path",
                    "origin_type",
                    "cicw_mapping_count",
                    "mechanical_score",
                    "reasons",
                ):
                    evidence[f"candidate_{i}_{suffix}"] = ""
        evidence["gpt_semantic_decision"] = ""
        evidence["gpt_target_canonical_id"] = ""
        evidence["gpt_mapping_type"] = ""
        evidence["gpt_reason"] = ""
        evidence["gpt_confidence_class"] = ""
        out.append(evidence)

    out.sort(key=lambda r: (r["review_key"],))
    return out, reference_rows


def b01_evidence_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *B01_EVIDENCE_FIELDS)


def render_report(
    evidence_rows: list[dict],
    reference_rows: list[dict],
    evidence_sha_value: str,
    reference_sha_value: str,
) -> str:
    with_candidates = sum(
        1 for r in evidence_rows if r["evidence_state"] == "CANDIDATES_FOUND"
    )
    no_candidates = sum(
        1 for r in evidence_rows if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE"
    )
    exact = sum(1 for r in evidence_rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE")
    semantic = sum(
        1 for r in evidence_rows if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"
    )
    stopwords_dump = "(none)" if not STOPWORDS else ", ".join(sorted(STOPWORDS))
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B01-EVIDENCE-001 KOSHA B01 semantic review evidence
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA B01 Semantic Review Evidence

## THIS IS EVIDENCE ONLY

```text
THIS IS EVIDENCE ONLY
THIS IS NOT GPT SEMANTIC DECISION
THIS IS NOT MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
KOSHA IDENTITY HOLD IS PRESERVED
```

## Inputs (frozen repository evidence)

```text
GPT REVIEW PACK SHA               = {FROZEN_GPT_REVIEW_PACK_SHA}
KOSHA REVIEW UNIVERSE SHA         = {FROZEN_KOSHA_REVIEW_UNIVERSE_SHA}
CANONICAL RECEIPT SHA             = {FROZEN_CANONICAL_RECEIPT_SHA}
CIC_W PROPOSAL SHA                = {FROZEN_PROPOSAL_SHA}
MAP MATERIALIZATION RECEIPT SHA   = {FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA}
```

No live-DB query. CIC_W provenance is reconstructed from the frozen
proposal, gated by the frozen materialization receipt so we only trust
proven-in-production provenance (1139 rows).

## B01 composition

```text
B01 rows                          = {len(evidence_rows)}
EXACT_NAME_CANDIDATE              = {exact}
SEMANTIC_SEARCH_REQUIRED          = {semantic}
rows with mechanical candidates   = {with_candidates}
rows with zero mechanical candidates = {no_candidates}
canonical TASK reference          = {len(reference_rows)}
```

## Mechanical scoring (WO §14)

```text
EXACT_NORMALIZED_NAME             = {SCORE_EXACT_NORMALIZED_NAME}
source in canonical (substring)   = {SCORE_SOURCE_IN_CANONICAL_SUBSTRING}
canonical in source (substring)   = {SCORE_CANONICAL_IN_SOURCE_SUBSTRING}
shared source-name token          = {SCORE_SHARED_NAME_TOKEN} each
shared work_type token in path    = {SCORE_SHARED_WORK_TYPE_PATH_TOKEN} each
shared project_kind token in path = {SCORE_SHARED_PROJECT_KIND_PATH_TOKEN} each
top-N cap                         = {CANDIDATE_CAP}
```

This score is a deterministic sort key, not a semantic confidence. Higher score
does **not** imply approval or equivalence. GPT semantic review must still pick
the mapping type + status.

### Tokenization

```text
normalization        = NFC + collapse whitespace + [\\s/·ㆍ・,] normalizer
tokenization         = re.split(r'[^\\w]+') with unicode flag
stopwords            = {stopwords_dump}
morphological analyzer = none (no Kiwi, no synonyms)
```

## SHAs

```text
RISK KOSHA B01 CANONICAL TASK REFERENCE SHA = {reference_sha_value}
RISK KOSHA B01 SEMANTIC EVIDENCE SHA        = {evidence_sha_value}
```

## Verdict

```text
{WO_ID} = EVIDENCE_FROZEN / GPT_REVIEW_READY
B01 SEMANTIC DECISIONS = 0
KOSHA PRODUCTION MAPPINGS = 0
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 01
STOP
```
"""


def write_all() -> dict:
    ev_a, ref_a = build_b01_evidence()
    ev_b, ref_b = build_b01_evidence()

    if ev_a != ev_b:
        raise SystemExit("B01_EVIDENCE_ROW_ORDER_DRIFT")
    if ref_a != ref_b:
        raise SystemExit("CANONICAL_TASK_REFERENCE_ROW_ORDER_DRIFT")

    ev_sha_a = b01_evidence_sha(ev_a)
    ev_sha_b = b01_evidence_sha(ev_b)
    ref_sha_a = canonical_task_reference_sha(ref_a)
    ref_sha_b = canonical_task_reference_sha(ref_b)
    if ev_sha_a != ev_sha_b:
        raise SystemExit(f"B01_EVIDENCE_SHA_DRIFT {ev_sha_a} vs {ev_sha_b}")
    if ref_sha_a != ref_sha_b:
        raise SystemExit(f"CANONICAL_TASK_REFERENCE_SHA_DRIFT {ref_sha_a} vs {ref_sha_b}")

    write_tsv(ref_a, CANONICAL_TASK_REFERENCE_PATH, CANONICAL_TASK_REFERENCE_FIELDS)
    write_tsv(ev_a, B01_EVIDENCE_PATH, B01_EVIDENCE_FIELDS)
    REPORT_PATH.write_text(
        render_report(ev_a, ref_a, ev_sha_a, ref_sha_a), encoding="utf-8"
    )

    with_candidates = sum(1 for r in ev_a if r["evidence_state"] == "CANDIDATES_FOUND")
    no_candidates = sum(1 for r in ev_a if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE")

    return {
        "b01_rows": len(ev_a),
        "canonical_task_reference_rows": len(ref_a),
        "rows_with_mechanical_candidates": with_candidates,
        "rows_with_zero_mechanical_candidates": no_candidates,
        "b01_evidence_sha_run1": ev_sha_a,
        "b01_evidence_sha_run2": ev_sha_b,
        "canonical_task_reference_sha_run1": ref_sha_a,
        "canonical_task_reference_sha_run2": ref_sha_b,
        "canonical_task_reference_path": str(CANONICAL_TASK_REFERENCE_PATH),
        "b01_evidence_path": str(B01_EVIDENCE_PATH),
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
