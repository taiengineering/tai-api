"""QA Catalog Sync tests — WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP C.

CS-01: dry_run=True, all new → would_create populated, counts.created=0
CS-02: dry_run=False, new scenarios → created=N, schedules inserted
CS-03: idempotent — same manifest → unchanged=N, created=0, updated=0
CS-04: dry_run=False + mutable field changed → updated=1
CS-05: new item gets enabled=false (sync cannot overwrite enabled)
CS-06: invalid site_code → validation error, not inserted
CS-07: duplicate scenario_id in input → fail-close, zero writes
CS-08: invalid area_code → error reported
CS-09: new item schedule: MANUAL / enabled=false / no next_run_at
CS-10: dry_run=True + mutable field changed → would_update populated, counts.updated=0
CS-11: empty input → created=0, unchanged=0, updated=0
CS-12: invalid qa_type → error reported
CS-13: any validation error + valid scenario in same batch → fail-close, zero writes
CS-14: duplicate in batch → fail-close, zero writes
CS-15: scenario without category field → valid; area_code used as DB category fallback
CS-16: scenario_id prefix mismatches priority → validation error
CS-17: qa_schedules.insert failure → compensating delete of qa_items
CS-18: update of existing item never patches enabled field
CS-19: updating existing item does not touch qa_schedules
CS-20: missing X-Internal-Secret → 403
CS-21: wrong X-Internal-Secret → 403
CS-22: valid secret + dry_run=True → 200
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch as mock_patch

import pytest

from services.qa_catalog_sync_svc import sync_catalog


# ── helpers ───────────────────────────────────────────────────────────────────

def _scenario(**kwargs):
    base = {
        'scenario_id':  'P1-TEST-001',
        'name':         '테스트 시나리오',
        'description':  '설명',
        'site_code':    'WWW',
        'priority':     'P1',
        'runner_type':  'PLAYWRIGHT',
        'service_code': 'WWW',
        'area_code':    'AUTH',
        'qa_type':      'AVAILABILITY',
    }
    return {**base, **kwargs}


def _make_sb(existing_items=None, insert_ids=None, schedule_fail=False):
    """Supabase mock for sync_catalog. Returns same mock per table name."""
    sb = MagicMock()
    _cache: dict = {}

    def _table(name):
        if name in _cache:
            return _cache[name]
        m = MagicMock()
        if name == 'qa_items':
            select_chain = MagicMock()
            select_chain.execute.return_value = MagicMock(data=existing_items or [])
            m.select.return_value.in_.return_value = select_chain

            insert_chain = MagicMock()
            insert_chain.execute.return_value = MagicMock(data=insert_ids or [])
            m.insert.return_value = insert_chain

            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
            m.update.return_value = update_chain

            delete_chain = MagicMock()
            delete_chain.in_.return_value.execute.return_value = MagicMock(data=[])
            m.delete.return_value = delete_chain

        elif name == 'qa_schedules':
            sched_insert_chain = MagicMock()
            if schedule_fail:
                sched_insert_chain.execute.side_effect = Exception("schedule insert failed")
            else:
                sched_insert_chain.execute.return_value = MagicMock(data=[{}])
            m.insert.return_value = sched_insert_chain

        _cache[name] = m
        return m

    sb.table.side_effect = _table
    sb._cache = _cache
    return sb


# ── tests ─────────────────────────────────────────────────────────────────────

def test_cs01_dry_run_new_scenarios():
    """CS-01: dry_run=True, all new → would_create populated, counts.created=0."""
    sb = _make_sb(existing_items=[])
    s = _scenario()
    result = sync_catalog(sb, [s], dry_run=True)

    assert result['dry_run'] is True
    assert result['would_create'] == ['P1-TEST-001']
    assert result['counts']['created'] == 0
    assert result['counts']['unchanged'] == 0
    # No INSERT or UPDATE in dry_run
    items_mock = sb._cache.get('qa_items')
    assert items_mock is None or not items_mock.insert.called
    assert items_mock is None or not items_mock.update.called


def test_cs02_dry_run_false_creates_item_and_schedule():
    """CS-02: dry_run=False, new scenario → qa_items inserted + schedule inserted."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item])
    s = _scenario()
    result = sync_catalog(sb, [s], dry_run=False)

    assert result['dry_run'] is False
    assert result['created'] == ['P1-TEST-001']
    assert result['counts']['created'] == 1

    # qa_items insert called
    items_mock = sb._cache['qa_items']
    assert items_mock.insert.called

    # qa_schedules insert called with MANUAL + enabled=False
    sched_mock = sb._cache['qa_schedules']
    assert sched_mock.insert.called
    sched_row = sched_mock.insert.call_args[0][0][0]
    assert sched_row['qa_item_id'] == 'item-uuid-1'
    assert sched_row['frequency_type'] == 'MANUAL'
    assert sched_row['enabled'] is False
    assert 'next_run_at' not in sched_row


def test_cs03_idempotent():
    """CS-03: same manifest as existing → unchanged=1, created=0, updated=0."""
    existing = {
        'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001',
        'name': '테스트 시나리오', 'description': '설명',
        'expected_summary': None,
        'site_code': 'WWW', 'category': 'AUTH', 'priority': 'P1',
        'runner_type': 'PLAYWRIGHT', 'service_code': 'WWW',
        'area_code': 'AUTH', 'qa_type': 'AVAILABILITY', 'enabled': False,
    }
    sb = _make_sb(existing_items=[existing])
    s = _scenario()
    result = sync_catalog(sb, [s], dry_run=False)

    assert result['existing_unchanged'] == ['P1-TEST-001']
    assert result['counts']['unchanged'] == 1
    assert result['counts']['created'] == 0
    assert result['counts']['updated'] == 0


def test_cs04_mutable_field_updated():
    """CS-04: dry_run=False + name changed → updated=1."""
    existing = {
        'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001',
        'name': '구 이름', 'description': '설명', 'expected_summary': None,
        'site_code': 'WWW', 'category': 'AUTH', 'priority': 'P1',
        'runner_type': 'PLAYWRIGHT', 'service_code': 'WWW',
        'area_code': 'AUTH', 'qa_type': 'AVAILABILITY', 'enabled': False,
    }
    sb = _make_sb(existing_items=[existing])
    s = _scenario(name='신규 이름')
    result = sync_catalog(sb, [s], dry_run=False)

    assert result['existing_updated'] == ['P1-TEST-001']
    assert result['counts']['updated'] == 1
    # update called
    assert sb._cache['qa_items'].update.called


def test_cs05_new_item_enabled_false():
    """CS-05: new item always inserted with enabled=False."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item])
    s = _scenario()
    sync_catalog(sb, [s], dry_run=False)

    row = sb._cache['qa_items'].insert.call_args[0][0][0]
    assert row['enabled'] is False


def test_cs06_invalid_site_code():
    """CS-06: invalid site_code → validation error, not inserted."""
    sb = _make_sb()
    s = _scenario(site_code='INVALID_SITE')
    result = sync_catalog(sb, [s], dry_run=False)

    assert len(result['errors']) == 1
    assert 'site_code' in result['errors'][0]['reason']
    assert result['counts']['created'] == 0
    # No INSERT when all fail validation
    assert 'qa_items' not in sb._cache or not sb._cache['qa_items'].insert.called


def test_cs07_duplicate_scenario_id():
    """CS-07: duplicate scenario_id in input → fail-close, zero writes."""
    sb = _make_sb(existing_items=[])
    s1 = _scenario(scenario_id='P1-TEST-001')
    s2 = _scenario(scenario_id='P1-TEST-001', name='다른 이름')
    result = sync_catalog(sb, [s1, s2], dry_run=False)

    assert len(result['errors']) == 1
    assert result['errors'][0]['reason'] == 'duplicate scenario_id in input'
    assert result['counts']['created'] == 0
    items_mock = sb._cache.get('qa_items')
    assert items_mock is None or not items_mock.insert.called


def test_cs08_invalid_area_code():
    """CS-08: invalid area_code (lowercase) → error reported."""
    sb = _make_sb()
    s = _scenario(area_code='invalid_area')
    result = sync_catalog(sb, [s], dry_run=False)

    assert len(result['errors']) == 1
    assert 'area_code' in result['errors'][0]['reason']


def test_cs09_new_item_schedule_no_next_run_at():
    """CS-09: schedule row must not contain next_run_at."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item])
    sync_catalog(sb, [_scenario()], dry_run=False)

    sched_row = sb._cache['qa_schedules'].insert.call_args[0][0][0]
    assert 'next_run_at' not in sched_row


def test_cs10_dry_run_detects_update():
    """CS-10: dry_run=True + field changed → would_update populated, counts.updated=0."""
    existing = {
        'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001',
        'name': '구 이름', 'description': None, 'expected_summary': None,
        'site_code': 'WWW', 'category': 'AUTH', 'priority': 'P1',
        'runner_type': 'PLAYWRIGHT', 'service_code': 'WWW',
        'area_code': 'AUTH', 'qa_type': 'AVAILABILITY', 'enabled': False,
    }
    sb = _make_sb(existing_items=[existing])
    s = _scenario(name='신규 이름')
    result = sync_catalog(sb, [s], dry_run=True)

    assert result['dry_run'] is True
    assert result['would_update'] == ['P1-TEST-001']
    assert result['counts']['updated'] == 0  # dry_run → no actual update


def test_cs11_empty_input():
    """CS-11: empty scenario list → all zero counts."""
    sb = _make_sb()
    result = sync_catalog(sb, [], dry_run=False)

    assert result['counts'] == {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}
    assert not sb._cache  # no table calls for empty input


def test_cs12_invalid_qa_type():
    """CS-12: invalid qa_type → error reported."""
    sb = _make_sb()
    s = _scenario(qa_type='UNKNOWN_TYPE')
    result = sync_catalog(sb, [s], dry_run=False)

    assert len(result['errors']) == 1
    assert 'qa_type' in result['errors'][0]['reason']


def test_cs13_mixed_valid_invalid_fail_close():
    """CS-13: valid + invalid scenario in same batch → fail-close, zero writes."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item])
    s_valid   = _scenario(scenario_id='P1-TEST-001')
    s_invalid = _scenario(scenario_id='P1-TEST-002', site_code='INVALID')
    result = sync_catalog(sb, [s_valid, s_invalid], dry_run=False)

    assert len(result['errors']) == 1
    assert result['counts']['created'] == 0
    items_mock = sb._cache.get('qa_items')
    assert items_mock is None or not items_mock.insert.called


def test_cs14_duplicate_fail_close_zero_writes():
    """CS-14: duplicate scenario_id → fail-close, no table writes at all."""
    sb = _make_sb(existing_items=[])
    s1 = _scenario(scenario_id='P1-TEST-001')
    s2 = _scenario(scenario_id='P1-TEST-001', name='복사본')
    result = sync_catalog(sb, [s1, s2], dry_run=False)

    assert result['counts']['created'] == 0
    assert result['counts']['updated'] == 0
    # fail-close: no table access beyond error handling
    items_mock = sb._cache.get('qa_items')
    assert items_mock is None or not items_mock.insert.called
    assert items_mock is None or not items_mock.update.called


def test_cs15_no_category_field_uses_area_code():
    """CS-15: scenario without category → valid; area_code used as DB category fallback."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item])
    s = _scenario()  # _scenario() has no category field
    result = sync_catalog(sb, [s], dry_run=False)

    assert result['counts']['created'] == 1
    assert len(result['errors']) == 0
    row = sb._cache['qa_items'].insert.call_args[0][0][0]
    assert row['category'] == 'AUTH'  # area_code used as fallback


def test_cs16_priority_prefix_mismatch():
    """CS-16: scenario_id=P1-... with priority=P2 → validation error."""
    sb = _make_sb()
    s = _scenario(scenario_id='P1-TEST-001', priority='P2')
    result = sync_catalog(sb, [s], dry_run=False)

    assert len(result['errors']) == 1
    assert 'priority prefix mismatch' in result['errors'][0]['reason']
    assert result['counts']['created'] == 0


def test_cs17_schedule_insert_failure_rollback():
    """CS-17: qa_schedules.insert failure → compensating delete of qa_items."""
    new_item = {'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001'}
    sb = _make_sb(existing_items=[], insert_ids=[new_item], schedule_fail=True)
    with pytest.raises(Exception):
        sync_catalog(sb, [_scenario()], dry_run=False)
    # compensating delete must have been called
    assert sb._cache['qa_items'].delete.called


def test_cs18_existing_enabled_not_overwritten():
    """CS-18: update of existing item never patches enabled field."""
    existing = {
        'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001',
        'name': '구 이름', 'description': None, 'expected_summary': None,
        'site_code': 'WWW', 'category': 'AUTH', 'priority': 'P1',
        'runner_type': 'PLAYWRIGHT', 'service_code': 'WWW',
        'area_code': 'AUTH', 'qa_type': 'AVAILABILITY', 'enabled': True,
    }
    sb = _make_sb(existing_items=[existing])
    s = _scenario(name='신규 이름')
    sync_catalog(sb, [s], dry_run=False)

    patch = sb._cache['qa_items'].update.call_args[0][0]
    assert 'enabled' not in patch


def test_cs19_update_does_not_touch_schedules():
    """CS-19: updating existing item leaves qa_schedules untouched."""
    existing = {
        'id': 'item-uuid-1', 'scenario_id': 'P1-TEST-001',
        'name': '구 이름', 'description': None, 'expected_summary': None,
        'site_code': 'WWW', 'category': 'AUTH', 'priority': 'P1',
        'runner_type': 'PLAYWRIGHT', 'service_code': 'WWW',
        'area_code': 'AUTH', 'qa_type': 'AVAILABILITY', 'enabled': False,
    }
    sb = _make_sb(existing_items=[existing])
    s = _scenario(name='신규 이름')
    sync_catalog(sb, [s], dry_run=False)

    sched_mock = sb._cache.get('qa_schedules')
    assert sched_mock is None or not sched_mock.insert.called


# ── auth endpoint tests ───────────────────────────────────────────────────────

def _catalog_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router as qa_router
    app = FastAPI()
    app.include_router(qa_router)
    return TestClient(app, raise_server_exceptions=False)


def test_cs20_missing_secret_returns_403(monkeypatch):
    """CS-20: missing X-Internal-Secret → 403."""
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    client = _catalog_client()
    resp = client.post(
        "/internal/qa/catalog/sync",
        json={"dry_run": True, "scenarios": []},
    )
    assert resp.status_code == 403


def test_cs21_wrong_secret_returns_403(monkeypatch):
    """CS-21: wrong X-Internal-Secret → 403."""
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    client = _catalog_client()
    resp = client.post(
        "/internal/qa/catalog/sync",
        json={"dry_run": True, "scenarios": []},
        headers={"X-Internal-Secret": "wrong"},
    )
    assert resp.status_code == 403


def test_cs22_valid_secret_dry_run_returns_200(monkeypatch):
    """CS-22: valid X-Internal-Secret + dry_run=True + empty scenarios → 200."""
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    client = _catalog_client()
    with mock_patch("routers.internal_qa.get_supabase", return_value=_make_sb()):
        resp = client.post(
            "/internal/qa/catalog/sync",
            json={"dry_run": True, "scenarios": []},
            headers={"X-Internal-Secret": "correct"},
        )
    assert resp.status_code == 200
