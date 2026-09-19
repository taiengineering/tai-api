"""OpenSearch index mapping & settings — WO-TAI-SHARED-SEARCH-F3 §10-§13.

SOLE authority for:
  - index settings (shards, replicas)
  - Nori analyzer definitions (tai_nori_index / tai_nori_search)
  - field mappings (§12)
  - alias name
  - physical index naming convention

No other file defines or duplicates these.

Nori configuration is explicit (§13): no implicit default analyzer.
Index and search analyzers are named separately so that
search-time token filter decompound can be tuned independently.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from services.shared_search.opensearch_client import CURRENT_ALIAS


# ---------------------------------------------------------------------------
# Physical index naming (§11)
# ---------------------------------------------------------------------------

def candidate_index_name(run_id: str) -> str:
    """Return deterministic physical index name for a rebuild run.

    Format: tai-shared-search-v1-{first_16_of_run_id}
    OpenSearch requires lowercase index names.
    """
    short = run_id.replace("-", "").lower()[:16]
    return f"tai-shared-search-v1-{short}"


# ---------------------------------------------------------------------------
# Nori analyzer definitions (§13)
# ---------------------------------------------------------------------------

_NORI_SETTINGS = {
    "analysis": {
        "analyzer": {
            # Index-time: decompound + POS filter to reduce noise tokens
            "tai_nori_index": {
                "type": "custom",
                "tokenizer": "tai_nori_tokenizer",
                "filter": [
                    "tai_nori_part_of_speech",
                    "tai_nori_decompound",
                    "lowercase",
                    "asciifolding",
                ],
            },
            # Search-time: lighter — keep user intent intact
            "tai_nori_search": {
                "type": "custom",
                "tokenizer": "tai_nori_tokenizer",
                "filter": [
                    "tai_nori_part_of_speech",
                    "lowercase",
                    "asciifolding",
                ],
            },
        },
        "tokenizer": {
            "tai_nori_tokenizer": {
                "type": "nori_tokenizer",
                # mixed: split compound words AND keep the original for better recall
                "decompound_mode": "mixed",
                # user_dictionary_rules: custom entries injected at runtime if needed.
                # Leave empty here; loaded via opensearch_bootstrap if dictionary
                # artifacts are present.
            },
        },
        "filter": {
            # Remove uninformative POS tags (particles, endings, symbols)
            "tai_nori_part_of_speech": {
                "type": "nori_part_of_speech",
                "stoptags": [
                    "E",    # verbal ending
                    "IC",   # interjection
                    "J",    # postpositional particle
                    "MAG",  # adverb that has little discriminating value
                    "MM",   # determiner
                    "SP",   # space
                    "SSC",  # closing parenthesis
                    "SSO",  # opening parenthesis
                    "SC",   # comma, period
                    "SE",   # ellipsis
                    "XPN",  # prefix
                    "XSA",  # adjective suffix
                    "XSN",  # noun suffix
                    "XSV",  # verb suffix
                    "UNA",  # unknown
                    "NA",   # noise
                    "VSV",  # unknown verb
                ],
            },
            "tai_nori_decompound": {
                "type": "nori_readingform",  # converts hanja → hangul
            },
        },
    }
}

_INDEX_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,   # bumped to 1+ post-G1 in production
    "refresh_interval": "5s",
    **_NORI_SETTINGS,
}


# ---------------------------------------------------------------------------
# Field mapping (§12)
# ---------------------------------------------------------------------------

_NORI_TEXT_FIELD = {
    "type": "text",
    "analyzer": "tai_nori_index",
    "search_analyzer": "tai_nori_search",
}

_MAPPING_PROPERTIES = {
    "object_type":        {"type": "keyword"},
    "canonical_id":       {"type": "keyword"},
    "source_id":          {"type": "keyword"},
    "source_key":         {"type": "keyword"},

    "title": {
        **_NORI_TEXT_FIELD,
        "fields": {
            "raw":    {"type": "keyword"},        # TITLE_EXACT tier
            "prefix": {"type": "search_as_you_type"},
        },
    },
    "summary":       {**_NORI_TEXT_FIELD},
    "search_text":   {**_NORI_TEXT_FIELD},

    "aliases": {
        **_NORI_TEXT_FIELD,
        "fields": {
            "raw": {"type": "keyword"},           # ALIAS_EXACT tier
        },
    },
    "keywords":      {**_NORI_TEXT_FIELD},

    "subjects": {
        "type": "nested",
        "properties": {
            "subject_type": {"type": "keyword"},
            "subject_key":  {"type": "keyword"},  # SUBJECT_EXACT tier
        },
    },
    "context": {
        "type": "nested",
        "properties": {
            "context_type": {"type": "keyword"},
            "context_key":  {"type": "keyword"},  # CONTEXT_EXACT tier
        },
    },

    "public_url":         {"type": "keyword", "index": False},
    "saas_url":           {"type": "keyword", "index": False},

    "publication_status": {"type": "keyword"},
    "visibility_scopes":  {"type": "keyword"},  # term filter (§27)

    "source_updated_at":  {"type": "date"},
    "content_hash":       {"type": "keyword"},
    "indexed_at":         {"type": "date"},
}

INDEX_BODY = {
    "settings": _INDEX_SETTINGS,
    "mappings": {"properties": _MAPPING_PROPERTIES},
}


# ---------------------------------------------------------------------------
# Mapping hash — for verification
# ---------------------------------------------------------------------------

def mapping_sha256() -> str:
    """Stable SHA-256 of the canonical INDEX_BODY.
    Used by opensearch_verify to detect drift."""
    canonical = json.dumps(INDEX_BODY, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Alias helpers
# ---------------------------------------------------------------------------

def build_alias_action(
    new_index: str,
    old_index: Optional[str] = None,
) -> dict:
    """Build atomic alias switch actions body (§37).

    If old_index is given, removes it from the alias atomically.
    """
    actions = []
    if old_index:
        actions.append({"remove": {"index": old_index, "alias": CURRENT_ALIAS}})
    actions.append({"add": {"index": new_index, "alias": CURRENT_ALIAS}})
    return {"actions": actions}
