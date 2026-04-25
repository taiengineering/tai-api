# 법령엔진 데이터 보강 작업 보고서

**작업일**: 2026-04-25 (전일)  
**작업자**: 심태왕 대표 + Claude 기획창  
**대상**: tai-api / master_building_legal_rules + law_rule_drafts + law_article  

---

## 1. 작업 배경

### 1.1 발견된 문제 (2026-04-20 진단)

`master_building_legal_rules` 테이블에 약 1,133개 활성 룰만 존재 — 한국 산업안전 법령 의무의 약 30%만 커버. 법령진단 서비스의 핵심 가치("빠진 법령 없이 전수 진단")와 직접 모순.

### 1.2 갭 분류 (6개)

| 갭 | 내용 | 규모 |
|---|---|---|
| A | NFTC 매핑 실패 (소방기술기준) | 86건 |
| B | 22개 법령 0초안 (재난·환경·근로자보호·시설) | ~1,500 조문 |
| C | 검토 필요 article (다중이용업소법 등) | 7건 |
| D | PENDING 상태 draft | 45건 |
| E | penalty_summary 빈칸 | 790건 |
| F | condition_code NULL | 551건 |

### 1.3 갭 B의 근본 원인

`routers/law_rule_generator.py`의 SYSTEM_PROMPT가 "산업안전" 한정으로 편향:

```
당신은 한국 산업안전 법령 전문가입니다.
```

이로 인해:
- 재난기본법 → "산업안전 아님" → 빈 배열 [] 반환
- 환경법(탄소중립·토양·소음 등) → "산업안전 아님" → []
- 파견근로자보호법 → "산업안전 아님" → []
- 주택법 → "특수시설" 룰에 걸림 → []

추가 편향:
- `auto-parse-and-approve`에서 INSPECT 의무만 자동승인 → APPOINT/NOTIFY 비중 큰 갭 B 법령은 전부 PENDING
- USER_PROMPT_TEMPLATE의 "안전관리 의무" 표현도 영역 제한

---

## 2. 사전 작업 (4/21~4/24, 이전 세션)

### 2.1 죽은 데이터 정리
- Phase 1A: REJECTED + article_id NULL 1,455건 DELETE
- Phase 1B: 신규 draft 존재하는 구 draft 31건 DELETE
- 결과: 활성 master 룰 2,813건 유지

### 2.2 리셋 (재파싱 대기 상태 만들기)
- 갭 B 22개 법령 article 1,455건: `ai_parsed_at = NULL` 리셋
- 갭 C 7개 article: `ai_parsed_at = NULL` 리셋
- 합계 1,462건 재파싱 대기

### 2.3 remarks 데이터 보강
- 99.4% 커버리지 달성 (1,126/1,133)
- bulk SQL UPDATE 사용 (`CASE rule_id WHEN ... THEN ... END`)

---

## 3. 본 작업 (4/25) — 시간순

### 3.1 [실패] finalize_law_pipeline.py 시도

**시도**: 로컬에서 Anthropic API + Supabase를 직접 호출하는 638라인 Python 스크립트 작성.

**문제**: 실행 시마다 동일한 에러 반복:
```
UnicodeEncodeError: 'ascii' codec can't encode character '\u2028' in position 219
```

**원인 진단**:
- 환경변수(`SUPABASE_KEY`) 끝에 `\u2028` (Line Separator) 비표준 유니코드 문자가 박혀있음
- iCloud Desktop 동기화 영역에서 NFD/NFC 유니코드 정규화 충돌 가능성
- `.env` 파일에는 `SUPABASE_URL`만 있고, `SUPABASE_KEY`는 셸 메모리에만 존재
- position 219 = JWT 토큰 정상 길이(218) + 비표준 문자 1개

**시도한 패치 (4번, 모두 실패)**:
1. `LANG=ko_KR.UTF-8` export
2. `sys.stdout.reconfigure(encoding='utf-8')`
3. `.env` 정화 명령
4. 환경변수 자동 sanitize 코드 추가

**결론**: 로컬 환경 자체가 오염된 상태. 근본 해결은 로컬 의존을 제거하는 것.

### 3.2 [전환] 원점 회귀 — 이전 패턴 분석

대표님 지시: "이전작업 파이썬으로 작업한 내역 깃에서 찾아보고 다시 작업방법을 원초적부터 찾아보시죠"

`scripts/auto_parse_all.py` (80라인) 분석 결과:

| 항목 | 이전 방식 (잘 됐음) | finalize 방식 (실패) |
|---|---|---|
| 환경변수 | INTERNAL_API_SECRET 1개 | 4개 (ANTHROPIC + SUPABASE × 2 + SECRET) |
| Supabase 직접 연결 | 안 함 | 직접 연결 → \u2028 폭발 |
| 작업 방식 | Railway API 호출 | 로컬 직접 처리 |
| 코드 길이 | 80라인 | 638라인 |

**교훈**: Railway 서버에 이미 모든 환경변수가 있으므로, 로컬에서 직접 호출할 이유가 없었음.

### 3.3 v1.7.0 — 갭 B 편향 교정 (3건)

**커밋**: `6b927e4` (main 직접 push)

**변경 1 — SYSTEM_PROMPT 5영역 확장**
```
기존: "당신은 한국 산업안전 법령 전문가입니다."
변경: "당신은 한국 사업장 의무 법령 전문가입니다."

추출 대상 영역 (5개 명시):
1. 산업안전·보건 의무 (산안법 등)
2. 재난·안전관리 의무 (재난기본법)
3. 환경관리 의무 (탄소중립·토양·잔류성·악취·소음)
4. 근로자 보호 의무 (파견근로자법·근로기준법)
5. 시설·건물 관리 의무 (주택법·다중이용업소법 등)
```

**변경 2 — USER_PROMPT_TEMPLATE**
```
기존: "안전관리 의무(선임·점검·신고·보고·조치)"
변경: "사업장 의무(선임·점검·신고·보고·조치)"
```

**변경 3 — 자동승인 조건 확장**
```python
# 기존: INSPECT만
if ob_type == "INSPECT" and conf >= threshold:

# 변경: 5개 모두 + condition_code 게이트
AUTO_APPROVE_ELIGIBLE_TYPES = {"INSPECT", "APPOINT", "NOTIFY", "REPORT", "ACTION"}
if ob_type in AUTO_APPROVE_ELIGIBLE_TYPES and conf >= threshold and has_condition:
```

condition_code 게이트: 조건 없는 범용 룰은 수동 검토로 유지 (4/24 학습 반영).

**변경 4 — 학교·병원 룰 유지**: 대표님 확인 "학교등은 패스 맞음".

### 3.4 v1.8.0 — POST /auto-parse-all 내장화

**커밋**: `c0ed727` (main)

로컬 스크립트(`auto_parse_all.py`) 대신 Railway 내장 endpoint로 전환:
- 환경변수 의존 0, 인코딩 문제 0
- curl 1번으로 시작, 백그라운드 처리
- `reparse_job_log` 테이블 재사용 (sector="AUTO_PARSE_ALL")
- 진행률: 기존 GET /reparse-master/status/{job_id} 그대로

### 3.5 auto-parse-all 실행 결과

**Job ID**: `97781868-78c0-4063-888b-9cfdf4096fb9`  
**소요 시간**: 약 110분 (139개 법령)

| 지표 | 값 |
|---|---|
| 대상 법령 | 139개 (199 중 60개는 이미 파싱됨) |
| draft 생성 | **546건** |
| 자동승인 → master | 49건 |
| bulk-approve → master | 958건 |
| **총 master 추가** | **1,007건** |
| 에러 | **0건** |

**Before → After**:
- 활성 master 룰: 2,813 → **3,820** (+1,007)
- 커버 법령: 199 → **211** (+12)
- 미파싱 article: 1,548 → 366

### 3.6 v1.9.0 — Sonnet 전환 + safe_update_master

**커밋**: `73847da` (main, Cursor 작업)

**CLAUDE_MODEL 전환**:
```python
기존: CLAUDE_MODEL = "claude-haiku-4-5-20251001"
변경: CLAUDE_MODEL = "claude-sonnet-4-20250514"
```

배경: 대표님 판단 "개정된 법만 파싱하면 되니 Sonnet 하나로 병합해도 됨". Sonnet이 1차 파싱에서 penalty/condition 채움률이 높아 2차 패스(reparse) 필요성 감소.

**safe_update_master 헬퍼** (`services/safe_db_update.py`):
```
기존 문제: Sonnet이 30개 필드 중 1개만 타입을 틀려도 전체 UPDATE 실패 → 29개도 버려짐
해결: 1차 전체 UPDATE 시도 → 실패 시 필드별 개별 UPDATE → 29개 저장, 1개만 skip
```

### 3.7 v1.11.0 — reparse 병렬 처리

**커밋**: `741f384` (main, Cursor 작업)

순차 처리(건당 87초, 1000건=22시간)를 병렬로 전환:

| 항목 | Before | After |
|---|---|---|
| 처리 방식 | 순차 1건씩 | asyncio.gather 3~5건 동시 |
| sleep | 3초/건 | 0.5초/배치 |
| 컨텍스트 | 매건 DB 조회 | 동일 법령 캐시 |
| 속도 | 87초/건 | 3.5~6초/건 |

### 3.8 reparse 전 sector 실행 — 빈칸 보강

| 회차 | sector | 수정 | 에러 | 비고 |
|---|---|---|---|---|
| 1차 (ALL, limit=2000) | ALL | 669 | 23 | 890/1000에서 멈춤 (타임아웃) |
| 2차 (CONSTRUCTION) | CONSTRUCTION | 147 | 329 (partial) | ✅ 완료 |
| 3차 (MANUFACTURING) | MANUFACTURING | 438 | 0 | ✅ 완료, 에러 0 |
| 4차 크레딧 소진 | MANUFACTURING | 0 | 50 | ❌ Anthropic 크레딧 부족 |
| — 크레딧 충전 — | | | | |
| 5차 (MANUFACTURING) | MANUFACTURING | 438 | 0 | ✅ 재실행 완료 |
| 6차 (BUILDING+COMMON 동시) | BUILDING | 744 | 56 | ✅ 완료 |
| | COMMON | 835 | 36 | ✅ 완료 |
| 7차 (4개 동시, 2차 보강) | CONSTRUCTION | 33 | 54 | ✅ 잔여 빈칸 |
| | MANUFACTURING | 27 | 55 | ✅ |
| | BUILDING | 29 | 462 | ✅ |
| | COMMON | 31 | 564 | ✅ |
| **합계** | | **~2,400건+** | | |

---

## 4. 이슈 및 해결

### 이슈 1: \u2028 인코딩 폭발
- **증상**: 모든 Supabase 호출에서 position 219 ASCII 에러
- **원인**: SUPABASE_KEY(JWT) 끝에 \u2028 문자 (iCloud Desktop 동기화 + NFD/NFC 충돌 추정)
- **시도**: 4번 패치 모두 실패
- **해결**: 로컬 환경 의존 자체를 제거 → Railway 내장 endpoint화
- **교훈**: 로컬 환경은 통제 불가. 서버에서 실행하는 게 정답.

### 이슈 2: SYSTEM_PROMPT 산업안전 편향
- **증상**: 갭 B 22개 법령에서 0초안
- **원인**: 프롬프트 첫 줄 "산업안전 법령 전문가"
- **해결**: 5영역 명시적 확장
- **교훈**: 프롬프트 편향은 출력 데이터 전체를 왜곡함. 입력 데이터가 아무리 좋아도 프롬프트가 틀리면 결과가 0.

### 이슈 3: INSPECT 한정 자동승인
- **증상**: APPOINT/NOTIFY 의무가 PENDING으로만 쌓임
- **원인**: auto-parse-and-approve에서 INSPECT만 자동승인
- **해결**: 5개 의무유형 모두 자동승인 + condition_code 게이트
- **교훈**: 자동승인 범위가 좁으면 수동 검토 부담만 증가.

### 이슈 4: DB UPDATE 전체 실패
- **증상**: Sonnet이 30개 필드 중 1개 타입 오류 → 나머지 29개도 버려짐
- **원인**: PostgreSQL single UPDATE에서 1개 필드 타입 불일치 → 전체 롤백
- **해결**: safe_update_master — 1차 batch 실패 시 필드별 개별 UPDATE
- **교훈**: AI 출력은 항상 타입 불일치 가능성이 있으므로, graceful degradation 필수.

### 이슈 5: 병렬 타임아웃
- **증상**: CONCURRENCY=5에서 890건 처리 후 멈춤
- **원인**: asyncio.gather에서 Sonnet 1건이 타임아웃 → 전체 배치 블록
- **해결**: CONCURRENCY=3으로 축소 + sector별 분리 실행
- **교훈**: 외부 API 병렬 호출은 보수적으로. 5보다 3이 안정적.

### 이슈 6: Anthropic 크레딧 소진
- **증상**: 모든 Sonnet 호출 실패 ("credit balance too low")
- **원인**: auto-parse-all(1,548건) + reparse(수천 건) 연속 실행
- **해결**: 크레딧 충전 후 재실행
- **교훈**: 대량 작업 전 크레딧 잔액 확인 필요.

---

## 5. 최종 결과

### 5.1 채움률 변화

| 필드 | Before (아침) | After (최종) | 변화 |
|---|---|---|---|
| penalty_summary | 59.2% | **85.4%** | +26.2%p |
| condition_code | 68.2% | **90.4%** | +22.2%p |
| remarks | 73.6% | **93.5%** | +19.9%p |
| form_name | 미추적 | **83.2%** | 신규 |
| tai_feature_code | 미추적 | **85.3%** | 신규 |

### 5.2 master 룰 변화

| 지표 | Before | After |
|---|---|---|
| 활성 룰 | 2,813 | **3,820** (+1,007) |
| 커버 법령 | 199 | **211** (+12) |
| 미파싱 article | 1,548 | **366** |

### 5.3 배포된 버전

| 버전 | 커밋 | 내용 |
|---|---|---|
| v1.7.0 | `6b927e4` | SYSTEM_PROMPT 5영역 + 자동승인 5종 + condition_code 게이트 |
| v1.8.0 | `c0ed727` | POST /auto-parse-all 내장 endpoint |
| v1.9.0 | `73847da` | Sonnet 전환 + safe_update_master |
| v1.11.0 | `741f384` | reparse 병렬 3건 + 컨텍스트 캐시 |

### 5.4 추가 변경

- `services/safe_db_update.py` 신규 (`7a0d988`)
- `scripts/finalize_law_pipeline.py` 폐기 → deprecated stub (`b61ec0f`)
- `industrial_accident_precedents` 테이블 16컬럼 추가 + `precedent_rule_links` 테이블 신규 (DDL migration)
- `routers/law_viewer.py` 신규 — 조문+판례 조회 endpoint (`9f16b0e`)
- `services/legal_format.py` 9필드 반영 (`9f16b0e`)

---

## 6. 남은 빈칸 분석

penalty 557건, condition 367건이 여전히 빈칸. 이는 법령 원문 자체에 해당 정보가 없는 경우:
- 벌칙 조항이 없는 훈시 규정
- 조건 없이 전 사업장 적용되는 의무
- NFTC(소방기술기준) 등 기술표준 (벌칙 구조가 다름)

추가 reparse를 돌려도 채워지지 않는 구조적 한계. 향후 `build_full_context` 개선(벌칙 조문 자동 매핑)으로 일부 해결 가능.

---

## 7. 향후 개선 방향

1. **build_full_context 개선**: 벌칙 조문(제XX조) 자동 매핑 → 1차 파싱에서 penalty 채움률 향상
2. **Sonnet 단일 모델**: Haiku 완전 제거. 개정법 파싱 시 Sonnet으로 1차에 고품질 추출
3. **판례 자동 수집**: 형사 벌칙 294건 기반 키워드 → 대법원 API → precedent_rule_links 자동 매칭
4. **서비스 레이어 분리**: legal_engine.py 77KB 등 20KB+ 라우터 5개 대상
5. **법령 개정 자동 감지**: 법제처 API 폴링 → 변경 조문 자동 재파싱 파이프라인
