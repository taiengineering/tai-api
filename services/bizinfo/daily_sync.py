"""WO-TAI-BIZINFO-DAILY-SYNC-SLACK-001 — 일일 수집·상태 갱신·Slack 알림.

기존 TAI bizinfo 모듈을 조합해 매일 KST 13:00에 실행되는 일일 동기화 엔진.
실제 스케줄 활성화·Slack 발송은 별도 Owner 승인 Gate.

판정 보호 정책:
  기존 IN_SCOPE, OUT_OF_SCOPE → 보존 (덮어쓰지 않음)
  기존 REVIEW_REQUIRED 또는 None → 신규 판정으로 업데이트
  신규 공고 → 항상 판정

Slack 중복 방지:
  event_id = "bizinfo_daily_sync_{YYYY-MM-DD}" — 하루 1회 메시지
  accept_relay_event() 중복 시 False → 재전송 없음, 기존 이벤트 재처리 경로 유지

API 개별 조회 미제공:
  페이지 목록 탐색으로 기존 IN_SCOPE 공고를 재확인한다.
  탐색 범위 내에서 발견되지 않은 공고는 "미확인"으로 기록하고,
  취소·마감으로 판정하지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Literal, Optional

from services.bizinfo.api_access import fetch_source_batch
from services.bizinfo.normalizer import ParseFailure, normalize_bizinfo_record
from services.bizinfo.repository import BizinfoRepository
from services.bizinfo.selector import RelevanceDecision, review_relevance
from services.bizinfo.status import (
    detect_change,
    event_status,
    program_status,
)
from services.bizinfo.normalizer import NormalizedSourceRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_SIZE = 100
_MAX_PAGES = 5         # 기본 최대 500건 탐색
_SLACK_CHANNEL = "C0CCQKVQCQP"
_VERDICTS_TO_PRESERVE = frozenset({"IN_SCOPE", "OUT_OF_SCOPE"})


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NewInScopeEvent:
    record: NormalizedSourceRecord
    decision: RelevanceDecision


@dataclass(frozen=True)
class StatusChangeEvent:
    source_kind: Literal["PROGRAM", "EVENT"]
    source_key: str
    title: str
    bizinfo_url: Optional[str]
    old_status: str
    new_status: str


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SyncKindResult:
    source_kind: Literal["PROGRAM", "EVENT"]
    fetched: int = 0
    new_records_saved: int = 0
    new_in_scope: list[NewInScopeEvent] = field(default_factory=list)
    status_changes: list[StatusChangeEvent] = field(default_factory=list)
    in_scope_total: int = 0       # DB에 있는 기존 IN_SCOPE 건수
    in_scope_confirmed: int = 0   # 이번 탐색에서 재발견된 건수
    api_errors: list[str] = field(default_factory=list)


@dataclass
class BizinfoDailySyncResult:
    run_at: datetime
    program: SyncKindResult = field(
        default_factory=lambda: SyncKindResult("PROGRAM")
    )
    event: SyncKindResult = field(
        default_factory=lambda: SyncKindResult("EVENT")
    )
    slack_sent: bool = False
    slack_event_id: Optional[str] = None
    slack_skipped_reason: Optional[str] = None

    @property
    def total_new_in_scope(self) -> int:
        return len(self.program.new_in_scope) + len(self.event.new_in_scope)

    @property
    def total_status_changes(self) -> int:
        return len(self.program.status_changes) + len(self.event.status_changes)


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _program_status_label(record: NormalizedSourceRecord, as_of: date) -> str:
    ps = program_status(record, as_of=as_of)
    return ps.application_status


def _event_status_label(record: NormalizedSourceRecord, as_of: date) -> str:
    es = event_status(record, as_of=as_of)
    return f"접수:{es.reception_status}/행사:{es.progress_status}"


def _detect_status_change(
    prior: NormalizedSourceRecord,
    current: NormalizedSourceRecord,
    as_of: date,
) -> Optional[StatusChangeEvent]:
    """이전 공고와 현재 공고의 상태를 비교해 의미 있는 변화를 반환.

    이전 상태는 prior.retrieved_at.date()를 기준으로,
    현재 상태는 as_of(오늘)를 기준으로 계산한다.
    날짜 변경 없이 시간 경과만으로 발생하는 전환(UPCOMING→OPEN 등)도 포함된다.
    """
    prior_check = prior.retrieved_at.date()
    source_kind = current.source_kind

    if source_kind == "PROGRAM":
        old = _program_status_label(prior, prior_check)
        new = _program_status_label(current, as_of)
    else:
        old = _event_status_label(prior, prior_check)
        new = _event_status_label(current, as_of)

    if old == new:
        return None

    return StatusChangeEvent(
        source_kind=source_kind,
        source_key=current.source_key,
        title=current.title,
        bizinfo_url=current.bizinfo_url,
        old_status=old,
        new_status=new,
    )


# ---------------------------------------------------------------------------
# Kind-level sync
# ---------------------------------------------------------------------------


def _sync_kind(
    source_kind: Literal["PROGRAM", "EVENT"],
    known_in_scope: set[str],
    repo: BizinfoRepository,
    as_of: date,
    get_fn: Optional[Callable],
    max_pages: int,
) -> SyncKindResult:
    result = SyncKindResult(
        source_kind=source_kind,
        in_scope_total=len(known_in_scope),
    )
    confirmed: set[str] = set()
    # verdict 캐시 — per-record DB 호출 중복 방지
    _verdict_cache: dict[str, str] = {}

    for page in range(1, max_pages + 1):
        batch = fetch_source_batch(
            source_kind, page=page, size=_PAGE_SIZE, get_fn=get_fn
        )

        if batch.error_code is not None:
            result.api_errors.append(f"page={page} error_code={batch.error_code}")
            break  # 첫 페이지 실패도, 중간 페이지 종료도 동일하게 처리

        result.fetched += len(batch.items)

        for raw in batch.items:
            normalized = normalize_bizinfo_record(
                source_kind, raw, batch.retrieved_at
            )
            if isinstance(normalized, ParseFailure):
                continue

            key = normalized.source_key
            prior = repo.get_prior_record(source_kind, key)
            is_new = prior is None
            change = detect_change(prior, normalized)

            # 최신 공고 내용 저장 (항상)
            repo.save_record(normalized, change)

            if is_new:
                result.new_records_saved += 1
                decision = review_relevance(normalized)
                repo.save_relevance_verdict(source_kind, key, decision.verdict)
                if decision.verdict == "IN_SCOPE":
                    result.new_in_scope.append(
                        NewInScopeEvent(record=normalized, decision=decision)
                    )
            else:
                # 기존 공고 — 판정 보호 적용
                if key in known_in_scope:
                    # IN_SCOPE 확정 → 판정 보존 + 상태 변경 감지
                    confirmed.add(key)
                    status_ev = _detect_status_change(prior, normalized, as_of)
                    if status_ev:
                        result.status_changes.append(status_ev)
                else:
                    # 비IN_SCOPE 기존 공고 — 판정 확인 (캐시 우선)
                    existing = _verdict_cache.get(key)
                    if existing is None:
                        existing = repo.get_relevance_verdict(source_kind, key)
                        if existing is not None:
                            _verdict_cache[key] = existing

                    if existing not in _VERDICTS_TO_PRESERVE:
                        # REVIEW_REQUIRED 또는 None → 재판정
                        decision = review_relevance(normalized)
                        repo.save_relevance_verdict(source_kind, key, decision.verdict)
                        _verdict_cache[key] = decision.verdict

        if len(batch.items) < _PAGE_SIZE:
            break  # 마지막 페이지

        # 모든 known IN_SCOPE를 확인했으면 조기 종료 (page >= 2 이후)
        if page >= 2 and known_in_scope.issubset(confirmed):
            break

    result.in_scope_confirmed = len(confirmed)
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_bizinfo_daily_sync(
    repo: BizinfoRepository,
    slack_accept_fn: Callable[..., bool],
    *,
    as_of: Optional[date] = None,
    get_fn: Optional[Callable] = None,
    max_pages: int = _MAX_PAGES,
) -> BizinfoDailySyncResult:
    """기업마당 일일 수집·상태 갱신·Slack 알림 실행.

    repo:            BizinfoRepository 구현체 (Supabase 또는 InMemory)
    slack_accept_fn: accept_relay_event 시그니처 호환 함수 (테스트 모의 주입)
    as_of:           기준 날짜 (None = 오늘 UTC)
    get_fn:          HTTP 함수 주입 (None = kr_get 기본값)
    max_pages:       API 최대 탐색 페이지 수
    """
    today = as_of or datetime.now(timezone.utc).date()
    run_at = datetime.now(timezone.utc)
    result = BizinfoDailySyncResult(run_at=run_at)

    for source_kind in ("PROGRAM", "EVENT"):
        # 기존 IN_SCOPE 키 목록 (pagination)
        known_in_scope: set[str] = set()
        offset = 0
        while True:
            batch_keys = repo.list_in_scope_keys(source_kind, limit=200, offset=offset)
            known_in_scope.update(batch_keys)
            if len(batch_keys) < 200:
                break
            offset += 200

        kind_result = _sync_kind(
            source_kind=source_kind,
            known_in_scope=known_in_scope,
            repo=repo,
            as_of=today,
            get_fn=get_fn,
            max_pages=max_pages,
        )

        if source_kind == "PROGRAM":
            result.program = kind_result
        else:
            result.event = kind_result

    # Slack 알림 — 이벤트 있을 때만
    has_events = result.total_new_in_scope > 0 or result.total_status_changes > 0
    if has_events:
        message = build_slack_message(result, today)
        event_id = f"bizinfo_daily_sync_{today.isoformat()}"
        accepted = slack_accept_fn(
            event_id=event_id,
            relay_channel="direct://bizinfo_daily_sync",
            target_channel=_SLACK_CHANNEL,
            message_text=message,
            sender_id="bizinfo_daily_sync",
            source_message_ts=None,
        )
        result.slack_event_id = event_id
        result.slack_sent = accepted
        if not accepted:
            result.slack_skipped_reason = "duplicate_event_id"
    else:
        result.slack_skipped_reason = "no_events"

    return result


# ---------------------------------------------------------------------------
# Slack message builder
# ---------------------------------------------------------------------------


def build_slack_message(result: BizinfoDailySyncResult, run_date: date) -> str:
    """일일 동기화 결과를 Slack 메시지 형식으로 변환."""
    kst_str = run_date.strftime("%Y-%m-%d") + " 13:00"

    all_new = result.program.new_in_scope + result.event.new_in_scope
    all_changes = result.program.status_changes + result.event.status_changes

    lines = [
        f"[TAI 기업마당 안전지원 정보 | {kst_str}]",
        "",
        f"신규 안전 관련 확정: {len(all_new)}건",
        f"기존 공고 상태 변경: {len(all_changes)}건",
    ]

    if all_new:
        lines.append("")
        lines.append("*신규 확정*")
        for ev in all_new:
            rec = ev.record
            lines.append(f"• *{rec.title}*")
            if rec.source_org:
                lines.append(f"  기관: {rec.source_org}")
            if rec.support_target:
                lines.append(f"  지원대상: {rec.support_target}")
            ap = rec.application_period
            if ap and (ap.start or ap.end):
                s = ap.start.isoformat() if ap.start else "미정"
                e = ap.end.isoformat() if ap.end else "미정"
                lines.append(f"  접수기간: {s} ~ {e}")
            ep = rec.event_period
            if ep and (ep.start or ep.end):
                s = ep.start.isoformat() if ep.start else "미정"
                e = ep.end.isoformat() if ep.end else "미정"
                lines.append(f"  행사기간: {s} ~ {e}")
            if rec.bizinfo_url:
                lines.append(f"  링크: {rec.bizinfo_url}")

    if all_changes:
        lines.append("")
        lines.append("*상태 변경*")
        for ev in all_changes:
            lines.append(f"• *{ev.title}*")
            lines.append(f"  변경: {ev.old_status} → {ev.new_status}")
            if ev.bizinfo_url:
                lines.append(f"  링크: {ev.bizinfo_url}")

    return "\n".join(lines)
