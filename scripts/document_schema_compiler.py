#!/usr/bin/env python3
"""
document_schema_compiler.py — TAI 오염 방지형 Document Schema Compiler

작업지시서 16개 섹션 규칙에 따라 HWP 문서를 증거 기반으로 구조화.
문서를 해석하지 않음. 문서에 실제 존재하는 구조만 추출.

파이프라인: HWP → hwp5html → XHTML → 파싱 → Document Schema Candidate Package JSON

실행:
  cd ~/Desktop/tai-engineering/tai-api
  railway run python3 scripts/document_schema_compiler.py --dry-run          # 1건 테스트
  railway run python3 scripts/document_schema_compiler.py --limit 5          # 5건
  railway run python3 scripts/document_schema_compiler.py                    # 전체
"""
import argparse, json, os, re, subprocess, sys, tempfile, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html.parser import HTMLParser

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: railway run 으로 실행하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_SRC = "form-originals"
OUTPUT_DIR = Path("./form_originals_hwp/compiled")
KST = timezone(timedelta(hours=9))


# ══════════════════════════════════════════════════════
# 섹션 1. HWP → XHTML 변환 (원본 보존)
# ══════════════════════════════════════════════════════

def hwp_to_xhtml(hwp_path: Path, output_dir: Path) -> Path | None:
    """hwp5html로 XHTML 변환. 원본 HWP는 수정하지 않음."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["hwp5html", str(hwp_path), "--output", str(output_dir)],
            capture_output=True, timeout=60, check=True,
        )
        xhtml = output_dir / "index.xhtml"
        return xhtml if xhtml.exists() else None
    except Exception as e:
        print(f"    hwp5html 실패: {e}")
        return None


# ══════════════════════════════════════════════════════
# 섹션 2. XHTML 파싱 → 문서 단위 분해
# ══════════════════════════════════════════════════════

class XHTMLTableExtractor(HTMLParser):
    """XHTML에서 표 구조를 추출. 각 셀의 텍스트+위치를 수집."""

    def __init__(self):
        super().__init__()
        self.tables = []       # [{rows: [[{text, rowspan, colspan}]]}]
        self._in_table = False
        self._in_td = False
        self._in_p = False
        self._current_table = None
        self._current_row = None
        self._current_cell = None
        self._text_buf = []
        self._table_idx = 0
        self._row_idx = 0
        self._col_idx = 0
        # 표 밖 텍스트
        self.paragraphs = []
        self._para_buf = []
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self._in_body = True
        elif tag == "table":
            self._in_table = True
            self._table_idx += 1
            self._current_table = {"table_idx": self._table_idx, "rows": []}
            self._row_idx = 0
        elif tag == "tr" and self._in_table:
            self._row_idx += 1
            self._col_idx = 0
            self._current_row = []
        elif tag == "td" and self._in_table:
            self._in_td = True
            self._col_idx += 1
            self._current_cell = {
                "row": self._row_idx,
                "col": self._col_idx,
                "rowspan": int(a.get("rowspan", 1)),
                "colspan": int(a.get("colspan", 1)),
                "text": "",
            }
            self._text_buf = []
        elif tag == "p":
            self._in_p = True
            if not self._in_table:
                self._para_buf = []

    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            self._in_td = False
            if self._current_cell is not None:
                self._current_cell["text"] = " ".join(self._text_buf).strip()
                self._current_cell["text"] = re.sub(r'\s+', ' ', self._current_cell["text"])
            if self._current_row is not None:
                self._current_row.append(self._current_cell)
            self._current_cell = None
            self._text_buf = []
        elif tag == "tr" and self._current_row is not None:
            if self._current_table is not None:
                self._current_table["rows"].append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._in_table:
            self._in_table = False
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None
        elif tag == "p":
            self._in_p = False
            if not self._in_table and self._para_buf:
                text = " ".join(self._para_buf).strip()
                if text:
                    self.paragraphs.append(text)

    def handle_data(self, data):
        clean = data.replace("\r", "").replace("\n", " ").strip()
        if not clean:
            return
        if self._in_td:
            self._text_buf.append(clean)
        elif self._in_p and not self._in_table:
            self._para_buf.append(clean)


def parse_xhtml(xhtml_path: Path) -> dict:
    """XHTML 파싱 → 표 구조 + 문단 추출"""
    text = xhtml_path.read_text(encoding="utf-8", errors="ignore")
    parser = XHTMLTableExtractor()
    parser.feed(text)
    return {"tables": parser.tables, "paragraphs": parser.paragraphs}


# ══════════════════════════════════════════════════════
# 섹션 3~5. Field / Checklist / Evidence Candidate 생성
# ══════════════════════════════════════════════════════

# 필드 라벨 패턴 (문서에서 실제 발견되는 것만)
FIELD_PATTERNS = [
    (r'사업장명', 'site_name'),
    (r'사업자\s*등록\s*번호', 'business_registration_no'),
    (r'사업장\s*관리\s*번호', 'site_management_no'),
    (r'근로자\s*수', 'worker_count'),
    (r'점검일자|점검일|작성일', 'inspection_date'),
    (r'점검자|작성자|검사자', 'inspector_name'),
    (r'확인자', 'verifier_name'),
    (r'서명|인', 'signature'),
    (r'첨부사진|첨부파일|사진', 'attachment'),
    (r'비고', 'remarks'),
    (r'조치사항|개선사항', 'corrective_action'),
    (r'점검결과|판정|결과', 'inspection_result'),
    (r'제출처|귀하', 'submit_to'),
    (r'보존기간', 'retention_period'),
    (r'보고번호', 'report_no'),
    (r'업종', 'industry_type'),
    (r'소재지|주소', 'address'),
    (r'전화번호|연락처', 'phone'),
    (r'대표자', 'representative'),
]

EVIDENCE_KEYWORDS = ['사진', '첨부', '서명', '인', '확인자', '작성자', '보존기간', '제출처', '제출일', '보고번호']
CHECKLIST_PATTERNS = [r'여부\s*확인', r'이상\s*없', r'점검\s*항목', r'확인\s*사항', r'체크']


def extract_candidates(parsed: dict, doc_id: str) -> dict:
    """파싱된 구조에서 후보 추출. 문서에 실제 존재하는 것만."""
    fields = []
    checklists = []
    evidence = []
    elements = []  # 전체 분해 요소
    fc_seq = ec_seq = cc_seq = el_seq = 0

    for table in parsed["tables"]:
        tidx = table["table_idx"]
        for row in table["rows"]:
            for cell in row:
                text = cell.get("text", "")
                if not text:
                    continue

                el_seq += 1
                elements.append({
                    "element_id": f"EL-{el_seq:04d}",
                    "element_type": "TABLE_CELL",
                    "raw_text": text[:300],
                    "source_location": {
                        "table_idx": tidx,
                        "row": cell["row"],
                        "col": cell["col"],
                        "rowspan": cell["rowspan"],
                        "colspan": cell["colspan"],
                    },
                    "status": "EXTRACTED",
                })

                # 섹션 3: Field Candidate
                for pattern, canonical in FIELD_PATTERNS:
                    if re.search(pattern, text):
                        fc_seq += 1
                        fields.append({
                            "field_candidate_id": f"FC-{fc_seq:03d}",
                            "raw_label": text[:200],
                            "canonical_field_candidate": canonical,
                            "source_location": {
                                "table_idx": tidx,
                                "row": cell["row"],
                                "col": cell["col"],
                            },
                            "status": "CANDIDATE",
                        })
                        break

                # 섹션 5: Evidence Candidate
                for kw in EVIDENCE_KEYWORDS:
                    if kw in text:
                        ec_seq += 1
                        evidence.append({
                            "evidence_field_candidate_id": f"EFC-{ec_seq:03d}",
                            "raw_label": text[:200],
                            "evidence_family": f"{kw.upper()}_EVIDENCE_FAMILY",
                            "source_location": {
                                "table_idx": tidx,
                                "row": cell["row"],
                                "col": cell["col"],
                            },
                            "status": "CANDIDATE",
                        })
                        break

                # 섹션 4: Checklist Candidate
                for cp in CHECKLIST_PATTERNS:
                    if re.search(cp, text):
                        cc_seq += 1
                        checklists.append({
                            "checklist_item_candidate_id": f"CIC-{cc_seq:03d}",
                            "raw_text": text[:300],
                            "source_location": {
                                "table_idx": tidx,
                                "row": cell["row"],
                                "col": cell["col"],
                            },
                            "status": "CANDIDATE",
                        })
                        break

    # 표 밖 문단에서도 추출
    for i, para in enumerate(parsed["paragraphs"]):
        el_seq += 1
        elements.append({
            "element_id": f"EL-{el_seq:04d}",
            "element_type": "PARAGRAPH",
            "raw_text": para[:300],
            "source_location": {"paragraph_idx": i + 1},
            "status": "EXTRACTED",
        })

    return {
        "elements": elements,
        "field_candidates": fields,
        "checklist_item_candidates": checklists,
        "evidence_field_candidates": evidence,
    }


# ══════════════════════════════════════════════════════
# 섹션 6~16. 나머지 처리
# ══════════════════════════════════════════════════════

def build_package(doc_id: str, file_name: str, source_path: str,
                  parsed: dict, candidates: dict) -> dict:
    """Document Schema Candidate Package 조립"""
    now = datetime.now(KST).isoformat()

    # 섹션 6: Document Family 후보 (확정 아님)
    doc_family = [{
        "document_family_candidate_id": "DFC-001",
        "candidate_family": "UNKNOWN_DOCUMENT_FAMILY",
        "reason": "자동 확정 금지. Human Review 필요.",
        "status": "CANDIDATE",
    }]

    # 섹션 7-8: 법령 매핑 없음 (자동 확정 금지)
    doc_req_mapping = []

    # 섹션 9: 회사 양식 매핑 없음 (확정 불가)
    company_mapping = []

    # 섹션 12: Residual
    residuals = []
    for el in candidates["elements"]:
        text = el.get("raw_text", "")
        # 필드도 체크도 증빙도 아닌 셀 → residual 아님 (단순 데이터)
        # 병합셀 구조 불명확한 경우만 residual
        loc = el.get("source_location", {})
        if loc.get("rowspan", 1) > 3 or loc.get("colspan", 1) > 10:
            residuals.append({
                "document_residual_id": f"RES-{len(residuals)+1:03d}",
                "raw_text": text[:200],
                "reason": "COMPLEX_MERGED_CELL",
                "source_location": loc,
                "status": "NEEDS_HUMAN_REVIEW",
            })

    # 섹션 13: Human Review Queue
    hrq = []
    hrq.append({
        "review_id": "HRQ-001",
        "target_id": "DFC-001",
        "review_type": "DOCUMENT_FAMILY_CONFIRMATION",
        "description": "문서 유형 확정 필요",
        "status": "PENDING",
    })
    for fc in candidates["field_candidates"]:
        hrq.append({
            "review_id": f"HRQ-FC-{fc['field_candidate_id']}",
            "target_id": fc["field_candidate_id"],
            "review_type": "CANONICAL_FIELD_CONFIRMATION",
            "description": f"필드 '{fc['raw_label'][:50]}' canonical 확정 필요",
            "status": "PENDING",
        })

    # 섹션 11: Validation
    issues = []
    for fc in candidates["field_candidates"]:
        if not fc.get("source_location"):
            issues.append(f"FAIL: {fc['field_candidate_id']} 위치 근거 없음")
    if not candidates["field_candidates"]:
        issues.append("WARN: 추출된 필드 후보 0건")

    validation = {
        "status": "PASS" if not any(i.startswith("FAIL") for i in issues) else "FAIL",
        "issues": issues,
    }

    # 섹션 15: Final Output
    return {
        "_schema_version": "1.0.0",
        "_compiler": "TAI Document Schema Compiler (오염 방지형)",
        "_generated_at": now,

        "document_id": doc_id,
        "file_name": file_name,
        "file_type": "HWP",
        "source_path": source_path,
        "original_text_preserved": True,

        "document_metadata": {
            "table_count": len(parsed["tables"]),
            "paragraph_count": len(parsed["paragraphs"]),
            "total_cells": sum(
                len(cell)
                for t in parsed["tables"]
                for cell in t["rows"]
            ),
            "element_count": len(candidates["elements"]),
        },

        "document_family_candidates": doc_family,
        "field_candidates": candidates["field_candidates"],
        "checklist_item_candidates": candidates["checklist_item_candidates"],
        "evidence_field_candidates": candidates["evidence_field_candidates"],
        "document_requirement_mapping_candidates": doc_req_mapping,
        "company_form_mapping_candidates": company_mapping,
        "residuals": residuals,
        "human_review_queue": hrq,
        "validation": validation,
    }


# ══════════════════════════════════════════════════════
# 메인: HWP 파일 처리 루프
# ══════════════════════════════════════════════════════

def process_one(hwp_path: Path, doc_id: str, source_path: str) -> dict | None:
    """HWP 1건 처리 → Document Schema Candidate Package"""
    with tempfile.TemporaryDirectory() as tmpdir:
        xhtml_dir = Path(tmpdir) / "xhtml"
        xhtml_path = hwp_to_xhtml(hwp_path, xhtml_dir)
        if not xhtml_path:
            return None

        parsed = parse_xhtml(xhtml_path)
        candidates = extract_candidates(parsed, doc_id)
        package = build_package(
            doc_id=doc_id,
            file_name=hwp_path.name,
            source_path=source_path,
            parsed=parsed,
            candidates=candidates,
        )
        return package


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="1건만 테스트")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--file", type=str, default=None, help="특정 HWP 파일 경로")
    args = ap.parse_args()

    print("=" * 70)
    print("  TAI Document Schema Compiler (오염 방지형)")
    print("  작업지시서 16개 섹션 규칙 적용")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        # 단일 파일 처리
        hwp = Path(args.file)
        if not hwp.exists():
            print(f"ERROR: {hwp} 없음")
            sys.exit(1)
        print(f"\n  단일 파일: {hwp}")
        pkg = process_one(hwp, hwp.stem, str(hwp))
        if pkg:
            out = OUTPUT_DIR / f"{hwp.stem}.json"
            out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✓ 출력: {out}")
            print(f"    필드: {len(pkg['field_candidates'])}건")
            print(f"    체크: {len(pkg['checklist_item_candidates'])}건")
            print(f"    증빙: {len(pkg['evidence_field_candidates'])}건")
            print(f"    요소: {pkg['document_metadata']['element_count']}건")
        return

    # form_templates + document_forms에서 HWP 목록 수집
    hwp_files = []

    # form_templates
    ft = sb.table("form_templates").select("form_code,original_storage_path").not_.is_("original_storage_path", "null").execute()
    for r in (ft.data or []):
        local = Path(f"./form_originals_hwp/{r['form_code']}.hwp")
        if local.exists():
            hwp_files.append((local, r["form_code"], f"{BUCKET_SRC}/{r['original_storage_path']}"))

    # document_forms
    df = sb.table("document_forms").select("doc_id,file_url").not_.is_("file_url", "null").eq("has_legal_form", True).execute()
    for r in (df.data or []):
        local = Path(f"./form_originals_hwp/doc_forms/{r['doc_id']}.hwp")
        if local.exists():
            hwp_files.append((local, r["doc_id"], r.get("file_url", "")))

    print(f"\n  로컬 HWP 파일: {len(hwp_files)}건")

    if args.dry_run:
        hwp_files = hwp_files[:1]
        print("  [DRY RUN] 1건만 처리")
    elif args.limit:
        hwp_files = hwp_files[:args.limit]

    print(f"  처리 대상: {len(hwp_files)}건\n")

    stats = {"ok": 0, "fail": 0}

    for i, (hwp_path, doc_id, src) in enumerate(hwp_files, 1):
        print(f"  [{i:3}/{len(hwp_files)}] {doc_id}: {hwp_path.name}")
        pkg = process_one(hwp_path, doc_id, src)
        if pkg:
            out = OUTPUT_DIR / f"{doc_id}.json"
            out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
            fc = len(pkg["field_candidates"])
            cc = len(pkg["checklist_item_candidates"])
            ec = len(pkg["evidence_field_candidates"])
            el = pkg["document_metadata"]["element_count"]
            print(f"    ✓ 필드={fc} 체크={cc} 증빙={ec} 요소={el}")
            stats["ok"] += 1
        else:
            print(f"    ✗ 실패")
            stats["fail"] += 1

    print("\n" + "=" * 70)
    print("  컴파일 결과")
    print("=" * 70)
    print(f"  성공: {stats['ok']}건")
    print(f"  실패: {stats['fail']}건")
    print(f"  출력: {OUTPUT_DIR}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
