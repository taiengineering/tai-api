#!/usr/bin/env python3
"""
document_schema_compiler.py v3 — TAI 오염 방지형 Document Schema Compiler

v2 대비 핵심 개선:
- 구조적 분석: 라벨-입력칸 쌍, 행 패턴, 테이블 목적 분류
- 번호 항목(①~⑳) 전수 추출
- 작성방법 테이블 자동 분리
- DB form_name 활용 Document Family 분류

실행:
  python3 scripts/document_schema_compiler.py --file form_originals_hwp/OSHACT-FORM-001.hwp
  railway run python3 scripts/document_schema_compiler.py
"""
import argparse,json,os,re,subprocess,sys,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from html.parser import HTMLParser

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

SCRIPT_VERSION = "3.1.0"
KST = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("./form_originals_hwp/compiled")

# ═══ HWP → XHTML ═══

def hwp_to_xhtml(hwp_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["hwp5html", str(hwp_path), "--output", str(output_dir)],
                       capture_output=True, timeout=60, check=True)
        x = output_dir / "index.xhtml"
        return x if x.exists() else None
    except Exception as e:
        print(f"    hwp5html 실패: {e}"); return None

# ═══ XHTML 파서 ═══

class XHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables=[]; self.paragraphs=[]
        self._in_table=self._in_td=False
        self._cur_table=self._cur_row=self._cur_cell=None
        self._buf=[]; self._pbuf=[]; self._tidx=self._ridx=self._cidx=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="table":
            self._in_table=True;self._tidx+=1;self._ridx=0
            self._cur_table={"table_idx":self._tidx,"rows":[]}
        elif tag=="tr" and self._in_table:
            self._ridx+=1;self._cidx=0;self._cur_row=[]
        elif tag=="td" and self._in_table:
            self._in_td=True;self._cidx+=1;self._buf=[]
            self._cur_cell={"row":self._ridx,"col":self._cidx,
                "rowspan":int(a.get("rowspan",1)),"colspan":int(a.get("colspan",1)),"text":""}
        elif tag=="p" and not self._in_table: self._pbuf=[]
    def handle_endtag(self,tag):
        if tag=="td" and self._in_td:
            self._in_td=False
            if self._cur_cell:
                self._cur_cell["text"]=re.sub(r'\s+',' '," ".join(self._buf)).strip()
            if self._cur_row is not None: self._cur_row.append(self._cur_cell)
        elif tag=="tr" and self._cur_row is not None:
            if self._cur_table: self._cur_table["rows"].append(self._cur_row)
            self._cur_row=None
        elif tag=="table" and self._in_table:
            self._in_table=False
            if self._cur_table: self.tables.append(self._cur_table)
        elif tag=="p" and not self._in_table:
            t=" ".join(self._pbuf).strip()
            if t: self.paragraphs.append(t)
    def handle_data(self,data):
        c=data.replace("\r","").replace("\n"," ").strip()
        if not c: return
        if self._in_td: self._buf.append(c)
        elif not self._in_table: self._pbuf.append(c)

def parse_xhtml(path):
    p=XHTMLParser(); p.feed(path.read_text(encoding="utf-8",errors="ignore"))
    return {"tables":p.tables,"paragraphs":p.paragraphs}

# ═══ 테이블 목적 분류 ═══

def classify_table_purpose(table):
    """테이블의 전체 텍스트를 보고 목적 분류. 증거 기반."""
    all_text = " ".join(c.get("text","") for r in table["rows"] for c in r)
    if re.search(r'작성방법|작성요령|유의사항|기재요령', all_text):
        return "INSTRUCTION_TABLE"
    return "FORM_TABLE"

# ═══ 셀 분류 ═══

NUMBERED_RE = re.compile(r'^[①-⑳⑴-⒇㉠-㉻]\s*|^\([0-9]+\)\s*|^[0-9]+[\.\)]\s*|^[Ⅰ-Ⅹ]+[\.\s]')
SECTION_RE = re.compile(r'^[Ⅰ-Ⅹ]+\.\s')
PLACEHOLDER_RE = re.compile(r'^\s*$|^_+$|^\.{4,}$|^년\s*월\s*일\s*$|^명\s*$|^%\s*$|^‱\s*$|^원\s*$')

def classify_cell(text, rowspan, colspan):
    t = text.strip()
    if not t: return "EMPTY_CELL"
    if PLACEHOLDER_RE.match(t): return "INPUT_FIELD"
    if re.search(r'[□☐☑✓✗■]', t): return "CHECKBOX"
    if re.search(r'\(서명\s*(또는)?\s*인\)', t): return "SIGNATURE_FIELD"
    if SECTION_RE.match(t): return "SECTION_HEADER"
    if NUMBERED_RE.match(t): return "NUMBERED_LABEL"
    if re.search(r'작성방법|작성요령|유의사항', t): return "INSTRUCTION_TEXT"
    if re.search(r'귀하\s*$', t): return "SUBMIT_TO_FIELD"
    if re.search(r'년\s+월\s+일', t): return "DATE_FIELD"
    if re.search(r'첨부|별첨', t): return "ATTACHMENT_FIELD"
    if re.search(r'^비고$', t): return "REMARKS_FIELD"
    # 짧은 텍스트(≤30자)이고 한글 포함 → 라벨 가능성
    if len(t) <= 30 and re.search(r'[가-힣]', t): return "FIELD_LABEL"
    # 긴 텍스트 → 설명문 or 데이터
    if len(t) > 100: return "DESCRIPTION_TEXT"
    return "DATA_CELL"

# ═══ 라벨-입력칸 쌍 감지 ═══

def detect_label_input_pairs(table):
    """같은 행에서 라벨 셀 다음에 빈/플레이스홀더 셀이 오면 쌍으로 연결"""
    pairs = []
    for row in table["rows"]:
        for i, cell in enumerate(row):
            ctype = classify_cell(cell["text"], cell["rowspan"], cell["colspan"])
            if ctype in ("FIELD_LABEL", "NUMBERED_LABEL"):
                # 다음 셀이 입력칸/빈칸인지 확인
                if i + 1 < len(row):
                    next_cell = row[i + 1]
                    ntype = classify_cell(next_cell["text"], next_cell["rowspan"], next_cell["colspan"])
                    if ntype in ("INPUT_FIELD", "EMPTY_CELL", "DATA_CELL"):
                        pairs.append({
                            "label_cell": cell,
                            "input_cell": next_cell,
                            "label_type": ctype,
                        })
    return pairs

# ═══ 필드 canonical 매핑 ═══

CANONICAL_MAP = [
    (r'사업장명', 'site_name'), (r'사업자\s*등록\s*번호', 'business_registration_no'),
    (r'사업장\s*관리\s*번호', 'site_management_no'), (r'사업개시번호', 'business_start_no'),
    (r'근로자\s*수', 'worker_count'), (r'점검일|작성일|보고일', 'date_field'),
    (r'점검자|작성자|검사자|조사자', 'author_name'), (r'확인자', 'verifier_name'),
    (r'\(서명\s*(또는)?\s*인\)', 'signature'), (r'첨부사진|첨부파일|별첨', 'attachment'),
    (r'^비고$', 'remarks'), (r'조치사항|개선사항|시정조치', 'corrective_action'),
    (r'점검결과|판정|결과', 'inspection_result'), (r'귀하', 'submit_to'),
    (r'보존기간', 'retention_period'), (r'보고번호|접수번호', 'report_no'),
    (r'^업종$|업종명', 'industry_type'), (r'소재지|^주소$', 'address'),
    (r'전화번호|연락처|팩스', 'phone'), (r'^대표자$|대표이사', 'representative'),
    (r'사고사망자\s*수', 'accident_death_count'), (r'질병사망자\s*수', 'disease_death_count'),
    (r'사고재해자\s*수', 'accident_casualty_count'), (r'질병재해자\s*수', 'disease_casualty_count'),
    (r'재해율|산업재해율', 'accident_rate'), (r'사망만인율|만인율', 'death_rate_per_10k'),
    (r'선임일|위촉일', 'appointment_date'), (r'자격증\s*번호|면허\s*번호', 'license_no'),
    (r'허가번호|등록번호|인가번호', 'permit_no'), (r'공사명|공사 명칭', 'construction_name'),
    (r'공사기간|공사 기간', 'construction_period'), (r'공사금액|도급금액', 'construction_amount'),
    (r'발주자|발주처', 'client_name'), (r'시공자|시공업체', 'contractor_name'),
    (r'감리자|감리원', 'supervisor_name'), (r'설계자|설계업체', 'designer_name'),
]

EVIDENCE_MAP = [
    (r'첨부사진|증빙사진|사진첨부', 'PHOTO_EVIDENCE'),
    (r'첨부파일|별첨|첨부서류', 'FILE_ATTACHMENT_EVIDENCE'),
    (r'측정값|측정결과|측정수치', 'MEASUREMENT_EVIDENCE'),
    (r'\(서명\s*(또는)?\s*인\)', 'SIGNATURE_EVIDENCE'),
    (r'확인자|검토자|승인자', 'VERIFIER_EVIDENCE'),
    (r'작성자\s*소속|작성자\s*성명', 'AUTHOR_EVIDENCE'),
    (r'보존기간|보관기간', 'RETENTION_EVIDENCE'),
    (r'귀하|제출처', 'SUBMIT_TO_EVIDENCE'),
    (r'보고번호|접수번호|관리번호', 'REPORT_NO_EVIDENCE'),
]

CHECKLIST_RE = [
    re.compile(p) for p in [
        r'양호\s*/?\s*불량', r'적합\s*/?\s*부적합', r'정상\s*/?\s*이상',
        r'합격\s*/?\s*불합격', r'여부\s*(확인|점검)', r'이상\s*(없|유)',
        r'[□☐]\s*예\s*[□☐]\s*아니', r'해당\s*/?\s*비해당',
    ]
]

def find_canonical(text):
    for pat, canon in CANONICAL_MAP:
        if re.search(pat, text): return canon
    return None

def find_evidence(text):
    for pat, family in EVIDENCE_MAP:
        if re.search(pat, text): return family
    return None

def is_checklist(text):
    return any(p.search(text) for p in CHECKLIST_RE)

# ═══ Document Family (서식명 기반) ═══

FAMILY_RULES = [
    (r'점검|체크|check', "INSPECTION_DOCUMENT_FAMILY"),
    (r'교육|훈련|training|수료', "TRAINING_RECORD_DOCUMENT_FAMILY"),
    (r'보고서|조사표|현황|report|통보서|결과서', "REPORT_DOCUMENT_FAMILY"),
    (r'선임|신고서|해임', "APPOINTMENT_REPORT_DOCUMENT_FAMILY"),
    (r'허가|신청서|계획서', "WORK_PERMIT_DOCUMENT_FAMILY"),
    (r'사고|재해|재난', "ACCIDENT_REPORT_DOCUMENT_FAMILY"),
    (r'기록부|대장|일지|관리대장', "RECORD_RETENTION_DOCUMENT_FAMILY"),
]

def classify_family(form_name):
    families = []
    fn = (form_name or "").lower()
    for pat, fam in FAMILY_RULES:
        if re.search(pat, fn) and fam not in families:
            families.append(fam)
    if not families: families.append("UNKNOWN_DOCUMENT_FAMILY")
    return [{"document_family_candidate_id": f"DFC-{i+1:03d}",
             "candidate_family": f, "reason": f"서식명 '{form_name}' 패턴",
             "status": "CANDIDATE"} for i, f in enumerate(families)]

def classify_origin(source_path):
    if "law.go.kr" in (source_path or "") or "form-originals" in (source_path or ""):
        return {"form_origin_candidate": "OFFICIAL_LEGAL_FORM",
                "reason": "법제처(law.go.kr) 출처", "status": "CANDIDATE"}
    return {"form_origin_candidate": "UNKNOWN_FORM_ORIGIN",
            "reason": "출처 미확인", "status": "NEEDS_HUMAN_REVIEW"}

# ═══ 핵심: 전수 추출 엔진 ═══

def extract_all(parsed, doc_id, file_name, form_name, source_path):
    elements = []; fields = []; checklists = []; evidence = []
    pairs_list = []; residuals = []
    fc=ec=cc=el=0
    seen_evidence = set()
    type_dist = {}

    for table in parsed["tables"]:
        tidx = table["table_idx"]
        purpose = classify_table_purpose(table)

        # 라벨-입력칸 쌍 감지
        table_pairs = detect_label_input_pairs(table)
        pairs_list.extend(table_pairs)

        for row in table["rows"]:
            for cell in row:
                text = cell.get("text","")
                if not text: continue
                el += 1
                etype = classify_cell(text, cell["rowspan"], cell["colspan"])
                loc = {"table_idx":tidx, "table_purpose":purpose,
                       "row":cell["row"], "col":cell["col"],
                       "rowspan":cell["rowspan"], "colspan":cell["colspan"]}

                type_dist[etype] = type_dist.get(etype, 0) + 1
                elements.append({"element_id":f"EL-{el:04d}", "element_type":etype,
                    "raw_text":text[:500], "source_location":loc, "status":"EXTRACTED"})

                # 안내문 셀 자체만 스킵 (테이블 전체 스킵 금지)
                if etype == "INSTRUCTION_TEXT" or etype == "DESCRIPTION_TEXT":
                    continue

                # 번호 항목(①~⑳) → 무조건 필드 후보
                if etype == "NUMBERED_LABEL":
                    fc += 1
                    canon = find_canonical(text) or "numbered_field"
                    fields.append({"field_candidate_id":f"FC-{fc:03d}",
                        "raw_label":text[:300], "canonical_field_candidate":canon,
                        "source_location":loc, "status":"CANDIDATE"})

                # 일반 라벨 → 무조건 필드 후보 (canonical은 보너스)
                elif etype == "FIELD_LABEL":
                    fc += 1
                    canon = find_canonical(text) or "unclassified_field"
                    fields.append({"field_candidate_id":f"FC-{fc:03d}",
                        "raw_label":text[:300], "canonical_field_candidate":canon,
                        "source_location":loc, "status":"CANDIDATE"})

                # 서명란, 날짜란, 비고란, 첨부란, 제출처 → 필드 + 증빙
                elif etype in ("SIGNATURE_FIELD","DATE_FIELD","REMARKS_FIELD",
                               "ATTACHMENT_FIELD","SUBMIT_TO_FIELD"):
                    fc += 1
                    canon = find_canonical(text) or etype.lower().replace("_field","")
                    fields.append({"field_candidate_id":f"FC-{fc:03d}",
                        "raw_label":text[:300], "canonical_field_candidate":canon,
                        "source_location":loc, "status":"CANDIDATE"})

                # 증빙 감지
                ev_fam = find_evidence(text)
                if ev_fam and ev_fam not in seen_evidence:
                    ec += 1; seen_evidence.add(ev_fam)
                    evidence.append({"evidence_field_candidate_id":f"EFC-{ec:03d}",
                        "raw_label":text[:300], "evidence_family":ev_fam,
                        "source_location":loc, "status":"CANDIDATE"})

                # 체크리스트 감지
                if is_checklist(text):
                    cc += 1
                    checklists.append({"checklist_item_candidate_id":f"CIC-{cc:03d}",
                        "raw_text":text[:300], "source_location":loc, "status":"CANDIDATE"})

                # Residual: 복잡 병합셀
                if cell["rowspan"] > 3 or cell["colspan"] > 10:
                    residuals.append({"document_residual_id":f"RES-{len(residuals)+1:03d}",
                        "raw_text":text[:200], "reason":"COMPLEX_MERGED_CELL",
                        "source_location":loc, "status":"NEEDS_HUMAN_REVIEW"})

                # Residual: 긴 미분류 텍스트
                if etype == "DATA_CELL" and len(text) > 150:
                    residuals.append({"document_residual_id":f"RES-{len(residuals)+1:03d}",
                        "raw_text":text[:200], "reason":"LONG_UNCLASSIFIED_TEXT",
                        "source_location":loc, "status":"NEEDS_HUMAN_REVIEW"})

    # 문단
    for i, para in enumerate(parsed["paragraphs"]):
        el += 1
        elements.append({"element_id":f"EL-{el:04d}", "element_type":"PARAGRAPH",
            "raw_text":para[:300], "source_location":{"paragraph_idx":i+1}, "status":"EXTRACTED"})

    # 라벨-입력칸 쌍
    field_pairs = []
    for p in pairs_list:
        field_pairs.append({
            "label": p["label_cell"]["text"][:200],
            "label_type": p["label_type"],
            "input_value": p["input_cell"]["text"][:200] if p["input_cell"]["text"] else "(빈칸)",
            "label_location": {"row":p["label_cell"]["row"], "col":p["label_cell"]["col"]},
            "input_location": {"row":p["input_cell"]["row"], "col":p["input_cell"]["col"]},
        })

    # 문서 Family
    name_for_family = form_name or file_name
    doc_families = classify_family(name_for_family)
    form_origin = classify_origin(source_path)

    # Human Review Queue
    hrq = []
    for df in doc_families:
        hrq.append({"review_id":f"HRQ-{df['document_family_candidate_id']}",
            "target_id":df["document_family_candidate_id"],
            "review_type":"DOCUMENT_FAMILY_CONFIRMATION","status":"PENDING"})
    hrq.append({"review_id":"HRQ-ORIGIN","target_id":"form_origin",
        "review_type":"OFFICIAL_CUSTOM_CONFIRMATION","status":"PENDING"})
    for f in fields:
        hrq.append({"review_id":f"HRQ-{f['field_candidate_id']}",
            "target_id":f["field_candidate_id"],
            "review_type":"CANONICAL_FIELD_CONFIRMATION","status":"PENDING"})
    for c in checklists:
        hrq.append({"review_id":f"HRQ-{c['checklist_item_candidate_id']}",
            "target_id":c["checklist_item_candidate_id"],
            "review_type":"CHECKLIST_CONFIRMATION","status":"PENDING"})
    for r in residuals:
        hrq.append({"review_id":f"HRQ-{r['document_residual_id']}",
            "target_id":r["document_residual_id"],
            "review_type":"RESIDUAL_RESOLUTION","status":"PENDING"})

    # Validation
    issues = []
    if not fields: issues.append("WARN: 필드 후보 0건")
    classified = sum(1 for e in elements if e["element_type"] not in ("DATA_CELL","PARAGRAPH","EMPTY_CELL"))
    total_el = len(elements)
    if total_el > 0:
        ratio = classified / total_el
        if ratio < 0.3: issues.append(f"WARN: 분류율 {ratio:.0%} ({classified}/{total_el})")
    status = "FAIL" if any(i.startswith("FAIL") for i in issues) else "PASS"

    # Audit
    audit = {"compiler_version":SCRIPT_VERSION,"compiled_at":datetime.now(KST).isoformat(),
        "source_file":file_name,"form_name_used":name_for_family,
        "extraction_counts":{"elements":len(elements),"fields":len(fields),
            "checklists":len(checklists),"evidence":len(evidence),
            "field_pairs":len(field_pairs),"residuals":len(residuals)},
        "rollback_possible":True}

    return {
        "_schema_version":"3.0.0","_compiler":f"TAI Document Schema Compiler v{SCRIPT_VERSION}",
        "_generated_at":datetime.now(KST).isoformat(),
        "document_id":doc_id,"file_name":file_name,"file_type":"HWP",
        "form_name":name_for_family,"source_path":source_path,
        "original_text_preserved":True,
        "document_metadata":{"table_count":len(parsed["tables"]),
            "paragraph_count":len(parsed["paragraphs"]),
            "total_cells":sum(len(c) for t in parsed["tables"] for c in t["rows"]),
            "element_count":len(elements),"element_type_distribution":type_dist},
        "form_origin_candidate":form_origin,
        "document_family_candidates":doc_families,
        "field_candidates":fields,
        "field_label_input_pairs":field_pairs,
        "checklist_item_candidates":checklists,
        "evidence_field_candidates":evidence,
        "document_requirement_mapping_candidates":[],
        "company_form_mapping_candidates":[],
        "residuals":residuals,
        "human_review_queue":hrq,
        "validation":{"status":status,"issues":issues},
        "audit":audit,
    }

# ═══ 메인 ═══

def process_one(hwp_path, doc_id, form_name, source_path):
    with tempfile.TemporaryDirectory() as tmp:
        xhtml = hwp_to_xhtml(hwp_path, Path(tmp)/"xhtml")
        if not xhtml: return None
        parsed = parse_xhtml(xhtml)
        return extract_all(parsed, doc_id, hwp_path.name, form_name, source_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--file", type=str, default=None)
    args = ap.parse_args()

    print("="*70)
    print(f"  TAI Document Schema Compiler v{SCRIPT_VERSION}")
    print("  작업지시서 16개 섹션 이행 · 전수 추출")
    print("="*70)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        hwp = Path(args.file)
        if not hwp.exists(): print(f"ERROR: {hwp} 없음"); sys.exit(1)
        pkg = process_one(hwp, hwp.stem, hwp.stem, str(hwp))
        if pkg:
            out = OUTPUT_DIR / f"{hwp.stem}.json"
            out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
            m = pkg["audit"]["extraction_counts"]
            td = pkg["document_metadata"]["element_type_distribution"]
            print(f"\n  ✓ {out}")
            print(f"    필드={m['fields']} 체크={m['checklists']} 증빙={m['evidence']} 요소={m['elements']} 쌍={m['field_pairs']} 잔여={m['residuals']}")
            print(f"    Family: {[d['candidate_family'] for d in pkg['document_family_candidates']]}")
            print(f"    Origin: {pkg['form_origin_candidate']['form_origin_candidate']}")
            print(f"    요소분포: {td}")
            print(f"    Validation: {pkg['validation']['status']}")
            for i in pkg["validation"]["issues"]: print(f"      → {i}")
        return

    # DB 모드
    try:
        from supabase import create_client
        SB_URL = os.environ.get("SUPABASE_URL")
        SB_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY"))
        sb = create_client(SB_URL, SB_KEY)
    except: print("ERROR: DB 연결 필요."); sys.exit(1)

    # form_templates (form_name DB에서 가져옴)
    hwp_files = []
    ft = sb.table("form_templates").select("form_code,form_name,original_storage_path").not_.is_("original_storage_path","null").execute()
    for r in (ft.data or []):
        local = Path(f"./form_originals_hwp/{r['form_code']}.hwp")
        if local.exists():
            hwp_files.append((local, r["form_code"], r.get("form_name",""), f"form-originals/{r['original_storage_path']}"))

    # document_forms (doc_name DB에서 가져옴)
    df = sb.table("document_forms").select("doc_id,doc_name,file_url").not_.is_("file_url","null").eq("has_legal_form",True).execute()
    for r in (df.data or []):
        local = Path(f"./form_originals_hwp/doc_forms/{r['doc_id']}.hwp")
        if local.exists():
            hwp_files.append((local, r["doc_id"], r.get("doc_name",""), r.get("file_url","")))

    print(f"\n  로컬 HWP: {len(hwp_files)}건")
    if args.dry_run: hwp_files=hwp_files[:1]; print("  [DRY RUN] 1건")
    elif args.limit: hwp_files=hwp_files[:args.limit]
    print(f"  처리: {len(hwp_files)}건\n")

    ok=fail=0
    for i,(hp,did,fname,src) in enumerate(hwp_files,1):
        pkg = process_one(hp, did, fname, src)
        if pkg:
            (OUTPUT_DIR/f"{did}.json").write_text(json.dumps(pkg,ensure_ascii=False,indent=2),encoding="utf-8")
            m = pkg["audit"]["extraction_counts"]
            print(f"  [{i:3}/{len(hwp_files)}] {did:30} F={m['fields']:2d} C={m['checklists']:2d} E={m['evidence']:2d} P={m['field_pairs']:2d} R={m['residuals']:2d}")
            ok += 1
        else: print(f"  [{i:3}/{len(hwp_files)}] {did:30} ✗ 실패"); fail += 1

    print(f"\n{'='*70}\n  성공: {ok}건 / 실패: {fail}건\n  출력: {OUTPUT_DIR}/\n{'='*70}")

if __name__ == "__main__": main()
