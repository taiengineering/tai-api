"""QA Catalog Sync Service — WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP C.

POST /internal/qa/catalog/sync 로직.

dry_run=True  → DB 변경 없음. would_create/would_update 분류 + 실제 counts 반환.
dry_run=False → qa_items INSERT (새 항목) + UPDATE (변경 필드).
               새 항목: enabled=false, qa_schedules(MANUAL/disabled/next_run_at NULL).

DELETE 없음 — 제거된 scenario는 DB 유지.
Fail-close: 어떤 입력이라도 validation 오류 → DB 쓰기 없음.
idempotency: 동일 manifest 재실행 → created=0, updated=0.
Schedule rollback: qa_schedules INSERT 실패 → 방금 INSERT된 qa_items 보상 DELETE.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from services.time import now_kst, serialize_external_utc

log = logging.getLogger("qa_catalog_sync")

_VALID_SITE_CODES    = frozenset({'WWW', 'SAFE', 'API', 'ADMIN', 'MKT', 'WORKER', 'EXTERNAL'})
_VALID_PRIORITIES    = frozenset({'P0', 'P1', 'P2', 'P3'})
_VALID_RUNNER_TYPES  = frozenset({'PLAYWRIGHT', 'API', 'HEALTH'})
_VALID_SERVICE_CODES = frozenset({'WWW', 'SAAS', 'ADMIN', 'WORKER'})
_VALID_QA_TYPES      = frozenset({
    'AVAILABILITY', 'FUNCTIONAL', 'INTEGRATION', 'E2E', 'API',
    'PERFORMANCE', 'SECURITY', 'DATA', 'ACCESSIBILITY', 'VISUAL',
})
_AREA_CODE_RE       = re.compile(r'^[A-Z][A-Z0-9_]*$')
# canonical: P0-API-QA-001, P1-WWW-LANDING-AVL-001, …
_SCENARIO_ID_RE     = re.compile(r'^P[0-3](?:-[A-Z0-9]+)+$')
_PRIORITY_PREFIX_RE = re.compile(r'^(P\d)-')

# category omitted: LEGACY field, not managed by sync
_MUTABLE_FIELDS = frozenset({
    'name', 'description', 'expected_summary',
    'site_code', 'priority', 'runner_type',
    'service_code', 'area_code', 'qa_type',
})


def _validate(s: Dict[str, Any]) -> Optional[str]:
    sid = s.get('scenario_id', '')
    if not sid:
        return 'scenario_id is required'
    if not str(s.get('name', '')).strip():
        return f'{sid}: name is required'
    if not _SCENARIO_ID_RE.fullmatch(sid):
        return f'{sid}: invalid scenario_id format'
    if s.get('site_code') not in _VALID_SITE_CODES:
        return f'{sid}: invalid site_code={s.get("site_code")!r}'
    priority = s.get('priority')
    if priority not in _VALID_PRIORITIES:
        return f'{sid}: invalid priority={priority!r}'
    m = _PRIORITY_PREFIX_RE.match(sid)
    if m and m.group(1) != priority:
        return (
            f'{sid}: priority prefix mismatch: '
            f'id implies {m.group(1)!r} but priority={priority!r}'
        )
    if s.get('runner_type') not in _VALID_RUNNER_TYPES:
        return f'{sid}: invalid runner_type={s.get("runner_type")!r}'
    if s.get('service_code') not in _VALID_SERVICE_CODES:
        return f'{sid}: invalid service_code={s.get("service_code")!r}'
    if not _AREA_CODE_RE.match(s.get('area_code') or ''):
        return f'{sid}: invalid area_code={s.get("area_code")!r}'
    if s.get('qa_type') not in _VALID_QA_TYPES:
        return f'{sid}: invalid qa_type={s.get("qa_type")!r}'
    return None


def _empty_result(dry_run: bool, total: int, errors: List[Dict[str, str]]) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        'dry_run':            dry_run,
        'total_input':        total,
        'existing_unchanged': [],
        'errors':             errors,
    }
    if dry_run:
        return {
            **base,
            'would_create': [],
            'would_update': [],
            'counts': {'would_create': 0, 'would_update': 0, 'unchanged': 0, 'errors': len(errors)},
        }
    return {
        **base,
        'created':          [],
        'existing_updated': [],
        'counts': {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': len(errors)},
    }


def sync_catalog(
    supabase,
    scenarios: List[Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, Any]:
    """Sync scenarios into qa_items.

    dry_run=True returns {dry_run, total_input, would_create, would_update,
                          existing_unchanged, errors,
                          counts: {would_create, would_update, unchanged, errors}}.
    dry_run=False returns {dry_run, total_input, created, existing_updated,
                           existing_unchanged, errors,
                           counts: {created, updated, unchanged, errors}}.
    """
    errors: List[Dict[str, str]] = []
    valid: List[Dict[str, Any]] = []
    seen: set = set()

    for s in scenarios:
        sid = s.get('scenario_id', '')
        if sid in seen:
            errors.append({'scenario_id': sid, 'reason': 'duplicate scenario_id in input'})
            continue
        seen.add(sid)
        err = _validate(s)
        if err:
            errors.append({'scenario_id': sid, 'reason': err})
        else:
            valid.append(s)

    # Fail-close: any error → zero DB writes
    if errors:
        return _empty_result(dry_run, len(scenarios), errors)

    if not valid:
        return _empty_result(dry_run, len(scenarios), [])

    valid_ids = [s['scenario_id'] for s in valid]
    existing_res = (
        supabase.table('qa_items')
        .select(
            'id, scenario_id, name, description, expected_summary, '
            'site_code, category, priority, runner_type, '
            'service_code, area_code, qa_type, enabled'
        )
        .in_('scenario_id', valid_ids)
        .execute()
    )
    existing_map: Dict[str, Dict[str, Any]] = {
        row['scenario_id']: row for row in (existing_res.data or [])
    }

    now_iso = serialize_external_utc(now_kst())

    unchanged: List[str] = []
    to_update: List[Tuple[str, str, Dict[str, Any]]] = []  # (item_id, scenario_id, patch)
    to_create: List[Dict[str, Any]] = []

    for s in valid:
        sid = s['scenario_id']
        if sid in existing_map:
            existing = existing_map[sid]
            patch = {
                f: s[f]
                for f in _MUTABLE_FIELDS
                if f in s and s.get(f) is not None and s.get(f) != existing.get(f)
            }
            if patch:
                to_update.append((existing['id'], sid, patch))
            else:
                unchanged.append(sid)
        else:
            to_create.append(s)

    would_create_ids = [s['scenario_id'] for s in to_create]
    would_update_ids = [scenario_id for _, scenario_id, _ in to_update]

    if dry_run:
        return {
            'dry_run':            True,
            'total_input':        len(scenarios),
            'existing_unchanged': unchanged,
            'would_create':       would_create_ids,
            'would_update':       would_update_ids,
            'errors':             [],
            'counts':             {
                'would_create': len(would_create_ids),
                'would_update': len(would_update_ids),
                'unchanged':    len(unchanged),
                'errors':       0,
            },
        }

    # INSERT new items
    if to_create:
        insert_rows = [
            {
                'scenario_id':      s['scenario_id'],
                'name':             s['name'],
                'description':      s.get('description'),
                'expected_summary': s.get('expected_summary'),
                'site_code':        s['site_code'],
                # category is LEGACY NOT NULL; use input value or fall back to area_code
                'category':         s.get('category') or s['area_code'],
                'priority':         s['priority'],
                'runner_type':      s['runner_type'],
                'service_code':     s['service_code'],
                'area_code':        s['area_code'],
                'qa_type':          s['qa_type'],
                'enabled':          False,
                'created_at':       now_iso,
                'updated_at':       now_iso,
            }
            for s in to_create
        ]
        insert_res = supabase.table('qa_items').insert(insert_rows).execute()
        inserted = insert_res.data or []

        if len(inserted) != len(to_create):
            # Partial or zero insert: compensate what was written
            if inserted:
                inserted_ids = [row['id'] for row in inserted]
                try:
                    supabase.table('qa_items').delete().in_('id', inserted_ids).execute()
                    raise RuntimeError(
                        f'item insert count mismatch ({len(inserted)}/{len(to_create)}); '
                        f'inserted items rolled back'
                    )
                except RuntimeError:
                    raise
                except Exception as del_e:
                    log.error('[qa_catalog_sync] rollback delete failed: %s', del_e)
                    raise RuntimeError(
                        f'item insert count mismatch ({len(inserted)}/{len(to_create)}) '
                        f'AND rollback failed; reconciliation required'
                    ) from del_e
            raise RuntimeError(
                f'item insert count mismatch: expected {len(to_create)}, got {len(inserted)}'
            )

        if inserted:
            sched_rows = [
                {
                    'qa_item_id':     row['id'],
                    'enabled':        False,
                    'frequency_type': 'MANUAL',
                    'created_at':     now_iso,
                    'updated_at':     now_iso,
                }
                for row in inserted
            ]
            try:
                supabase.table('qa_schedules').insert(sched_rows).execute()
                log.info('[qa_catalog_sync] created %d items + schedules', len(inserted))
            except Exception as e:
                inserted_ids = [row['id'] for row in inserted]
                rollback_ok = False
                try:
                    supabase.table('qa_items').delete().in_('id', inserted_ids).execute()
                    rollback_ok = True
                except Exception as del_e:
                    log.error('[qa_catalog_sync] rollback delete failed: %s', del_e)
                if rollback_ok:
                    raise RuntimeError(
                        f'schedule insert failed; created items rolled back: {e}'
                    ) from e
                raise RuntimeError(
                    f'schedule insert failed AND rollback failed; reconciliation required'
                ) from e

    # UPDATE changed items
    for item_id, _, patch in to_update:
        patch['updated_at'] = now_iso
        supabase.table('qa_items').update(patch).eq('id', item_id).execute()
    if to_update:
        log.info('[qa_catalog_sync] updated %d items', len(to_update))

    return {
        'dry_run':            False,
        'total_input':        len(scenarios),
        'existing_unchanged': unchanged,
        'existing_updated':   would_update_ids,
        'created':            would_create_ids,
        'errors':             [],
        'counts':             {
            'created':   len(to_create),
            'updated':   len(to_update),
            'unchanged': len(unchanged),
            'errors':    0,
        },
    }
