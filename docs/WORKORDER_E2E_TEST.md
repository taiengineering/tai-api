# 작업지시서: 배포 확인 + 전체 파이프라인 E2E 테스트

> 목적: PR #105~#109 배포 후, 법령진단 전체 파이프라인을 실제로 테스트한다.
> 성격: 검증. 코드 수정 없음. 실제 API 호출 + DB 확인.
> 대상: api.taieng.co.kr (Railway tai-api-prod, main 자동배포)

## 사전 확인: 배포 완료 여부

```
1. 최신 main 커밋 확인:
   git log origin/main --oneline -1
   → 57f552b (PR #109) 인가?

2. Railway 배포 확인:
   curl -s https://api.taieng.co.kr/health
   → 200 OK?

3. 배포된 버전이 PR #109 포함인지:
   curl -s https://api.taieng.co.kr/health 응답에 버전/커밋 있으면 확인
```

배포가 아직이면 Railway 대시보드에서 재배포 또는 git push 트리거.

## E2E 테스트: 3섹터 × 입력 표준화 검증

### 테스트 1: BUILDING (병원, 5층, 50명)

```bash
curl -X POST https://api.taieng.co.kr/anonymous-diagnosis \
  -H "Content-Type: application/json" \
  -d '{
    "site_kind": "building",
    "building_use_type": "병원",
    "floor_area": 5000,
    "floor_count": 5,
    "worker_count": 50
  }'
```

확인:
- 응답 200, public_token 발급
- rules_table에 law_name 채워짐 (PR #107)
- obligations flat 구조 (PR #108)
- 각 row에 source="DIAGNOSIS" (PR #109)
- risk_level, applicable_count 존재

### 테스트 2: INDUSTRIAL (제조, 300명)

```bash
curl -X POST https://api.taieng.co.kr/anonymous-diagnosis \
  -H "Content-Type: application/json" \
  -d '{
    "site_kind": "manufacturing",
    "worker_count": 300,
    "floor_area": 12000,
    "ksic_major": "C"
  }'
```

확인:
- factories_sector_check 통과 (sector=INDUSTRIAL 저장, PR #106)
- 진단 정상 완료 (이전엔 깨졌음)

### 테스트 3: CONSTRUCTION (78억, 120명)

```bash
curl -X POST https://api.taieng.co.kr/anonymous-diagnosis \
  -H "Content-Type: application/json" \
  -d '{
    "site_kind": "construction",
    "construction_type": "건축",
    "contract_amount_eok": 78,
    "direct_workers": 120
  }'
```

### 테스트 4: 단위 문자열 방어 (STEP A)

```bash
curl -X POST https://api.taieng.co.kr/anonymous-diagnosis \
  -H "Content-Type: application/json" \
  -d '{
    "site_kind": "building",
    "building_use_type": "공장",
    "floor_area": 3000,
    "worker_count": 50,
    "electric_capacity": "800kVA"
  }'
```

확인:
- "800kVA" 문자열이 깨지지 않고 처리됨 (파이프라인 방어)

### 테스트 5: 결과 조회 (Layer 6)

```bash
# 테스트 1의 public_token으로
curl -s https://api.taieng.co.kr/anonymous-diagnosis/{token}
curl -s https://api.taieng.co.kr/anonymous-diagnosis/{token}/transform
```

확인:
- 조회 응답이 표준 형태 (rules_table, key_obligations, law_badges)
- transform 응답에 obligations flat 전개 + evidence
- 익명/통합 출력 일관 (PR #109)

## DB 확인: 저장된 결과 검증

```sql
-- 방금 생성된 결과의 구조 확인
SELECT 
  public_token, source_type, engine_version, rule_version,
  jsonb_array_length(full_result->'rules_table') as rules_count,
  full_result->'rules_table'->0->>'law_name' as first_law_name,
  full_result->'rules_table'->0->>'source' as first_source,
  full_result->>'risk_level' as risk_level
FROM anonymous_diagnosis_results
WHERE created_at > now() - interval '10 minutes'
ORDER BY created_at DESC;
```

확인:
- engine_version = v3.0-compiler-core-anonymous
- first_law_name 채워짐 (빈 문자열 아님)
- first_source = "DIAGNOSIS"
- rules_count > 0

## 산출물

파일: docs/E2E_TEST_RESULTS_20260609.md

```markdown
# E2E 테스트 결과 (배포 후)

## 배포 확인
- main 커밋: [sha]
- health: [200/실패]

## 섹터별 테스트
| 테스트 | 응답 | rules_count | law_name | source | 결과 |
|--------|------|-------------|----------|--------|------|
| BUILDING 병원 | ... | ... | ... | ... | PASS/FAIL |
| INDUSTRIAL 제조 | ... | ... | ... | ... | ... |
| CONSTRUCTION 78억 | ... | ... | ... | ... | ... |
| 단위 800kVA | ... | - | - | - | ... |

## Layer별 검증
- Layer 1→2 (입력 저장): [결과]
- Layer 3→4 (law_name): [결과]
- Layer 4→5 (obligations flat): [결과]
- Layer 5→6 (source, 출력 일관): [결과]

## 발견된 문제
- [있으면 기록]

## 결론
- 전체 파이프라인 정상 여부
```

## 주의

- 코드 수정 금지 (테스트만)
- 실제 운영 API 호출이므로 테스트 데이터는 [ANON] 또는 명확히 구분
- 문제 발견 시 기록만, 즉시 수정하지 말 것
- Supabase MCP project_id: vwlahtguyggrhvslabax
- 배포 안 됐으면 먼저 배포 확인
