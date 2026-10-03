"""QA Catalog Sync Service — WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP C.

POST /internal/qa/catalog/sync 로직.

dry_run=True  → DB 변경 없음. would_create/existing_updated 분류만 반환.
dry_run=False → qa_items INSERT (새 항목) + UPDATE (변경 필드).
               새 항목: enabled=false, qa_schedules(MANUAL/disabled/next_run_at NULL).

DELETE 없음 — 제거된 scenario는 DB 유지.
idempotency: 동일 manifest 재실행 → created=0, updated=0.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from services.time import now_kst, serialize_external_utc

log = logging.getLogger("qa_catalog_sync")

_VALID_SITE_CODES   = frozenset({'WWW', 'SAFE', 'API', 'ADMIN', 'MKT', 'WORKER', 'EXTERNAL'})
_VALID_PRIORITIES   = frozenset({'P0', 'P1', 'P2', 'P3'})
_VALID_RUNNER_TYPES = frozenset({'PLAYWRIGHT', 'API', 'HEALTH'})
_VALID_SERVICE_CODES = frozenset({'WWW', 'SAAS', 'ADMIN', 'WORKER'})
_VALID_QA_TYPES     = frozenset({
    'AVAILABILITY', 'FUNCTIONAL', 'INTEGRATION', 'E2E', 'API',
    'PERFORMANCE', 'SECURITY', 'DATA', 'ACCESSIBILITY', 'VISUAL',
})
_AREA_CODE_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')

_MUTABLE_FIELDS = frozenset({
    'name', 'description', 'expected_summary',
    'site_code', 'category', 'priority', 'runner_type',
    'service_code', 'area_code', 'qa_type',
})


def _validate(s: Dict[str, Any]) -> Optional[str]:
    sid = s.get('scenario_id', '')
    if not sid:
        return 'scenario_id is required'
    if not str(s.get('name', '')).strip():
        return f'{sid}: name is required'
    if not str(s.get('category', '')).strip():
        return f'{sid}: category is required'
    if s.get('site_code') not in _VALID_SITE_CODES:
        return f'{sid}: invalid site_code={s.get("site_code")!r}'
    if s.get('priority') not in _VALID_PRIORITIES:
        return f'{sid}: invalid priority={s.get("priority")!r}'
    if s.get('runner_type') not in _VALID_RUNNER_TYPES:
        return f'{sid}: invalid runner_type={s.get("runner_type")!r}'
    if s.get('service_code') not in _VALID_SERVICE_CODES:
        return f'{sid}: invalid service_code={s.get("service_code")!r}'
    if not _AREA_CODE_RE.match(s.get('area_code') or ''):
        return f'{sid}: invalid area_code={s.get("area_code")!r}'
    if s.get('qa_type') not in _VALID_QA_TYPES:
        return f'{sid}: invalid qa_type={s.get("qa_type")!r}'
    return None


def sync_catalog(
    supabase,
    scenarios: List[Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, Any]:
    """Sync scenarios into qa_items.

    Returns {
        dry_run, total_input,
        existing_unchanged: [scenario_id, ...],
        existing_updated:   [scenario_id, ...],
        created:            [scenario_id, ...],
        errors:             [{scenario_id, reason}, ...],
        counts: {created, updated, unchanged, errors},
    }
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

    if not valid:
        return {
            'dry_run':           dry_run,
            'total_input':       len(scenarios),
            'existing_unchanged': [],
            'existing_updated':  [],
            'created':           [],
            'errors':            errors,
            'counts':            {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': len(errors)},
        }

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

    created_ids = [s['scenario_id'] for s in to_create]
    updated_ids = [scenario_id for _, scenario_id, _ in to_update]

    if dry_run:
        return {
            'dry_run':           True,
            'total_input':       len(scenarios),
            'existing_unchanged': unchanged,
            'existing_updated':  updated_ids,
            'created':           created_ids,
            'errors':            errors,
            'counts':            {'created': 0, 'updated': 0, 'unchanged': len(unchanged), 'errors': len(errors)},
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
                'category':         s['category'],
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
            supabase.table('qa_schedules').insert(sched_rows).execute()
            log.info('[qa_catalog_sync] created %d items + schedules', len(inserted))

    # UPDATE changed items
    for item_id, _, patch in to_update:
        patch['updated_at'] = now_iso
        supabase.table('qa_items').update(patch).eq('id', item_id).execute()
    if to_update:
        log.info('[qa_catalog_sync] updated %d items', len(to_update))

    return {
        'dry_run':           False,
        'total_input':       len(scenarios),
        'existing_unchanged': unchanged,
        'existing_updated':  updated_ids,
        'created':           created_ids,
        'errors':            errors,
        'counts':            {'created': len(to_create), 'updated': len(to_update), 'unchanged': len(unchanged), 'errors': len(errors)},
    }
