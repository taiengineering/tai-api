# 작업지시서 — 갭 B + C + E 동시 진행 (2026-04-25)

> **이 문서는 백엔드 창(Cursor / Claude Code / Railway 터미널)에서 실행할 작업지시서입니다.** 기획창에서 사전 SQL 리셋이 완료된 상태이므로, 이 문서대로 두 트랙을 동시 진행하면 됩니다.

## 목표

법령엔진 데이터 클린업 직후 마지막 마무리 작업으로, 세 갭을 한 번에 정리:

| 갭 | 내용 | 트랙 | 도구 |
|---|---|---|---|
| **B** | 22개 0초안 일반법령 재파싱 | 1 | M2max 로컬 `auto_parse_parallel.py` |
| **C** | 검토필요 REJECTED 7건 article 재파싱 | 1 | (B와 같이 처리됨) |
| **E** | penalty 빈칸 790건 보강 | 2 | Railway API `reparse-master` |

---

## 사전 준비 (완료 — 기획창에서 처리됨)

이미 다음 SQL이 실행되어 있음:

```sql
-- 갭 B: 22개 법령의 article 1,455건 → ai_parsed_at = NULL
-- 갭 C: 검토필요 7건 article → ai_parsed_at = NULL
-- 합계 1,462건 article이 재파싱 대기 상태
```

검증:
```sql
SELECT COUNT(*) FROM law_article 
WHERE ai_parsed_at IS NULL 
  AND length(article_text) >= 20;
-- 예상: 1,462 + 86(NFTC) = 1,548건
```

---

## 트랙 1 — M2max 로컬 (갭 B + 갭 C 통합 처리)

### 1-1. auto_parse_parallel.py 프롬프트 확장 (필수)

**파일**: `scripts/auto_parse_parallel.py`

**수정 위치**: `SYSTEM_PROMPT` 상수 (또는 user prompt template)

**기존 (산업안전 편향)**:
```
당신은 한국 산업안전 법령 전문가입니다.
법령 조문 텍스트를 분석하여 안전관리 시스템의 판정 룰을 추출합니다.

추출 대상 의무 유형:
- APPOINT, INSPECT, NOTIFY, REPORT, ACTION
```

**확장 (갭 B 영역 포함)**:
```
당신은 한국 사업장 의무 법령 전문가입니다.
법령 조문 텍스트를 분석하여 사업장이 이행해야 할 의무 룰을 추출합니다.

추출 대상 영역:
1. 산업안전·보건 의무 (산안법, 안전기준규칙 등)
2. 재난·안전관리 의무 (재난기본법 — 모든 사업장 재난 대비)
3. 환경관리 의무 (탄소중립, 토양환경, 잔류성오염, 악취방지, 소음진동)
4. 근로자 보호 의무 (파견근로자 보호법, 근로기준법)
5. 시설·건물 관리 의무 (주택법, 다중이용업소법 등)

추출 대상 의무 유형:
- APPOINT: 안전관리자·재난관리책임자·환경관리자 등 선임 의무
- INSPECT: 정기점검·안전검사·환경측정 의무
- NOTIFY: 신고·보고·제출 의무 (재난신고, 환경신고 포함)
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무 (재난대비, 환경기준 준수 포함)

⚠️ 사업장 적용 가능 의무만 추출:
- 행정기관·국가 권한 규정 → 빈 배열 []
- 단순 정의·목적·적용범위 → 빈 배열 []
- 사업장이 직접 이행해야 하는 의무만 추출
```

### 1-2. 환경 변수 + 실행

```bash
cd ~/Desktop/tai-engineering/tai-api  # 또는 iCloud 이전 후 경로
git pull origin dev
git checkout dev

export ANTHROPIC_API_KEY='...'  # 기존 키
export INTERNAL_API_SECRET='...'  # 기존 키

# 백그라운드 실행 (이전 4/24 패턴, 약 15-20분 예상)
nohup python3 scripts/auto_parse_parallel.py > ~/parse_log_gap_bc.txt 2>&1 &
echo $! > ~/parse_pid.txt

tail -f ~/parse_log_gap_bc.txt
```

### 1-3. 모니터링 SQL (5분마다)

```sql
SELECT 
  COUNT(*) FILTER (WHERE ai_parsed_at IS NOT NULL) as 파싱완료,
  COUNT(*) FILTER (WHERE ai_parsed_at IS NULL AND length(article_text) >= 20) as 미파싱잔여,
  ROUND(100.0 * COUNT(*) FILTER (WHERE ai_parsed_at IS NOT NULL) / NULLIF(COUNT(*),0), 1) as 진행률
FROM law_article;
```

### 1-4. 완료 후 검증

```sql
-- 갭 B 22개 법령에서 draft 생성 확인
SELECT lm.law_name, COUNT(d.id) as 신규draft수, AVG(d.ai_confidence) as 평균신뢰도
FROM law_master lm
JOIN law_version lv ON lv.law_id = lm.id AND lv.is_current = true
JOIN law_article la ON la.law_version_id = lv.id
LEFT JOIN law_rule_drafts d ON d.article_id = la.id AND d.created_at > '2026-04-25'
WHERE lm.id IN (
  'c2c24eb2-dbca-4164-acaf-33f0716bcbe8','be0b549b-f0a4-47cc-b1a6-bfc2df07c342',
  '5f509f66-c109-43bd-8956-6bdd6b62e44c','e4377f90-4456-4a89-b136-133d842234a0',
  '9f3279cd-c3aa-446e-9ec6-c188bdbb7f5b','3896063e-871e-432a-81fe-2a5549cc8669',
  '706a456a-0248-40e6-9a74-5a9909f9b47f','9da41295-17ef-4076-9c82-0aa464e3fe05',
  'dfd1fbd5-5409-45be-b4fd-d457fdb299d2','4e37da27-efa8-411b-8a0e-5fb87b83bf11',
  '5223f65a-03d4-4b17-84d4-7286a9ab2c20','c1aaf76f-3da0-42b8-b0f5-37d9dfe25458',
  'fa7e70a0-4f15-440d-b2af-482f71739af2','45d8e01b-bf5f-416e-a532-fe22a4d31c30',
  'e14db680-a407-4172-b2e7-9aab9803306a','6ae20558-beeb-4ac7-80c1-fb8cba30ae00',
  '8946f29e-53ef-4b66-92ef-87ef86422dd0','2d30f8a8-f1f8-4bf6-b052-a69880ec4ef2',
  '3025355a-b0ca-4ce8-8a48-39d8ee504100','30b91f42-88be-4351-9c04-7448090bdb8a',
  'a1ab10ab-70eb-4395-863c-75a78bccb3ce','3a881389-5729-48fd-9aec-0be5d2428867'
)
GROUP BY lm.law_name
ORDER BY 신규draft수 DESC;

-- 갭 C 7건 article에서 신 draft 생성 확인
SELECT la.id, la.article_no, la.article_title, COUNT(d.id) as 신draft수
FROM law_article la
LEFT JOIN law_rule_drafts d ON d.article_id = la.id AND d.created_at > '2026-04-25'
WHERE la.id IN (
  '7d06685d-4afd-4a89-a1fb-1c8422b751e5','d0c02286-c90b-4282-8b36-acdf92083db9',
  'dc427d5b-a86a-44db-9cea-e1b8f793460e','defbc815-da90-479a-ad94-5c733cbec365',
  '213e7cee-a218-4b3f-860b-f94ce1fcb1df','91e17d4c-cb24-4f73-9cea-1649e120b839',
  '1c9b52bc-0a41-4582-99a0-30457f785d13'
)
GROUP BY la.id, la.article_no, la.article_title;
```

### 1-5. 신 draft 자동승인 + master 등록

파싱 완료 후 신뢰도 80+ + condition_code 있음 일괄 승인:

```bash
curl -X POST "https://api.taieng.co.kr/law-rule-generator/auto-parse-and-approve" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{"auto_approve_threshold": 80}'

# 또는 bulk-approve (이미 PENDING으로 들어가 있는 것 일괄 승인)
curl -X POST "https://api.taieng.co.kr/law-rule-generator/bulk-approve-unregistered" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET"
```

---

## 트랙 2 — Railway API (갭 E: penalty 빈칸 790건)

### 2-1. 실행 전 주의사항 (4/24 학습)

- ❌ **2개 이상 sector 동시 실행 금지** — DB 커넥션 풀 고갈
- ✅ **sector별 순차 실행** (1개 완료 → 다음 시작)
- ✅ Supabase 메모리 2배 업그레이드 상태 유지
- ❌ **트랙 2 실행 중 main 브랜치 push 금지** (BackgroundTask 사망)

### 2-2. 4 sector 순차 실행

```bash
# 1. COMMON (394건, 가장 많음)
curl -X POST "https://api.taieng.co.kr/law-rule-generator/reparse-master" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{
    "secret": "'$INTERNAL_API_SECRET'",
    "sector": "COMMON",
    "limit": 400,
    "fill_empty_only": true
  }'
# → job_id 받아서 ~30분 모니터링 → 완료 확인

# 2. BUILDING (254건)
curl -X POST "https://api.taieng.co.kr/law-rule-generator/reparse-master" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{
    "secret": "'$INTERNAL_API_SECRET'",
    "sector": "BUILDING",
    "limit": 260,
    "fill_empty_only": true
  }'

# 3. MANUFACTURING (90건)
curl -X POST "https://api.taieng.co.kr/law-rule-generator/reparse-master" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{
    "secret": "'$INTERNAL_API_SECRET'",
    "sector": "MANUFACTURING",
    "limit": 100,
    "fill_empty_only": true
  }'

# 4. CONSTRUCTION (52건)
curl -X POST "https://api.taieng.co.kr/law-rule-generator/reparse-master" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{
    "secret": "'$INTERNAL_API_SECRET'",
    "sector": "CONSTRUCTION",
    "limit": 60,
    "fill_empty_only": true
  }'
```

### 2-3. 모니터링

```bash
# 진행 중 job 조회
curl "https://api.taieng.co.kr/law-rule-generator/reparse-master/jobs?limit=5" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET"

# 특정 job 상세
curl "https://api.taieng.co.kr/law-rule-generator/reparse-master/status/{job_id}" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET"
```

### 2-4. 완료 후 검증

```sql
SELECT 
  sector,
  COUNT(*) as 활성룰,
  COUNT(*) FILTER (WHERE penalty_summary IS NOT NULL AND penalty_summary != '') as penalty채움,
  ROUND(100.0 * COUNT(*) FILTER (WHERE penalty_summary IS NOT NULL AND penalty_summary != '') 
        / NULLIF(COUNT(*),0), 1) as penalty채움률
FROM master_building_legal_rules
WHERE is_active = true
GROUP BY sector
ORDER BY 활성룰 DESC;
```

목표: penalty 채움률 71.9% → 90%+

---

## 동시 진행 시 안전 가이드

두 트랙은 **다른 환경 + 다른 테이블**을 쓰므로 동시 실행 가능:

| 트랙 | 환경 | 쓰기 대상 | 주 부하 |
|---|---|---|---|
| 1 | M2max 로컬 | `law_article.ai_parsed_at` UPDATE + `law_rule_drafts` INSERT | Anthropic API + Supabase 쓰기 |
| 2 | Railway 서버 | `master_building_legal_rules` UPDATE | Anthropic API + Supabase 쓰기 |

**위험 신호 발생 시 즉시 중단**:
- Supabase 대시보드에 "exhausting multiple resources" 경고
- API 응답 타임아웃 (`/health`가 503 또는 미응답)
- DB 쿼리 타임아웃

→ 발생 시: 트랙 2의 다음 sector 호출을 보류, 트랙 1만 완료시키고 재시작

---

## 완료 기준

세 갭 모두 다음 조건 만족 시 완료:

| 갭 | 측정 SQL | 목표 |
|---|---|---|
| B | 22개 법령 합계 신규 draft 수 | 200건+ (조문당 평균 0.15건+) |
| C | 7개 article에서 신 draft 생성 | 7건 이상 |
| E | penalty 채움률 (전체) | 90%+ (현재 71.9%) |

---

## 완료 후 보고 형식

작업창에서 다음 결과 보고 (기획창에 전달):

```
✅ 갭 B 완료
- 22개 법령 처리, 신규 draft N건 생성
- 자동승인 N건, master 등록 N건
- 활성 룰 2,813 → ?,??? (+???)

✅ 갭 C 완료
- 7개 article 재파싱, 신 draft N건 생성
- 검토필요 0건 (또는 잔여 N건)

✅ 갭 E 완료
- 4 sector reparse 완료
- penalty 채움률 71.9% → ??.?%

⚠️ 이슈 (있으면)
```

---

## 관련 문서

- `docs/session-handoff-20260424-25-law-pipeline.md` — 4/21~4/25 전체 맥락
- `docs/post-cleanup-scorecard-20260425.md` — 클린업 직후 스코어카드 (이 작업의 출발점)
- 이슈 `taiengineering/tai-api#24` — 법령엔진 파이프라인 보강

---

**작성일**: 2026-04-25 12:00 KST
**작성**: 기획창 (TAI 기획010)
**실행 대상**: 백엔드 창 (Cursor / Claude Code) + Railway 터미널
**예상 소요**: 트랙 1 ~20분, 트랙 2 ~50분 (동시 진행 시 ~50분)
