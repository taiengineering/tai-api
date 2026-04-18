def _get_penalty_from_rule(r) -> float:
    """규칙 dict/str에서 과태료 금액 추출."""
    if not isinstance(r, dict):
        return _parse_penalty_krw(r) if isinstance(r, str) else 0.0
    amt = r.get("penalty_amount")
    if amt is not None:
        parsed = _parse_penalty_krw(amt)
        if parsed > 0:
            return parsed
    return _parse_penalty_krw(r.get("penalty_summary") or r.get("penalty_text") or "")
