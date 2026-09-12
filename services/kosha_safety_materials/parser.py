"""Parse KOSHA selectMediaList JSON — WP-1C-2."""
from __future__ import annotations

from typing import Any

SOURCE_FIELDS = (
    "medSeq", "medName", "medName2", "medNote", "medKeyword", "autNm",
    "contsRegYmd", "frstRegDt", "contsPblsNo",
    "contsFbctnShpCd", "contsFbctnShpNm",
    "medGonggongnuri", "medGonggongnuriNm",
    "medThumbnailPath", "thumbAtcflNo", "thumbPath",
    "contsAtcflNo", "medFileYn", "ytbUrlAddr",
    "contsFldCd", "contsTpbizCd", "constntId", "codeSeq", "codeCd",
    "langCrtrNtnltyNm",
)

VOLATILE_FIELDS = frozenset({
    "totHitSum", "medRecommend", "contsRcmdtnYn", "actlInvtQty",
})


def _norm_seq(v: Any) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).strip()
    if s.isdigit():
        return str(int(s))
    return s


def parse_detail(raw: dict[str, Any] | None, requested_med_seq: str | int, http_status: int | None = 200) -> dict:
    """Return {status, failure_reason, item, fields}."""
    req = _norm_seq(requested_med_seq)
    if http_status is not None and http_status != 200:
        return {"status": "DETAIL_HTTP_ERROR", "failure_reason": f"http {http_status}", "item": None, "fields": {}}
    if not isinstance(raw, dict):
        return {"status": "INVALID_RESPONSE", "failure_reason": "not object", "item": None, "fields": {}}
    result = str(raw.get("result") or "").lower()
    if result and result not in ("success", "ok", "true"):
        return {"status": "INVALID_RESPONSE", "failure_reason": f"result={raw.get('result')!r}", "item": None, "fields": {}}
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return {"status": "INVALID_RESPONSE", "failure_reason": "payload missing", "item": None, "fields": {}}
    lst = payload.get("list")
    if not isinstance(lst, list):
        return {"status": "INVALID_RESPONSE", "failure_reason": "payload.list not list", "item": None, "fields": {}}
    if len(lst) == 0:
        return {"status": "CURRENT_NO_DETAIL", "failure_reason": "DETAIL_EMPTY", "item": None, "fields": {}}
    matches = [x for x in lst if isinstance(x, dict) and _norm_seq(x.get("medSeq")) == req]
    if len(matches) != 1:
        if not matches:
            return {"status": "MEDSEQ_MISMATCH", "failure_reason": "MEDSEQ_MISMATCH", "item": None, "fields": {}}
        return {"status": "INVALID_RESPONSE", "failure_reason": "ambiguous medSeq matches", "item": None, "fields": {}}
    item = matches[0]
    fields = {k: item.get(k) for k in SOURCE_FIELDS}
    fields["medSeq"] = req
    return {"status": "OK", "failure_reason": None, "item": item, "fields": fields}
