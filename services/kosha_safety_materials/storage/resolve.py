"""Match DB logical asset identity to live selectAtchList / getFileList — WP-1C-5B."""
from __future__ import annotations

from .storage_keys import source_asset_key
from ..asset_parser import parse_attachments


class ResolutionError(Exception):
    def __init__(self, code: str = "SOURCE_ASSET_RESOLUTION_BLOCKED", message: str = ""):
        super().__init__(message or code)
        self.code = code


def match_logical_attachment(
    *,
    material_id: str,
    expected_checksum: str,
    expected_filename: str | None,
    atch_json,
    http_status: int | None = 200,
    requested_med_seq: str | None = None,
    response_med_seq: str | None = None,
) -> dict:
    if requested_med_seq and response_med_seq and str(requested_med_seq) != str(response_med_seq):
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    parsed = parse_attachments(
        atch_json, material_id=material_id, source_url="https://portal.kosha.or.kr/",
        video_storage_false=True, http_status=http_status,
    )
    if not parsed.get("ok"):
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    hits = [a for a in parsed["assets"] if a.get("checksum") == expected_checksum]
    if len(hits) != 1:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    hit = hits[0]
    if expected_filename and hit.get("file_name") and hit["file_name"] != expected_filename:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    return hit


def match_downloadable_file(file_list: list[dict], *, file_name: str | None, atcfl_no: str) -> dict:
    hits = []
    for it in file_list or []:
        name = str(it.get("orgnlAtchFileNm") or "")
        no = str(it.get("atcflNo") or it.get("contsAtcflNo") or atcfl_no)
        if file_name and name == file_name:
            hits.append(it)
        elif not file_name and str(no) == str(atcfl_no):
            hits.append(it)
    if file_name and not hits:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    if len(hits) != 1:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    it = hits[0]
    seq = it.get("atcflSeq")
    if seq is None:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED")
    return {
        "atcfl_no": str(it.get("atcflNo") or it.get("contsAtcflNo") or atcfl_no),
        "atcfl_seq": seq,
        "file_name": it.get("orgnlAtchFileNm") or file_name,
        "mime_type": it.get("atcflMimeType") or it.get("mimeType"),
    }


def logical_key(material_id, atcfl_no, seq, file_name="") -> str:
    return source_asset_key(material_id, atcfl_no, seq, file_name)
