#!/usr/bin/env python3
"""
collect_form_templates_v2.py — DB raw_xml에서 별지서식 flSeq 추출 → HWP 다운로드

law_content_raw.raw_xml에 이미 최신 법령 XML이 저장되어 있고,
그 안에 <별표단위> 블록의 <별표서식파일링크>/LSW/flDownload.do?flSeq=... 가 포함됨.
외부 API 호출 없이 DB에서 직접 추출.

실행:
  cd ~/Desktop/tai-engineering/tai-api
  railway run python3 scripts/collect_form_templates_v2.py --dry-run
  railway run python3 scripts/collect_form_templates_v2.py
"""
import argparse, os, re, sys, time
from pathlib import Path

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
    print("ERROR: SUPABASE_URL / SUPABASE_KEY 필요. railway run 으로 실행하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "form-originals"
DL_DIR = Path("./form_originals_hwp")
HEADERS_SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
BASE_URL = "https://www.law.go.kr"

# 대상 시행규칙 MST
RULE_MST = {
    "산업안전보건법 시행규칙": "271485",
    "건설기술 진흥법 시행규칙": "279455",
    "건설산업기본법 시행규칙": "282375",
    "고압가스 안전관리법 시행규칙": "278693",
    "위험물안전관리법 시행규칙": "262765",
    "화학물질관리법 시행규칙": "279031",
    "화학물질의 등록 및 평가 등에 관한 법률 시행규칙": "282061",
    "에너지이용 합리화법 시행규칙": "278965",
    "소방시설 설치 및 관리에 관한 법률 시행규칙": "280195",
    "승강기 안전관리법 시행규칙": "268955",
    "전기안전관리법 시행규칙": "279943",
    "석면안전관리법 시행규칙": "278931",
    "시설물의 안전 및 유지관리에 관한 특별법 시행규칙": "282381",
    "소방시설공사업법 시행규칙": "282735",
}


def extract_forms_from_xml(raw_xml: str) -> list[dict]:
    """raw_xml에서 별표단위 블록을 파싱해 서식 정보 추출"""
    forms = []
    # 별표단위 블록 추출 (CDATA 포함 가능하므로 non-greedy 대신 태그 기반)
    blocks = re.split(r'<별표단위\s', raw_xml)
    
    for block in blocks[1:]:  # 첫 번째는 별표단위 앞 텍스트
        # 별표구분 (별표 or 서식)
        m_type = re.search(r'<별표구분>([^<\s]+)', block)
        form_type = m_type.group(1).strip() if m_type else ""
        
        # 별표번호
        m_no = re.search(r'<별표번호>(\d+)', block)
        form_no = m_no.group(1) if m_no else ""
        
        # 별표가지번호
        m_sub = re.search(r'<별표가지번호>(\d+)', block)
        form_sub = m_sub.group(1) if m_sub else "00"
        
        # 별표제목 (CDATA 포함 가능)
        m_title = re.search(r'<별표제목>\s*(?:<!\[CDATA\[(.+?)\]\]>|([^<]*))', block, re.DOTALL)
        form_title = ""
        if m_title:
            form_title = (m_title.group(1) or m_title.group(2) or "").strip()
        
        # HWP 링크
        m_hwp = re.search(r'<별표서식파일링크>\s*([^<\s]+)', block)
        hwp_link = m_hwp.group(1).strip() if m_hwp else ""
        
        # PDF 링크
        m_pdf = re.search(r'<별표서식PDF파일링크>\s*([^<\s]+)', block)
        pdf_link = m_pdf.group(1).strip() if m_pdf else ""
        
        # flSeq 추출
        fl_seq = ""
        if hwp_link:
            m_seq = re.search(r'flSeq=(\d+)', hwp_link)
            fl_seq = m_seq.group(1) if m_seq else ""
        
        forms.append({
            "type": form_type,
            "no": form_no,
            "sub": form_sub,
            "title": form_title[:200],
            "hwp_link": hwp_link,
            "pdf_link": pdf_link,
            "fl_seq": fl_seq,
        })
    
    return forms


def download_hwp(url: str, save_path: Path) -> bool:
    try:
        full_url = url if url.startswith("http") else BASE_URL + url
        resp = requests.get(full_url, timeout=30, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 TAI-Bot"})
        resp.raise_for_status()
        size = len(resp.content)
        if size < 512:
            text = resp.content[:300].decode("utf-8", errors="ignore")
            if "<html" in text.lower():
                print(f"    ✗ HTML 에러 ({size}b)")
                return False
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        print(f"    ✓ 다운로드: {size:,}b → {save_path.name}")
        return True
    except Exception as e:
        print(f"    ✗ 다운로드 실패: {e}")
        return False


def upload_storage(local: Path, path: str) -> bool:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    data = local.read_bytes()
    resp = requests.post(url, headers={**HEADERS_SB, "Content-Type": "application/x-hwp",
                                       "x-upsert": "true"}, data=data)
    if resp.status_code in (200, 201):
        print(f"    ✓ 업로드: {BUCKET}/{path}")
        return True
    print(f"    ✗ 업로드 실패 ({resp.status_code}): {resp.text[:150]}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--law", type=str, default=None, help="특정 법령만")
    args = ap.parse_args()

    print("=" * 70)
    print("  법정서식 HWP 수집기 v2 (DB raw_xml 파싱)")
    print("=" * 70)

    # 1. form_templates 로드
    ft_resp = sb.table("form_templates").select("*").execute()
    ft_list = ft_resp.data or []
    print(f"\n  form_templates: {len(ft_list)}건")

    stats = {"laws": 0, "forms_total": 0, "forms_sik": 0, "matched": 0,
             "dl_ok": 0, "dl_fail": 0, "up_ok": 0}

    all_forms = []  # 전체 서식 CSV용

    # 2. 법령별 raw_xml에서 서식 추출
    for law_name, mst in RULE_MST.items():
        if args.law and args.law not in law_name:
            continue

        # DB에서 raw_xml 조회
        result = sb.rpc("", {}).execute()  # dummy - use SQL instead
        # PostgREST로 raw_xml 가져오기
        lm = sb.table("law_master").select("id,current_version_id").eq("law_mst_no", mst).limit(1).execute()
        if not lm.data:
            print(f"\n[{law_name}] law_master에 없음. 스킵.")
            continue
        
        vid = lm.data[0]["current_version_id"]
        if not vid:
            print(f"\n[{law_name}] current_version_id 없음. 스킵.")
            continue
        
        raw = sb.table("law_content_raw").select("raw_xml").eq("law_version_id", vid).limit(1).execute()
        if not raw.data or not raw.data[0].get("raw_xml"):
            print(f"\n[{law_name}] raw_xml 없음. 스킵.")
            continue

        raw_xml = raw.data[0]["raw_xml"]
        forms = extract_forms_from_xml(raw_xml)
        stats["laws"] += 1
        stats["forms_total"] += len(forms)
        
        sik_forms = [f for f in forms if f["type"] == "서식"]
        byul_forms = [f for f in forms if f["type"] == "별표"]
        stats["forms_sik"] += len(sik_forms)
        
        print(f"\n[{law_name}] 별표 {len(byul_forms)}건 + 서식 {len(sik_forms)}건 = {len(forms)}건")
        
        for f in forms:
            all_forms.append({
                "law_name": law_name,
                "mst": mst,
                **f,
            })

        # 서식만 출력
        for f in sik_forms:
            no_str = f"제{int(f['no'])}호" if f["no"] else ""
            sub_str = f"의{int(f['sub'])}" if f["sub"] and f["sub"] != "00" else ""
            title = f["title"] or "(제목없음)"
            print(f"  서식 {no_str}{sub_str}: {title}")
            print(f"    HWP: {f['hwp_link']}")
            
            # form_templates 매칭 시도
            for ft in ft_list:
                ft_name = ft.get("form_name", "")
                if ft_name and (ft_name in title or title in ft_name):
                    fc = ft["form_code"]
                    print(f"    ★ 매칭: → {fc}")
                    stats["matched"] += 1
                    
                    if args.dry_run:
                        continue
                    
                    if ft.get("original_storage_path"):
                        print(f"    이미 완료. 스킵.")
                        continue
                    
                    # 다운로드
                    local = DL_DIR / f"{fc}.hwp"
                    if not download_hwp(f["hwp_link"], local):
                        stats["dl_fail"] += 1
                        continue
                    stats["dl_ok"] += 1
                    
                    # 업로드
                    sp = f"{fc}/{fc}.hwp"
                    if not upload_storage(local, sp):
                        continue
                    stats["up_ok"] += 1
                    
                    # DB 업데이트
                    new_url = f"{BASE_URL}{f['hwp_link']}"
                    sb.table("form_templates").update({
                        "hwp_url": new_url,
                        "original_storage_path": sp,
                    }).eq("id", ft["id"]).execute()
                    print(f"    ✓ DB 업데이트")
                    break

        time.sleep(0.3)

    # 3. CSV 저장
    csv_path = DL_DIR / "all_bylaw_forms.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8") as cf:
        cf.write("law_name,mst,type,no,sub,title,hwp_link,pdf_link,fl_seq\n")
        for f in all_forms:
            title = f.get("title", "").replace('"', "'")
            law = f.get("law_name", "").replace('"', "'")
            cf.write(f'"{law}",{f["mst"]},{f["type"]},{f["no"]},{f["sub"]},')
            cf.write(f'"{title}",{f.get("hwp_link","")},{f.get("pdf_link","")},{f.get("fl_seq","")}\n')

    # 4. 결과
    print("\n" + "=" * 70)
    print("  수집 결과")
    print("=" * 70)
    print(f"  법령 처리: {stats['laws']}건")
    print(f"  전체 별표+서식: {stats['forms_total']}건")
    print(f"  서식만: {stats['forms_sik']}건")
    print(f"  form_templates 매칭: {stats['matched']}건 / {len(ft_list)}건")
    if not args.dry_run:
        print(f"  다운로드: {stats['dl_ok']} 성공 / {stats['dl_fail']} 실패")
        print(f"  업로드: {stats['up_ok']} 성공")
    print(f"\n  전체 서식 CSV: {csv_path} ({len(all_forms)}건)")
    print("=" * 70)


if __name__ == "__main__":
    main()
