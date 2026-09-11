"""Match DB logical asset identity to live selectAtchList / getFileList — WP-1C-5B."""
from __future__ import annotations

from .storage_keys import source_asset_key
from ..asset_parser import parse_attachments


class ResolutionError(Exception):
    def __init__(self, code: str = "SOURCE_ASSET_RESOLUTION_BLOCKED", message: str = "",
                 observed_files: list | None = None):
        super().__init__(message or code)
        self.code = code
        self.observed_files = list(observed_files or [])


def observed_from_file_list(file_list: list[dict] | None) -> list[dict]:
    out = []
    for it in file_list or []:
        out.append({
            "file_name": it.get("orgnlAtchFileNm"),
            "atcfl_no": it.get("atcflNo") or it.get("contsAtcflNo"),
            "atcfl_seq": it.get("atcflSeq"),
        })
    return out


def observed_from_assets(assets: list[dict] | None) -> list[dict]:
    out = []
    for a in assets or []:
        out.append({
            "file_name": a.get("file_name"),
            "checksum": a.get("checksum"),
        })
    return out


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
    assets = parsed.get("assets") or []
    observed = observed_from_assets(assets)
    hits = [a for a in assets if a.get("checksum") == expected_checksum]
    if len(hits) == 0:
        raise ResolutionError("SOURCE_ASSET_ZERO_MATCH", observed_files=observed)
    if len(hits) != 1:
        raise ResolutionError("SOURCE_ASSET_MULTI_MATCH", observed_files=observed)
    hit = hits[0]
    if expected_filename and hit.get("file_name") and hit["file_name"] != expected_filename:
        raise ResolutionError("SOURCE_ASSET_FILENAME_MISMATCH", observed_files=observed)
    return hit


def match_downloadable_file(file_list: list[dict], *, file_name: str | None, atcfl_no: str) -> dict:
    observed = observed_from_file_list(file_list)
    hits = []
    for it in file_list or []:
        name = str(it.get("orgnlAtchFileNm") or "")
        no = str(it.get("atcflNo") or it.get("contsAtcflNo") or atcfl_no)
        if file_name and name == file_name:
            hits.append(it)
        elif not file_name and str(no) == str(atcfl_no):
            hits.append(it)
    if file_name and not hits:
        if not (file_list or []):
            raise ResolutionError("SOURCE_ASSET_ZERO_MATCH", observed_files=observed)
        raise ResolutionError("SOURCE_ASSET_FILENAME_MISMATCH", observed_files=observed)
    if len(hits) == 0:
        raise ResolutionError("SOURCE_ASSET_ZERO_MATCH", observed_files=observed)
    if len(hits) != 1:
        raise ResolutionError("SOURCE_ASSET_MULTI_MATCH", observed_files=observed)
    it = hits[0]
    seq = it.get("atcflSeq")
    if seq is None:
        raise ResolutionError("SOURCE_ASSET_RESOLUTION_BLOCKED", observed_files=observed)
    return {
        "atcfl_no": str(it.get("atcflNo") or it.get("contsAtcflNo") or atcfl_no),
        "atcfl_seq": seq,
        "file_name": it.get("orgnlAtchFileNm") or file_name,
        "mime_type": it.get("atcflMimeType") or it.get("mimeType"),
    }


def logical_key(material_id, atcfl_no, seq, file_name="") -> str:
    return source_asset_key(material_id, atcfl_no, seq, file_name)
