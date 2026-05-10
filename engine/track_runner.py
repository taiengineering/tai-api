"""Track A~E 법령 단위 순차 검증 엔진.

법령마다 A → B → C → D → E 순서로 정순+역순 검증.
FAIL → 이슈 유형 분류 → track_issue_log 저장 → 다음 법령.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TRACK_ORDER = ("A", "B", "C", "D", "E")
DEFAULT_THRESHOLD = 0.90

ISSUE_TYPES = (
    "ISSUE_PARSE_STRUCTURE",
    "ISSUE_MISSING_SUBJECT",
    "ISSUE_ATTACHMENT_REFERENCE",
    "ISSUE_EXCEPTION_CONFLICT",
    "ISSUE_CONDITION_AMBIGUOUS",
    "ISSUE_SCHEDULE_UNCLEAR",
    "ISSUE_TARGET_OBJECT_UNKNOWN",
)


# ── 결과 구조 ──────────────────────────────────────────

@dataclass
class TrackIssue:
    law_id: Any
    track: str
    issue_type: str
    direction: str  # FORWARD / REVERSE
    accuracy: float = 0.0
    source_text: str | None = None
    article_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrackVerdict:
    track: str
    law_id: Any
    forward_pass: bool
    forward_accuracy: float
    forward_classified: int
    reverse_pass: bool
    reverse_accuracy: float
    reverse_classified: int
    issues: list[TrackIssue] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LawResult:
    law_id: Any
    verdicts: list[TrackVerdict] = field(default_factory=list)
    stopped_at: str | None = None


@dataclass
class RunResult:
    results: list[LawResult] = field(default_factory=list)
    total_laws: int = 0

    @property
    def passed(self) -> list[LawResult]:
        return [r for r in self.results if r.stopped_at is None]

    @property
    def failed(self) -> list[LawResult]:
        return [r for r in self.results if r.stopped_at is not None]

    def fail_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {t: 0 for t in TRACK_ORDER}
        for r in self.failed:
            if r.stopped_at:
                counts[r.stopped_at] = counts.get(r.stopped_at, 0) + 1
        return counts

    def all_issues(self) -> list[TrackIssue]:
        out: list[TrackIssue] = []
        for r in self.results:
            for v in r.verdicts:
                out.extend(v.issues)
        return out

    def issue_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.all_issues():
            counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1
        return counts


# ── DB 헬퍼 ────────────────────────────────────────────

def _get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    import psycopg2
    return psycopg2.connect(url)


def _fetch_all_law_ids(conn) -> list[Any]:
    cur = conn.cursor()
    cur.execute("""
        SELECT la.law_id, COUNT(*)::bigint AS cnt
        FROM stage_2_elements s2
        JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
        JOIN law_article_part lap ON lap.id = s1.part_id
        JOIN law_article la ON la.id = lap.article_id
        GROUP BY la.law_id ORDER BY cnt ASC
    """)
    ids = [r[0] for r in cur.fetchall()]
    cur.close()
    return ids


def _save_issues(conn, issues: list[TrackIssue]) -> int:
    if not issues:
        return 0
    import json
    cur = conn.cursor()
    saved = 0
    for iss in issues:
        try:
            cur.execute("""
                INSERT INTO track_issue_log
                    (law_id, track, issue_type, direction, accuracy, source_text, article_id, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(iss.law_id), iss.track, iss.issue_type, iss.direction,
                iss.accuracy, iss.source_text, iss.article_id,
                json.dumps(iss.detail, ensure_ascii=False),
            ))
            saved += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("track_issue_log INSERT 실패: %s", e)
    conn.commit()
    cur.close()
    return saved


def _v(track: str, law_id: Any) -> TrackVerdict:
    return TrackVerdict(
        track=track, law_id=law_id,
        forward_pass=False, forward_accuracy=0.0, forward_classified=0,
        reverse_pass=False, reverse_accuracy=0.0, reverse_classified=0,
    )


# ── Track A: 인프라 ───────────────────────────────────

def run_track_a(conn, law_id: Any, morpheme_engine=None) -> TrackVerdict:
    v = _v("A", law_id)
    cur = conn.cursor()
    cur.execute("""
        SELECT lap.part_text FROM law_article_part lap
        JOIN law_article la ON la.id = lap.article_id
        WHERE la.law_id = %s LIMIT 5000
    """, (law_id,))
    parts = [r[0] or "" for r in cur.fetchall()]
    cur.close()

    if not parts:
        v.issues.append(TrackIssue(
            law_id=law_id, track="A", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="FORWARD", detail={"reason": "law_article_part 0건"},
        ))
        return v

    if morpheme_engine is None:
        has_text = sum(1 for p in parts if p.strip())
        acc = has_text / len(parts) if parts else 0.0
        v.forward_accuracy = acc
        v.forward_classified = len(parts)
        v.forward_pass = acc >= DEFAULT_THRESHOLD
        v.reverse_pass = v.forward_pass
        v.reverse_accuracy = acc
        v.reverse_classified = len(parts)
        if not v.forward_pass:
            v.issues.append(TrackIssue(
                law_id=law_id, track="A", issue_type="ISSUE_PARSE_STRUCTURE",
                direction="FORWARD", accuracy=acc,
                detail={"has_text": has_text, "total": len(parts)},
            ))
        return v

    if morpheme_engine.user_dict_size != 1725:
        v.issues.append(TrackIssue(
            law_id=law_id, track="A", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="FORWARD",
            detail={"dict_size": morpheme_engine.user_dict_size, "expected": 1725},
        ))
        return v

    valid = classified = 0
    for text in parts:
        text = text.strip()
        if not text:
            continue
        classified += 1
        if morpheme_engine.tokenize(text):
            valid += 1

    v.forward_classified = classified
    v.forward_accuracy = valid / classified if classified else 1.0
    v.forward_pass = v.forward_accuracy >= DEFAULT_THRESHOLD
    if not v.forward_pass:
        v.issues.append(TrackIssue(
            law_id=law_id, track="A", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="FORWARD", accuracy=v.forward_accuracy,
        ))
        return v

    # 역순
    total_tok = valid_tok = 0
    for text in parts[:200]:
        text = text.strip()
        if not text:
            continue
        for tok in morpheme_engine.tokenize(text):
            total_tok += 1
            if 0 <= tok.start < tok.end <= len(text):
                valid_tok += 1

    v.reverse_classified = total_tok
    v.reverse_accuracy = valid_tok / total_tok if total_tok else 1.0
    v.reverse_pass = v.reverse_accuracy >= DEFAULT_THRESHOLD
    if not v.reverse_pass:
        v.issues.append(TrackIssue(
            law_id=law_id, track="A", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="REVERSE", accuracy=v.reverse_accuracy,
        ))
    return v


# ── Track B: 가족 관계 (citation 제외) ────────────────

def run_track_b(conn, law_id: Any) -> TrackVerdict:
    """정순: family_mapping 존재 확인. 역순: 자식 법령이면 parent가 law_master에 있는지.
    citation 매칭률은 수집 진행 상황이므로 검증 대상에서 제외."""
    v = _v("B", law_id)
    cur = conn.cursor()

    cur.execute("SELECT family_role, parent_law_id FROM law_family_mapping WHERE law_master_id = %s", (law_id,))
    fam = cur.fetchone()
    if not fam:
        v.issues.append(TrackIssue(
            law_id=law_id, track="B", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="FORWARD", detail={"reason": "family_mapping 없음"},
        ))
        cur.close()
        return v

    family_role, parent_law_id = fam

    # 정순: family_mapping 존재 = PASS
    v.forward_accuracy = 1.0
    v.forward_classified = 1
    v.forward_pass = True

    # 역순: 자식 법령이면 parent가 실제 존재하는지
    if family_role in ("ENFORCEMENT_DECREE", "ENFORCEMENT_RULE", "ADMINISTRATIVE_RULE") and parent_law_id:
        cur.execute("SELECT 1 FROM law_master WHERE id = %s", (parent_law_id,))
        exists = cur.fetchone() is not None
        v.reverse_accuracy = 1.0 if exists else 0.0
        v.reverse_classified = 1
        v.reverse_pass = exists
        if not exists:
            v.issues.append(TrackIssue(
                law_id=law_id, track="B", issue_type="ISSUE_TARGET_OBJECT_UNKNOWN",
                direction="REVERSE",
                detail={"parent_law_id": str(parent_law_id), "reason": "law_master에 없음"},
            ))
    else:
        v.reverse_pass = True
        v.reverse_accuracy = 1.0
        v.reverse_classified = 1

    v.detail = {"role": family_role}
    cur.close()
    return v


# ── Track C: 사전 ─────────────────────────────────────

def run_track_c(conn, law_id: Any, morpheme_engine=None) -> TrackVerdict:
    v = _v("C", law_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dict_legal_terms WHERE verified = true")
    verified = cur.fetchone()[0]
    cur.close()

    v.forward_classified = 1
    if verified >= 1725:
        v.forward_accuracy = 1.0
        v.forward_pass = True
    else:
        v.forward_accuracy = verified / 1725
        v.issues.append(TrackIssue(
            law_id=law_id, track="C", issue_type="ISSUE_PARSE_STRUCTURE",
            direction="FORWARD", detail={"verified": verified},
        ))
        return v

    if morpheme_engine is not None:
        loaded = morpheme_engine.user_dict_size
        v.reverse_classified = 1
        v.reverse_accuracy = 1.0 if loaded >= 1725 else loaded / 1725
        v.reverse_pass = loaded >= 1725
        if not v.reverse_pass:
            v.issues.append(TrackIssue(
                law_id=law_id, track="C", issue_type="ISSUE_PARSE_STRUCTURE",
                direction="REVERSE", detail={"loaded": loaded},
            ))
    else:
        v.reverse_pass = True
        v.reverse_accuracy = 1.0
    return v


# ── Track D: 별표 ─────────────────────────────────────

def run_track_d(conn, law_id: Any) -> TrackVerdict:
    v = _v("D", law_id)
    cur = conn.cursor()
    cur.execute("""
        SELECT la_att.extraction_verdict, la_att.attachment_text
        FROM law_attachment la_att
        JOIN law_version lv ON lv.id = la_att.law_version_id
        WHERE lv.law_id = %s
    """, (law_id,))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        v.forward_pass = True
        v.forward_accuracy = 1.0
        v.reverse_pass = True
        v.reverse_accuracy = 1.0
        return v

    total = len(rows)
    clean = sum(1 for s, _ in rows if s == "CLEAN")
    v.forward_classified = total
    v.forward_accuracy = clean / total if total else 0.0
    v.forward_pass = v.forward_accuracy >= DEFAULT_THRESHOLD
    if not v.forward_pass:
        v.issues.append(TrackIssue(
            law_id=law_id, track="D", issue_type="ISSUE_ATTACHMENT_REFERENCE",
            direction="FORWARD", accuracy=v.forward_accuracy,
            detail={"total": total, "clean": clean},
        ))
        return v

    clean_rows = [(s, t) for s, t in rows if s == "CLEAN"]
    if clean_rows:
        has_text = sum(1 for _, t in clean_rows if t and t.strip())
        v.reverse_classified = len(clean_rows)
        v.reverse_accuracy = has_text / len(clean_rows)
        v.reverse_pass = v.reverse_accuracy >= DEFAULT_THRESHOLD
        if not v.reverse_pass:
            v.issues.append(TrackIssue(
                law_id=law_id, track="D", issue_type="ISSUE_ATTACHMENT_REFERENCE",
                direction="REVERSE", accuracy=v.reverse_accuracy,
                detail={"clean": len(clean_rows), "has_text": has_text},
            ))
    else:
        v.reverse_pass = v.forward_pass
        v.reverse_accuracy = v.forward_accuracy
    return v


# ── Track E: Stage 분해 ───────────────────────────────

def _classify_track_e_issues(conn, law_id: Any, v: TrackVerdict) -> None:
    """Track E 실패 시 sub_type별 FP를 이슈 유형으로 분류."""
    from engine.sample_accuracy import _verify_row

    cur = conn.cursor()
    cur.execute("""
        SELECT s2.sub_type, s1.source_text, s2.if_pattern
        FROM stage_2_elements s2
        JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
        JOIN law_article_part lap ON lap.id = s1.part_id
        JOIN law_article la ON la.id = lap.article_id
        WHERE la.law_id = %s LIMIT 5000
    """, (law_id,))
    rows = cur.fetchall()
    cur.close()

    SUB_TO_ISSUE = {
        "OBLIGATION_HEADER": "ISSUE_MISSING_SUBJECT",
        "AUTHORITY_HEADER": "ISSUE_MISSING_SUBJECT",
        "EXCEPTION_CLAUSE": "ISSUE_EXCEPTION_CONFLICT",
        "PROHIBITION_HEADER": "ISSUE_MISSING_SUBJECT",
        "DELEGATION_ACTIVE": "ISSUE_TARGET_OBJECT_UNKNOWN",
        "REFERENCE_TO_ATTACHMENT": "ISSUE_ATTACHMENT_REFERENCE",
        "REFERENCE_INVOCATION": "ISSUE_ATTACHMENT_REFERENCE",
        "DATE_EFFECTIVE": "ISSUE_SCHEDULE_UNCLEAR",
    }

    for sub_type, source_text, if_pattern in rows:
        sub_type = sub_type or "UNCLASSIFIED"
        source_text = source_text or ""
        verdict = _verify_row(sub_type, source_text)
        if verdict != "FP":
            continue

        issue_type = SUB_TO_ISSUE.get(sub_type, "ISSUE_PARSE_STRUCTURE")
        if if_pattern and if_pattern != "UNCONDITIONAL" and sub_type == "UNCLASSIFIED":
            issue_type = "ISSUE_CONDITION_AMBIGUOUS"

        v.issues.append(TrackIssue(
            law_id=law_id, track="E", issue_type=issue_type,
            direction="FORWARD", source_text=source_text[:200],
            detail={"sub_type": sub_type, "if_pattern": if_pattern},
        ))


def run_track_e(conn, law_id: Any, supabase=None) -> TrackVerdict:
    from engine.sample_accuracy import (
        compute_law_reverse_verification,
        compute_stage2_sample_accuracy,
    )
    v = _v("E", law_id)

    fwd_acc, fwd_n = compute_stage2_sample_accuracy(
        supabase, law_id=law_id, exclude_isolated=False,
    )
    v.forward_accuracy = fwd_acc
    v.forward_classified = fwd_n
    v.forward_pass = fwd_acc >= DEFAULT_THRESHOLD

    rev_ok, rev_acc, rev_n = compute_law_reverse_verification(
        supabase, law_id, exclude_isolated=False,
    )
    v.reverse_pass = rev_ok
    v.reverse_accuracy = rev_acc
    v.reverse_classified = rev_n

    if not v.forward_pass or not v.reverse_pass:
        _classify_track_e_issues(conn, law_id, v)

    v.detail = {"fwd_acc": fwd_acc, "rev_acc": rev_acc}
    return v


# ── TrackRunner ────────────────────────────────────────

class TrackRunner:
    def __init__(self, *, morpheme_engine=None, supabase=None) -> None:
        self.morpheme_engine = morpheme_engine
        self.supabase = supabase

    def run_all(self) -> RunResult:
        conn = _get_conn()
        if conn is None:
            logger.error("DATABASE_URL 미설정")
            return RunResult()

        law_ids = _fetch_all_law_ids(conn)
        result = RunResult(total_laws=len(law_ids))
        logger.info("TrackRunner 시작: %d 법령", len(law_ids))

        for i, law_id in enumerate(law_ids):
            lr = self._run_single_law(conn, law_id)
            result.results.append(lr)

            # 이슈 DB 저장
            for vd in lr.verdicts:
                if vd.issues:
                    _save_issues(conn, vd.issues)

            if (i + 1) % 50 == 0 or lr.stopped_at:
                status = "PASS" if lr.stopped_at is None else f"FAIL@{lr.stopped_at}"
                logger.info("[%d/%d] law_id=%s %s", i + 1, len(law_ids), law_id, status)

        conn.close()
        logger.info(
            "완료: %d/%d PASS, FAIL=%s, ISSUES=%s",
            len(result.passed), result.total_laws,
            result.fail_summary(), result.issue_summary(),
        )
        return result

    def _run_single_law(self, conn, law_id: Any) -> LawResult:
        lr = LawResult(law_id=law_id)
        for track in TRACK_ORDER:
            v = self._run_track(conn, track, law_id)
            lr.verdicts.append(v)
            if not v.forward_pass or not v.reverse_pass:
                lr.stopped_at = track
                return lr
        return lr

    def _run_track(self, conn, track: str, law_id: Any) -> TrackVerdict:
        if track == "A":
            return run_track_a(conn, law_id, self.morpheme_engine)
        if track == "B":
            return run_track_b(conn, law_id)
        if track == "C":
            return run_track_c(conn, law_id, self.morpheme_engine)
        if track == "D":
            return run_track_d(conn, law_id)
        if track == "E":
            return run_track_e(conn, law_id, self.supabase)
        raise ValueError(f"알 수 없는 Track: {track}")
