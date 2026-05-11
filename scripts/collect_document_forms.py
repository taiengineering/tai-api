#!/usr/bin/env python3
"""
collect_document_forms.py — document_forms 138건 ↔ CSV 1,015건 매칭 → HWP 다운로드

1) all_bylaw_forms.csv (1,015건 서식 URL) 로드
2) document_forms (has_legal_form=true, 138건) DB 조회
3) 법령+서식명 정규화 매칭
4) HWP 다운로드 → form-originals 버킷 업로드 → document_forms.file_url 업데이트

실행:
  cd ~/Desktop/tai-engineering/tai-api
  railway run python3 scripts/collect_document_forms.py --dry-run
  railway run python3 scripts/collect_document_forms.py
"""
import argparse, csv, os, re, sys, time, unicodedata
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
    print("ERROR: railway run 으로 실행하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "form-originals"
BASE_URL = "https://www.law.go.kr"
DL_DIR = Path("./form_originals_hwp/doc_forms")
CSV_PATH = Path("./form_originals_hwp/all_bylaw_forms.csv")
HEADERS_SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# law_ref → CSV law_name 매핑
LAW_REF_MAP = {
    "산안법": "산업안전보건법 시행규칙",
    "산업안전보건법": "산업안전보건법 시행규칙",
    "안전보건규칙": "산업안전보건법 시행규칙",
    "건설기술진흥법": "건설기술 진흥법 시행규칙",
    "건설산업기본법": "건설산업기본법 시행규칙",
    "고압가스안전관리법": "고압가스 안전관리법 시행규칙",
    "위험물안전관리법": "위험물안전관리법 시행규칙",
    "화학물질관리법": "화학물질관리법 시행규칙",
    "화학물질등록평가법": "화학물질의 등록 및 평가 등에 관한 법률 시행규칙",
    "에너지이용합리화법": "에너지이용 합리화법 시행규칙",
    "소방시설법": "소방시설 설치 및 관리에 관한 법률 시행규칙",
    "승강기안전관리법": "승강기 안전관리법 시행규칙",
    "전기안전관리법": "전기안전관리법 시행규칙",
    "석면안전관리법": "석면안전관리법 시행규칙",
    "시설물안전법": "시설물의 안전 및 유지관리에 관한 특별법 시행규칙",
    "중대재해처벌법": None,  # 서식 없음
}


def normalize(s: str) -> str:
    """매칭용 정규화: 공백/특수문자 제거, 가운뎃점 통일"""
    s = s.replace("·", "").replace("ㆍ", "").replace("•", "")
    s = s.replace(" ", "").replace("\u3000", "")
    s = re.sub(r'[(\[\{].*?[)\]\}]', '', s)  # 괄호 내용 제거
    s = s.strip()
    return s


def extract_law_key(law_ref: str) -> str:
    """law_ref에서 법령 키워드 추출"""
    for key in LAW_REF_MAP:
        if key in law_ref:
            return key
    return ""


def load_csv(path: Path) -> list[dict]:
    """all_bylaw_forms.csv 로드"""
    forms = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("type") == "서식":  # 별표 제외
                forms.append(row)
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
                return False
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        print(f"      ✓ {size:,}b → {save_path.name}")
        return True
    except Exception as e:
        print(f"      ✗ 다운로드 실패: {e}")
        return False


def upload_storage(local: Path, path: str) -> bool:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    data = local.read_bytes()
    resp = requests.post(url, headers={**HEADERS_SB, "Content-Type": "application/x-hwp",
                                       "x-upsert": "true"}, data=data)
    if resp.status_code in (200, 201):
        return True
    print(f"      ✗ 업로드 실패 ({resp.status_code})")
    return False


def find_best_match(doc_name: str, law_key: str, csv_forms: list[dict]) -> dict | None:
    """document_forms의 doc_name과 CSV 서식명을 매칭"""
    csv_law_name = LAW_REF_MAP.get(law_key)
    if not csv_law_name:
        return None

    # 1차: 같은 법령의 서식만 필터
    candidates = [f for f in csv_forms if csv_law_name in f.get("law_name", "")]
    if not candidates:
        return None

    doc_norm = normalize(doc_name)

    # 2차: 정규화 후 포함 관계 매칭
    for c in candidates:
        c_norm = normalize(c.get("title", ""))
        if doc_norm and c_norm:
            if doc_norm in c_norm or c_norm in doc_norm:
                return c

    # 3차: 핵심 키워드 매칭 (3글자 이상 연속 일치)
    for c in candidates:
        c_norm = normalize(c.get("title", ""))
        # 긴 쪽에서 짧은 쪽 부분문자열 검사
        short, long_ = sorted([doc_norm, c_norm], key=len)
        if len(short) >= 3 and short in long_:
            return c

    # 4차: 공통 글자 비율
    best = None
    best_ratio = 0
    for c in candidates:
        c_norm = normalize(c.get("title", ""))
        if not c_norm or not doc_norm:
            continue
        common = sum(1 for ch in doc_norm if ch in c_norm)
        ratio = common / max(len(doc_norm), len(c_norm))
        if ratio > best_ratio and ratio >= 0.6:
            best_ratio = ratio
            best = c

    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    print("=" * 70)
    print("  document_forms 법정서식 HWP 수집기")
    print("=" * 70)

    # 1. CSV 로드
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} 없음. collect_form_templates_v2.py --dry-run 먼저 실행.")
        sys.exit(1)
    csv_forms = load_csv(CSV_PATH)
    print(f"\n  CSV 서식: {len(csv_forms)}건 (별표 제외)")

    # 2. document_forms 조회
    resp = sb.table("document_forms").select(
        "id,doc_id,doc_name,law_ref,file_url,has_legal_form,category"
    ).eq("has_legal_form", True).order("category").execute()
    doc_forms = resp.data or []
    print(f"  document_forms (has_legal_form=true): {len(doc_forms)}건")

    # 이미 file_url 있는 것 필터
    todo = [d for d in doc_forms if not d.get("file_url")]
    skip = len(doc_forms) - len(todo)
    if skip:
        print(f"  이미 완료: {skip}건 스킵")
    if args.limit:
        todo = todo[:args.limit]
    print(f"  처리 대상: {len(todo)}건\n")

    # 3. 매칭 + 다운로드
    stats = {"matched": 0, "unmatched": 0, "dl_ok": 0, "dl_fail": 0, "up_ok": 0}
    unmatched_list = []

    for i, doc in enumerate(todo, 1):
        doc_id = doc["doc_id"]
        doc_name = doc["doc_name"]
        law_ref = doc["law_ref"]
        law_key = extract_law_key(law_ref)

        match = find_best_match(doc_name, law_key, csv_forms)

        if match:
            stats["matched"] += 1
            title = match.get("title", "")[:50]
            hwp_link = match.get("hwp_link", "")
            fl_seq = match.get("fl_seq", "")
            print(f"  [{i:3}/{len(todo)}] ✓ {doc_name[:35]:35} → {title}")

            if args.dry_run:
                continue

            # 다운로드
            local = DL_DIR / f"{doc_id}.hwp"
            if not download_hwp(hwp_link, local):
                stats["dl_fail"] += 1
                continue
            stats["dl_ok"] += 1

            # 업로드
            sp = f"doc_forms/{doc_id}.hwp"
            if not upload_storage(local, sp):
                continue
            stats["up_ok"] += 1

            # DB 업데이트
            new_url = f"{BASE_URL}{hwp_link}"
            sb.table("document_forms").update({
                "file_url": new_url,
            }).eq("id", doc["id"]).execute()

            time.sleep(0.3)
        else:
            stats["unmatched"] += 1
            unmatched_list.append((doc_id, doc_name, law_ref))
            print(f"  [{i:3}/{len(todo)}] ✗ {doc_name[:35]:35} ({law_ref})")

    # 4. 결과
    print("\n" + "=" * 70)
    print("  수집 결과")
    print("=" * 70)
    print(f"  매칭 성공: {stats['matched']}건")
    print(f"  매칭 실패: {stats['unmatched']}건")
    if not args.dry_run:
        print(f"  다운로드: {stats['dl_ok']} 성공 / {stats['dl_fail']} 실패")
        print(f"  업로드: {stats['up_ok']} 성공")

    if unmatched_list:
        print(f"\n  미매칭 목록 ({len(unmatched_list)}건):")
        for did, dname, lref in unmatched_list:
            print(f"    {did}: {dname} ({lref})")

    # 5. 미매칭 CSV 저장
    if unmatched_list:
        um_path = DL_DIR / "unmatched_forms.csv"
        um_path.parent.mkdir(parents=True, exist_ok=True)
        with open(um_path, "w", encoding="utf-8") as f:
            f.write("doc_id,doc_name,law_ref\n")
            for did, dname, lref in unmatched_list:
                f.write(f'{did},"{dname}","{lref}"\n')
        print(f"\n  미매칭 CSV: {um_path}")

    print("=" * 70)


if __name__ == "__main__":
    main()
