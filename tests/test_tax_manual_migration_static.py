"""WO-TAX-INVOICE-MANUAL-01 WP-A — tax_invoice_requests DDL 정적 검증.

up/down 아티팩트 텍스트 정적 검증. DB 접속 없음. 코드/서비스 변경 0 (이 테스트만 신규).

케이스:
  D1  source_check 재정의: AUTO_PAYMENT + ADMIN_MANUAL 포함 (AUTO_PAYMENT defect 동시 수정)
  D2  기존 활성 source (MYPAGE, SAAS, AUTO_SAAS) 유지
  D3  payment_id / company_id DROP NOT NULL 두 문장 모두 존재
  D4  invariant CHECK 존재 (ADMIN_MANUAL 만 payment_id NULL 허용, 그 외 NOT NULL 강제)
  D5  metadata 컬럼 3개 신설 (idempotency_key uuid, item_name text, issue_reason text)
  D6  partial UNIQUE index (source='ADMIN_MANUAL' AND idempotency_key IS NOT NULL) 신설
  D7  amount_check(total=supply+vat) 삭제/완화 문구 부재 (unchanged)
  D8  이 마이그레이션이 apply_migration 을 자동 호출하지 않음 (docs/sql 파일만)
"""
from __future__ import annotations

import os
import pathlib
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260906_tax_invoice_requests_manual_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260906_tax_invoice_requests_manual_down.sql"))


def _up() -> str:
    with open(UP, encoding="utf-8") as f:
        return f.read()


def _down() -> str:
    with open(DOWN, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    """공백 압축 + 소문자 (SQL 대소문자 무시 매칭용)."""
    return re.sub(r"\s+", " ", s).lower()


# ═════════════════════════════════════════════════════════════════════
# D1 — source_check 재정의: AUTO_PAYMENT + ADMIN_MANUAL 포함
# ═════════════════════════════════════════════════════════════════════
def test_D1_source_check_contains_auto_payment_and_admin_manual():
    n = _norm(_up())
    # 새 CHECK 존재
    assert "add constraint tax_invoice_requests_source_check" in n
    # 정확히 5개 값 (MYPAGE, SAAS, AUTO_PAYMENT, AUTO_SAAS, ADMIN_MANUAL)
    m = re.search(r"tax_invoice_requests_source_check\s+check\s*\(\s*source\s*=\s*any\s*\(\s*array\[([^\]]+)\]\s*\)\s*\)", n)
    assert m, "source_check ARRAY[...] 파싱 실패"
    values = [v.strip().strip("'") for v in m.group(1).split(",")]
    assert set(values) == {"mypage", "saas", "auto_payment", "auto_saas", "admin_manual"}, (
        f"source_check 값 집합 불일치: {values}"
    )


# ═════════════════════════════════════════════════════════════════════
# D1b — DROP 기존 source_check 문장이 존재 (재정의를 위해 필수)
# ═════════════════════════════════════════════════════════════════════
def test_D1b_source_check_drop_before_readd():
    n = _norm(_up())
    assert "drop constraint if exists tax_invoice_requests_source_check" in n
    # DROP 이 ADD 앞에 나와야 함
    drop_idx = n.find("drop constraint if exists tax_invoice_requests_source_check")
    add_idx = n.find("add constraint tax_invoice_requests_source_check")
    assert 0 <= drop_idx < add_idx, "DROP 이 ADD 앞에 나와야 함"


# ═════════════════════════════════════════════════════════════════════
# D2 — 기존 활성 source (MYPAGE, SAAS, AUTO_SAAS) 유지 (D1 값 집합에 포함)
# ═════════════════════════════════════════════════════════════════════
def test_D2_existing_active_sources_preserved():
    n = _norm(_up())
    m = re.search(r"tax_invoice_requests_source_check\s+check\s*\(\s*source\s*=\s*any\s*\(\s*array\[([^\]]+)\]\s*\)\s*\)", n)
    values = {v.strip().strip("'") for v in m.group(1).split(",")}
    for existing in ("mypage", "saas", "auto_saas"):
        assert existing in values, f"기존 source '{existing}' 유지 실패"


# ═════════════════════════════════════════════════════════════════════
# D3 — payment_id / company_id DROP NOT NULL 두 문장 모두 존재
# ═════════════════════════════════════════════════════════════════════
def test_D3_payment_id_company_id_nullable():
    n = _norm(_up())
    assert "alter column payment_id drop not null" in n
    assert "alter column company_id drop not null" in n


# ═════════════════════════════════════════════════════════════════════
# D4 — invariant CHECK: ADMIN_MANUAL 만 payment_id NULL, 그 외 NOT NULL 강제
# ═════════════════════════════════════════════════════════════════════
def test_D4_invariant_check_admin_manual_only_null():
    n = _norm(_up())
    assert "add constraint tax_invoice_requests_admin_manual_payment_check" in n
    # CHECK 절 내부에 두 분기가 모두 있어야 함
    m = re.search(
        r"tax_invoice_requests_admin_manual_payment_check\s+check\s*\((.+?)\);", n, re.DOTALL,
    )
    assert m, "invariant CHECK 파싱 실패"
    body = m.group(1)
    # 분기 1: ADMIN_MANUAL AND payment_id IS NULL
    assert "'admin_manual'" in body and "payment_id is null" in body
    # 분기 2: source <> 'ADMIN_MANUAL' AND payment_id IS NOT NULL AND company_id IS NOT NULL
    assert "source <> 'admin_manual'" in body
    assert "payment_id is not null" in body
    assert "company_id is not null" in body


# ═════════════════════════════════════════════════════════════════════
# D5 — metadata 컬럼 3개 신설 (idempotency_key uuid, item_name text, issue_reason text)
# ═════════════════════════════════════════════════════════════════════
def test_D5_metadata_columns_added():
    n = _norm(_up())
    assert "add column if not exists idempotency_key uuid" in n
    assert "add column if not exists item_name text" in n
    assert "add column if not exists issue_reason text" in n


# ═════════════════════════════════════════════════════════════════════
# D6 — partial UNIQUE index (source='ADMIN_MANUAL' AND idempotency_key IS NOT NULL)
# ═════════════════════════════════════════════════════════════════════
def test_D6_partial_unique_index_admin_manual():
    n = _norm(_up())
    assert "create unique index if not exists uq_tax_invoice_requests_admin_manual_idem" in n
    # WHERE 절 확인 (partial)
    m = re.search(
        r"create unique index if not exists uq_tax_invoice_requests_admin_manual_idem\s+on\s+public\.tax_invoice_requests\s*\(\s*idempotency_key\s*\)\s+where\s+(.+?);",
        n, re.DOTALL,
    )
    assert m, "partial UNIQUE index WHERE 절 파싱 실패"
    where = m.group(1)
    assert "source = 'admin_manual'" in where
    assert "idempotency_key is not null" in where


# ═════════════════════════════════════════════════════════════════════
# D7 — amount_check(total=supply+vat) 삭제/완화 문구 부재 (기존 CHECK 유지)
# ═════════════════════════════════════════════════════════════════════
def test_D7_amount_check_not_touched():
    n = _norm(_up())
    # 이 마이그레이션은 amount_check 를 건드리지 않아야 함
    assert "drop constraint if exists tax_invoice_requests_amount_check" not in n
    assert "alter constraint tax_invoice_requests_amount_check" not in n
    assert "drop constraint tax_invoice_requests_amount_check" not in n
    # amount_check 를 삭제/재정의하는 어떤 문장도 없음


# ═════════════════════════════════════════════════════════════════════
# D8 — 이 마이그레이션은 자동 apply 되지 않음 (파일만 존재).
#      migrations/ dir 없음 (SoT = Supabase). 코드/CI 어디에도 자동 실행 훅 없음.
# ═════════════════════════════════════════════════════════════════════
def test_D8_no_auto_apply_hook_in_repo():
    """이 SQL 파일을 자동 실행하는 코드가 저장소에 없어야 함 (production DB write 방지)."""
    root = pathlib.Path(__file__).parent.parent
    filename_stub = "20260906_tax_invoice_requests_manual"
    hits = []
    for p in root.rglob("*.py"):
        # 자신 (테스트 파일) 은 제외
        if p.name == "test_tax_manual_migration_static.py":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if filename_stub in text:
            hits.append(str(p.relative_to(root)))
    assert hits == [], (
        f"이 마이그레이션 파일을 참조하는 파이썬 코드가 있어서는 안 됨 (자동 적용 방지): {hits}"
    )

    # 워크플로우/CI 에도 없음
    workflows = root / ".github" / "workflows"
    if workflows.exists():
        for p in workflows.rglob("*.yml"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert filename_stub not in text, (
                f"CI 워크플로우가 이 SQL 을 자동 실행: {p.name}"
            )


# ═════════════════════════════════════════════════════════════════════
# 추가: DOWN 파일 sanity — 3 컬럼 삭제 + 인덱스 삭제 + source_check 되돌림 존재
# ═════════════════════════════════════════════════════════════════════
def test_down_reverses_all_up_changes():
    n = _norm(_down())
    assert "drop index if exists public.uq_tax_invoice_requests_admin_manual_idem" in n
    assert "drop column if exists idempotency_key" in n
    assert "drop column if exists item_name" in n
    assert "drop column if exists issue_reason" in n
    assert "drop constraint if exists tax_invoice_requests_admin_manual_payment_check" in n
    # source_check 되돌림 (defect 상태 복귀 — WO 문서화)
    assert "check (source = any (array['mypage', 'saas', 'auto_saas']))" in n


# ═════════════════════════════════════════════════════════════════════
# 회귀: 프로덕션 코드가 사용하는 source 값이 새 CHECK 를 통과 (defect 재발 방지)
# ═════════════════════════════════════════════════════════════════════
def test_production_code_source_values_pass_new_check():
    """코드에서 실제로 사용하는 source 값이 새 CHECK enum 에 반드시 포함되어야 함."""
    from services.tax_invoice_request_svc import _ALLOWED_SOURCES

    up = _norm(_up())
    m = re.search(r"tax_invoice_requests_source_check\s+check\s*\(\s*source\s*=\s*any\s*\(\s*array\[([^\]]+)\]\s*\)\s*\)", up)
    ddl_values = {v.strip().strip("'").upper() for v in m.group(1).split(",")}

    for src in _ALLOWED_SOURCES:
        # AUTO_SAAS 는 향후 예비 — DDL 에 있는지 여부와 무관하게 코드는 준비.
        # 이 테스트는 코드가 사용하는 source 가 DDL 에서 허용되는지만 검사.
        assert src in ddl_values, (
            f"코드에서 사용하는 source '{src}' 가 DDL source_check 에 없음. "
            f"DDL: {ddl_values}. 프로덕션 CHECK 위반 위험 (AUTO_PAYMENT defect 유사)."
        )

    # ADMIN_MANUAL 도 반드시 포함 (수동발행 경로)
    assert "ADMIN_MANUAL" in ddl_values
