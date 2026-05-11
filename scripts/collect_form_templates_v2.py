#!/usr/bin/env python3
"""
collect_form_templates_v2.py — 법제처 오픈API로 별지서식 HWP 자동 수집

법제처 DRF API의 '별표서식' 엔드포인트로 최신 bylSeq를 동적 조회한 뒤
HWP 다운로드 → Supabase form-originals 버킷 업로드 → DB 업데이트.

bylSeq가 법령 개정마다 변경되므로 하드코딩 URL 대신 API 동적 조회 사용.

실행:
  cd ~/Desktop/tai-engineering/tai-api
  railway run python3 scripts/collect_form_templates_v2.py --dry-run
  railway run python3 scripts/collect_form_templates_v2.py
"""
import argparse, os, re, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from supabase import create_client

# ── env ──
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
)
LAW_OC = os.environ.get("LAW_API_OC", "taieng")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_KEY 필요. railway run 으로 실행하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "form-originals"
DL_DIR = Path("./form_originals_hwp")
HEADERS_SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# ── 대상 시행규칙 MST (law_master에서 조회한 값) ──
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


def fetch_bylaw_forms(mst: str) -> list[dict]:
    """법제처 DRF API로 해당 법령의 별표서식 목록 조회 (bylSeq 포함)"""
    url = "http://www.law.go.kr/DRF/lawService.do"
    params = {"OC": LAW_OC, "target": "bylSc", "MST": mst, "type": "XML"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    API 오류: {e}")
        return []

    forms = []
    try:
        root = ET.fromstring(resp.content)
        for item in root.iter("bylSc"):  # 또는 root.findall(".//bylSc")
            seq = (item.findtext("bylSeq") or "").strip()
            name = (item.findtext("bylNm") or item.findtext("서식명") or "").strip()
            btype = (item.findtext("bylType") or item.findtext("구분") or "").strip()
            if seq:
                forms.append({"bylSeq": seq, "name": name, "type": btype})
    except ET.ParseError:
        # XML이 아닐 수 있음 — HTML 에러 페이지 등
        print(f"    XML 파싱 실패. 응답 시작: {resp.text[:200]}")
    return forms


def download_hwp(bylseq: str, save_path: Path) -> bool:
    """bylSeq로 HWP 다운로드"""
    url = f"https://www.law.go.kr/LSW/bylFileP.do?bylSeq={bylseq}&fileType=hwp"
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 TAI-Bot"})
        resp.raise_for_status()
        size = len(resp.content)
        if size < 512:
            text = resp.content[:300].decode("utf-8", errors="ignore")
            if "<html" in text.lower() or "에러" in text:
                print(f"    ✗ HTML 에러 응답 ({size}b). 스킵.")
                return False
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        print(f"    ✓ 다운로드: {size:,}b → {save_path.name}")
        return True
    except Exception as e:
        print(f"    ✗ 다운로드 실패: {e}")
        return False


def upload_storage(local: Path, path: str) -> bool:
    """Supabase Storage 업로드"""
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    data = local.read_bytes()
    resp = requests.post(url, headers={**HEADERS_SB, "Content-Type": "application/x-hwp",
                                       "x-upsert": "true"}, data=data)
    if resp.status_code in (200, 201):
        print(f"    ✓ 업로드: {BUCKET}/{path}")
        return True
    print(f"    ✗ 업로드 실패 ({resp.status_code}): {resp.text[:150]}")
    return False


def update_form_templates(bylseq_old: str, bylseq_new: str, storage_path: str):
    """form_templates 테이블의 bylseq, hwp_url, original_storage_path 업데이트"""
    new_url = f"https://www.law.go.kr/LSW/bylFileP.do?bylSeq={bylseq_new}&fileType=hwp"
    sb.table("form_templates").update({
        "bylseq": bylseq_new,
        "hwp_url": new_url,
        "original_storage_path": storage_path,
    }).eq("bylseq", bylseq_old).execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="API 조회만, 다운로드 안 함")
    ap.add_argument("--law", type=str, default=None, help="특정 법령만 (예: 산업안전보건법)")
    ap.add_argument("--all-forms", action="store_true", help="form_templates 11건 외에 전체 서식도 수집")
    args = ap.parse_args()

    print("=" * 70)
    print("  법정서식 HWP 수집기 v2 (법제처 DRF API 동적 조회)")
    print("=" * 70)

    # 1. form_templates의 기존 bylSeq 로드 (매칭용)
    ft_resp = sb.table("form_templates").select("form_code,form_name,bylseq,original_storage_path").execute()
    ft_map = {r["bylseq"]: r for r in (ft_resp.data or []) if r.get("bylseq")}
    print(f"\n  form_templates: {len(ft_map)}건 (기존 bylSeq 매칭 대상)")

    stats = {"api_ok": 0, "api_fail": 0, "forms_found": 0, "matched": 0,
             "dl_ok": 0, "dl_fail": 0, "up_ok": 0, "skip": 0}

    # 2. 법령별 API 조회
    targets = RULE_MST.items()
    if args.law:
        targets = [(k, v) for k, v in RULE_MST.items() if args.law in k]

    all_forms = []  # (법령명, bylSeq, 서식명, type) 수집

    for law_name, mst in targets:
        print(f"\n[{law_name}] MST={mst}")
        forms = fetch_bylaw_forms(mst)
        if not forms:
            stats["api_fail"] += 1
            continue
        stats["api_ok"] += 1

        # 서식만 필터 (별표 제외, 또는 전부 포함)
        form_items = [f for f in forms if "서식" in f.get("type", "") or "서식" in f.get("name", "")]
        if not form_items:
            form_items = forms  # 서식 구분 안 되면 전체

        stats["forms_found"] += len(form_items)
        print(f"  → 서식 {len(form_items)}건 발견")

        for f in form_items:
            seq = f["bylSeq"]
            name = f["name"]
            ftype = f.get("type", "")
            all_forms.append((law_name, seq, name, ftype))

            # form_templates 매칭 체크 (서식명 유사도)
            matched_ft = None
            for old_seq, ft in ft_map.items():
                # 이름 부분 매칭
                ft_name = ft.get("form_name", "")
                if ft_name and (ft_name in name or name in ft_name):
                    matched_ft = ft
                    break

            if matched_ft:
                stats["matched"] += 1
                old_seq = matched_ft["bylseq"]
                fc = matched_ft["form_code"]
                print(f"  ★ 매칭: {name} → {fc} (old={old_seq} → new={seq})")

                if args.dry_run:
                    continue

                if matched_ft.get("original_storage_path"):
                    print(f"    이미 업로드됨. 스킵.")
                    stats["skip"] += 1
                    continue

                # 다운로드
                local = DL_DIR / f"{fc}.hwp"
                if not download_hwp(seq, local):
                    stats["dl_fail"] += 1
                    continue
                stats["dl_ok"] += 1

                # 업로드
                sp = f"{fc}/{fc}.hwp"
                if not upload_storage(local, sp):
                    continue
                stats["up_ok"] += 1

                # DB 업데이트
                update_form_templates(old_seq, seq, sp)
                print(f"    ✓ DB 업데이트 완료")
            else:
                if args.all_forms:
                    print(f"  ○ 미매칭 서식: [{ftype}] {name} (bylSeq={seq})")

        time.sleep(0.5)  # API 부하 방지

    # 3. 결과 출력
    print("\n" + "=" * 70)
    print("  수집 결과")
    print("=" * 70)
    print(f"  API 조회: {stats['api_ok']} 성공 / {stats['api_fail']} 실패")
    print(f"  서식 발견: {stats['forms_found']}건")
    print(f"  form_templates 매칭: {stats['matched']}건 / {len(ft_map)}건")
    if not args.dry_run:
        print(f"  다운로드: {stats['dl_ok']} 성공 / {stats['dl_fail']} 실패")
        print(f"  업로드: {stats['up_ok']} 성공")
        print(f"  스킵(이미완료): {stats['skip']}건")

    # 4. 전체 서식 목록 CSV 저장 (다른 260건 매핑용)
    csv_path = DL_DIR / "all_bylaw_forms.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8") as cf:
        cf.write("law_name,bylSeq,form_name,form_type\n")
        for law, seq, name, ftype in all_forms:
            cf.write(f'"{law}",{seq},"{name}","{ftype}"\n')
    print(f"\n  전체 서식 목록 CSV: {csv_path} ({len(all_forms)}건)")
    print("  → 이 CSV로 document_forms 260건과 매칭 가능")
    print("=" * 70)


if __name__ == "__main__":
    main()
