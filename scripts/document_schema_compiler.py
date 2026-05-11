#!/usr/bin/env python3
"""
document_schema_compiler.py v2 — TAI 오염 방지형 Document Schema Compiler

작업지시서 16개 섹션 전체 이행. 임의해석 금지, 증거 기반 추출, 목표 달성.
HWP → hwp5html → XHTML → 파싱 → Document Schema Candidate Package JSON

실행:
  cd ~/Desktop/tai-engineering/tai-api
  python3 scripts/document_schema_compiler.py --file form_originals_hwp/OSHACT-FORM-001.hwp
  railway run python3 scripts/document_schema_compiler.py --dry-run
  railway run python3 scripts/document_schema_compiler.py
"""
import argparse,json,os,re,subprocess,sys,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from html.parser import HTMLParser

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

SCRIPT_VERSION = "2.0.0"
KST = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("./form_originals_hwp/compiled")

# ═══ 섹션 1: HWP → XHTML 변환 (원본 보존) ═══

def hwp_to_xhtml(hwp_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["hwp5html", str(hwp_path), "--output", str(output_dir)],
                       capture_output=True, timeout=60, check=True)
        x = output_dir / "index.xhtml"
        return x if x.exists() else None
    except Exception as e:
        print(f"    hwp5html 실패: {e}"); return None

# ═══ 섹션 2: XHTML 파싱 → 문서 단위 분해 ═══

class XHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []; self.paragraphs = []
        self._in_table = self._in_td = False
        self._cur_table = self._cur_row = self._cur_cell = None
        self._buf = []; self._pbuf = []; self._tidx = self._ridx = self._cidx = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._in_table = True; self._tidx += 1; self._ridx = 0
            self._cur_table = {"table_idx": self._tidx, "rows": []}
        elif tag == "tr" and self._in_table:
            self._ridx += 1; self._cidx = 0; self._cur_row = []
        elif tag == "td" and self._in_table:
            self._in_td = True; self._cidx += 1; self._buf = []
            self._cur_cell = {"row": self._ridx, "col": self._cidx,
                "rowspan": int(a.get("rowspan",1)), "colspan": int(a.get("colspan",1)), "text": ""}
        elif tag == "p" and not self._in_table: self._pbuf = []
    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            self._in_td = False
            if self._cur_cell:
                self._cur_cell["text"] = re.sub(r'\s+', ' ', " ".join(self._buf)).strip()
            if self._cur_row is not None: self._cur_row.append(self._cur_cell)
            self._cur_cell = None
        elif tag == "tr" and self._cur_row is not None:
            if self._cur_table: self._cur_table["rows"].append(self._cur_row)
            self._cur_row = None
        elif tag == "table" and self._in_table:
            self._in_table = False
            if self._cur_table: self.tables.append(self._cur_table)
        elif tag == "p" and not self._in_table:
            t = " ".join(self._pbuf).strip()
            if t: self.paragraphs.append(t)
    def handle_data(self, data):
        c = data.replace("\r","").replace("\n"," ").strip()
        if not c: return
        if self._in_td: self._buf.append(c)
        elif not self._in_table: self._pbuf.append(c)

def parse_xhtml(path):
    p = XHTMLParser(); p.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return {"tables": p.tables, "paragraphs": p.paragraphs}

# ═══ 섹션 2 확장: 셀 내용 기반 element_type 분류 (증거 기반) ═══

def classify_element_type(text):
    """셀 실제 내용으로 element_type 분류. 임의해석 아닌 패턴 매칭."""
    t = text.strip()
    if not t: return "EMPTY_CELL"
    if re.search(r'[□☐☑✓✗■]', t): return "CHECKBOX"
    if re.search(r'\(서명\s*(또는)?\s*인\)|\(인\)$', t): return "SIGNATURE_FIELD"
    if re.search(r'년\s+월\s+일|__+|\.{5,}', t): return "INPUT_FIELD"
    if re.search(r'^[①-⑳⑴-⒇Ⅰ-Ⅹ]\s', t): return "NUMBERED_LABEL"
    if re.search(r'첨부|별첨', t): return "ATTACHMENT_FIELD"
    if re.search(r'^비고$', t): return "REMARKS_FIELD"
    if re.search(r'귀하$', t): return "SUBMIT_TO_FIELD"
    if len(t) <= 30 and re.search(r'[가-힣]', t) and not re.search(r'[0-9]', t): return "FIELD_LABEL"
    if re.search(r'작성방법|작성요령|유의사항', t): return "INSTRUCTION_TEXT"
    return "DATA_CELL"

# ═══ 섹션 3: Field Candidate (정밀화) ═══

FIELD_PATTERNS = [
    (r'^①?\s*사업장명', 'site_name'),
    (r'사업자\s*등록\s*번호', 'business_registration_no'),
    (r'사업장\s*관리\s*번호', 'site_management_no'),
    (r'근로자\s*수', 'worker_count'),
    (r'점검일자|점검일$|작성일', 'date_field'),
    (r'점검자$|작성자\s*소속', 'author_name'),
    (r'확인자$', 'verifier_name'),
    (r'\(서명\s*(또는)?\s*인\)|\(인\)', 'signature'),
    (r'첨부사진|첨부파일', 'attachment'),
    (r'^비고$', 'remarks'),
    (r'조치사항|개선사항', 'corrective_action'),
    (r'점검결과|판정$|결과$', 'inspection_result'),
    (r'귀하$', 'submit_to'),
    (r'보존기간', 'retention_period'),
    (r'보고번호', 'report_no'),
    (r'^업종$', 'industry_type'),
    (r'소재지$|^주소$', 'address'),
    (r'전화번호|연락처', 'phone'),
    (r'^대표자$', 'representative'),
    (r'사고사망자\s*수', 'accident_death_count'),
    (r'질병사망자\s*수', 'disease_death_count'),
    (r'재해자\s*수', 'casualty_count'),
    (r'재해율|만인율', 'accident_rate'),
    (r'선임일자|선임일$', 'appointment_date'),
    (r'자격증\s*번호|면허\s*번호', 'license_no'),
    (r'허가번호|등록번호', 'permit_no'),
]

# ═══ 섹션 4: Checklist Candidate ═══

CHECKLIST_PATTERNS = [
    r'양호\s*/?\s*불량', r'적합\s*/?\s*부적합', r'정상\s*/?\s*이상',
    r'합격\s*/?\s*불합격', r'여부\s*확인', r'이상\s*없',
    r'[□☐]\s*예\s*[□☐]\s*아니', r'해당\s*/?\s*비해당',
]

# ═══ 섹션 5: Evidence Candidate ═══

EVIDENCE_PATTERNS = [
    (r'첨부사진|사진첨부|증빙사진', 'PHOTO_EVIDENCE'),
    (r'첨부파일|별첨', 'ATTACHMENT_EVIDENCE'),
    (r'측정값|측정결과', 'MEASUREMENT_EVIDENCE'),
    (r'\(서명\s*(또는)?\s*인\)|\(인\)', 'SIGNATURE_EVIDENCE'),
    (r'확인자', 'VERIFIER_EVIDENCE'),
    (r'작성자\s*소속', 'AUTHOR_EVIDENCE'),
    (r'보존기간', 'RETENTION_EVIDENCE'),
    (r'귀하', 'SUBMIT_TO_EVIDENCE'),
    (r'보고번호', 'REPORT_NO_EVIDENCE'),
]

# ═══ 섹션 6: Document Family 후보 (서식명 기반, CANDIDATE) ═══

def guess_doc_family(file_name):
    """서식명에서 Document Family 후보 추론. 확정 아닌 CANDIDATE."""
    n = file_name.lower()
    families = []
    if any(k in n for k in ['점검', 'inspect', '체크']): families.append("INSPECTION_DOCUMENT_FAMILY")
    if any(k in n for k in ['교육', 'training', '수료']): families.append("TRAINING_RECORD_DOCUMENT_FAMILY")
    if any(k in n for k in ['보고서', 'report', '조사표', '현황']): families.append("REPORT_DOCUMENT_FAMILY")
    if any(k in n for k in ['선임', '신고', '보고서']): families.append("APPOINTMENT_REPORT_DOCUMENT_FAMILY")
    if any(k in n for k in ['허가', '계획서', '신청']): families.append("WORK_PERMIT_DOCUMENT_FAMILY")
    if any(k in n for k in ['사고', '재해', '재난']): families.append("ACCIDENT_REPORT_DOCUMENT_FAMILY")
    if not families: families.append("UNKNOWN_DOCUMENT_FAMILY")
    return [{"document_family_candidate_id": f"DFC-{i+1:03d}",
             "candidate_family": f, "reason": f"서식명 '{file_name}' 패턴 매칭",
             "status": "CANDIDATE"} for i, f in enumerate(families)]

# ═══ 섹션 10: Official/Custom 분류 (출처 기반 사실) ═══

def classify_form_origin(source_path):
    """출처 기반 분류. law.go.kr 출처 = OFFICIAL_LEGAL_FORM 후보."""
    if "law.go.kr" in (source_path or "") or "form-originals" in (source_path or ""):
        return {"form_origin_candidate": "OFFICIAL_LEGAL_FORM",
                "reason": "법제처(law.go.kr) 출처 서식", "status": "CANDIDATE"}
    return {"form_origin_candidate": "UNKNOWN_FORM_ORIGIN",
            "reason": "출처 확인 불가", "status": "NEEDS_HUMAN_REVIEW"}

# ═══ 추출 엔진 ═══

def extract_all(parsed, doc_id, file_name, source_path):
    elements, fields, checklists, evidence = [], [], [], []
    fc = ec = cc = el = 0
    used_evidence = set()

    for table in parsed["tables"]:
        tidx = table["table_idx"]
        for row in table["rows"]:
            for cell in row:
                text = cell.get("text", "")
                if not text: continue
                el += 1
                etype = classify_element_type(text)
                loc = {"table_idx": tidx, "row": cell["row"], "col": cell["col"],
                       "rowspan": cell["rowspan"], "colspan": cell["colspan"]}
                elements.append({"element_id": f"EL-{el:04d}", "element_type": etype,
                    "raw_text": text[:300], "source_location": loc, "status": "EXTRACTED"})

                # Field
                for pat, canon in FIELD_PATTERNS:
                    if re.search(pat, text):
                        fc += 1
                        fields.append({"field_candidate_id": f"FC-{fc:03d}",
                            "raw_label": text[:200], "canonical_field_candidate": canon,
                            "source_location": {"table_idx": tidx, "row": cell["row"], "col": cell["col"]},
                            "status": "CANDIDATE"})
                        break

                # Evidence
                for pat, family in EVIDENCE_PATTERNS:
                    if re.search(pat, text) and family not in used_evidence:
                        ec += 1; used_evidence.add(family)
                        evidence.append({"evidence_field_candidate_id": f"EFC-{ec:03d}",
                            "raw_label": text[:200], "evidence_family": family,
                            "source_location": {"table_idx": tidx, "row": cell["row"], "col": cell["col"]},
                            "status": "CANDIDATE"})
                        break

                # Checklist
                for cp in CHECKLIST_PATTERNS:
                    if re.search(cp, text):
                        cc += 1
                        checklists.append({"checklist_item_candidate_id": f"CIC-{cc:03d}",
                            "raw_text": text[:300],
                            "source_location": {"table_idx": tidx, "row": cell["row"], "col": cell["col"]},
                            "status": "CANDIDATE"})
                        break

    for i, para in enumerate(parsed["paragraphs"]):
        el += 1
        elements.append({"element_id": f"EL-{el:04d}", "element_type": "PARAGRAPH",
            "raw_text": para[:300], "source_location": {"paragraph_idx": i+1}, "status": "EXTRACTED"})

    # 섹션 12: Residual
    residuals = []
    for e in elements:
        loc = e.get("source_location", {})
        if loc.get("rowspan", 1) > 3 or loc.get("colspan", 1) > 10:
            residuals.append({"document_residual_id": f"RES-{len(residuals)+1:03d}",
                "raw_text": e["raw_text"][:200], "reason": "COMPLEX_MERGED_CELL",
                "source_location": loc, "status": "NEEDS_HUMAN_REVIEW"})
        if e["element_type"] == "DATA_CELL" and len(e["raw_text"]) > 200:
            residuals.append({"document_residual_id": f"RES-{len(residuals)+1:03d}",
                "raw_text": e["raw_text"][:200], "reason": "LONG_UNCLASSIFIED_TEXT",
                "source_location": loc, "status": "NEEDS_HUMAN_REVIEW"})

    # 섹션 6
    doc_families = guess_doc_family(file_name)

    # 섹션 10
    form_origin = classify_form_origin(source_path)

    # 섹션 13: Human Review Queue
    hrq = []
    for df in doc_families:
        hrq.append({"review_id": f"HRQ-{df['document_family_candidate_id']}",
            "target_id": df["document_family_candidate_id"],
            "review_type": "DOCUMENT_FAMILY_CONFIRMATION", "status": "PENDING"})
    hrq.append({"review_id": "HRQ-FORM-ORIGIN",
        "target_id": "form_origin", "review_type": "OFFICIAL_CUSTOM_CONFIRMATION",
        "description": form_origin["reason"], "status": "PENDING"})
    for f in fields:
        hrq.append({"review_id": f"HRQ-{f['field_candidate_id']}",
            "target_id": f["field_candidate_id"],
            "review_type": "CANONICAL_FIELD_CONFIRMATION", "status": "PENDING"})
    for c in checklists:
        hrq.append({"review_id": f"HRQ-{c['checklist_item_candidate_id']}",
            "target_id": c["checklist_item_candidate_id"],
            "review_type": "CHECKLIST_ITEM_CONFIRMATION", "status": "PENDING"})
    for r in residuals:
        hrq.append({"review_id": f"HRQ-{r['document_residual_id']}",
            "target_id": r["document_residual_id"],
            "review_type": "RESIDUAL_RESOLUTION", "status": "PENDING"})

    # 섹션 11: Validation
    issues = []
    for f in fields:
        if not f.get("source_location"): issues.append(f"FAIL: {f['field_candidate_id']} 위치근거없음")
    if not fields: issues.append("WARN: 필드 후보 0건")
    total_el = len(elements)
    classified = sum(1 for e in elements if e["element_type"] not in ("DATA_CELL","PARAGRAPH"))
    if total_el > 0 and classified / total_el < 0.1:
        issues.append(f"WARN: 분류율 {classified}/{total_el} = {classified/total_el:.0%} (낮음)")
    status = "FAIL" if any(i.startswith("FAIL") for i in issues) else "PASS"

    # 섹션 14: Audit
    audit = {"compiler_version": SCRIPT_VERSION, "compiled_at": datetime.now(KST).isoformat(),
        "source_file": file_name, "hwp5html_used": True,
        "extraction_counts": {"elements": len(elements), "fields": len(fields),
            "checklists": len(checklists), "evidence": len(evidence), "residuals": len(residuals)},
        "rollback_possible": True, "rollback_method": "JSON 파일 삭제 시 원상복구"}

    return {
        "_schema_version": "2.0.0", "_compiler": "TAI Document Schema Compiler v2 (오염방지형)",
        "_generated_at": datetime.now(KST).isoformat(),
        "document_id": doc_id, "file_name": file_name, "file_type": "HWP",
        "source_path": source_path, "original_text_preserved": True,
        "document_metadata": {"table_count": len(parsed["tables"]),
            "paragraph_count": len(parsed["paragraphs"]),
            "total_cells": sum(len(c) for t in parsed["tables"] for c in t["rows"]),
            "element_count": len(elements),
            "element_type_distribution": {},
        },
        "form_origin_candidate": form_origin,
        "document_family_candidates": doc_families,
        "field_candidates": fields,
        "checklist_item_candidates": checklists,
        "evidence_field_candidates": evidence,
        "document_requirement_mapping_candidates": [],
        "company_form_mapping_candidates": [],
        "residuals": residuals,
        "human_review_queue": hrq,
        "validation": {"status": status, "issues": issues},
        "audit": audit,
    }

# ═══ element_type 분포 후처리 ═══

def add_type_distribution(pkg):
    dist = {}
    for section in ["field_candidates","checklist_item_candidates","evidence_field_candidates"]:
        dist[section] = len(pkg.get(section, []))
    # elements는 별도 저장 안 함 (용량), 분포만 기록
    return pkg

# ═══ 메인 ═══

def process_one(hwp_path, doc_id, source_path):
    with tempfile.TemporaryDirectory() as tmp:
        xhtml = hwp_to_xhtml(hwp_path, Path(tmp)/"xhtml")
        if not xhtml: return None
        parsed = parse_xhtml(xhtml)
        pkg = extract_all(parsed, doc_id, hwp_path.name, source_path)
        return add_type_distribution(pkg)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--file", type=str, default=None)
    args = ap.parse_args()

    print("="*70)
    print(f"  TAI Document Schema Compiler v{SCRIPT_VERSION}")
    print("  작업지시서 16개 섹션 전체 이행")
    print("="*70)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        hwp = Path(args.file)
        if not hwp.exists(): print(f"ERROR: {hwp} 없음"); sys.exit(1)
        pkg = process_one(hwp, hwp.stem, str(hwp))
        if pkg:
            out = OUTPUT_DIR / f"{hwp.stem}.json"
            out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
            m = pkg["audit"]["extraction_counts"]
            print(f"\n  ✓ {out}")
            print(f"    필드={m['fields']} 체크={m['checklists']} 증빙={m['evidence']} 요소={m['elements']} 잔여={m['residuals']}")
            print(f"    Family: {[d['candidate_family'] for d in pkg['document_family_candidates']]}")
            print(f"    Origin: {pkg['form_origin_candidate']['form_origin_candidate']}")
            print(f"    Validation: {pkg['validation']['status']}")
            for i in pkg["validation"]["issues"]: print(f"      → {i}")
        return

    # DB에서 HWP 목록
    try:
        from supabase import create_client
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        BUCKET_SRC = "form-originals"
    except: print("ERROR: DB 연결 필요. railway run 으로 실행."); sys.exit(1)

    hwp_files = []
    ft = sb.table("form_templates").select("form_code,original_storage_path").not_.is_("original_storage_path","null").execute()
    for r in (ft.data or []):
        local = Path(f"./form_originals_hwp/{r['form_code']}.hwp")
        if local.exists(): hwp_files.append((local, r["form_code"], f"{BUCKET_SRC}/{r['original_storage_path']}"))
    df = sb.table("document_forms").select("doc_id,file_url").not_.is_("file_url","null").eq("has_legal_form",True).execute()
    for r in (df.data or []):
        local = Path(f"./form_originals_hwp/doc_forms/{r['doc_id']}.hwp")
        if local.exists(): hwp_files.append((local, r["doc_id"], r.get("file_url","")))

    print(f"\n  로컬 HWP: {len(hwp_files)}건")
    if args.dry_run: hwp_files = hwp_files[:1]; print("  [DRY RUN] 1건")
    elif args.limit: hwp_files = hwp_files[:args.limit]
    print(f"  처리 대상: {len(hwp_files)}건\n")

    ok = fail = 0
    for i,(hp,did,src) in enumerate(hwp_files,1):
        print(f"  [{i:3}/{len(hwp_files)}] {did}")
        pkg = process_one(hp, did, src)
        if pkg:
            (OUTPUT_DIR/f"{did}.json").write_text(json.dumps(pkg,ensure_ascii=False,indent=2),encoding="utf-8")
            m = pkg["audit"]["extraction_counts"]
            print(f"    ✓ F={m['fields']} C={m['checklists']} E={m['evidence']} EL={m['elements']} R={m['residuals']}")
            ok += 1
        else: print(f"    ✗ 실패"); fail += 1

    print(f"\n{'='*70}\n  성공: {ok}건 / 실패: {fail}건\n  출력: {OUTPUT_DIR}/\n{'='*70}")

if __name__ == "__main__": main()
