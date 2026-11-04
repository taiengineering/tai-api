"""DOC260 서식 원본 파일 경로 계산.

doc_id를 DOC-{SECTOR}-{NUMBER} 형식으로 검증한 후 표준 storage 경로를 반환한다.
파일 존재 여부는 storage 조회(Gate 4)에서 최종 확인한다.
형식 검증으로 path traversal을 원천 차단한다 (허용 문자: 대문자·숫자·하이픈).

수집된 서식을 별도 등록 절차 없이 직접 제공한다. 형식 불일치 doc_id만 차단.
"""
from __future__ import annotations
import re

_BUCKET = "form-originals"

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
    return f"doc_forms/{doc_id}.hwp"
