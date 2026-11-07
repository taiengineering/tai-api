"""FORM647 공개 승인 정책 테스트 — R8 OD-01~03
WO-TAI-FORM647-R8-OWNER-RELEASE-POLICY-001

approve_form() SQL 함수의 선행 Owner 결정 Gate 로직(GA-008)을 Python으로 검증한다.
_resolve_latest_owner_disposition() 은 SQL DECLARE+SELECT 블록의 Python 등가 구현:

  SELECT event_type INTO v_latest_owner_decision
  FROM form647_review.review_events
  WHERE run_id = p_run_id AND ek = p_ek
    AND event_type IN ('OWNER_APPROVED_FOR_PUBLIC', 'OWNER_REJECTED_FOR_PUBLIC')
  ORDER BY id DESC
  LIMIT 1;

A01  Owner 결정 없음 → None → BLOCK
A02  GPT 긍정 판단만 존재 → None → BLOCK (OD-01: GPT 판단 공개 권한 없음)
A03  Owner 최신 결정 OWNER_APPROVED_FOR_PUBLIC → 'APPROVED' → ALLOW
A04  Owner 승인 후 거부(더 높은 id) → 'REJECTED' → BLOCK (OD-02: 최신 결정 우선)
A05  Owner 거부 후 재승인(더 높은 id) → 'APPROVED' → ALLOW (OD-02)
A06  GPT 판단이 Owner 결정 사이에 끼어도 Owner 결정만 사용 (OD-01)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# SQL GA-008 Gate 로직의 Python 등가 구현
# ---------------------------------------------------------------------------

def _resolve_latest_owner_disposition(
    events: list[dict],
    run_id: str,
    ek: str,
) -> str | None:
    """approve_form() GA-008 선행 Gate 로직.

    SQL: SELECT event_type FROM review_events
         WHERE run_id=? AND ek=?
           AND event_type IN ('OWNER_APPROVED_FOR_PUBLIC', 'OWNER_REJECTED_FOR_PUBLIC')
         ORDER BY id DESC LIMIT 1

    Returns:
        'APPROVED'  — 최신 Owner 결정이 OWNER_APPROVED_FOR_PUBLIC (Gate 통과)
        'REJECTED'  — 최신 Owner 결정이 OWNER_REJECTED_FOR_PUBLIC (Gate 차단)
        None        — Owner 결정 없음 (Gate 차단)

    GPT_POSITIVE_DISPOSITION · GPT_NEGATIVE_DISPOSITION 은 무시 (OD-01).
    """
    owner_events = [
        e for e in events
        if e['run_id'] == run_id
        and e['ek'] == ek
        and e['event_type'] in ('OWNER_APPROVED_FOR_PUBLIC', 'OWNER_REJECTED_FOR_PUBLIC')
    ]
    if not owner_events:
        return None
    latest = max(owner_events, key=lambda e: e['id'])
    return 'APPROVED' if latest['event_type'] == 'OWNER_APPROVED_FOR_PUBLIC' else 'REJECTED'


_RUN_ID = 'form647-remediation-002-714df47a637e3e73'
_EK = '15267319'


# ---------------------------------------------------------------------------
# A01-A06 테스트
# ---------------------------------------------------------------------------

def test_a01_no_owner_decision_blocks():
    """A01: Owner 결정 없음 → None → BLOCK."""
    assert _resolve_latest_owner_disposition([], _RUN_ID, _EK) is None


def test_a02_gpt_only_blocks():
    """A02: GPT 긍정 판단만 존재 → None → BLOCK (OD-01: GPT 판단 공개 권한 없음)."""
    events = [
        {'id': 1, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'GPT_POSITIVE_DISPOSITION'},
    ]
    assert _resolve_latest_owner_disposition(events, _RUN_ID, _EK) is None


def test_a03_owner_approved_allows():
    """A03: Owner 최신 결정 OWNER_APPROVED_FOR_PUBLIC → 'APPROVED' → ALLOW."""
    events = [
        {'id': 1, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_APPROVED_FOR_PUBLIC'},
    ]
    assert _resolve_latest_owner_disposition(events, _RUN_ID, _EK) == 'APPROVED'


def test_a04_rejection_after_approval_blocks():
    """A04: Owner 승인 후 거부(더 높은 id) → 'REJECTED' → BLOCK (OD-02: 최신 결정 우선)."""
    events = [
        {'id': 1, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_APPROVED_FOR_PUBLIC'},
        {'id': 2, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_REJECTED_FOR_PUBLIC'},
    ]
    assert _resolve_latest_owner_disposition(events, _RUN_ID, _EK) == 'REJECTED'


def test_a05_reapproval_after_rejection_allows():
    """A05: Owner 거부 후 재승인(더 높은 id) → 'APPROVED' → ALLOW (OD-02)."""
    events = [
        {'id': 1, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_REJECTED_FOR_PUBLIC'},
        {'id': 2, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_APPROVED_FOR_PUBLIC'},
    ]
    assert _resolve_latest_owner_disposition(events, _RUN_ID, _EK) == 'APPROVED'


def test_a06_gpt_between_owner_decisions_ignored():
    """A06: GPT 판단이 Owner 결정 사이에 끼어도 Owner 결정만 사용 (OD-01).

    이벤트 순서 (id 오름차순):
      id=1  OWNER_APPROVED_FOR_PUBLIC
      id=2  GPT_NEGATIVE_DISPOSITION   ← 무시
      id=3  OWNER_REJECTED_FOR_PUBLIC  ← 최신 Owner 결정
      id=4  GPT_POSITIVE_DISPOSITION   ← 무시 (Owner 결정 덮어쓰기 불가)
    → 최신 Owner 결정 = REJECTED → BLOCK
    """
    events = [
        {'id': 1, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_APPROVED_FOR_PUBLIC'},
        {'id': 2, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'GPT_NEGATIVE_DISPOSITION'},
        {'id': 3, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'OWNER_REJECTED_FOR_PUBLIC'},
        {'id': 4, 'run_id': _RUN_ID, 'ek': _EK,
         'event_type': 'GPT_POSITIVE_DISPOSITION'},
    ]
    assert _resolve_latest_owner_disposition(events, _RUN_ID, _EK) == 'REJECTED'
