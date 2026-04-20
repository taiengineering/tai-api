# 세션 핸드오프 2026-04-20 v4.1 (기획창 4일차 최종)

## 이번 세션 완료 작업

### 법령엔진 심층 진단 + 수집엔진 보강 기획 (이슈 #24)

소비자 결과물의 6하원칙 관점에서 역추적하여 근본 원인 파악 + 해결 설계.

#### 발견 사항
1. **DB 2,287건 중 프로덕션 1,133건** — 923건은 inactive+needs_review 방치
2. **82개 컬럼 중 ~15개만 채워진 채 프로덕션** — 6하원칙 중 4개 미달
3. **기존 7개 컬럼 추가 불필요** — 이미 존재하는 컬럼이 비어있는 것이 문제
4. **215건 판정 로직 깨짐** — condition_code는 있지만 operator 없음
5. **report_method_code 0%** — 142건 전부 공백, 자동신고 대행 불가
6. **qualification_code 3%** — 선임매칭 불가능 상태
7. **submit_org_code 100% 있지만 코드만** — 한글 라벨 매핑 필요 (8개 코드)

#### 소비자 6하원칙 기준 현재 품질
| 6하원칙 | 채움률 | 등급 |
|---|---|---|
| 무엇을 (WHAT) | 100% | ✅ |
| 왜 (WHY) | 27% | ❌ |
| 누가 (WHO) | 3% | ❌ |
| 언제 (WHEN) | 31~69% | ⚠️ |
| 어디서 (WHERE) | 100% 코드만 | ⚠️ |
| 어떻게 (HOW) | 0~17% | ❌ |

#### 기존 인프라 확인 (새로 만들 필요 없음)
- **법령 원문 수집 완료**: 473개 법령, 33,845조문, 54,925항, 37,083호·목, 5,567별표
- **Haiku 파싱 엔진 존재**: `routers/law_rule_generator.py` (34KB)
- **draft→master 워크플로우 존재**: law_rule_drafts 2,152건
- **법령 DB 테이블 25개+, 컬럼 530개+**

#### 근본 원인
Haiku 엔진이 조문 텍스트 1개만(3,000자) 받고 13개 필드만 출력.
시행령/별표/벌칙 미포함 → 6하원칙 중 WHY/WHO/HOW 추출 불가.

#### 해결: 기존 law_rule_generator.py 보강 (작업지시서 v2.1)
1. **AI 입력 확장**: 조문 1개 → 법률+시행령+별표+벌칙 풀세트 (DB에서 조립)
2. **AI 출력 확장**: 13개 → 30개+ 필드 (6하원칙 완전 커버)
3. **condition_code**: 12개 → 24개 완전 제공
4. **reparse-master**: 기존 1,133건 빈칸 채움 (Sonnet)
5. **validate-master**: 무결성 자동 검증
6. **submit_org_code 한글 매핑**: 8개 코드 → 한글 라벨
7. **tai_feature_code**: 유일한 신규 컬럼 (DDL 1개)
8. **AI 모델**: Haiku(신규 파싱) + Sonnet(reparse 복잡 케이스)
9. **few-shot 예시**: 잘 채워진 룰 예시를 프롬프트에 포함

---

## GitHub 산출물

### tai-api (dev)
- `docs/law-engine-enhancement-workorder.md` — **작업지시서 v2.1 (기준 문서)**
- `docs/session-handoff-20260420-v4.md` — 본 문서
- 이전 문서 (대체됨): `docs/law-pipeline-workorder.md`, `docs/law-pipeline-consumer-delivery.md`

### 이슈 #24
- 제목: `[법령엔진] 수집엔진 보강 — 소비자 전달 품질 + 무결성 확보`
- Phase 1~3 체크리스트 포함

---

## 다음 세션 작업 (Cursor/Claude Code)

### Phase 1: 무결성 확보
1. `services/law_context_builder.py` 신규 — 법령 원문 체인 조립 서비스
2. `routers/law_rule_generator.py` 보강 — validate-master + reparse-master 엔드포인트
3. Supabase: `ALTER TABLE tai_feature_code` 1개
4. validate-master 실행 → 전체 무결성 리포트
5. 테스트: FIREACT-005-MFG, ENERGYACT-002, ODORACTS-001-MFG reparse

### Phase 2: 소비자 품질 (6하원칙)
6. 시스템 프롬프트 보강 (24개 코드 + few-shot + 30개 출력 필드)
7. reparse-master로 1,133건 빈칸 채움
8. submit_org_code 한글 매핑 적용

---

## 다음 세션 프롬프트

```
이 창은 TAI Safe 구현 창입니다.

이번 작업: 법령엔진 수집엔진 보강 (이슈 #24)

기준 문서: docs/law-engine-enhancement-workorder.md (dev 브랜치, v2.1)
세션 핸드오프: docs/session-handoff-20260420-v4.md

작업 순서:
1. 기준 문서 읽기
2. services/law_context_builder.py 신규 작성
   - law_article + law_paragraph + 시행령 + 별표 + 벌칙 조항 → 하나의 컨텍스트
3. routers/law_rule_generator.py 보강
   - 시스템 프롬프트: condition_code 24개 + few-shot + 출력 30개 필드
   - POST /validate-master 엔드포인트
   - POST /reparse-master 엔드포인트
4. Supabase: ALTER TABLE tai_feature_code
5. validate-master 실행 → 리포트 확인
6. 테스트: FIREACT-005-MFG, ENERGYACT-002, ODORACTS-001-MFG reparse

주의:
- routers/law_rule_generator.py는 200줄+ → Cursor 사용
- from db.supabase_client import get_supabase
- AI 모델: Haiku(신규) + Sonnet(reparse)
- ANTHROPIC_API_KEY 환경변수 필요
```
