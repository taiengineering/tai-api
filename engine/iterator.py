"""Pipeline Iterator — 법령 단위 순회 + Phase 2.2 v3/v4 격리·역순 검증."""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

from engine.pipeline import PipelineHaltError, TAIExtractionPipeline
from engine.sample_accuracy import (
    compute_law_reverse_verification,
    compute_stage2_sample_accuracy,
    compute_subtype_group_accuracy,
    _verify_row,
    _verify_row_reverse,
)
from engine.validator import CheckResult

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)

IteratorOrder = Literal[
    "ascending_size", "descending_size", "random", "sequential"
]


def fetch_law_ids_ordered(order: IteratorOrder) -> list[Any]:
    """Phase 2 처리 대상 법령만 순회 (stage_2_elements ∩ 조항 조인).

    law_master 768 전체가 아니라, 조항·S2가 있는 법령 집합(~704, PM ground truth).
    정렬은 해당 법령별 stage_2 row 수(cnt) 기준.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        logger.warning(
            "DATABASE_URL 없음 — fetch_law_ids_ordered 빈 목록",
        )
        return []

    try:
        import psycopg2

        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT la.law_id, COUNT(*)::bigint AS cnt
            FROM stage_2_elements s2
            JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
            JOIN law_article_part lap ON lap.id = s1.part_id
            JOIN law_article la ON la.id = lap.article_id
            GROUP BY la.law_id
            """
        )
        rows = [(r[0], int(r[1] or 0)) for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_law_ids_ordered SQL 실패: %s", e)
        return []

    if not rows:
        return []

    if order == "ascending_size":
        rows.sort(key=lambda x: x[1])
    elif order == "descending_size":
        rows.sort(key=lambda x: -x[1])
    elif order == "random":
        random.shuffle(rows)
    else:
        rows.sort(key=lambda x: str(x[0]))

    return [r[0] for r in rows]


def _verdict_is_tp_like(verdict: str) -> bool:
    return verdict in ("TP", "PHASE1_TP")


def isolation_reason_for_fp_subtype(sub_type: str | None) -> str:
    """CHECK 제약 isolation_reason 값 (FP_* 열거)."""
    s = sub_type or ""
    if s == "AS_본다":
        return "FP_AS_본다_보조_룰"
    if "OBLIGATION_DETAIL" in s or "GWAN" in s or "SAHANG" in s:
        return "FP_OBLIGATION_DETAIL_GWAN_SAHANG"
    if (
        "REFERENCE" in s
        or "별표" in s
        or "DELEGATION" in s
        or s == "REFERENCE_TO_ATTACHMENT"
    ):
        return "FP_DELEGATION_ETRAHADA_별표"
    if "PROHIBITION" in s:
        return "FP_PROHIBITION_NOT_DOEN"
    if s.startswith("WEAK_"):
        return "FP_WEAK_JUNYONG_HADA"
    return "FP_OTHER"


@dataclass
class IteratorRun:
    """Iterator 실행 결과 (Track A P3)."""

    laws_processed: list[Any] = field(default_factory=list)
    laws_failed: list[tuple[Any, CheckResult]] = field(default_factory=list)
    total_laws: int = 0
    halted: bool = False


class PipelineIterator:
    """법령 단위 자동 순회 + 회귀 검증."""

    def __init__(
        self,
        pipeline: TAIExtractionPipeline,
        supabase: SupabaseClient | None,
        *,
        order: IteratorOrder = "ascending_size",
        regression_window: int = 0,
        halt_on_first_fail: bool = True,
    ) -> None:
        self.pipeline = pipeline
        self.supabase = supabase
        self.order = order
        self.regression_window = regression_window
        self.halt_on_first_fail = halt_on_first_fail

    def iterate(self, *, only_stages: list[int] | None = None) -> IteratorRun:
        """모든 법령 순회 + 검증 hook."""
        run = IteratorRun()
        law_ids = self._fetch_law_order()
        run.total_laws = len(law_ids)

        for i, law_id in enumerate(law_ids):
            try:
                self.pipeline.run(
                    input_data=None,
                    only_stages=only_stages,
                    law_id=law_id,
                )
                run.laws_processed.append(law_id)
                logger.info(
                    "[Iterator %s/%s] law_id=%s PASS",
                    i + 1,
                    run.total_laws,
                    law_id,
                )

                if (
                    self.regression_window > 0
                    and i > 0
                    and i % 10 == 0
                ):
                    recent = run.laws_processed[-self.regression_window :]
                    self._regression_check(recent, only_stages=only_stages)

            except PipelineHaltError as e:
                run.laws_failed.append((law_id, e.check))
                logger.error(
                    "[Iterator %s/%s] law_id=%s %s",
                    i + 1,
                    run.total_laws,
                    law_id,
                    e.check.result_status,
                )
                if self.halt_on_first_fail:
                    run.halted = True
                    return run

        return run

    def _regression_check(
        self,
        recent_law_ids: list[Any],
        *,
        only_stages: list[int] | None,
    ) -> None:
        """이전 N개 법령 재검증 (동일 Pipeline · 검증 hook)."""
        for lid in recent_law_ids:
            self.pipeline.run(
                input_data=None,
                only_stages=only_stages,
                law_id=lid,
            )

    def _fetch_law_order(self) -> list[Any]:
        return fetch_law_ids_ordered(self.order)


@dataclass
class LawProcessRun:
    """단일 법령 처리 결과 (Phase 2.2 v3/v4).

    final_status: PASS | PASS_STABLE | FAIL_HALT
    PASS — Pipeline 정순 통과 + 역순 검증(compute_law_reverse_verification) 통과.
    PASS_STABLE — 격리 변동 0 안정 상태(v3 본질 보전).
    """

    law_id: Any
    iterations_used: int
    final_status: str
    isolated_fp_marked: int = 0


@dataclass
class Phase22V3IteratorRun:
    """Phase 2.2 v3 순회 결과."""

    law_results: list[LawProcessRun] = field(default_factory=list)
    laws_halted: list[tuple[Any, LawProcessRun]] = field(default_factory=list)
    total_laws: int = 0
    halted: bool = False


class Phase22V3Iterator:
    """단일 법령 격리 분석 · 정순+역순 검증 · 회귀 (Phase 2.2 v3/v4)."""

    def __init__(
        self,
        pipeline: TAIExtractionPipeline,
        supabase: SupabaseClient | None,
        *,
        order: IteratorOrder = "ascending_size",
        regression_window: int = 10,
        max_iterations_per_law: int = 5,
        halt_on_first_fail: bool = True,
    ) -> None:
        self.pipeline = pipeline
        self.supabase = supabase
        self.order = order
        self.regression_window = regression_window
        self.max_iterations_per_law = max_iterations_per_law
        self.halt_on_first_fail = halt_on_first_fail
        # 법령 최초 PASS 시점의 비격리 row별 Ground Truth verdict — 회귀 시 TP 훼손 검출
        self._tp_baseline: dict[Any, dict[str, str]] = {}

    def iterate(self, *, only_stages: list[int] | None = None) -> Phase22V3IteratorRun:
        run = Phase22V3IteratorRun()
        law_ids = fetch_law_ids_ordered(self.order)
        run.total_laws = len(law_ids)
        passed_ids: list[Any] = []

        for i, law_id in enumerate(law_ids):
            lp = self._process_single_law(law_id, only_stages=only_stages)
            run.law_results.append(lp)
            if lp.final_status in ("PASS", "PASS_STABLE"):
                passed_ids.append(law_id)
                self._record_tp_baseline_if_missing(law_id)
                logger.info(
                    "[Phase22V3 %s/%s] law_id=%s %s (it=%s)",
                    i + 1,
                    run.total_laws,
                    law_id,
                    lp.final_status,
                    lp.iterations_used,
                )
                if (
                    self.regression_window > 0
                    and i > 0
                    and i % 10 == 0
                ):
                    recent = passed_ids[-self.regression_window :]
                    self._regression_check(recent, only_stages=only_stages)
            else:
                run.laws_halted.append((law_id, lp))
                run.halted = True
                logger.error(
                    "[Phase22V3 %s/%s] law_id=%s FAIL_HALT it=%s marked=%s",
                    i + 1,
                    run.total_laws,
                    law_id,
                    lp.iterations_used,
                    lp.isolated_fp_marked,
                )
                if self.halt_on_first_fail:
                    return run

        return run

    def _process_single_law(
        self,
        law_id: Any,
        *,
        only_stages: list[int] | None,
    ) -> LawProcessRun:
        total_marked = 0
        prev_marked = -1
        for it in range(1, self.max_iterations_per_law + 1):
            iso_mode = it > 1
            excl = iso_mode
            try:
                self.pipeline.run(
                    input_data=None,
                    only_stages=only_stages,
                    law_id=law_id,
                    isolation_mode=iso_mode,
                    exclude_isolated=excl,
                )
            except PipelineHaltError as e:
                chk = e.check
                marked = self._isolate_fp_rows(law_id, chk)
                total_marked += marked
                logger.info(
                    "law_id=%s iteration=%s 검증 %s — FP 격리 %s건",
                    law_id,
                    it,
                    chk.result_status,
                    marked,
                )
                # 안정 상태: 이번 격리 0건 + 누적 변동 없음 → 검증 미달이어도 진행 종료
                if marked == 0 and total_marked == prev_marked:
                    logger.info(
                        "law_id=%s iteration=%s 격리 변동 0 (안정 상태) — PASS_STABLE 처리",
                        law_id,
                        it,
                    )
                    return LawProcessRun(law_id, it, "PASS_STABLE", total_marked)
                prev_marked = total_marked
                continue

            rev_ok, rev_acc, rev_n = compute_law_reverse_verification(
                self.supabase,
                law_id,
                exclude_isolated=excl,
            )
            logger.info(
                "law_id=%s iteration=%s 역순 검증 ok=%s acc=%.4f classified=%s",
                law_id,
                it,
                rev_ok,
                rev_acc,
                rev_n,
            )
            if rev_ok:
                return LawProcessRun(law_id, it, "PASS", total_marked)

            marked = self._isolate_failed_subtypes(law_id)
            total_marked += marked
            logger.info(
                "law_id=%s iteration=%s 역순 FAIL — 역순 FP 격리 %s건",
                law_id,
                it,
                marked,
            )
            if marked == 0 and total_marked == prev_marked:
                logger.info(
                    "law_id=%s iteration=%s 역순 후 격리 변동 0 — PASS_STABLE 처리",
                    law_id,
                    it,
                )
                return LawProcessRun(law_id, it, "PASS_STABLE", total_marked)
            prev_marked = total_marked

        return LawProcessRun(
            law_id,
            self.max_iterations_per_law,
            "FAIL_HALT",
            total_marked,
        )

    def _isolate_fp_rows(self, law_id: Any, check: CheckResult) -> int:
        """_verify_row FP만 is_isolated 마킹 (sub_type 불변)."""
        _ = check
        url = os.environ.get("DATABASE_URL")
        if url:
            return self._isolate_fp_rows_psycopg2(url, law_id)
        return self._isolate_fp_rows_supabase(law_id)

    def _isolate_fp_rows_psycopg2(self, url: str, law_id: Any) -> int:
        import psycopg2

        n = 0
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s2.id, s2.sub_type, s1.source_text
            FROM stage_2_elements s2
            JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
            JOIN law_article_part lap ON lap.id = s1.part_id
            JOIN law_article la ON la.id = lap.article_id
            WHERE la.law_id = %s
            """,
            (law_id,),
        )
        now = datetime.now(timezone.utc)
        for row in cur.fetchall():
            eid, st, stext = row[0], row[1], row[2]
            st_s = st or "UNCLASSIFIED"
            stext_s = stext or ""
            if _verify_row(st_s, stext_s) != "FP":
                continue
            reason = isolation_reason_for_fp_subtype(st)
            cur.execute(
                """
                UPDATE stage_2_elements
                SET is_isolated = true,
                    isolation_reason = %s,
                    isolated_at = %s
                WHERE id = %s::uuid
                  AND COALESCE(is_isolated, false) = false
                """,
                (reason, now, str(eid)),
            )
            n += cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return n

    def _isolate_fp_rows_supabase(self, law_id: Any) -> int:
        if self.supabase is None:
            logger.warning("_isolate_fp_rows: supabase 없음")
            return 0
        from engine.clause_fetch import fetch_clauses_by_law_id

        n = 0
        now = datetime.now(timezone.utc).isoformat()
        clauses = fetch_clauses_by_law_id(self.supabase, law_id)
        for cl in clauses:
            cid = cl.get("id")
            if not cid:
                continue
            res = (
                self.supabase.table("stage_2_elements")
                .select("id, sub_type, is_isolated")
                .eq("clause_id", cid)
                .execute()
                .data
                or []
            )
            stext = cl.get("source_text") or ""
            for elem in res:
                if elem.get("is_isolated") is True:
                    continue
                st = elem.get("sub_type") or "UNCLASSIFIED"
                if _verify_row(st, stext) != "FP":
                    continue
                reason = isolation_reason_for_fp_subtype(st)
                self.supabase.table("stage_2_elements").update(
                    {
                        "is_isolated": True,
                        "isolation_reason": reason,
                        "isolated_at": now,
                    }
                ).eq("id", elem["id"]).execute()
                n += 1
        return n

    def _isolate_failed_subtypes(self, law_id: Any) -> int:
        """역순 검증 FP 행만 격리 — sub_type 불변 (WARNING_LOW_ACCURACY)."""
        url = os.environ.get("DATABASE_URL")
        if url:
            return self._isolate_failed_subtypes_psycopg2(url, law_id)
        return self._isolate_failed_subtypes_supabase(law_id)

    def _isolate_failed_subtypes_psycopg2(self, url: str, law_id: Any) -> int:
        import psycopg2

        n = 0
        reason = "WARNING_LOW_ACCURACY"
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s2.id, s2.sub_type, s1.source_text
            FROM stage_2_elements s2
            JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
            JOIN law_article_part lap ON lap.id = s1.part_id
            JOIN law_article la ON la.id = lap.article_id
            WHERE la.law_id = %s
            """,
            (law_id,),
        )
        now = datetime.now(timezone.utc)
        for row in cur.fetchall():
            eid, st, stext = row[0], row[1], row[2]
            st_s = st or "UNCLASSIFIED"
            stext_s = stext or ""
            if _verify_row_reverse(st_s, stext_s) != "FP":
                continue
            cur.execute(
                """
                UPDATE stage_2_elements
                SET is_isolated = true,
                    isolation_reason = %s,
                    isolated_at = %s
                WHERE id = %s::uuid
                  AND COALESCE(is_isolated, false) = false
                """,
                (reason, now, str(eid)),
            )
            n += cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return n

    def _isolate_failed_subtypes_supabase(self, law_id: Any) -> int:
        if self.supabase is None:
            logger.warning("_isolate_failed_subtypes: supabase 없음")
            return 0
        from engine.clause_fetch import fetch_clauses_by_law_id

        n = 0
        reason = "WARNING_LOW_ACCURACY"
        now = datetime.now(timezone.utc).isoformat()
        clauses = fetch_clauses_by_law_id(self.supabase, law_id)
        for cl in clauses:
            cid = cl.get("id")
            if not cid:
                continue
            res = (
                self.supabase.table("stage_2_elements")
                .select("id, sub_type, is_isolated")
                .eq("clause_id", cid)
                .execute()
                .data
                or []
            )
            stext = cl.get("source_text") or ""
            for elem in res:
                if elem.get("is_isolated") is True:
                    continue
                st = elem.get("sub_type") or "UNCLASSIFIED"
                if _verify_row_reverse(st, stext) != "FP":
                    continue
                self.supabase.table("stage_2_elements").update(
                    {
                        "is_isolated": True,
                        "isolation_reason": reason,
                        "isolated_at": now,
                    }
                ).eq("id", elem["id"]).execute()
                n += 1
        return n

    def _record_tp_baseline_if_missing(self, law_id: Any) -> None:
        """최초 PASS 법령만 스냅샷 고정 — 이후 회귀 비교 기준."""
        if law_id in self._tp_baseline:
            return
        self._tp_baseline[law_id] = self._tp_snapshot_for_law(law_id)
        logger.info(
            "regression baseline 저장 law_id=%s rows=%s",
            law_id,
            len(self._tp_baseline[law_id]),
        )

    def _tp_snapshot_for_law(self, law_id: Any) -> dict[str, str]:
        """비격리 stage_2 row id → _verify_row verdict."""
        url = os.environ.get("DATABASE_URL")
        if url:
            return self._tp_snapshot_psycopg2(url, law_id)
        return self._tp_snapshot_supabase(law_id)

    def _tp_snapshot_psycopg2(self, url: str, law_id: Any) -> dict[str, str]:
        import psycopg2

        out: dict[str, str] = {}
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s2.id::text, s2.sub_type, s1.source_text
            FROM stage_2_elements s2
            JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
            JOIN law_article_part lap ON lap.id = s1.part_id
            JOIN law_article la ON la.id = lap.article_id
            WHERE la.law_id = %s
              AND COALESCE(s2.is_isolated, false) = false
            """,
            (law_id,),
        )
        for eid, st, stext in cur.fetchall():
            out[str(eid)] = _verify_row((st or "UNCLASSIFIED"), stext or "")
        cur.close()
        conn.close()
        return out

    def _tp_snapshot_supabase(self, law_id: Any) -> dict[str, str]:
        from engine.clause_fetch import fetch_clauses_by_law_id

        out: dict[str, str] = {}
        if self.supabase is None:
            return out
        clauses = fetch_clauses_by_law_id(self.supabase, law_id)
        for cl in clauses:
            cid = cl.get("id")
            if not cid:
                continue
            stext = cl.get("source_text") or ""
            res = (
                self.supabase.table("stage_2_elements")
                .select("id, sub_type, is_isolated")
                .eq("clause_id", cid)
                .execute()
                .data
                or []
            )
            for elem in res:
                if elem.get("is_isolated") is True:
                    continue
                eid = elem.get("id")
                if not eid:
                    continue
                st = elem.get("sub_type") or "UNCLASSIFIED"
                out[str(eid)] = _verify_row(st, stext)
        return out

    def _check_tp_variance(self, law_id: Any) -> int:
        """베이스라인 대비 TP·PHASE1_TP 가 깨진 비격리 row 수."""
        baseline = self._tp_baseline.get(law_id)
        if not baseline:
            return 0
        current = self._tp_snapshot_for_law(law_id)
        lost = 0
        for eid, v0 in baseline.items():
            if not _verdict_is_tp_like(v0):
                continue
            v1 = current.get(eid)
            if v1 is None or not _verdict_is_tp_like(v1):
                lost += 1
        return lost

    def _stage2_for_halt(self):
        for s in self.pipeline.stages:
            if s.stage_number == 2:
                return s
        return self.pipeline.stages[0]

    def _regression_check(
        self,
        recent_law_ids: list[Any],
        *,
        only_stages: list[int] | None,
    ) -> None:
        """회귀 검증 — 샘플 재측정(n≥30) + 비격리 TP 행 정합."""
        _ = only_stages

        for law_id in recent_law_ids:
            accuracy, n = compute_stage2_sample_accuracy(
                self.supabase,
                law_id=law_id,
                exclude_isolated=False,
            )
            logger.info(
                "regression sample_accuracy law_id=%s accuracy=%.4f n=%s",
                law_id,
                accuracy,
                n,
            )
            if n < 30:
                logger.info(
                    "law_id=%s sample %s < 30 → 회귀 통계 건너뜀",
                    law_id,
                    n,
                )
                continue

            tp_diff = self._check_tp_variance(law_id)
            if tp_diff > 0:
                stage2 = self._stage2_for_halt()
                chk = CheckResult(
                    stage=2,
                    check_name="phase22_v3_regression_tp_variance",
                    check_type="AUTO_HOOK",
                    result_status="FAIL",
                    expected_value="TP 변동 0",
                    actual_value=str(tp_diff),
                    threshold="0",
                    sample_size=n,
                    error_count=tp_diff,
                    notes=f"sample_accuracy={accuracy:.4f}",
                )
                raise PipelineHaltError(stage2, chk)

        self._log_global_subtype_diagnostic()

    def _log_global_subtype_diagnostic(self) -> None:
        """회귀 구간 전역 sub_type accuracy 진단 로그."""
        if self.supabase is None:
            return
        try:
            groups = compute_subtype_group_accuracy(
                self.supabase,
                law_id=None,
                sample_articles=400,
                exclude_isolated=True,
            )
            ranked = sorted(
                groups.items(),
                key=lambda kv: kv[1].get("accuracy", 1.0),
            )[:15]
            logger.info(
                "regression global subtype diagnostic (low acc first): %s",
                [(k, v.get("accuracy"), v.get("classified"), v.get("fp"))
                 for k, v in ranked],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("global subtype diagnostic 실패: %s", e)
