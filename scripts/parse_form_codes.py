"""
parse_form_codes.py
===================
법령 조문 텍스트에서 "별지 제 N호서식" 패턴을 자동 추캜하여
master_building_legal_rules.form_code 업데이트

실행:
    python3 scripts/parse_form_codes.py
    python3 scripts/parse_form_codes.py --dry-run   # DB 수정 없이 판단만
    python3 scripts/parse_form_codes.py --law "산업안전보건법 시행규칙"  # 특정 법령만
"""

import os
import re
import sys
import argparse
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# 별지 서식 코드 패턴
# 예: 별지 제2호서식, 별지 제2호의 2서식, 별지 제48호의 2서식
FORM_PATTERN = re.compile(r'별지\s*제\s*([\d]+)\s*호\s*(?:의\s*([\d]+)\s*)?\s*서식')

# 조문 텍스트에서 제제출/신고 의무 키워드
OBLIGATION_KEYWORDS = [
    '제출', '신고', '보고', '신청', '작성', '체출',
    '등록', '신고서', '신청서', '보고서', '미리신고',
]


def extract_form_codes(text: str) -> list[str]:
    """
    조문 텍스트에서 별지 서식 코드 모두 추출
    예: ["별지 제2호서식", "별지 제3호서식"]
    """
    results = []
    for m in FORM_PATTERN.finditer(text):
        num = m.group(1)
        sub = m.group(2)
        if sub:
            code = f"별지 제{num}호의{sub}서식"
        else:
            code = f"별지 제{num}호서식"
        if code not in results:
            results.append(code)
    return results


def has_obligation_keyword(text: str) -> bool:
    """REPORT/NOTIFY 의무 관련 텍스트인지 판단"""
    return any(kw in text for kw in OBLIGATION_KEYWORDS)


def normalize_article_no(article_no) -> str:
    """DB의 article_no(정수) → "제N조" 형식 변환"""
    try:
        return f"제{int(article_no)}조"
    except (TypeError, ValueError):
        return str(article_no)


def run(dry_run=False, target_law=None):
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[개시] dry_run={dry_run}, target_law={target_law or '전체'}")

    # 1. 법령 목록 조회
    law_q = sb.table("law_master").select("id, law_name, law_type_code")\
        .in_("law_type_code", ["ENFORCEMENT_RULE", "ENFORCEMENT_DECREE"])
    if target_law:
        law_q = law_q.ilike("law_name", f"%{target_law}%")
    laws = law_q.execute().data or []
    print(f"대상 법령: {len(laws)}개")

    total_updated = 0
    total_skipped = 0
    results_log = []

    for law in laws:
        law_id = law["id"]
        law_name = law["law_name"]

        # 2. 현행 버전 조회
        ver_res = sb.table("law_version").select("id")\
            .eq("law_id", law_id).eq("is_current", True).limit(1).execute()
        if not ver_res.data:
            continue
        ver_id = ver_res.data[0]["id"]

        # 3. 별지서식이 언급된 조문+항 조회
        para_res = sb.rpc("sql_exec_for_form_parse", {}).execute()  # fallback to direct query
        # Supabase python에서는 LIKE 스타일로 직접 접근
        arts_res = sb.table("law_article").select("id, article_no")\
            .eq("law_version_id", ver_id).execute()
        articles = arts_res.data or []

        for art in articles:
            art_id = art["id"]
            art_no_raw = art["article_no"]
            art_no_str = normalize_article_no(art_no_raw)  # "제11조"

            # 4. 해당 조문의 항 텍스트 조회
            para_res = sb.table("law_paragraph").select("paragraph_text")\
                .eq("article_id", art_id).execute()
            paras = para_res.data or []

            for para in paras:
                text = para.get("paragraph_text", "") or ""
                if "별지" not in text or "서식" not in text:
                    continue
                if not has_obligation_keyword(text):
                    continue

                form_codes = extract_form_codes(text)
                if not form_codes:
                    continue

                # 5. master_building_legal_rules에서 해당 법령+조문 룰 찾기
                primary_form = form_codes[0]  # 첫 번째 서식이 주 서식

                rules_res = sb.table("master_building_legal_rules")\
                    .select("id, rule_id, law_article, obligation_type, form_code, obligation_summary")\
                    .eq("law_name", law_name)\
                    .eq("law_article", art_no_str)\
                    .eq("is_active", True)\
                    .in_("obligation_type", ["REPORT", "NOTIFY"])\
                    .execute()
                rules = rules_res.data or []

                for rule in rules:
                    if rule.get("form_code"):  # 이미 연결된 것은 스킵
                        total_skipped += 1
                        continue

                    log_entry = {
                        "law": law_name,
                        "article": art_no_str,
                        "rule_id": rule["rule_id"],
                        "form_code": primary_form,
                        "all_forms": form_codes,
                        "text_snippet": text[:100],
                    }
                    results_log.append(log_entry)

                    if not dry_run:
                        update_data = {"form_code": primary_form}
                        # 의무요약에 서식 코드 추가
                        existing_summary = rule.get("obligation_summary", "") or ""
                        if primary_form not in existing_summary:
                            update_data["obligation_summary"] = existing_summary.rstrip() + f" — {primary_form}"
                        sb.table("master_building_legal_rules")\
                            .update(update_data)\
                            .eq("id", rule["id"])\
                            .execute()
                        total_updated += 1
                    else:
                        total_updated += 1  # dry_run에서는 예상 수치
                    break  # 룰당 첫 매칭만 1개

    # 6. 결과 출력
    print(f"\n{'=== DRY-RUN ===' if dry_run else '=== 실제 업데이트 ==='} ")
    print(f"업데이트 {'(예상)' if dry_run else ''}: {total_updated}개")
    print(f"스킵(이미 연결): {total_skipped}개")
    print()
    for entry in results_log:
        status = "[DRY]" if dry_run else "[OK]"
        print(f"{status} [{entry['law']}] {entry['article']} → {entry['form_code']}")
        if len(entry['all_forms']) > 1:
            print(f"      추가 서식: {entry['all_forms'][1:]}")
        print(f"      텍스트: {entry['text_snippet']}...")

    return total_updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="별지 서식 코드 자동 파싱")
    parser.add_argument("--dry-run", action="store_true", help="DB 수정 없이 예상만 표시")
    parser.add_argument("--law", type=str, default=None, help="특정 법령명 필터 (부분 일치)")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL, SUPABASE_SERVICE_KEY 환경변수 필요")
        sys.exit(1)

    run(dry_run=args.dry_run, target_law=args.law)
