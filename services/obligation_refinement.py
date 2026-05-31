"""
services/obligation_refinement.py — Obligation Refinement v2.0.0

변경:
- 반복 그룹 식별 (삭제 아님, 그룹화만)
- Usability Flag 부여 (web/task/doc)
- Internal Family Code 탐지
- 조건 상태 표시 (PRESENT/MISSING)
- 원본 보존 100%
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Set, Tuple

_FAMILY_PATTERN = re.compile(r'\b[A-Z]+_FAMILY\b')

def is_internal_family_code(value: str) -> bool:
    return bool(_FAMILY_PATTERN.search(value or ''))

def _usability(ob: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    law   = (ob.get('law_name') or '').strip()
    art   = (ob.get('article_no') or '').strip()
    title = (ob.get('title') or '').strip()
    what  = (ob.get('what') or '').strip()
    who   = (ob.get('who') or '').strip()
    when  = (ob.get('when') or '').strip()
    how   = (ob.get('how') or '').strip()
    chain = (ob.get('evidence') or {}).get('chain') or []
    cid   = (ob.get('metadata') or {}).get('candidate_id') or ''

    display = title or what or how

    if is_internal_family_code(how):
        reasons.append('INTERNAL_FAMILY_CODE')
    if is_internal_family_code(what):
        reasons.append('INTERNAL_FAMILY_CODE_WHAT')
    if is_internal_family_code(title):
        reasons.append('INTERNAL_FAMILY_CODE_TITLE')

    if not when:
        reasons.append('MISSING_WHEN')
    if not who:
        reasons.append('MISSING_WHO')
    if not chain and not cid:
        reasons.append('MISSING_EVIDENCE')

    has_family = 'INTERNAL_FAMILY_CODE' in reasons

    web_usable  = bool(law and art and display and not has_family)
    task_usable = bool(display and who and when and not has_family)
    doc_usable  = bool(law and art and display and (chain or cid) and not has_family)

    return {
        'web_usable':  web_usable,
        'task_usable': task_usable,
        'doc_usable':  doc_usable,
        'reason_codes': list(dict.fromkeys(reasons)),
    }

def _condition_status(ob: Dict[str, Any]) -> str:
    cond = ob.get('condition') or {}
    if cond.get('code') or cond.get('value') is not None:
        return 'PRESENT'
    return 'MISSING'

def _repeat_key(ob: Dict[str, Any]) -> Tuple:
    cond = ob.get('condition') or {}
    return (
        (ob.get('law_name') or '').strip(),
        (ob.get('article_no') or '').strip(),
        (ob.get('metadata') or {}).get('source_type', ''),
        (ob.get('who') or '').strip(),
        (ob.get('when') or '').strip(),
        (ob.get('what') or '').strip(),
        (ob.get('how') or '').strip(),
        (ob.get('why') or '').strip(),
        (cond.get('code') or '').strip(),
        str(cond.get('value') or ''),
    )

def refine(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not obligations:
        return {
            'obligations': [], 'article_groups': [], 'repeat_groups': [],
            'indexes': {'by_law': {}, 'by_article': {}, 'by_source_type': {}, 'by_usability': {}},
            'quality': {k: 0 for k in ['total','repeat_group_count','repeated_member_count',
                'condition_missing_count','internal_code_count',
                'web_usable_count','task_usable_count','doc_usable_count']},
        }

    # ── 1. usability + condition_status + internal_code 부여 ──
    for ob in obligations:
        ob['usability'] = _usability(ob)
        ob['condition_status'] = _condition_status(ob)
        ob['internal_code_detected'] = is_internal_family_code(ob.get('how','')) \
            or is_internal_family_code(ob.get('what','')) \
            or is_internal_family_code(ob.get('title',''))

    # ── 2. Index: obligation_id → obligation ─────────────────
    index: Dict[str, Dict] = {ob['obligation_id']: ob for ob in obligations if ob.get('obligation_id')}

    # ── 3. Article groups: (law_name, article_no) ────────────
    ag_map: Dict[Tuple, Dict] = {}
    for ob in obligations:
        key = ((ob.get('law_name') or '').strip(), (ob.get('article_no') or '').strip())
        if key not in ag_map:
            ag_map[key] = {
                'group_id': f'{key[0]}|{key[1]}',
                'law_name': key[0], 'article_no': key[1],
                'obligation_ids': [], 'source_types': set(),
                'has_who': False, 'has_when': False, 'has_condition': False,
            }
        g = ag_map[key]
        g['obligation_ids'].append(ob['obligation_id'])
        if ob.get('metadata', {}).get('source_type'): g['source_types'].add(ob['metadata']['source_type'])
        if (ob.get('who') or '').strip(): g['has_who'] = True
        if (ob.get('when') or '').strip(): g['has_when'] = True
        if ob.get('condition_status') == 'PRESENT': g['has_condition'] = True

    article_groups = []
    for g in ag_map.values():
        g['source_types'] = sorted(g['source_types'])
        g['obligation_count'] = len(g['obligation_ids'])
        article_groups.append(g)
    article_groups.sort(key=lambda x: -x['obligation_count'])

    # ── 4. Repeat groups: 동일 키 그룹화 (삭제 없음) ──────────
    rg_map: Dict[Tuple, Dict] = {}
    for ob in obligations:
        rk = _repeat_key(ob)
        if rk not in rg_map:
            rg_map[rk] = {
                'repeat_group_id': f'RG-{len(rg_map):04d}',
                'repeat_key': {
                    'law_name': rk[0], 'article_no': rk[1], 'source_type': rk[2],
                    'who': rk[3], 'when': rk[4], 'what': rk[5],
                    'how': rk[6], 'why': rk[7],
                    'condition_code': rk[8], 'condition_value': rk[9],
                },
                'member_obligation_ids': [],
                'representative_obligation_id': ob['obligation_id'],
                'is_identical_repeat': False,
            }
        rg_map[rk]['member_obligation_ids'].append(ob['obligation_id'])

    repeat_groups = []
    for rg in rg_map.values():
        rg['member_count'] = len(rg['member_obligation_ids'])
        rg['is_identical_repeat'] = rg['member_count'] > 1
        repeat_groups.append(rg)
    repeat_groups.sort(key=lambda x: -x['member_count'])

    # ── 5. Indexes ─────────────────────────────────────────────
    by_law: Dict[str, List[str]] = {}
    by_art: Dict[str, List[str]] = {}
    by_src: Dict[str, List[str]] = {}
    by_usa = {'web_usable': [], 'task_usable': [], 'doc_usable': [],
              'web_unusable': [], 'task_unusable': [], 'doc_unusable': []}

    for ob in obligations:
        oid = ob['obligation_id']
        ln  = ob.get('law_name', '')
        art = ob.get('article_no', '')
        src = (ob.get('metadata') or {}).get('source_type', '')
        usa = ob['usability']

        by_law.setdefault(ln,  []).append(oid)
        by_art.setdefault(art, []).append(oid)
        by_src.setdefault(src, []).append(oid)

        if usa['web_usable']:   by_usa['web_usable'].append(oid)
        else:                   by_usa['web_unusable'].append(oid)
        if usa['task_usable']:  by_usa['task_usable'].append(oid)
        else:                   by_usa['task_unusable'].append(oid)
        if usa['doc_usable']:   by_usa['doc_usable'].append(oid)
        else:                   by_usa['doc_unusable'].append(oid)

    # ── 6. Quality stats ───────────────────────────────────────
    quality = {
        'total':                  len(obligations),
        'repeat_group_count':     sum(1 for rg in repeat_groups if rg['is_identical_repeat']),
        'repeated_member_count':  sum(rg['member_count'] for rg in repeat_groups if rg['is_identical_repeat']),
        'condition_missing_count': sum(1 for ob in obligations if ob['condition_status'] == 'MISSING'),
        'internal_code_count':    sum(1 for ob in obligations if ob['internal_code_detected']),
        'web_usable_count':       len(by_usa['web_usable']),
        'task_usable_count':      len(by_usa['task_usable']),
        'doc_usable_count':       len(by_usa['doc_usable']),
        'unique_in_repeat_groups': sum(1 for rg in repeat_groups if not rg['is_identical_repeat']),
    }

    return {
        'obligations':    obligations,
        'article_groups': article_groups,
        'repeat_groups':  repeat_groups,
        'indexes': {
            'by_law':        by_law,
            'by_article':    by_art,
            'by_source_type': by_src,
            'by_usability':  by_usa,
        },
        'quality': quality,
    }
