"""Runtime-only tiers for the TAI search dictionary — Kiwi TOKEN + pg_trgm.

MASTER-WO-TAI-SEARCH-DICT-001 §T4. Kept OUT of search_core to preserve the
"pure stdlib, no external deps" contract of the deterministic core. This module
is imported only when the service layer opts in.

Tier 4 (TOKEN):  match_type='TOKEN'. Kiwi analyzes the query and produces noun
                 tokens (NNG/NNP/SL). We match against APPROVED subject tokens
                 (noun-analysis of each subject's approved surface terms).
                 Score = jaccard-like overlap, expressed in MATCH_SCORE['TOKEN'].
                 Deterministic: same projection + same Kiwi model -> same result.

Tier 6 (TRIGRAM): match_type='TRIGRAM'. Uses pg_trgm `similarity()` on a scratch
                 Postgres table of APPROVED surface forms. NEVER writes to
                 leg-prod (WO §2 guardrail). Returned candidates carry raw
                 similarity so the ranker keeps EXACT/NORMALIZED_EXACT above.
"""
from __future__ import annotations

import os
import sys
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import normalize as N  # noqa: E402

# Only Korean nouns / latin symbols carry search signal for our corpus
KIWI_NOUN_TAGS = {"NNG", "NNP", "SL"}


class TokenTier:
    """Tier 4 — Kiwi-noun overlap matcher."""

    def __init__(self, projection: dict, kiwi=None, user_dict_path: str | None = None):
        from kiwipiepy import Kiwi
        self.kiwi = kiwi or Kiwi()
        if user_dict_path:
            self.kiwi.load_user_dictionary(user_dict_path)
        # subject_key_full -> set of tokens (from APPROVED surfaces)
        self._subject_tokens: dict[str, set[str]] = {}
        self._subject: dict[str, dict] = {}
        for s in projection.get("subjects", []):
            skf = f"{s['subject_type']}::{s['subject_key']}"
            self._subject[skf] = s
            toks: set[str] = set()
            for t in s["terms"]:
                if t.get("non_production"):
                    continue
                toks |= self._noun_tokens(t["term_normalized"])
            if toks:
                self._subject_tokens[skf] = toks

    def _noun_tokens(self, s: str) -> set[str]:
        r = self.kiwi.analyze(s, top_n=1)
        if not r:
            return set()
        toks, _score = r[0]
        return {t.form for t in toks if t.tag in KIWI_NOUN_TAGS}

    def candidates(self, query: str, min_overlap: int = 1):
        qt = self._noun_tokens(query)
        if not qt:
            return []
        # rank by (overlap desc, subject_key asc) — deterministic
        hits = []
        for skf, toks in self._subject_tokens.items():
            overlap = len(qt & toks)
            if overlap >= min_overlap:
                # jaccard(0..1) as an explainability signal
                jac = overlap / len(qt | toks) if (qt or toks) else 0.0
                hits.append((overlap, jac, skf))
        hits.sort(key=lambda x: (-x[0], -x[1], x[2]))
        out = []
        for overlap, jac, skf in hits:
            s = self._subject[skf]
            out.append({
                "subject_type": s["subject_type"],
                "subject_key": s["subject_key"],
                "matched_term": " ".join(sorted(qt)),
                "match_type": "TOKEN",
                "overlap": overlap,
                "jaccard": jac,
            })
        return out


class TrigramTier:
    """Tier 6 — pg_trgm similarity() over APPROVED surfaces.

    Loads projection surfaces into a scratch table (created on first use).
    Reads the Postgres DSN from env TAI_SEARCH_SCRATCH_DSN. WO §2 guardrail:
    this DSN must NEVER point at leg-prod; the loader refuses if the host looks
    like a Supabase project ref matching the leg-prod ID.
    """
    _LEGPROD_REF = "wrfcedzgdrfupenzqhur"

    def __init__(self, projection: dict, dsn: str | None = None):
        import psycopg
        self._psycopg = psycopg
        dsn = dsn or os.environ["TAI_SEARCH_SCRATCH_DSN"]
        if self._LEGPROD_REF in dsn:
            raise RuntimeError(
                "refusing to use leg-prod DSN for pg_trgm scratch table"
            )
        self.dsn = dsn
        self._subject_by_surface: dict[str, dict] = {}
        self._prepare(projection)

    def _prepare(self, projection: dict) -> None:
        rows = []
        for s in projection.get("subjects", []):
            skf = f"{s['subject_type']}::{s['subject_key']}"
            for t in s["terms"]:
                if t.get("non_production"):
                    continue
                surface = t["term_normalized"]
                rows.append((surface, s["subject_type"], s["subject_key"]))
                self._subject_by_surface[surface] = {
                    "subject_type": s["subject_type"],
                    "subject_key": s["subject_key"],
                }
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tai_search_surfaces_scratch (
                    surface       TEXT PRIMARY KEY,
                    subject_type  TEXT NOT NULL,
                    subject_key   TEXT NOT NULL
                )
            """)
            cur.execute("TRUNCATE tai_search_surfaces_scratch")
            cur.executemany(
                "INSERT INTO tai_search_surfaces_scratch(surface, subject_type, "
                "subject_key) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                rows,
            )
            cur.execute("""
                CREATE INDEX IF NOT EXISTS tai_search_surface_trgm
                ON tai_search_surfaces_scratch USING gin (surface gin_trgm_ops)
            """)
            conn.commit()
        self._nrows = len(rows)

    def candidates(self, query: str, limit: int = 5, min_sim: float = 0.3):
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT surface, subject_type, subject_key, "
                "similarity(surface, %s) AS sim "
                "FROM tai_search_surfaces_scratch "
                "WHERE surface %% %s "
                "ORDER BY sim DESC, surface ASC LIMIT %s",
                (query, query, limit),
            )
            rows = cur.fetchall()
        out = []
        for surface, subject_type, subject_key, sim in rows:
            if float(sim) < min_sim:
                continue
            out.append({
                "subject_type": subject_type,
                "subject_key": subject_key,
                "matched_term": surface,
                "match_type": "TRIGRAM",
                "similarity": float(sim),
            })
        return out


def build_from_projection_path(
    projection_path: str,
    kiwi_user_dict: str | None = None,
    scratch_dsn: str | None = None,
) -> tuple[TokenTier | None, TrigramTier | None]:
    import json
    with open(projection_path, encoding="utf-8") as f:
        proj = json.load(f)
    tok = TokenTier(proj, user_dict_path=kiwi_user_dict)
    trg = None
    if scratch_dsn:
        trg = TrigramTier(proj, dsn=scratch_dsn)
    return tok, trg
