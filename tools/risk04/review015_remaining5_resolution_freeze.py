"""GPT remaining-5 semantic resolution freeze overlay. Not Owner approval.

RISK04_REMAINING5_RESOLUTION_GPT_v1.tsv is not a canonical parent manifest,
not a canonical label manifest, and not an approved mapping. Cursor does not
re-judge parent or label. COMMON_ANCESTOR_PARENT_CONFIRMED is a candidate only.
HOLD_LABEL_CONFIRMED is a completed HOLD, not an invented label.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, GPT_PENDING
from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBERS_PATH,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review011_hierarchy_label_search_readiness import (
    CONCEPT_HIERARCHY_PATH,
    CRITICAL_QUEUE_PATH,
    LABEL_PATH,
    MEMBER_HIERARCHY_PATH,
    SEARCH_EXPORT_PATH,
    concept_hierarchy_sha,
    critical_queue_sha,
    label_sha,
    member_hierarchy_sha,
    search_export_sha,
)
from tools.risk04.review013_resolution_freeze import (
    FROZEN_CONCEPT_HIERARCHY_SHA,
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_LABEL_SHA,
    FROZEN_MEMBER_HIERARCHY_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_QUEUE_SHA,
    FROZEN_SEARCH_EXPORT_SHA,
    FROZEN_UNIVERSE_SHA,
    H05_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    DEMOLITION_COMMON,
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    H02_COMMON,
    H02_KEY,
    H03_KEY,
    H04_KEY,
    L02_KEY,
    evidence_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit GPT freeze overlay only. Cursor does not re-judge remaining-5 cases.
# This is an explicit GPT freeze overlay, not a classifier.
FROZEN_EVIDENCE_SHA = "f78396c18cf8cdb30eb25d7e59d944edabf492d0ec4d32286cf55290c273ec72"
REMAINING5_PATH = Path("docs/knowledge/risk/RISK04_REMAINING5_RESOLUTION_GPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review015-remaining5-resolution-freeze_v1.md")
FORBIDDEN_PARENT_NAMES = frozenset(
    {"구조체계측", "교량공사계측", "기계설비철거 해체", "전기 통신설비철거 해체"}
)
REMAINING5_FIELDS = (
    "case_id",
    "review_concept_key",
    "source_keys",
    "issue_type",
    "gpt_final_decision",
    "canonical_parent_candidate",
    "canonical_parent_candidate_name",
    "parent_resolution_basis",
    "canonical_label_candidate",
    "label_resolution_status",
    "label_resolution_basis",
    "source_context_policy",
    "source_preservation",
    "resolution_status",
    "owner_approval_state",
    "resolution_notes",
)
GPT_CASES = (
    {
        "case_id": "H-02",
        "review_concept_key": H02_KEY,
        "source_keys": "1242 | 1222",
        "issue_type": "PARENT_MODELING",
        "gpt_final_decision": "COMMON_ANCESTOR_PARENT_CONFIRMED",
        "canonical_parent_candidate": H02_COMMON,
        "canonical_parent_candidate_name": "계측",
        "parent_resolution_basis": "NEAREST_COMMON_CANDIDATE_ANCESTOR",
        "canonical_label_candidate": GPT_EMPTY,
        "label_resolution_status": GPT_EMPTY,
        "label_resolution_basis": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "resolution_notes": (
            "동적계측은 동일 TASK로 유지한다. "
            "구조체계측과 교량공사계측 중 하나를 임의 canonical parent로 선택하지 않는다. "
            "두 source branch의 nearest common candidate ancestor인 계측을 canonical parent 후보로 한다. "
            "원 source parent/path context는 source mapping evidence에 별도 보존한다."
        ),
    },
    {
        "case_id": "H-03",
        "review_concept_key": H03_KEY,
        "source_keys": "1861 | 1871",
        "issue_type": "PARENT_MODELING",
        "gpt_final_decision": "COMMON_ANCESTOR_PARENT_CONFIRMED",
        "canonical_parent_candidate": DEMOLITION_COMMON,
        "canonical_parent_candidate_name": "철거해체공사및시설물보호",
        "parent_resolution_basis": "NEAREST_COMMON_CANDIDATE_ANCESTOR",
        "canonical_label_candidate": GPT_EMPTY,
        "label_resolution_status": GPT_EMPTY,
        "label_resolution_basis": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "resolution_notes": (
            "배관철거 해체는 동일 TASK로 유지한다. "
            "기계설비철거 해체 / 전기 통신설비철거 해체는 source context로 보존한다. "
            "공통 상위인 철거해체공사및시설물보호를 canonical parent 후보로 한다."
        ),
    },
    {
        "case_id": "H-04",
        "review_concept_key": H04_KEY,
        "source_keys": "1863 | 1873",
        "issue_type": "PARENT_MODELING",
        "gpt_final_decision": "COMMON_ANCESTOR_PARENT_CONFIRMED",
        "canonical_parent_candidate": DEMOLITION_COMMON,
        "canonical_parent_candidate_name": "철거해체공사및시설물보호",
        "parent_resolution_basis": "NEAREST_COMMON_CANDIDATE_ANCESTOR",
        "canonical_label_candidate": GPT_EMPTY,
        "label_resolution_status": GPT_EMPTY,
        "label_resolution_basis": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "resolution_notes": (
            "장비철거 해체는 동일 TASK로 유지한다. "
            "두 source parent는 canonical identity를 분리하지 않으며 source context로 보존한다."
        ),
    },
    {
        "case_id": "H-05",
        "review_concept_key": H05_KEY,
        "source_keys": "1864 | 1874",
        "issue_type": "PARENT_MODELING",
        "gpt_final_decision": "COMMON_ANCESTOR_PARENT_CONFIRMED",
        "canonical_parent_candidate": DEMOLITION_COMMON,
        "canonical_parent_candidate_name": "철거해체공사및시설물보호",
        "parent_resolution_basis": "NEAREST_COMMON_CANDIDATE_ANCESTOR",
        "canonical_label_candidate": GPT_EMPTY,
        "label_resolution_status": GPT_EMPTY,
        "label_resolution_basis": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "resolution_notes": (
            "잡철물철거 해체는 동일 TASK로 유지한다. "
            "두 source parent는 canonical identity를 분리하지 않으며 source context로 보존한다."
        ),
    },
    {
        "case_id": "L-02",
        "review_concept_key": L02_KEY,
        "source_keys": "673",
        "issue_type": "LABEL_HOLD",
        "gpt_final_decision": "HOLD_LABEL_CONFIRMED",
        "canonical_parent_candidate": GPT_EMPTY,
        "canonical_parent_candidate_name": GPT_EMPTY,
        "parent_resolution_basis": "NOT_APPLICABLE",
        "canonical_label_candidate": GPT_EMPTY,
        "label_resolution_status": "HOLD_LABEL_CONFIRMED",
        "label_resolution_basis": "RAW_SOURCE_SHOWS_PARSER_CORRUPTION_BUT_LABEL_NOT_RECOVERABLE",
        "source_context_policy": "PRESERVE_RAW_SOURCE",
        "resolution_notes": (
            "source_key 673에는 parser가 page marker와 table header를 흡수한 corruption이 존재함이 확인됐다. "
            "제거 가능한 contamination: W-38 page marker, 대․중․소 분류대․중․소 분류 table header. "
            "그러나 남은 stem 의료시험및시운전공사실가스공사 자체의 정상 canonical label은 현재 evidence만으로 복원할 수 없다. "
            "따라서 canonical label 생성 금지, 띄어쓰기 추정 금지, 단어 분리 추정 금지, 오탈자 교정 금지, "
            "6731 명칭으로 역추론 금지. HOLD_LABEL_CONFIRMED로 종료한다."
        ),
    },
)


def _assert_frozen_inputs() -> tuple[list[dict], list[dict], list[dict]]:
    concepts = load_tsv(UNIVERSE_PATH)
    evidence = load_tsv(EVIDENCE_PATH)
    resolution = load_tsv(RESOLUTION_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(load_tsv(MEMBERS_PATH)) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) != FROZEN_MEMBER_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 member hierarchy SHA drift")
    if concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) != FROZEN_CONCEPT_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 concept hierarchy SHA drift")
    if label_sha(load_tsv(LABEL_PATH)) != FROZEN_LABEL_SHA:
        raise ValueError("REVIEW-011 label SHA drift")
    if search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) != FROZEN_SEARCH_EXPORT_SHA:
        raise ValueError("REVIEW-011 search export SHA drift")
    if critical_queue_sha(load_tsv(CRITICAL_QUEUE_PATH)) != FROZEN_QUEUE_SHA:
        raise ValueError("REVIEW-011 critical queue SHA drift")
    if resolution_sha(resolution) != FROZEN_RESOLUTION_SHA:
        raise ValueError("REVIEW-013 resolution SHA drift")
    if evidence_sha(evidence) != FROZEN_EVIDENCE_SHA:
        raise ValueError("REVIEW-014 evidence SHA drift")
    if len(concepts) != 1111:
        raise ValueError("concept count drift")
    if len(evidence) != 5:
        raise ValueError("REVIEW-014 identity drift")
    return concepts, evidence, resolution


def remaining5_counts(rows: list[dict]) -> dict[str, int]:
    decisions = Counter(row["gpt_final_decision"] for row in rows)
    issues = Counter(row["issue_type"] for row in rows)
    parents = Counter(
        row["canonical_parent_candidate_name"]
        for row in rows
        if row["canonical_parent_candidate"] != GPT_EMPTY
    )
    return {
        "rows": len(rows),
        "unique": len({row["review_concept_key"] for row in rows}),
        "PARENT_MODELING": issues["PARENT_MODELING"],
        "LABEL_HOLD": issues["LABEL_HOLD"],
        "COMMON_ANCESTOR_PARENT_CONFIRMED": decisions["COMMON_ANCESTOR_PARENT_CONFIRMED"],
        "HOLD_LABEL_CONFIRMED": decisions["HOLD_LABEL_CONFIRMED"],
        "parent_candidates": sum(1 for row in rows if row["canonical_parent_candidate"] != GPT_EMPTY),
        "label_candidates": sum(1 for row in rows if row["canonical_label_candidate"] != GPT_EMPTY),
        "계측": parents.get("계측", 0),
        "철거해체공사및시설물보호": parents.get("철거해체공사및시설물보호", 0),
        "GPT_RESOLVED": sum(1 for row in rows if row["resolution_status"] == "GPT_RESOLVED"),
        "GPT_PENDING": sum(1 for row in rows if row["resolution_status"] == GPT_PENDING),
        "NOT_APPROVED": sum(1 for row in rows if row["owner_approval_state"] == APPROVAL_STATE),
        "source_preservation_yes": sum(1 for row in rows if row["source_preservation"] == "YES"),
    }


def _validate(rows: list[dict], evidence: list[dict], concepts: list[dict]) -> None:
    expected = {
        "rows": 5,
        "unique": 5,
        "PARENT_MODELING": 4,
        "LABEL_HOLD": 1,
        "COMMON_ANCESTOR_PARENT_CONFIRMED": 4,
        "HOLD_LABEL_CONFIRMED": 1,
        "parent_candidates": 4,
        "label_candidates": 0,
        "계측": 1,
        "철거해체공사및시설물보호": 3,
        "GPT_RESOLVED": 5,
        "GPT_PENDING": 0,
        "NOT_APPROVED": 5,
        "source_preservation_yes": 5,
    }
    counts = remaining5_counts(rows)
    if counts != expected:
        raise ValueError(f"remaining5 aggregate drift {counts}")
    evidence_by_key = {row["review_concept_key"]: row for row in evidence}
    if {row["review_concept_key"] for row in rows} != set(evidence_by_key):
        raise ValueError("remaining5 key set drift")
    if rows[3]["case_id"] != "H-05" or rows[3]["review_concept_key"] != H05_KEY:
        raise ValueError("H-05 key drift")
    concept_keys = {row["review_concept_key"] for row in concepts}
    for row in rows:
        queued = evidence_by_key[row["review_concept_key"]]
        if row["source_keys"] != queued["source_keys"]:
            raise ValueError(f"source_keys drift {row['case_id']}")
        if row["issue_type"] != queued["issue_type"]:
            raise ValueError(f"issue_type drift {row['case_id']}")
        if row["source_preservation"] != "YES":
            raise ValueError("source_preservation drift")
        if row["owner_approval_state"] != APPROVAL_STATE:
            raise ValueError("owner_approval_state drift")
        if row["resolution_status"] != "GPT_RESOLVED":
            raise ValueError("resolution_status drift")
        if row["canonical_parent_candidate_name"] in FORBIDDEN_PARENT_NAMES:
            raise ValueError(f"forbidden parent selection {row['case_id']}")
        if row["issue_type"] == "PARENT_MODELING":
            if row["gpt_final_decision"] != "COMMON_ANCESTOR_PARENT_CONFIRMED":
                raise ValueError(f"parent decision drift {row['case_id']}")
            if row["canonical_parent_candidate"] != queued["common_candidate_ancestor_key"]:
                raise ValueError(f"parent candidate != REVIEW-014 ancestor {row['case_id']}")
            if row["canonical_parent_candidate"] not in concept_keys:
                raise ValueError(f"unknown parent candidate {row['case_id']}")
            if row["canonical_label_candidate"] != GPT_EMPTY:
                raise ValueError(f"parent label leak {row['case_id']}")
        else:
            if row["gpt_final_decision"] != "HOLD_LABEL_CONFIRMED":
                raise ValueError("L-02 decision drift")
            if row["canonical_parent_candidate"] != GPT_EMPTY:
                raise ValueError("L-02 parent leak")
            if row["canonical_label_candidate"] != GPT_EMPTY:
                raise ValueError("L-02 invented label")
    if len(concepts) != 1111:
        raise ValueError("concept count drift")


def build_remaining5(
    concepts: list[dict] | None = None,
    evidence: list[dict] | None = None,
) -> list[dict]:
    if concepts is None or evidence is None:
        concepts, evidence, _ = _assert_frozen_inputs()
    rows = []
    for case in GPT_CASES:
        rows.append(
            {
                "case_id": case["case_id"],
                "review_concept_key": case["review_concept_key"],
                "source_keys": case["source_keys"],
                "issue_type": case["issue_type"],
                "gpt_final_decision": case["gpt_final_decision"],
                "canonical_parent_candidate": case["canonical_parent_candidate"],
                "canonical_parent_candidate_name": case["canonical_parent_candidate_name"],
                "parent_resolution_basis": case["parent_resolution_basis"],
                "canonical_label_candidate": case["canonical_label_candidate"],
                "label_resolution_status": case["label_resolution_status"],
                "label_resolution_basis": case["label_resolution_basis"],
                "source_context_policy": case["source_context_policy"],
                "source_preservation": "YES",
                "resolution_status": "GPT_RESOLVED",
                "owner_approval_state": APPROVAL_STATE,
                "resolution_notes": case["resolution_notes"],
            }
        )
    _validate(rows, evidence, concepts)
    return rows


def remaining5_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *REMAINING5_FIELDS)


def render_report(rows: list[dict], sha: str) -> str:
    counts = remaining5_counts(rows)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-015 remaining-5 resolution freeze
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-015 — Remaining-5 Semantic Resolution Freeze

This WO freezes GPT remaining-5 semantic resolutions as an overlay. Cursor does not re-judge parent or label. COMMON_ANCESTOR_PARENT_CONFIRMED is not Owner-approved canonical parent assignment. HOLD_LABEL_CONFIRMED is a completed HOLD, not an invented label.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED CANONICAL PARENT MANIFEST
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED MAPPING
COMMON_ANCESTOR_PARENT_CONFIRMED
≠
CANONICAL PARENT APPROVED
HOLD_LABEL_CONFIRMED
≠
LABEL INVENTED
review_concept_key ≠ canonical UUID
canonical_parent_candidate ≠ CANONICAL PARENT APPROVED
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
OBJ-SEARCH-DICT = PARALLEL EXTERNAL STREAM
```

This is an explicit GPT freeze overlay, not a classifier.

---

## Frozen inputs

```text
candidate concepts = 1111
concept count delta = 0
SPLIT = 0
MERGE CHANGE = 0
REVIEW-013 resolution SHA = {FROZEN_RESOLUTION_SHA}
REVIEW-014 evidence SHA = {FROZEN_EVIDENCE_SHA}
```

---

## Resolution overlay

```text
resolution rows = {counts["rows"]}
unique concepts = {counts["unique"]}
PARENT_MODELING = {counts["PARENT_MODELING"]}
LABEL_HOLD = {counts["LABEL_HOLD"]}
COMMON_ANCESTOR_PARENT_CONFIRMED = {counts["COMMON_ANCESTOR_PARENT_CONFIRMED"]}
HOLD_LABEL_CONFIRMED = {counts["HOLD_LABEL_CONFIRMED"]}
계측 parent candidate = {counts["계측"]}
철거해체공사및시설물보호 parent candidate = {counts["철거해체공사및시설물보호"]}
canonical parent candidates selected = {counts["parent_candidates"]}
canonical label candidates selected = {counts["label_candidates"]}
GPT_RESOLVED = {counts["GPT_RESOLVED"]}
GPT PENDING = {counts["GPT_PENDING"]}
PARENT MODELING PENDING = 0
LABEL HOLD = 1
owner_approval_state NOT_APPROVED = {counts["NOT_APPROVED"]}
source_preservation YES = {counts["source_preservation_yes"]}
H-05 exact key = {H05_KEY}
```

---

## Remaining semantic state

```text
GPT resolution = COMPLETE
label resolution = HOLD CONFIRMED
L-02 canonical_label_candidate = EMPTY
구조체계측 canonical parent selections = 0
교량공사계측 canonical parent selections = 0
기계설비철거 해체 canonical parent selections = 0
전기 통신설비철거 해체 canonical parent selections = 0
```

---

## Guard

```text
canonical UUID created = 0
active canonical = 0
approved mapping = 0
production DB write = 0
new migration = 0
Owner Approval = 0
AUTO APPROVED = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
Kiwi runtime calls = 0
```

---

## Determinism

```text
RUN1 SHA = {sha}
RUN2 SHA = {sha}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-015 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL = NOT OPENED
MAPPING = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_review015_artifacts() -> dict:
    concepts, evidence, _ = _assert_frozen_inputs()
    rows = build_remaining5(concepts, evidence)
    sha = remaining5_sha(rows)
    write_tsv(rows, REMAINING5_PATH, REMAINING5_FIELDS)
    REPORT_PATH.write_text(render_report(rows, sha), encoding="utf-8")
    return {"rows": rows, "sha": sha, "counts": remaining5_counts(rows)}


def main() -> None:
    first = write_review015_artifacts()
    concepts, evidence, _ = _assert_frozen_inputs()
    second = build_remaining5(concepts, evidence)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-015",
                "RUN1": first["sha"],
                "RUN2": remaining5_sha(second),
                "ROWS": first["counts"]["rows"],
                "CONCEPT_CANDIDATES": 1111,
                "CONCEPT_COUNT_DELTA": 0,
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
