# Cursor 작업 체크리스트 — Phase A-2 검증 (2026-04-23)

목표: v5.8.0 엔진이 조문 본문을 정상 반환하는지 검증.

추정 소요 시간: 15-25분

---

## ☑ Task 1: 코드 동기화

```bash
cd ~/dev/tai-api
git pull origin main

# 최신 커밋 확인
git log --oneline -3
# a59a6dfc  feat(engine): Phase A-2 - 조문 본문 통합 완료 (v5.8.0)
# f1fc543b  feat(engine): Phase A - 조문 본문 연결 (v5.8.0)
# 7a705c4d  docs: 내부 키 체계 구축 완료
```

---

## ☑ Task 2: Import 검증 (30초)

새 모듈이 정상인지 빠르게 확인:

```bash
set -a; source .env; set +a

python3 -c "
from services.legal_article_loader import fetch_article_contexts, classify_law_system
from services.legal_format import format_rule_result_db, _classify_rules_db
from services.legal_step1_builder import build_step1_result_data
from services.legal_runtime import _save_diagnosis_result, run_apply_engine_runtime
from routers.legal_engine import ENGINE_VERSION
assert ENGINE_VERSION == '5.8.0', f'버전 불일치: {ENGINE_VERSION}'
print(f'✅ 모든 import 성공, ENGINE_VERSION={ENGINE_VERSION}')
"
```

예상 출력:
```
✅ 모든 import 성공, ENGINE_VERSION=5.8.0
```

---

## ☑ Task 3: 헬퍼 단위 테스트

`fetch_article_contexts`가 실제 매핑을 잘 가져오는지 확인:

```bash
python3 -c "
from db.supabase_client import get_supabase
from services.legal_article_loader import fetch_article_contexts

sb = get_supabase()
# master_building_legal_rules에서 rule_id 몇 개 가져오기
rules = sb.table('master_building_legal_rules').select('rule_id').limit(5).execute().data
rule_ids = [r['rule_id'] for r in rules]
print(f'테스트 rule_ids: {rule_ids}')

ctx = fetch_article_contexts(sb, rule_ids)
print(f'매핑된 룰 수: {len(ctx)}')
for rid, info in list(ctx.items())[:2]:
    print(f'  {rid}:')
    print(f'    키: {info[\"article_internal_key\"]}')
    print(f'    체계: {info[\"law_system\"]}')
    print(f'    제목: {info[\"article_title\"][:40]}')
    print(f'    본문: {info[\"article_text\"][:80]}...')
"
```

예상 출력:
```
테스트 rule_ids: ['OSHSTD-001-MFG', ...]
매핑된 룰 수: 4  ← (5개 중 4개 매핑 = 88.4% 커버리지)
  OSHSTD-001-MFG:
    키: 0001001
    체계: LEGAL
    제목: 목적
    본문: 제1조(목적) 이 법은...
```

---

## ☑ Task 4: 실제 엔진 호출 테스트 (서버 실행)

서버 기동:
```bash
# 터미널 1
uvicorn main:app --reload --port 8000
```

다른 터미널에서:

```bash
# 테스트용 Step1 진단 호출
curl -X POST http://localhost:8000/legal-engine/diagnose/step1 \
  -H "Content-Type: application/json" \
  -d '{
    "sector": "MANUFACTURING",
    "employee_count": 50,
    "floor_area": 3000,
    "has_boiler": true
  }' | python3 -m json.tool > /tmp/step1_test.json

# 결과 확인 (조문 본문 포함성)
python3 -c "
import json
with open('/tmp/step1_test.json') as f:
    data = json.load(f)

res = data['data']
print(f'엔진 버전: {res[\"engine_version\"]}')
print(f'적용 룰: {res[\"applicable_count\"]}')
print(f'매핑 통계: {res.get(\"article_mapping_stats\", {})}')
print()
print('첫 번째 룰:')
if res['appointment_required']:
    first = res['appointment_required'][0]
    print(f'  rule_id: {first[\"rule_id\"]}')
    print(f'  law_article: {first[\"law_article\"]}')
    print(f'  article_internal_key: {first.get(\"article_internal_key\")}')  # ⭐
    print(f'  article_title: {first.get(\"article_title\")}')                # ⭐
    print(f'  article_text[:100]: {first.get(\"article_text\", \"\")[:100]}')  # ⭐
    print(f'  law_system: {first.get(\"law_system\")}')
    print(f'  has_article_text: {first.get(\"has_article_text\")}')
"
```

예상:
```
엔진 버전: 5.8.0
적용 룰: 15
매핑 통계: {'total_rules': 15, 'mapped_rules': 13, 'coverage_pct': 86.7}

첫 번째 룰:
  rule_id: OSHSTD-APPT-001
  law_article: 제18조
  article_internal_key: 0018001        ← 새로 채워짐!
  article_title: 안전관리자
  article_text[:100]: 제18조(안전관리자) ① 사업주는 산업현장의... ← 조문 본문!
  law_system: LEGAL
  has_article_text: true
```

---

## ☑ Task 5: DB 저장 검증 (Supabase Dashboard)

Supabase SQL Editor에서 실행:

```sql
-- 최신 진단 결과에 조문 본문 들어갔는지 확인
SELECT 
  id,
  sector,
  diagnosis_stage,
  result_data->'article_mapping_stats' AS mapping_stats,
  jsonb_array_element(result_data->'rules', 0) AS first_rule
FROM factory_diagnosis_results
ORDER BY created_at DESC
LIMIT 1;
```

예상:
```json
{
  "mapping_stats": {
    "total_rules": 15,
    "mapped_rules": 13,
    "coverage_pct": 86.7
  },
  "first_rule": {
    "rule_code": "OSHSTD-008-MFG",
    "article_internal_key": "0050001",
    "article_text": "제50조(관리감독자...) ①...",
    "has_article_text": true
  }
}
```

⭕️ 이전 데이터에는 `article_internal_key` 없었음.
✅ 새 데이터는 필드들 채워져 있어야 함.

---

## ☑ Task 6: 실제 factory 전체 팀 테스트

기존 factory로 다시 진단:

```bash
# 실제 factory_id 조회
FACTORY_ID=$(
  python3 -c "
from db.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('factories').select('id').limit(1).execute()
print(res.data[0]['id'] if res.data else '')
"
)
echo "테스트 factory: $FACTORY_ID"

# apply/all 호출
curl -X POST "http://localhost:8000/legal-engine/apply/$FACTORY_ID" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool | head -60
```

---

## ☑ Task 7: 커버리지 확인 (매핑 퀄리티)

```sql
-- 전체 룰 중 조문 매핑 상태
SELECT 
  CASE WHEN EXISTS (
    SELECT 1 FROM rule_article_mapping ram 
    WHERE ram.rule_id = mblr.rule_id
  ) THEN 'mapped' ELSE 'unmapped' END AS mapping_status,
  COUNT(*) AS count
FROM master_building_legal_rules mblr
WHERE mblr.is_active = true
GROUP BY 1;
```

예상: 88.4%가 mapped

---

## ☑ Task 8: 배포 결정

### 전체 통과 시

```bash
# 관습적 픀지 배포 (사용하는 기법에 따라)
# 예: railway up, vercel --prod, docker build & push 등
```

### 문제 시 롤백

```bash
git revert a59a6dfc f1fc543b  # Phase A 두 커밋
git push origin main
```

⏱ 롤백 안전: 이전 통합 안 된 상태로 돌아가나 DB 영향 없음.

---

## 프론트엔드 변경사항 (참고)

프론트에서 `result_data.rules[i]`를 표시하는 컴포넌트에 다음 추가 가능:

```tsx
// Before
<div>{rule.law_name} {rule.law_article}</div>

// After (v5.8.0)
<div>
  <div className="text-sm text-gray-500">
    {rule.law_name} {rule.law_article}
  </div>
  {rule.has_article_text && (
    <details className="mt-2">
      <summary className="font-medium">
        📖 {rule.article_title} ({rule.law_system})
      </summary>
      <pre className="whitespace-pre-wrap mt-2 text-sm">
        {rule.article_text}
      </pre>
    </details>
  )}
</div>
```

---

## 예상 문제 & 해결

### 이슈 1: fetch_article_contexts에서 빈 dict 반환
**원인**: rule_id가 rule_article_mapping에 없음 (TEXT 일치 실패)  
**해결**: `SELECT COUNT(*) FROM rule_article_mapping` 로 2677건 확인.
         작아지면 재생성 필요 (dac947ba 커밋 스크립트)

### 이슈 2: classify_rules_db_fn TypeError
**원인**: 구 버전 디프렌스가 아직 배포되지 안음  
**해결**: 코드에 이미 try/except 폴백 있음. 자동 복원.

### 이슈 3: 대용량 JSON으로 result_data 크기 증가
**현재**: article_text 10KB × 15룰 = 유의미하게 증가  
**해결**: Supabase JSON 칼럼 제한 1GB니 괜찮음.  
        선택: 속도/앨 애플리케이션 차원에서 그렸음도 요구되면 `has_article_text` 플래그만 건네고 본문은 별도 GET /law-articles/{id}로 처리 가능 (앞으로 개선)

---

## 선택 작업 (나중)

지금은 안 해도 됨. 나중 개선 시:

1. `GET /law-articles/{article_id}` 엔드포인트 (조문 단일 조회)
2. NFTC 섹션 참조 룰 정규식 확장 (24건 미매칭 해결)
3. 과거 43건 진단 결과 마이그레이션 (거기에도 조문 붙임 원할 시)

---

## 완료 시

`git log --oneline -5` 확인 후:

```
a59a6dfc  feat(engine): Phase A-2 완료
f1fc543b  feat(engine): Phase A-1 헬퍼
7a705c4d  docs: 내부 키 체계
24676caf  docs: 내부 키 설계
5da25660  feat: 재파싱 스크립트
```

이 체크리스트 된 항목 수를 알려주세요:
  - ✅ 성공
  - ❌ 실패 (이슈 내용 포함)
  - ⚠️ 부분 성공 (어떤 Task에서 문제)
