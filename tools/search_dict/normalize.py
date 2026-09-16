"""TAI Search Dictionary — deterministic normalization + term_id.

MASTER-WO-TAI-SEARCH-DICT-001 §23 (deterministic term_id), §26 (conservative
normalization). Pure Python stdlib only — no network, no external analyzer.
The runtime search engine and the build compiler share this module so that a
query is normalized by exactly the same rules as the stored terms.

INVARIANTS (Constitution art.3/4):
  - term_original is NEVER mutated. Every normalized field is a derived copy.
  - normalization is conservative and reversible in intent: it only removes
    whitespace / lowercases Latin / strips punctuation into *separate* fields.
  - term_id is content-addressed and stable; it is NOT a canonical id (§23).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# Unicode categories treated as "punctuation/symbol" for the no-punct copy.
_PUNCT_CATS = {"Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps", "Sk", "Sm", "So", "Sc"}
_WS_RE = re.compile(r"\s+")


def nfc(text: str) -> str:
    """Unicode NFC normalization (WO §26). Deterministic, lossless for identity."""
    return unicodedata.normalize("NFC", text)


def normalize_basic(text: str) -> str:
    """term_normalized: NFC + trim + collapse internal whitespace. (WO §26)

    Original casing and characters are preserved; only whitespace shape changes.
    """
    t = nfc(text)
    t = t.strip()
    t = _WS_RE.sub(" ", t)
    return t


def compact(text: str) -> str:
    """term_compact: remove ALL whitespace (spacing-insensitive search copy)."""
    return _WS_RE.sub("", nfc(text)).strip()


def latin_lower(text: str) -> str:
    """term_latin_lower: casefold copy for Latin/ascii matching (MSDS==msds)."""
    return normalize_basic(text).casefold()


def no_punctuation(text: str) -> str:
    """term_no_punctuation: drop punctuation/symbols, then compact.

    Used only as a derived search copy (e.g. '배관·전로공사' -> '배관전로공사').
    Never applied to the stored original.
    """
    t = nfc(text)
    kept = [ch for ch in t if unicodedata.category(ch) not in _PUNCT_CATS]
    return _WS_RE.sub("", "".join(kept)).strip()


def term_id(source_id: str, source_key: str, term_type: str, original_term: str) -> str:
    """Deterministic content-addressed id (WO §23).

    payload = source_id \n source_key \n term_type \n original_term
    term_id = lowercase hex SHA-256 of UTF-8(payload).

    NOT a canonical id. Two different sources naming the same surface string
    intentionally yield different term_ids (§5: SAME NAME != SAME CONCEPT).
    """
    payload = "\n".join([source_id, source_key, term_type, original_term])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def relation_id(source_term_id: str, target_term_id: str, relation_type: str) -> str:
    """Deterministic relation id: SHA-256 over the directed typed edge."""
    payload = "\n".join([source_term_id, target_term_id, relation_type])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


if __name__ == "__main__":  # tiny self-check
    assert normalize_basic("  국소  배기 장치 ") == "국소 배기 장치"
    assert compact("국소 배기 장치") == "국소배기장치"
    assert latin_lower("MSDS") == "msds"
    assert no_punctuation("배관·전로공사") == "배관전로공사"
    a = term_id("SRC-X", "k", "ALIAS", "산안법")
    assert a == term_id("SRC-X", "k", "ALIAS", "산안법") and len(a) == 64
    print("normalize.py self-check OK")
