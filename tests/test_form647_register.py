"""WO-TAI-FORM647-DRAFT-REGISTER-R2 — 등록 스크립트 부분 실패 복구 검증

register_one() 의 4가지 시나리오를 인메모리 DB 로 검증한다.

R01  정상 최초 등록: INSERTED, 5테이블 순서대로 삽입, registry 마지막
R02  완전 등록 후 재실행: registry 있음 → SKIPPED, 추가 INSERT 없음
R03  콘텐츠 등록 실패 후 재실행: reference_forms 고아 정리 → 재실행 clean INSERTED
R04  HWP 등록 후 PDF 등록 실패 및 재실행: RESUMED, PDF만 추가 삽입
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.register_form647_draft import register_one

# ---------------------------------------------------------------------------
# 샘플 초안
# ---------------------------------------------------------------------------

_HWP_PATH = "form647/form647-remediation-002-714df47a637e3e73/hwp/15267319_licbyl.hwp"
_PDF_PATH = "form647/form647-remediation-002-714df47a637e3e73/pdf/15267319_licbyl.pdf"
_HWP_REF = f"storage://form-originals/{_HWP_PATH}"
_PDF_REF = f"storage://form-originals/{_PDF_PATH}"

_DRAFT = {
    "ek": "15267319",
    "api_target": "licbyl",
    "canonical_slug": "ref-f647-15267319",
    "title": "도급인의 안전·보건에 관한 정보 제공",
    "description": "",
    "body_html": "<p>이 서식은 <strong>산업안전보건법</strong>에 근거한 서식입니다.</p>",
    "source_name": "산업안전보건법",
    "source_url": "https://www.law.go.kr/test",
    "flags": {
        "deleted_from_law": False,
        "edition_drift": False,
        "law_name_missing": False,
        "actor_role_review_count": 0,
        "sha256_missing": False,
    },
    "files": [
        {"file_type": "hwp", "storage_path": _HWP_PATH, "sha256": "aabbcc"},
        {"file_type": "pdf", "storage_path": _PDF_PATH, "sha256": "ddeeff"},
    ],
}


# ---------------------------------------------------------------------------
# 인메모리 DB 목
# ---------------------------------------------------------------------------

class _Res:
    def __init__(self, data):
        self.data = data


class _TableProxy:
    """체인 호출(select/insert/delete/eq/limit/execute)을 흉내낸다."""

    def __init__(self, db: "InMemoryDB", name: str):
        self._db = db
        self._name = name
        self._op: str | None = None
        self._filters: list[tuple] = []
        self._data: dict | None = None

    def select(self, _cols="*"):
        self._op = "select"
        return self

    def insert(self, data):
        self._op = "insert"
        self._data = data
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        db = self._db
        name = self._name
        op = self._op

        # 오류 주입 확인
        key = (name, op)
        if key in db._error_fns:
            exc = db._error_fns[key](self._data)
            if exc is not None:
                raise exc

        if op == "insert":
            row = dict(self._data or {})
            if "id" not in row:
                row["id"] = db._next_id()
            db._rows[name].append(row)
            db._insert_order.append(name)
            return _Res([row])

        elif op == "select":
            rows = list(db._rows[name])
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
            return _Res(rows)

        elif op == "delete":
            rows = list(db._rows[name])
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) != val]
            db._rows[name] = rows
            return _Res([])

        return _Res([])


class InMemoryDB:
    """register_form647_draft.py 가 호출하는 Supabase 인터페이스의 인메모리 구현."""

    _TABLE_NAMES = [
        "reference_forms",
        "reference_form_content",
        "reference_form_slug_registry",
        "reference_form_sources",
        "reference_form_files",
    ]

    def __init__(self):
        self._counter = 0
        self._rows: dict[str, list] = {t: [] for t in self._TABLE_NAMES}
        self._insert_order: list[str] = []  # INSERT 순서 추적
        self._error_fns: dict[tuple, callable] = {}

    def _next_id(self):
        self._counter += 1
        return f"mock-id-{self._counter:04d}"

    def table(self, name):
        return _TableProxy(self, name)

    def inject_error(self, table: str, op: str, exc: Exception):
        """다음 (table, op) 호출 한 번에 예외를 발생시킨다."""
        def _once(_data):
            del self._error_fns[(table, op)]
            return exc
        self._error_fns[(table, op)] = _once

    def inject_error_on_nth_insert(self, table: str, n: int, exc: Exception):
        """table 에 대한 n 번째 insert 호출에 예외를 발생시킨다 (1-기반)."""
        counts = [0]

        def _nth(data):
            counts[0] += 1
            if counts[0] == n:
                del self._error_fns[(table, "insert")]
                return exc
            return None

        self._error_fns[(table, "insert")] = _nth

    def row_count(self, table: str) -> int:
        return len(self._rows[table])

    def file_refs(self, form_id: str) -> set[str]:
        return {r["file_ref"] for r in self._rows["reference_form_files"]
                if r.get("form_id") == form_id}

    def registry_slugs(self) -> set[str]:
        return {r["slug"] for r in self._rows["reference_form_slug_registry"]}


# ---------------------------------------------------------------------------
# R01 — 정상 최초 등록
# ---------------------------------------------------------------------------

def test_r01_normal_insert():
    """R01: 모든 단계 성공 → INSERTED, 5테이블 각각 행 삽입, registry 마지막."""
    db = InMemoryDB()
    draft = dict(_DRAFT)

    result = register_one(db, draft, dry_run=False)

    assert result == "INSERTED"
    assert db.row_count("reference_forms") == 1
    assert db.row_count("reference_form_content") == 1
    assert db.row_count("reference_form_sources") == 1
    assert db.row_count("reference_form_files") == 2       # hwp + pdf
    assert db.row_count("reference_form_slug_registry") == 1

    # registry 가 마지막에 삽입됐는지 삽입 순서 확인
    assert db._insert_order[-1] == "reference_form_slug_registry"

    # 슬러그가 registry 에 기록됐는지 확인
    assert draft["canonical_slug"] in db.registry_slugs()


# ---------------------------------------------------------------------------
# R02 — 완전 등록 후 재실행
# ---------------------------------------------------------------------------

def test_r02_idempotent_skip():
    """R02: 완전 등록 후 재실행 → SKIPPED, 추가 INSERT 없음."""
    db = InMemoryDB()
    draft = dict(_DRAFT)

    first = register_one(db, draft, dry_run=False)
    assert first == "INSERTED"

    before = db.row_count("reference_forms")
    second = register_one(db, draft, dry_run=False)

    assert second == "SKIPPED"
    # 모든 테이블 행 수 불변
    assert db.row_count("reference_forms") == before
    assert db.row_count("reference_form_content") == 1
    assert db.row_count("reference_form_slug_registry") == 1
    assert db.row_count("reference_form_sources") == 1
    assert db.row_count("reference_form_files") == 2


# ---------------------------------------------------------------------------
# R03 — 콘텐츠 등록 실패 후 재실행 (고아 방지)
# ---------------------------------------------------------------------------

def test_r03_content_fail_cleanup_then_rerun():
    """R03: content 삽입 실패 → reference_forms 고아 행 정리 → 재실행 INSERTED.

    1차 실행: reference_forms 생성 → content INSERT 실패 → reference_forms 행 삭제
    2차 실행: 깨끗한 상태에서 신규 등록 → INSERTED
    """
    db = InMemoryDB()
    draft = dict(_DRAFT)

    # content 삽입 시 오류 주입
    db.inject_error("reference_form_content", "insert", RuntimeError("content DB error"))
    result1 = register_one(db, draft, dry_run=False)

    assert result1.startswith("ERROR:")
    # 고아 방지: reference_forms 행이 정리돼야 함
    assert db.row_count("reference_forms") == 0
    assert db.row_count("reference_form_content") == 0
    assert db.row_count("reference_form_slug_registry") == 0

    # 2차 실행: 깨끗한 신규 등록
    result2 = register_one(db, draft, dry_run=False)

    assert result2 == "INSERTED"
    assert db.row_count("reference_forms") == 1
    assert db.row_count("reference_form_content") == 1
    assert db.row_count("reference_form_slug_registry") == 1
    assert db.row_count("reference_form_sources") == 1
    assert db.row_count("reference_form_files") == 2


# ---------------------------------------------------------------------------
# R04 — HWP 등록 후 PDF 등록 실패 및 재실행
# ---------------------------------------------------------------------------

def test_r04_partial_file_fail_then_resume():
    """R04: HWP 등록 후 PDF INSERT 실패 → 재실행 RESUMED, PDF만 추가 삽입.

    1차 실행: forms+content+sources+HWP 등록 → PDF INSERT 실패 → registry 없음
    2차 실행: RESUME 경로 → sources 존재 (skip) → PDF만 보완 → registry 등록 → RESUMED
    """
    db = InMemoryDB()
    draft = dict(_DRAFT)

    # reference_form_files 의 2번째 insert(PDF)에서 오류 주입
    db.inject_error_on_nth_insert(
        "reference_form_files", n=2, exc=RuntimeError("PDF DB error")
    )
    result1 = register_one(db, draft, dry_run=False)

    assert result1.startswith("ERROR:")
    # forms, content, sources, HWP 는 등록됨
    assert db.row_count("reference_forms") == 1
    assert db.row_count("reference_form_content") == 1
    assert db.row_count("reference_form_sources") == 1
    assert db.row_count("reference_form_files") == 1   # HWP만
    assert db.row_count("reference_form_slug_registry") == 0  # 미완료

    # 등록된 파일이 HWP인지 확인
    form_id = db._rows["reference_form_content"][0]["form_id"]
    assert db.file_refs(form_id) == {_HWP_REF}

    # 2차 실행: RESUME 경로
    result2 = register_one(db, draft, dry_run=False)

    assert result2 == "RESUMED"
    # sources 중복 없음
    assert db.row_count("reference_form_sources") == 1
    # PDF 추가, HWP 중복 없음
    assert db.row_count("reference_form_files") == 2
    assert db.file_refs(form_id) == {_HWP_REF, _PDF_REF}
    # registry 등록됨
    assert db.row_count("reference_form_slug_registry") == 1
    assert draft["canonical_slug"] in db.registry_slugs()
