"""TAI Search Dictionary — deterministic lexical search core.

MASTER-WO-TAI-SEARCH-DICT-001 §49-63. This is the runtime-independent core:
it operates purely on the compiled projection (TAI_SEARCH_RUNTIME_PROJECTION),
with the SAME normalization module used at build time. No external LLM, no
network (WO §95: runtime external LLM calls = 0).

Tiers implemented here (deterministic, explainable):
  T1 EXACT              term_normalized == normalized(query)
  T2 NORMALIZED_EXACT   term_compact == compact(query)  (spacing/punct-insensitive)
  T3 ALIAS/SYNONYM      APPROVED expansion edge from query.compact -> subject
Tier 4 (Kiwi token) and Tier 6 (pg_trgm) are injected by the service layer at
runtime; the core exposes a hook but never fabricates their results.

Ranking order (WO §63): EXACT > NORMALIZED_EXACT > ABBREVIATION/ALIAS > SYNONYM.
Every result carries match_type + matched_term (WO §62 explainability).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import normalize as N  # noqa: E402

MATCH_SCORE = {
    "EXACT": 100,
    "NORMALIZED_EXACT": 90,
    "PUNCTUATION": 88,
    "ABBREVIATION_OF": 80,
    "SPACING_VARIANT_OF": 78,
    "PUNCTUATION_VARIANT_OF": 76,
    "SPELLING_VARIANT_OF": 74,
    "ENGLISH_OF": 70,
    "EXACT_ALIAS": 68,
    "SYNONYM_OF": 60,
    "TOKEN": 40,
    "TRIGRAM": 20,
}


class SearchEngine:
    def __init__(self, projection: dict):
        self.snapshot = projection.get("snapshot_id")
        self.subjects = projection.get("subjects", [])
        self.expansions = projection.get("expansions", [])
        # indexes (only APPROVED, production terms)
        self._by_norm = {}     # term_normalized -> set(subject_key_full)
        self._by_compact = {}  # term_compact -> set(subject_key_full)
        self._by_nopunct = {}  # term_no_punctuation -> set(subject_key_full)
        self._subject = {}     # subject_key_full -> subject
        for s in self.subjects:
            skf = f"{s['subject_type']}::{s['subject_key']}"
            self._subject[skf] = s
            for t in s["terms"]:
                if t.get("non_production"):
                    continue  # PROPOSED not used in production tiers (WO §52)
                self._by_norm.setdefault(t["term_normalized"], set()).add(skf)
                self._by_compact.setdefault(t["term_compact"], set()).add(skf)
                npc = t.get("term_no_punctuation")
                if npc:
                    self._by_nopunct.setdefault(npc, set()).add(skf)
        self._expand = {}      # from_compact -> [(subject_key_full, relation_type)]
        self._expand_np = {}   # from_nopunct -> [(subject_key_full, relation_type)]
        for e in self.expansions:
            self._expand.setdefault(e["from_compact"], []).append(
                (e["to_subject"], e["relation_type"]))
            npf = e.get("from_nopunct")
            if npf:
                self._expand_np.setdefault(npf, []).append(
                    (e["to_subject"], e["relation_type"]))

    def _display(self, skf: str) -> str:
        s = self._subject.get(skf, {})
        return s.get("subject_key", skf)

    def search(self, q: str, limit: int = 10, subject_type: str | None = None):
        qn = N.normalize_basic(q)
        qc = N.compact(q)
        qp = N.no_punctuation(q)
        hits = {}  # (subject_key_full) -> best (score, match_type, matched_term)

        def offer(skf, score, mtype, matched):
            if subject_type and self._subject.get(skf, {}).get("subject_type") != subject_type:
                return
            cur = hits.get(skf)
            if cur is None or score > cur[0]:
                hits[skf] = (score, mtype, matched)

        # T1 exact
        for skf in self._by_norm.get(qn, ()):  # normalized exact
            offer(skf, MATCH_SCORE["EXACT"], "EXACT", qn)
        # T2 normalized/compact exact
        for skf in self._by_compact.get(qc, ()):
            offer(skf, MATCH_SCORE["NORMALIZED_EXACT"], "NORMALIZED_EXACT", qc)
        # T2b punctuation-insensitive exact (KR law-name separators)
        for skf in self._by_nopunct.get(qp, ()):
            offer(skf, MATCH_SCORE["PUNCTUATION"], "PUNCTUATION", qp)
        # T3 approved alias/synonym expansion (compact, then punct-insensitive)
        for (skf, rtype) in self._expand.get(qc, ()):
            offer(skf, MATCH_SCORE.get(rtype, 50), rtype, qc)
        for (skf, rtype) in self._expand_np.get(qp, ()):
            offer(skf, MATCH_SCORE.get(rtype, 50), rtype, qp)

        items = []
        for skf, (score, mtype, matched) in hits.items():
            s = self._subject[skf]
            items.append({
                "subject_type": s["subject_type"],
                "subject_key": s["subject_key"],
                "display_name": self._display(skf),
                "matched_term": matched,
                "match_type": mtype,
                "score": score,
            })
        # deterministic ranking: score desc, then subject_key asc
        items.sort(key=lambda x: (-x["score"], x["subject_key"]))
        return {
            "query": q,
            "normalized_query": qn,
            "compact_query": qc,
            "snapshot": self.snapshot,
            "items": items[:limit],
        }


def load(path: str) -> SearchEngine:
    with open(path, "r", encoding="utf-8") as f:
        return SearchEngine(json.load(f))
