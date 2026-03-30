# 별지 서식 코드 자동 파싱 작업 지시서
## 담당: Cursor (백엔드 창)
## 파일: scripts/parse_form_codes.py (신규)

---

## 배경

현재 상황:
- master_building_legal_rules 신고·보고 룰 190개 중 form_code 연결 52.5%
- 나머지 47.5%는 GPT가 수동으로 CSV 수집 → 클로드 회의실 창에서 업데이트 방식

DB에 법령 조문 텍스트가 모두 있음:
- law_paragraph.paragraph_text 안에 "별지 제2호서식" 패턴이 무수히 조회됨
- 시행규칙 1개만에도 111열 해당 패턴 존재 확인

**직접 파싱이 GPT 수동 수집보다 훨씬 빠르고 정확**

---

## 로직 설명

### 파싱 대상
- law_type_code: ENFORCEMENT_RULE, ENFORCEMENT_DECREE
- paragraph_text에 "별지" + "서식" 포함
- REPORT/NOTIFY obligation_type 룰만 업데이트
- 이미 form_code가 있으면 포인트 스킵

### 정규식
```python
FORM_PATTERN = re.compile(r'별지\s*제\s*([\d]+)\s*호\s*(?:의\s*([\d]+)\s*)?\s*서식')
```

### 매칭 비코어
- law_name: master_building_legal_rules.law_name = law_master.law_name
- law_article: article_no(정수) → "제N조" 변환 매칭
- 첫 번째 파싱된 서식코드를 form_code로 채움

---

## STEP 1. 의존성 설치

```bash
pip install supabase --break-system-packages
```

## STEP 2. parse_form_codes.py Supabase 판 파싱 이슈 해결

Supabase Python SDK에서 `LIKE` + `JOIN` 고성능 쿼리는 `execute_sql` RPC로 돌려서 해결:

```python
# supabase_client.py 또는 직접 슬라이스 SQL 실행 사용
from db.supabase_client import get_supabase

def get_form_paragraphs(law_name: str):
    """실제 DB에서 파싱: 해당 법령의 별지서식 언급 조문 조회"""
    sb = get_supabase()
    # Raw SQL로 JOIN+WHERE 한번에 조회
    result = sb.rpc('exec_sql', {'query': f"""
        SELECT la.article_no, lp.paragraph_text
        FROM law_master lm
        JOIN law_version lv ON lv.law_id=lm.id AND lv.is_current=true
        JOIN law_article la ON la.law_version_id=lv.id
        JOIN law_paragraph lp ON lp.article_id=la.id
        WHERE lm.law_name = '{law_name}'
          AND lp.paragraph_text LIKE '%별지%호서식%'
        ORDER BY la.article_no
    """}).execute()
    return result.data or []
```

대안: `supabase.execute_sql` 또는 `psycopg2` 직접 연결 (DATABASE_URL)

```python
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("""
    SELECT lm.law_name, la.article_no, lp.paragraph_text
    FROM law_master lm
    JOIN law_version lv ON lv.law_id=lm.id AND lv.is_current=true
    JOIN law_article la ON la.law_version_id=lv.id
    JOIN law_paragraph lp ON lp.article_id=la.id
    WHERE lm.law_type_code IN ('ENFORCEMENT_RULE','ENFORCEMENT_DECREE')
      AND lp.paragraph_text LIKE '%별지%호서식%'
    ORDER BY lm.law_name, la.article_no
""")
rows = cur.fetchall()
```

## STEP 3. 실제 실행 (검증 먼저)

```bash
# Dry-run: DB 수정 없이 결과만 확인
DATABASE_URL=postgresql://... python3 scripts/parse_form_codes.py --dry-run

# 특정 법령만 테스트
python3 scripts/parse_form_codes.py --dry-run --law "산업안전보건법 시행규칙"
```

## STEP 4. 예상 결과 (dry-run)

```
=== DRY-RUN ===
업데이트 (예상): 45개
스킵(이미 연결): 30개

[DRY] [산업안전보건법 시행규칙] 제11조 → 별지 제2호서식
[DRY] [산업안전보건법 시행규칙] 제16조 → 별지 제6호서식
...
```

## STEP 5. 실제 업데이트

```bash
# dry-run 결과 확인 후 실행
python3 scripts/parse_form_codes.py
```

## STEP 6. 결과를 회의실 창에 보고

```bash
# 첨부 템플릿
echo "파싱 결과:"
echo "- 업데이트 완료: N개"
echo "- DB form_code 연결 전: 96개"
echo "- DB form_code 연결 후: M개"
```

---

## 주의사항

1. **조문 번호 변환**: DB article_no는 정수(7 → "제7조")
2. **여러 서식**: 한 항에 서식이 여러 개 언급될 수 있음 → 첫 번째만 form_code 연결, 나머지는 obligation_summary에 로깅
3. **오탐매칭 대안**: `중요한 고시로` 등 선임 관련 서식은 obligation_type=APPOINT 제외
4. **기연결 보호**: form_code != '' 인 룰는 무조건 스킵
5. **플로우**: dry-run 먼저 실행 후 회의실 창에 보고, 승인 후 실제 업데이트

---

## 완료 기준
- [ ] parse_form_codes.py dry-run 성공
- [ ] 예상 업데이트 건수 회의실 창에 보고
- [ ] 승인 후 실제 업데이트 실행
- [ ] DB form_code 연결률 확인 (목표: 70%+)
