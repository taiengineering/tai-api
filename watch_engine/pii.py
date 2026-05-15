"""PII protection for payload_summary.

Blacklist-based key detection. Blocks known PII field names.
Does NOT parse values — only checks keys.
"""

import logging

logger = logging.getLogger("watch_engine.pii")

# Keys that must never appear in payload_summary
PII_BLACKLIST = frozenset({
    # Korean PII
    "name", "user_name", "username", "full_name",
    "email", "email_address", "mail",
    "phone", "phone_number", "mobile", "tel",
    "address", "addr", "zip_code", "postal_code",
    "ssn", "resident_number", "jumin",
    "birth", "birthday", "birth_date",
    "password", "passwd", "pw", "secret",
    "token", "access_token", "refresh_token", "api_key",
    "credit_card", "card_number", "card_no",
    "bank_account", "account_number",
    # Raw body
    "full_payload", "request_body", "raw_body", "body",
    "raw_request", "raw_response",
})


def check_pii(payload_summary: dict | None) -> list[str]:
    """Check payload_summary for PII keys.

    Returns list of detected PII key names (empty = clean).
    Does NOT raise — caller decides action.
    """
    if not payload_summary or not isinstance(payload_summary, dict):
        return []

    violations = []
    for key in payload_summary:
        key_lower = str(key).lower()
        if key_lower in PII_BLACKLIST:
            violations.append(key)

    if violations:
        logger.warning(
            "PII keys detected in payload_summary: %s — these will be stripped",
            violations,
        )

    return violations


def strip_pii(payload_summary: dict | None) -> dict | None:
    """Return a copy of payload_summary with PII keys removed."""
    if not payload_summary or not isinstance(payload_summary, dict):
        return payload_summary

    violations = check_pii(payload_summary)
    if not violations:
        return payload_summary

    cleaned = {k: v for k, v in payload_summary.items() if k not in violations}
    cleaned["_pii_stripped"] = True
    cleaned["_pii_stripped_keys"] = violations
    return cleaned
