from __future__ import annotations
from typing import Any, Dict, List

COMPLETENESS_FIELDS = ['law_name','article_no','what','who','when','how','why']

def _completeness(ob):
    score = sum(1 for f in COMPLETENESS_FIELDS if (ob.get(f) or '').strip())
    return round(score / len(COMPLETENESS_FIELDS) * 100)

def build_obligation(candidate):
    what = (candidate.get('what') or '').strip()
    law_name = (candidate.get('law_name') or '').strip()
    article_no = (candidate.get('article_no') or '').strip()
    if what: title = what
    elif law_name and article_no: title = f'{law_name} {article_no}'
    elif law_name: title = law_name
    else: title = ''
    ob = {
        'obligation_id': (candidate.get('candidate_id') or '').strip(),
        'title': title,
        'who':   (candidate.get('who')   or '').strip(),
        'when':  (candidate.get('when')  or '').strip(),
        'where': (candidate.get('where') or '').strip(),
        'what':  what,
        'how':   (candidate.get('how')   or '').strip(),
        'why':   (candidate.get('why')   or '').strip(),
        'law_name':   law_name,
        'article_no': article_no,
        'condition': {
            'exists': bool(candidate.get('condition_exists')),
            'code':   (candidate.get('condition_code')  or '').strip(),
            'value':  candidate.get('condition_value'),
        },
        'evidence': {'chain': candidate.get('evidence_chain') or []},
        'metadata': {
            'source_type':   (candidate.get('source_type')   or '').strip(),
            'source_bucket': (candidate.get('source_bucket') or '').strip(),
            'candidate_id':  (candidate.get('candidate_id')  or '').strip(),
        },
        'schedule': {
            'schedule_type': (candidate.get('schedule_type') or '').strip(),
            'cycle_unit':    (candidate.get('cycle_unit')    or '').strip(),
            'cycle_int':     candidate.get('cycle_int') or 0,
            'due_days':      candidate.get('due_days')  or 0,
        },
        'executor': {
            'type':          (candidate.get('executor_type')  or '').strip(),
            'qualification': (candidate.get('qualification')  or '').strip(),
        },
        'submission': {
            'org':    (candidate.get('submit_org')    or '').strip(),
            'method': (candidate.get('submit_method') or '').strip(),
        },
        'penalty': {'summary': (candidate.get('penalty_summary') or '').strip()},
        'form': {
            'name':       (candidate.get('form_name')   or '').strip(),
            'url':        (candidate.get('form_url')    or '').strip(),
            'system_url': (candidate.get('system_url')  or '').strip(),
        },
        'status': {'completeness': 0},
    }
    ob['status']['completeness'] = _completeness(ob)
    return ob

def build_obligations(candidates):
    return [build_obligation(c) for c in candidates]
