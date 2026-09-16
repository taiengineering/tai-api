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
        # WO-2 R1/R2: also index a "compact" form of each subject (subject_key +
        # each APPROVED surface with whitespace stripped). Used for the ordered-
        # noun-concat substring boost — this rescues cases where Kiwi bundles a
        # bare compound differently than its spaced/inflected form (e.g.,
        # "근로기준법" → {기준법, 근로} but "근로기준법을" → {근로, 기준, 법}).
        self._subject_compacts: dict[str, set[str]] = {}
        for s in projection.get("subjects", []):
            skf = f"{s['subject_type']}::{s['subject_key']}"
            self._subject[skf] = s
            toks: set[str] = set()
            compacts: set[str] = set()
            compacts.add(s["subject_key"].replace(" ", ""))
            for t in s["terms"]:
                if t.get("non_production"):
                    continue
                toks |= self._noun_tokens(t["term_normalized"])
                compacts.add(t["term_compact"])
                np = t.get("term_no_punctuation")
                if np:
                    compacts.add(np)
            if toks:
                self._subject_tokens[skf] = toks
            self._subject_compacts[skf] = {c for c in compacts if c}

    def _noun_tokens(self, s: str) -> set[str]:
        r = self.kiwi.analyze(s, top_n=1)
        if not r:
            return set()
        toks, _score = r[0]
        return {t.form for t in toks if t.tag in KIWI_NOUN_TAGS}

    def _noun_concat(self, s: str) -> str:
        """Concatenate noun tokens in analysis order (particles stripped)."""
        r = self.kiwi.analyze(s, top_n=1)
        if not r:
            return ""
        toks, _score = r[0]
        return "".join(t.form for t in toks if t.tag in KIWI_NOUN_TAGS)

    def candidates(self, query: str, min_overlap: int = 1):
        qt = self._noun_tokens(query)
        if not qt:
            return []
        qc = self._noun_concat(query)  # e.g., "근로기준법을" -> "근로기준법"
        n_q = len(qt)
        # rank by (score desc, subject_key asc) — deterministic. Score = overlap
        # + bonus if qc is a substring of, or equal to, any subject compact.
        hits = []
        for skf, toks in self._subject_tokens.items():
            overlap = len(qt & toks)
            substr_bonus = 0.0
            equal_compact = False
            substr_shorter_len = 0  # length of shortest compact that matched
            if qc:
                for c in self._subject_compacts.get(skf, ()):
                    if qc == c:
                        # Equal-compact match is a near-canonical signal; must
                        # dominate mere overlap counts within the TOKEN tier so
                        # e.g. `근로기준법을` (qc=`근로기준법`) resolves to
                        # `근로기준법` not `근로기준법 시행규칙`.
                        substr_bonus = 10.0
                        equal_compact = True
                        break
                    if qc in c or c in qc:
                        # Length-ratio guard: reject tiny-fragment substring
                        # coincidences (e.g., subject `법` inside query
                        # `화학물리법` → 1/5=20%). TOKEN tier is for
                        # morphology/compound, not general fuzzy — leave that
                        # to TRIGRAM. Require at least 40% length ratio.
                        short, long = (c, qc) if len(c) < len(qc) else (qc, c)
                        if len(short) / max(len(long), 1) >= 0.40:
                            substr_bonus = max(substr_bonus, 2.0)
                            if substr_shorter_len == 0 or len(short) > substr_shorter_len:
                                substr_shorter_len = len(short)
            score = overlap + substr_bonus
            coverage = overlap / n_q
            skey = self._subject[skf]["subject_key"]
            # -- Precision gates (WO-2 verification follow-up) --
            #
            # G1: Require ONE of:
            #   - actual noun-overlap >= 1
            #   - equal_compact (query strips to exactly this subject; needed
            #     for cases where Kiwi tokenizes bare `수도법` as {수도법}
            #     but `수도법을` as {수도, 법} — overlap=0 with subject)
            #   - substr_bonus from a subject compact of length >= 2 (rescues
            #     MORPHOLOGY like "공고이"→공고 where Kiwi bundles the query
            #     as a single unknown NNG but the subject compact is a real
            #     prefix). The 2-char floor blocks "없는법령명입니다" (noun
            #     "법령") from leaking to subject `법` (1 char).
            if (overlap < 1
                    and not equal_compact
                    and substr_shorter_len < 2):
                continue
            # G2: Strong-signal requirement. Emit only if one of:
            #   (a) equal_compact — the query strips to exactly this subject
            #   (b) overlap >= 2 AND coverage >= 0.60 — meaningful multi hit
            #       (rejects "건설기관계리법" 4-noun overlap-2 on
            #       `건설기술 진흥법` = 50% coverage → let TRIGRAM catch
            #       the real 건설기계관리법)
            #   (c) overlap == 1 AND coverage == 1.0 — query IS the noun
            #       (e.g., "감전을" -> 감전)
            #   (d) overlap == 1 AND substr_bonus > 0 — compound + suffix or
            #       compound + verb phrase (e.g., "국소배기장치 점검",
            #       "국소배기장치 안전관리"). The length-ratio guard on
            #       substr_bonus already excludes short-subject noise like
            #       "화학물리법"→`법` (25% ratio → no bonus → no rule d).
            strong = (
                equal_compact
                or (overlap >= 2 and coverage >= 0.60)
                or (overlap == 1 and coverage >= 1.0)
                or (overlap == 1 and substr_bonus > 0)
                or (overlap == 0 and substr_bonus > 0 and substr_shorter_len >= 2)
            )
            if not strong:
                continue
            # G3 removed (WO-2 verification follow-up): the intent was to
            # protect short subjects (`법`, `규칙`, `고시`) from noise,
            # but G1 (overlap>=1 or equal_compact) + G2 (strong signal
            # requirement) already cover the leak paths without also
            # rejecting legitimate inflected queries like "고시을"→고시.

            if score >= min_overlap:
                jac = overlap / len(qt | toks) if (qt or toks) else 0.0
                hits.append((score, overlap, jac, skf))
        hits.sort(key=lambda x: (-x[0], -x[2], x[3]))
        out = []
        for score, overlap, jac, skf in hits:
            s = self._subject[skf]
            out.append({
                "subject_type": s["subject_type"],
                "subject_key": s["subject_key"],
                "matched_term": " ".join(sorted(qt)),
                "match_type": "TOKEN",
                "overlap": overlap,
                "jaccard": jac,
                "score": score,
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

    # Tuning (WO-2 R2): widen indexed surfaces (normalized + compact + no_punctuation)
    # so a query with spacing/punctuation differences can still hit; lower per-query
    # threshold so short-Korean typos (2-3 char words) survive; keep post-filter as a
    # relevance floor so noise doesn't outrank real matches at rerank time.
    DEFAULT_MIN_SIM = 0.15
    PG_TRGM_THRESHOLD = 0.10

    def _prepare(self, projection: dict) -> None:
        rows = []
        for s in projection.get("subjects", []):
            skf = f"{s['subject_type']}::{s['subject_key']}"
            for t in s["terms"]:
                if t.get("non_production"):
                    continue
                # Include all 3 surface forms; dedup happens at PK. Same subject may
                # thus contribute up to 3 rows -> more forgiving trigram recall.
                for surface in (t["term_normalized"], t["term_compact"],
                                t.get("term_no_punctuation")):
                    if not surface:
                        continue
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

    def candidates(self, query: str, limit: int = 5, min_sim: float | None = None):
        if min_sim is None:
            min_sim = self.DEFAULT_MIN_SIM
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            # Lower pg_trgm threshold for this session so `%` returns more candidates;
            # then we rank by similarity DESC and post-filter with min_sim. `SET` does
            # not accept placeholders → use set_config().
            cur.execute("SELECT set_config('pg_trgm.similarity_threshold', %s, false)",
                        (str(self.PG_TRGM_THRESHOLD),))
            cur.execute(
                "SELECT surface, subject_type, subject_key, "
                "similarity(surface, %s) AS sim "
                "FROM tai_search_surfaces_scratch "
                "WHERE surface %% %s "
                "ORDER BY sim DESC, surface ASC LIMIT %s",
                (query, query, limit * 3),  # oversample to survive dedup
            )
            rows = cur.fetchall()
        # dedup by subject: keep best-similarity row per subject
        best: dict[tuple, tuple] = {}
        for surface, subject_type, subject_key, sim in rows:
            if float(sim) < min_sim:
                continue
            key = (subject_type, subject_key)
            cur_best = best.get(key)
            if cur_best is None or float(sim) > cur_best[3]:
                best[key] = (surface, subject_type, subject_key, float(sim))
        ordered = sorted(best.values(), key=lambda r: (-r[3], r[2]))[:limit]
        return [
            {
                "subject_type": subject_type,
                "subject_key": subject_key,
                "matched_term": surface,
                "match_type": "TRIGRAM",
                "similarity": sim,
            }
            for (surface, subject_type, subject_key, sim) in ordered
        ]


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
