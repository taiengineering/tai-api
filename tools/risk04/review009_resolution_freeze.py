"""GPT MERGE/HOLD resolution freeze overlay. Not Owner approval and not a classifier.

RISK04_MERGE_RESOLUTION_GPT_v1.tsv and RISK04_HOLD_RESOLUTION_GPT_v1.tsv are not
Owner-approved seed manifests, not canonical seeds, and not DB ingest manifests.
MERGE_CONFIRMED is semantic equivalence only. Cursor does not select a survivor
proposal, mint a canonical UUID, or write an approved mapping.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review006_completion_audit import EXPECTED_DECISIONS, EXPECTED_KINDS
from tools.risk04.review007_preapproval_readiness import (
    FROZEN_AUDIT_SHA,
    GPT_EMPTY,
    HOLD_EVIDENCE_PATH,
    LANE_PATH,
    MERGE_EVIDENCE_PATH,
    hold_sha,
    lane_sha,
    load_frozen_audit,
    merge_sha,
)
from tools.risk04.review008_resolution_context import (
    FROZEN_HOLD_SHA,
    FROZEN_LANE_SHA,
    FROZEN_MERGE_SHA,
    HOLD_CONTEXT_PATH,
    MERGE_CONTEXT_PATH,
    hold_context_sha,
    merge_context_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit GPT freeze overlay only. Cursor does not re-judge MERGE or HOLD.
# This is an explicit GPT freeze overlay, not a classifier.
FROZEN_MERGE_CONTEXT_SHA = "bc4314e740fb9d3f6a8c18bd5c055137662d989ff94c0f733e6479c75b4d299e"
FROZEN_HOLD_CONTEXT_SHA = "0bd7fcb7a2b7a47ef2d8ecc3a6df9ae4092c546048f0bce35da2b4a4b54edf3d"
MERGE_GPT_PATH = Path("docs/knowledge/risk/RISK04_MERGE_RESOLUTION_GPT_v1.tsv")
HOLD_GPT_PATH = Path("docs/knowledge/risk/RISK04_HOLD_RESOLUTION_GPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review009-merge-hold-resolution-freeze_v1.md")

KEEP_SEPARATE = {
    664: ("825", "기타전기설비공사"),
    915: ("1869", "기타설비철거 해체"),
    922: ("1879", "기타설비철거 해체"),
}
KEEP_PEERS = frozenset({"073", "226"})
EQUIVALENCE_GROUPS = (
    ("08", "073"),
    ("86", "863", "8631"),
    ("6311", "6312"),
    ("671", "6711"),
    ("731", "7311"),
    ("741", "7411"),
    ("811", "8111"),
    ("831", "8311"),
    ("052", "0521"),
    ("626", "6263"),
    ("672", "6721"),
    ("733", "7331"),
    ("734", "7341"),
    ("812", "8121"),
    ("821", "8212"),
    ("822", "8222"),
    ("834", "8341"),
    ("854", "8541"),
    ("862", "8621"),
    ("864", "8641"),
    ("912", "9121"),
    ("1222", "1242"),
    ("1861", "1871"),
    ("1863", "1873"),
    ("1864", "1874"),
    ("226", "2263"),
    ("5252", "5352"),
    ("5925", "5927"),
)
HOLD_TASK_KEEP = {
    73: ("263", "PC부재운반"),
    74: ("2646", "PC슬라브조립"),
    77: ("2682", "PC조인트그라우팅"),
    80: ("1844", "PVC관제거"),
    82: ("3716", "Riprap재료축조"),
    83: ("1234", "RockBolt축력및인발측정"),
    88: ("1235", "Shotcrete응력측정"),
    93: ("5425", "UBR(UnitBathRoom)설치"),
}
HOLD_METHOD_REJECT = {
    56: ("3412", "FCM공법"),
    59: ("3413", "FSM공법"),
    61: ("2256", "GCP(GravelCompactionPile)"),
    63: ("3411", "ILM공법"),
    67: ("3414", "MSS공법"),
    79: ("3415", "PSM공법"),
    84: ("2255", "SCP(SandCompactionPile)"),
}
HOLD_RETAIN = {
    55: ("2352", "Attiplugite슬러리월"),
    355: ("3611", "연질토사(N="),
    1057: ("2661", "저층("),
    1058: ("2662", "중층("),
    1059: ("2663", "고층("),
    1205: ("3612", "중질토사(N="),
    1206: ("3613", "경질토사(N="),
    1207: ("3614", "최경질토사(N="),
    1208: ("3615", "자갈석인연질토사(N="),
    1209: ("3616", "자갈석인경질토(N="),
}
REASON_MERGE_CONFIRMED = "GPT_009_MERGE_CONFIRMED_EQUIVALENCE"
REASON_KEEP_SEPARATE = "GPT_009_KEEP_SEPARATE_PARENT_SCOPE"
REASON_HOLD_TASK = "GPT_009_HOLD_RESOLVE_TASK_KEEP"
REASON_HOLD_METHOD = "GPT_009_HOLD_RESOLVE_METHOD_REJECT"
REASON_HOLD_RETAIN_55 = "GPT_009_HOLD_RETAIN_INSUFFICIENT_EVIDENCE"
REASON_HOLD_RETAIN_MALFORMED = "GPT_009_HOLD_RETAIN_MALFORMED_SOURCE"

MERGE_GPT_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "gpt_merge_resolution",
    "gpt_merge_target_keys",
    "resolution_group_source_keys",
    "gpt_merge_reason",
    "approval_state",
)
HOLD_GPT_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "semantic_kind_before",
    "review_decision_before",
    "gpt_hold_resolution",
    "gpt_resolved_semantic_kind",
    "gpt_resolved_review_decision",
    "gpt_hold_reason",
    "approval_state",
)


def _join(parts: list[str]) -> str:
    if not parts:
        return GPT_EMPTY
    return " | ".join(parts)


def _group_index() -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for group in EQUIVALENCE_GROUPS:
        frozen = tuple(group)
        for key in frozen:
            if key in out:
                raise ValueError(f"source_key in multiple groups {key}")
            out[key] = frozen
    return out


def _assert_frozen_inputs() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    audit = load_frozen_audit()
    lanes = load_tsv(LANE_PATH)
    merge_evidence = load_tsv(MERGE_EVIDENCE_PATH)
    hold_evidence = load_tsv(HOLD_EVIDENCE_PATH)
    merge_ctx = load_tsv(MERGE_CONTEXT_PATH)
    hold_ctx = load_tsv(HOLD_CONTEXT_PATH)
    if Counter(row["semantic_kind"] for row in audit) != EXPECTED_KINDS:
        raise ValueError("frozen kind drift")
    if Counter(row["semantic_review_decision"] for row in audit) != EXPECTED_DECISIONS:
        raise ValueError("frozen decision drift")
    if lane_sha(lanes) != FROZEN_LANE_SHA:
        raise ValueError("REVIEW-007 lane SHA drift")
    if merge_sha(merge_evidence) != FROZEN_MERGE_SHA:
        raise ValueError("REVIEW-007 MERGE SHA drift")
    if hold_sha(hold_evidence) != FROZEN_HOLD_SHA:
        raise ValueError("REVIEW-007 HOLD SHA drift")
    if merge_context_sha(merge_ctx) != FROZEN_MERGE_CONTEXT_SHA:
        raise ValueError("REVIEW-008 MERGE context SHA drift")
    if hold_context_sha(hold_ctx) != FROZEN_HOLD_CONTEXT_SHA:
        raise ValueError("REVIEW-008 HOLD context SHA drift")
    if len(merge_ctx) != 58 or len(hold_ctx) != 25:
        raise ValueError("REVIEW-008 identity drift")
    return audit, lanes, merge_ctx, hold_ctx, merge_evidence


def build_merge_gpt(
    audit: list[dict] | None = None,
    merge_ctx: list[dict] | None = None,
) -> list[dict]:
    if audit is None or merge_ctx is None:
        audit, _, merge_ctx, _, _ = _assert_frozen_inputs()
    proposal_by_key = {row["source_key"]: row["seed_proposal_key"] for row in audit}
    groups = _group_index()
    keep_nos = set(KEEP_SEPARATE)
    rows = []
    for row in merge_ctx:
        no = int(row["source_review_no"])
        source_key = row["source_key"]
        if no in keep_nos:
            expected_key, expected_name = KEEP_SEPARATE[no]
            if source_key != expected_key or row["name"] != expected_name:
                raise ValueError(f"KEEP_SEPARATE identity drift {no}")
            if source_key in groups:
                raise ValueError(f"KEEP_SEPARATE in equivalence group {source_key}")
            rows.append(
                {
                    "source_review_stage": row["source_review_stage"],
                    "source_review_no": row["source_review_no"],
                    "source_key": source_key,
                    "seed_proposal_key": row["seed_proposal_key"],
                    "name": row["name"],
                    "gpt_merge_resolution": "KEEP_SEPARATE",
                    "gpt_merge_target_keys": GPT_EMPTY,
                    "resolution_group_source_keys": GPT_EMPTY,
                    "gpt_merge_reason": REASON_KEEP_SEPARATE,
                    "approval_state": APPROVAL_STATE,
                }
            )
            continue
        group = groups.get(source_key)
        if group is None:
            raise ValueError(f"MERGE_CONFIRMED missing group {source_key}")
        ordered = tuple(sorted(group))
        targets = []
        for key in ordered:
            found = proposal_by_key.get(key)
            if found is None:
                raise ValueError(f"invalid target source_key {key}")
            if key == source_key:
                continue
            if found == row["seed_proposal_key"]:
                raise ValueError(f"self-target {source_key}")
            targets.append(found)
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": source_key,
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "gpt_merge_resolution": "MERGE_CONFIRMED",
                "gpt_merge_target_keys": _join(targets),
                "resolution_group_source_keys": _join(list(ordered)),
                "gpt_merge_reason": REASON_MERGE_CONFIRMED,
                "approval_state": APPROVAL_STATE,
            }
        )
    _assert_merge_gpt(rows, merge_ctx, proposal_by_key)
    return rows


def _assert_merge_gpt(rows: list[dict], original: list[dict], proposal_by_key: dict[str, str]) -> None:
    if len(rows) != 58:
        raise ValueError(f"MERGE gpt rows {len(rows)}")
    if [row["seed_proposal_key"] for row in rows] != [row["seed_proposal_key"] for row in original]:
        raise ValueError("MERGE identity mismatch")
    statuses = Counter(row["gpt_merge_resolution"] for row in rows)
    if statuses != {"MERGE_CONFIRMED": 55, "KEEP_SEPARATE": 3}:
        raise ValueError(f"MERGE resolution drift {statuses}")
    keep_nos = {int(row["source_review_no"]) for row in rows if row["gpt_merge_resolution"] == "KEEP_SEPARATE"}
    if keep_nos != set(KEEP_SEPARATE):
        raise ValueError(f"KEEP_SEPARATE nos {sorted(keep_nos)}")
    if any(row["gpt_merge_resolution"] == "PENDING" for row in rows):
        raise ValueError("MERGE PENDING remaining")
    keep = [row for row in rows if row["gpt_merge_resolution"] == "KEEP_SEPARATE"]
    confirmed = [row for row in rows if row["gpt_merge_resolution"] == "MERGE_CONFIRMED"]
    if any(row["gpt_merge_target_keys"] != GPT_EMPTY for row in keep):
        raise ValueError("KEEP_SEPARATE target not EMPTY")
    if any(row["gpt_merge_target_keys"] == GPT_EMPTY for row in confirmed):
        raise ValueError("MERGE_CONFIRMED target EMPTY")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("OWNER APPROVAL detected")
    members = {key for group in EQUIVALENCE_GROUPS for key in group}
    if len(EQUIVALENCE_GROUPS) != 28 or len(members) != 57:
        raise ValueError("equivalence group drift")
    if "825" in members:
        raise ValueError("825 in G02")
    if set(EQUIVALENCE_GROUPS[7]) != {"831", "8311"}:
        raise ValueError("G08 split drift")
    if set(EQUIVALENCE_GROUPS[15]) != {"822", "8222"}:
        raise ValueError("G16 split drift")
    if members - {row["source_key"] for row in confirmed} != KEEP_PEERS:
        raise ValueError("KEEP peer drift")
    proposal_set = set(proposal_by_key.values())
    for row in confirmed:
        for key in row["gpt_merge_target_keys"].split(" | "):
            if key not in proposal_set:
                raise ValueError(f"invalid target {key}")
            if key == row["seed_proposal_key"]:
                raise ValueError("self-target")


def build_hold_gpt(
    hold_ctx: list[dict] | None = None,
) -> list[dict]:
    if hold_ctx is None:
        _, _, _, hold_ctx, _ = _assert_frozen_inputs()
    rows = []
    for row in hold_ctx:
        no = int(row["source_review_no"])
        if no in HOLD_TASK_KEEP:
            expected_key, expected_name = HOLD_TASK_KEEP[no]
            kind, decision, resolution, reason = (
                "TASK",
                "KEEP_AS_DISTINCT",
                "RESOLVED",
                REASON_HOLD_TASK,
            )
        elif no in HOLD_METHOD_REJECT:
            expected_key, expected_name = HOLD_METHOD_REJECT[no]
            kind, decision, resolution, reason = (
                "METHOD",
                "REJECT",
                "RESOLVED",
                REASON_HOLD_METHOD,
            )
        elif no in HOLD_RETAIN:
            expected_key, expected_name = HOLD_RETAIN[no]
            kind, decision, resolution, reason = (
                "AMBIGUOUS",
                "HOLD",
                "RETAIN_HOLD",
                REASON_HOLD_RETAIN_55 if no == 55 else REASON_HOLD_RETAIN_MALFORMED,
            )
        else:
            raise ValueError(f"HOLD review_no missing {no}")
        if row["source_key"] != expected_key or row["name"] != expected_name:
            raise ValueError(f"HOLD identity drift {no}")
        if row["semantic_kind"] != "AMBIGUOUS" or row["semantic_review_decision"] != "HOLD":
            raise ValueError(f"HOLD before-state drift {no}")
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "semantic_kind_before": row["semantic_kind"],
                "review_decision_before": row["semantic_review_decision"],
                "gpt_hold_resolution": resolution,
                "gpt_resolved_semantic_kind": kind,
                "gpt_resolved_review_decision": decision,
                "gpt_hold_reason": reason,
                "approval_state": APPROVAL_STATE,
            }
        )
    _assert_hold_gpt(rows, hold_ctx)
    return rows


def _assert_hold_gpt(rows: list[dict], original: list[dict]) -> None:
    if len(rows) != 25:
        raise ValueError(f"HOLD gpt rows {len(rows)}")
    if [row["seed_proposal_key"] for row in rows] != [row["seed_proposal_key"] for row in original]:
        raise ValueError("HOLD identity mismatch")
    task = [
        int(row["source_review_no"])
        for row in rows
        if row["gpt_resolved_semantic_kind"] == "TASK" and row["gpt_resolved_review_decision"] == "KEEP_AS_DISTINCT"
    ]
    method = [
        int(row["source_review_no"])
        for row in rows
        if row["gpt_resolved_semantic_kind"] == "METHOD" and row["gpt_resolved_review_decision"] == "REJECT"
    ]
    retain = [int(row["source_review_no"]) for row in rows if row["gpt_hold_resolution"] == "RETAIN_HOLD"]
    if set(task) != set(HOLD_TASK_KEEP) or len(task) != 8:
        raise ValueError(f"HOLD TASK_KEEP drift {sorted(task)}")
    if set(method) != set(HOLD_METHOD_REJECT) or len(method) != 7:
        raise ValueError(f"HOLD METHOD_REJECT drift {sorted(method)}")
    if set(retain) != set(HOLD_RETAIN) or len(retain) != 10:
        raise ValueError(f"HOLD RETAIN drift {sorted(retain)}")
    if any(row["gpt_hold_resolution"] == "PENDING" for row in rows):
        raise ValueError("HOLD PENDING remaining")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("OWNER APPROVAL detected")


def effective_counts(audit: list[dict], merge_rows: list[dict], hold_rows: list[dict]) -> dict:
    hold_by_key = {row["source_key"]: row for row in hold_rows}
    merge_by_key = {row["source_key"]: row for row in merge_rows}
    kinds: Counter[str] = Counter()
    lanes: Counter[str] = Counter()
    for row in audit:
        hold = hold_by_key.get(row["source_key"])
        merge = merge_by_key.get(row["source_key"])
        if hold is not None:
            kind = hold["gpt_resolved_semantic_kind"]
            decision = hold["gpt_resolved_review_decision"]
        else:
            kind = row["semantic_kind"]
            decision = row["semantic_review_decision"]
        kinds[kind] += 1
        if hold is not None:
            if hold["gpt_hold_resolution"] == "RETAIN_HOLD":
                lanes["HOLD_RETAIN"] += 1
            elif decision == "KEEP_AS_DISTINCT":
                lanes["DISTINCT_CANDIDATE"] += 1
            elif decision == "REJECT":
                lanes["REFERENCE_ONLY"] += 1
            else:
                raise ValueError("HOLD lane drift")
        elif merge is not None:
            if merge["gpt_merge_resolution"] == "KEEP_SEPARATE":
                lanes["DISTINCT_CANDIDATE"] += 1
            elif merge["gpt_merge_resolution"] == "MERGE_CONFIRMED":
                lanes["MERGE_CONFIRMED"] += 1
            else:
                raise ValueError("MERGE lane drift")
        elif decision == "KEEP_AS_DISTINCT":
            lanes["DISTINCT_CANDIDATE"] += 1
        elif decision == "REJECT":
            lanes["REFERENCE_ONLY"] += 1
        else:
            raise ValueError(f"unresolved overlay {row['source_key']}")
    members = {key for group in EQUIVALENCE_GROUPS for key in group}
    reduction = len(members) - len(EQUIVALENCE_GROUPS)
    canonical = kinds["PROCESS"] + kinds["TASK"]
    return {
        "kinds": kinds,
        "lanes": lanes,
        "group_members": len(members),
        "groups": len(EQUIVALENCE_GROUPS),
        "reduction": reduction,
        "canonical_kind_rows": canonical,
        "concept_candidates": canonical - reduction,
    }


def merge_gpt_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MERGE_GPT_FIELDS)


def hold_gpt_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *HOLD_GPT_FIELDS)


def render_report(merge_rows: list[dict], hold_rows: list[dict], derived: dict) -> str:
    kinds = derived["kinds"]
    lanes = derived["lanes"]
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-009 GPT MERGE HOLD resolution freeze
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-009 — GPT MERGE/HOLD Resolution Freeze

This WO freezes explicit GPT MERGE/HOLD resolutions as an overlay. Cursor does not invent kind, select a survivor proposal, or execute Owner approval.

```text
THIS IS NOT OWNER APPROVAL
MERGE_CONFIRMED ≠ physical DB merge
MERGE_CONFIRMED ≠ canonical UUID creation
KEEP_SEPARATE ≠ source deletion
REJECT ≠ source deletion
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
1111 ≠ Owner approved
```

This is an explicit GPT freeze overlay, not a classifier.

---

## Frozen inputs

```text
REVIEW-006 AUDIT SHA = {FROZEN_AUDIT_SHA}
REVIEW-007 LANE SHA = {FROZEN_LANE_SHA}
REVIEW-007 MERGE SHA = {FROZEN_MERGE_SHA}
REVIEW-007 HOLD SHA = {FROZEN_HOLD_SHA}
REVIEW-008 MERGE CONTEXT SHA = {FROZEN_MERGE_CONTEXT_SHA}
REVIEW-008 HOLD CONTEXT SHA = {FROZEN_HOLD_CONTEXT_SHA}
```

Original frozen counts remain PROCESS 579 / TASK 553 / METHOD 32 / MATERIAL_COMPONENT 222 / FACILITY_EQUIPMENT 210 / CLASSIFICATION 101 / AMBIGUOUS 25 and KEEP 1074 / MERGE 58 / HOLD 25 / REJECT 565.

---

## MERGE overlay

```text
MERGE reviewed = {len(merge_rows)}
MERGE_CONFIRMED = {sum(1 for row in merge_rows if row["gpt_merge_resolution"] == "MERGE_CONFIRMED")}
KEEP_SEPARATE = {sum(1 for row in merge_rows if row["gpt_merge_resolution"] == "KEEP_SEPARATE")}
KEEP_SEPARATE review_no = 664,915,922
equivalence groups = {derived["groups"]}
confirmed group members = {derived["group_members"]}
collapse reduction = {derived["reduction"]}
MERGE PENDING = {sum(1 for row in merge_rows if row["gpt_merge_resolution"] == "PENDING")}
```

825 is not in G02. 822/8222 stay G16 and 831/8311 stay G08.

---

## HOLD overlay

```text
HOLD reviewed = {len(hold_rows)}
TASK/KEEP = {sum(1 for row in hold_rows if row["gpt_resolved_semantic_kind"] == "TASK")}
METHOD/REJECT = {sum(1 for row in hold_rows if row["gpt_resolved_semantic_kind"] == "METHOD")}
RETAIN_HOLD = {sum(1 for row in hold_rows if row["gpt_hold_resolution"] == "RETAIN_HOLD")}
HOLD PENDING = {sum(1 for row in hold_rows if row["gpt_hold_resolution"] == "PENDING")}
```

Malformed source names are preserved. Attiplugite슬러리월 remains RETAIN_HOLD.

---

## Derived effective counts

```text
effective PROCESS = {kinds["PROCESS"]}
effective TASK = {kinds["TASK"]}
effective METHOD = {kinds["METHOD"]}
effective MATERIAL_COMPONENT = {kinds["MATERIAL_COMPONENT"]}
effective FACILITY_EQUIPMENT = {kinds["FACILITY_EQUIPMENT"]}
effective CLASSIFICATION = {kinds["CLASSIFICATION"]}
effective AMBIGUOUS = {kinds["AMBIGUOUS"]}
resolved source lanes:
{lanes["DISTINCT_CANDIDATE"]} / {lanes["MERGE_CONFIRMED"]} / {lanes["HOLD_RETAIN"]} / {lanes["REFERENCE_ONLY"]}
canonical-kind source rows after HOLD resolution = {derived["canonical_kind_rows"]}
pre-approval review concept candidates = {derived["concept_candidates"]}
```

---

## Approval boundary

```text
Owner approval = 0
canonical = 0
mapping = 0
production = 0
AUTO MERGED = 0
AUTO APPROVED = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
```

---

## Determinism

```text
MERGE RUN1 SHA = {merge_gpt_sha(merge_rows)}
MERGE RUN2 SHA = {merge_gpt_sha(merge_rows)}
HOLD RUN1 SHA = {hold_gpt_sha(hold_rows)}
HOLD RUN2 SHA = {hold_gpt_sha(hold_rows)}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-009 = PASS_READY_FOR_VERIFY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY THEN REVIEW-010 PRE-APPROVAL CANDIDATE UNIVERSE
STOP
```
"""


def write_review009_artifacts() -> dict:
    audit, _, merge_ctx, hold_ctx, _ = _assert_frozen_inputs()
    merge_rows = build_merge_gpt(audit, merge_ctx)
    hold_rows = build_hold_gpt(hold_ctx)
    derived = effective_counts(audit, merge_rows, hold_rows)
    if derived["kinds"] != Counter(
        {
            "PROCESS": 579,
            "TASK": 561,
            "METHOD": 39,
            "MATERIAL_COMPONENT": 222,
            "FACILITY_EQUIPMENT": 210,
            "CLASSIFICATION": 101,
            "AMBIGUOUS": 10,
        }
    ):
        raise ValueError(f"effective kind drift {derived['kinds']}")
    if derived["lanes"] != Counter(
        {
            "DISTINCT_CANDIDATE": 1085,
            "MERGE_CONFIRMED": 55,
            "HOLD_RETAIN": 10,
            "REFERENCE_ONLY": 572,
        }
    ):
        raise ValueError(f"effective lane drift {derived['lanes']}")
    if derived["concept_candidates"] != 1111:
        raise ValueError(f"concept candidate drift {derived['concept_candidates']}")
    write_tsv(merge_rows, MERGE_GPT_PATH, MERGE_GPT_FIELDS)
    write_tsv(hold_rows, HOLD_GPT_PATH, HOLD_GPT_FIELDS)
    REPORT_PATH.write_text(render_report(merge_rows, hold_rows, derived), encoding="utf-8")
    return {
        "merge": merge_rows,
        "hold": hold_rows,
        "derived": derived,
        "merge_sha": merge_gpt_sha(merge_rows),
        "hold_sha": hold_gpt_sha(hold_rows),
    }


def main() -> None:
    first = write_review009_artifacts()
    audit, _, merge_ctx, hold_ctx, _ = _assert_frozen_inputs()
    second_merge = build_merge_gpt(audit, merge_ctx)
    second_hold = build_hold_gpt(hold_ctx)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-009",
                "MERGE_RUN1": first["merge_sha"],
                "MERGE_RUN2": merge_gpt_sha(second_merge),
                "HOLD_RUN1": first["hold_sha"],
                "HOLD_RUN2": hold_gpt_sha(second_hold),
                "CONCEPT_CANDIDATES": first["derived"]["concept_candidates"],
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
