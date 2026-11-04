"""DOC260 서식 원본 파일 경로 계산.

doc_id를 DOC-{SECTOR}-{NUMBER} 형식으로 검증한 후 표준 storage 경로를 반환한다.
파일 존재 여부는 storage 조회(Gate 4)에서 최종 확인한다.
형식 검증으로 path traversal을 원천 차단한다 (허용 문자: 대문자·숫자·하이픈).

수집된 서식을 별도 등록 절차 없이 직접 제공한다. 형식 불일치 doc_id만 차단.
"""
from __future__ import annotations
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

_BUCKET = "form-originals"
_DOC_FORMS_PREFIX = "doc_forms"
_STORAGE_LIST_LIMIT = 300

# doc_id 형식: DOC-{대문자영문}-{숫자}
_DOC_ID_RE = re.compile(r'^DOC-[A-Z]+-\d+$')


def source_file_bucket() -> str:
    return _BUCKET


def get_verified_path(doc_id: str) -> str | None:
    """doc_id의 표준 storage 경로를 반환.

    DOC-{SECTOR}-{NUMBER} 형식을 충족하지 않으면 None.
    반환 경로는 항상 'doc_forms/'로 시작하고 '..'을 포함하지 않는다.
    파일 존재 여부는 호출자(storage Gate)에서 확인한다.
    """
    if not doc_id or not _DOC_ID_RE.match(doc_id):
        return None
    return f"{_DOC_FORMS_PREFIX}/{doc_id}.hwp"


def list_available_doc_ids(supabase: Any) -> frozenset[str]:
    """doc_forms/ 디렉터리의 HWP 파일을 일괄 조회해 doc_id 집합을 반환.

    Storage 조회 실패 시 빈 집합(보수적 처리: 버튼 미표시 → false-negative 허용).
    한 번만 호출하고 결과를 호출자가 재사용한다 — 문서별 반복 금지.
    """
    try:
        objects = supabase.storage.from_(_BUCKET).list(
            _DOC_FORMS_PREFIX, {"limit": _STORAGE_LIST_LIMIT}
        )
        return frozenset(
            obj["name"].removesuffix(".hwp")
            for obj in (objects or [])
            if isinstance(obj.get("name"), str) and obj["name"].endswith(".hwp")
        )
    except Exception as exc:
        log.warning("source file list failed — defaulting to empty set: %s", exc)
        return frozenset()
