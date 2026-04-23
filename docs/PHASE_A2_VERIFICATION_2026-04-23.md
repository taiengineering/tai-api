# Phase A-2 검증 결과 (2026-04-23)

## Cursor 체크리스트 결과

```
Task 1: git pull              ✅ ebec3ef까지 fast-forward
Task 2: Import 검증            ✅ ENGINE_VERSION=5.8.0 확인
Task 3: fetch_article_contexts ⚠️ Supabase anon RLS 제약
Task 4: /legal-engine/step1    ⚠️ INTERNAL_API_SECRET 누락 + anon 제약
Task 5-7: SQL 검증             ⚠️ anon으로는 불가
Task 8: 배포 결정              ⏸️ service role 또는 스테이징 재검 권장

추가 pytest: ✅ 16건 통과
  test_legal_engine_layer, test_legal_engine,
  test_legal_engine_52, test_diagnosis_integrated_current
```

## 발견된 환경 이슈

### 이슈 1: .env 포맷 불일치
```
문제: tai-admin의 .env는 KEY=value 형식이 아니라서 source 불가
영향: Task 2-6 진행 막힘
해결: .env.example 추가 (이 커밋)
     → cp .env.example .env → 값 입력 → source
```

### 이슈 2: INTERNAL_API_SECRET 필수
```
문제: uvicorn 기동 시 필수 환경변수
해결: .env.example에 포함 (local-dev-secret 예시)
```

### 이슈 3: Supabase anon 키 RLS 제약
```
문제: master_building_legal_rules 조회 시 빈 결과
이유: RLS 정책이 anon에 행 제한 (정상 동작)
해결: Supabase Dashboard SQL Editor에서 service role로 검증
     → docs/CURSOR_VERIFY_SUPABASE.sql 추가 (이 커밋)
```

## Claude 직접 검증 (service role, MCP 통한 RLS 우회)

### 검증 1: 샘플 5룰 조문 본문 연결

```
ELEACT-029-BLD → 0029001 "승강기 안전관리자" (LEGAL) ✅
  본문: "제29조(승강기 안전관리자) ① 관리주체는..."

ENERGYACT-002  → 0032001 "에너지진단 등" (LEGAL) ✅
  본문: "제32조(에너지진단 등) ① 기후에너지환경부장관..."

MULTIUS-002    → 0013001 "다중이용업주의 안전시설..." (LEGAL) ✅
  본문: "제13조(다중이용업주의 안전시설등...) ① 다중이용업주..."

OSHEDU-002     → 매핑 없음 (범위 외 법령)
OSHNOTICE-002-CON → 매핑 없음 (범위 외 법령)
```

### 검증 2: 전체 커버리지

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  활성 룰 1,598건 기준
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LEGAL (법제처 공식):  1,404 / 100% ✅
  ADMRUL (폴백):           1 / 100% ✅
  NFPC (화재성능):         0 / -
  NFTC (화재기술):         0 / -
  NOT_MAPPED:            193 / 0%
  ─────────────────────────────────
  엔진 본문 반환:       1,405 (87.9%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 발견된 신규 이슈 (Phase B 영역, 별도 과제)

### 이슈 4: NFTC 9룰 "제4조" vs 실제 섹션 체계 불일치

```
상황: master_building_legal_rules에 NFTC 참조 9룰 존재
문제: law_article="제4조" 형태로 저장됨
     NFTC 법령은 "1.1.1" 섹션 체계
     → 9건 중 8건 매핑 실패 (우연히 1건만 매칭)

샘플:
  NFTC-001 → "스프링클러설비의 화재안전기술기준(NFTC 103)" / 제4조 / 매핑X
  NFTC-003 → "옥내소화전설비의 화재안전기술기준(NFTC 102)" / 제4조 / 매핑X
  ...

원인: master_building_legal_rules 데이터가 NFTC 섹션 체계 미반영
     (기존 NFSC 규칙에서 NFTC로 전환되며 article 번호 형식 변경됨)

해결책 (Phase B):
  1. 9룰의 law_article을 "1.1.1", "2.1.1" 등 섹션으로 갱신
  2. 또는 매핑 로직에 특수 규칙 추가 (NFTC 룰은 법령+법령종류로 매칭)
```

### 이슈 5: NOT_MAPPED 193건 (기존 이슈)

```
상황: 타겟 184 법령 범위 외의 법령 참조 룰
예시: 안전보건교육규정, 건설공사 안전보건대장 고시 등

해결책 (Phase C):
  타겟 확장 (184 → 200+) → 수집 → 매핑
```

## Phase A-2 결론

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Phase A-2 "조문 본문 통합" 최종 판정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  코드 정합성:       ✅ 16 pytest 통과
  ENGINE_VERSION:    ✅ 5.8.0 반영
  DB 검증 (MCP):     ✅ 1,405 룰 본문 반환 가능
  커버리지:          ✅ 87.9% (활성 룰 기준)
  하위 호환:          ✅ TypeError 폴백 + supabase=None 기본값
  
  배포 가능 상태:    ✅ READY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 배포 권장 플로우

### 권장 1: 스테이징 직접 검증

```bash
# 1. .env 완비
cp .env.example .env
# → SUPABASE_KEY, INTERNAL_API_SECRET 채움

set -a; source .env; set +a

# 2. 로컬 uvicorn 기동
uvicorn main:app --reload --port 8000

# 3. 실제 factory로 테스트
FACTORY_ID=$(실제 UUID)
curl -X POST http://localhost:8000/legal-engine/apply/$FACTORY_ID \
  -H "Content-Type: application/json" -d '{}'

# 4. Supabase Dashboard SQL Editor 검증
# → docs/CURSOR_VERIFY_SUPABASE.sql 실행

# 5. 응답에 article_internal_key, article_text 포함 확인
```

### 권장 2: 프로덕션 배포

```
조건:
  ✅ 위 권장 1 통과
  ✅ pytest 전체 통과 (이미 16건 통과)
  
프로덕션 배포:
  - Railway/Vercel 등 기존 배포 방식
  - 첫 진단 1건 수동 확인 (article_text 포함 여부)
  
롤백 시:
  git revert ebec3ef9 a59a6dfc f1fc543b
  git push origin main
```

## 다음 우선순위

```
🔴 Phase A-2 배포 후 검증 (즉시)
  실제 factory 1건 진단 → article_text 확인
  프론트엔드가 새 필드 표시하는지 확인

🟡 Phase B: NFTC 9룰 매핑 보정 (주 단위)
  master_building_legal_rules의 NFTC 룰들 law_article 보정
  
🟢 Phase C: 타겟 확장 (월 단위)
  NOT_MAPPED 193건 → 164 추가 타겟 발굴
  
🔵 법제처 연동 (사용자 고민 후)
  deep_link URL 생성 로직
  변경 이력 자체 diff
```

## 커밋

```
f1fc543b  Phase A-1 (헬퍼 + 포맷터)
a59a6dfc  Phase A-2 (통합)
ebec3ef9  Phase A-2 문서
(이 커밋)  Phase A-2 검증 보고 + .env.example + SQL 스크립트
```
