# 세션 핸드오프 — 법령엔진 파이프라인 정리 (2026-04-24 ~ 04-25)

> 이 문서는 클로드 기획창에서 진행된 4월 21일 시작 ~ 4월 25일 오전까지의 법령엔진 파이프라인 정리 작업 전체 맥락을 담은 인계 문서입니다. 다음 세션에서 이 문서만 읽으면 어디서 멈췄는지 정확히 파악할 수 있도록 작성했습니다.

---

## 1. 한 줄 요약

법령엔진의 데이터 측면(파싱·룰 등록·품질)이 "구 Haiku 파이프라인" → "신 Sonnet 파이프라인"으로 사실상 마이그레이션 완료된 상태이며, 활성 룰은 1,133 → 2,813건(+148%)으로 도달. 남은 미해결 갭은 NFTC 86건 미파싱과 21개 일반법령 0초안 문제 두 가지.

---

## 2. 핵심 사실 — "두 개의 디비"의 의미

대표님이 4/25 오전에 지적하신 **"구버전·신버전 두 개의 디비"** 는 별도 Supabase 프로젝트가 아니라, **같은 DB(`xntdkrjhgcscmqctdzyo`) 안에 두 세대의 파이프라인이 만들어 낸 데이터가 공존**한다는 의미.

| 구분 | 구 파이프라인 (Haiku) | 신 파이프라인 (Sonnet) |
|---|---|---|
| 시기 | 2026-04-02 ~ 04-03 | 2026-04-24 이후 |
| `law_rule_drafts.article_id` | **NULL** (외래키 미연결) | `law_article.id`와 연결 |
| 모델 | Claude Haiku 4.5 | Claude Sonnet (auto_parse_parallel.py) |
| 품질 | condition_code 미할당 잦음, executor/penalty 채움률 낮음 | condition_code/executor/penalty 평균 83~96% |
| 현재 상태 | 4/24에 일괄 REJECTED 처리 (정리 완료) | 활성 master 등록 중 |

### REJECTED 947건의 정체 — "이미 재파싱된 잔재"

- **909건은 `article_id = NULL`** — 구 파이프라인 흔적
- 38건은 `article_id` 있음 (9개 고유 article)
- 같은 의무가 신 파이프라인 Sonnet draft → master로 이미 들어가 있어, 구 Haiku draft는 더 이상 필요 없음 → REJECTED 정리

**결론: REJECTED 947건을 "복원해서 master 등록" 하면 안 된다.** 대표님 기억대로 이미 재파싱 완료. SQL로 복원 시 false positive 룰이 다시 master에 들어가 활성 2,813 → 3,700+로 부풀려지지만 품질이 망가짐.

---

## 3. 4/21 ~ 4/24 작업 흐름

### 4/21 — 완성도 측정
- 수집된 법령 398개 중 **140개만 룰 생성, 258개 미생성**
- 활성 룰 1,133건 / 필요 추정 3,000~5,000건 (커버리지 23~38%)
- reparse-master 엔드포인트 1차 완료분: 460건 처리 → 372건 빈 필드 채움 (81% 성공률)

### 4/24 새벽 ~ 오전 — auto_parse + reparse 대량 실행
1. **923건 비활성 룰 분석** → 138 중복 삭제 + 785 저품질 삭제(B방법: auto_parse Sonnet 재생성)
2. **auto_parse_parallel.py 백그라운드 실행** → 14,291/14,292건 파싱, 98분
3. **reparse 라운드** (Railway BackgroundTask, Claude Sonnet)
   - 1차: ALL 460/460 → 372건 수정
   - 2차: COMMON 366/366 (281 수정), BLD 300/300 (168 수정)
   - 3차: MFG 200, CON 100 → DB 재시작(메모리 2배 업그레이드)으로 사망 → 재시작 후 일부만 처리
4. **품질 변화 (전→후)**

| 필드 | 시작 | 1차 | 2차 | 3차 최종 |
|---|---|---|---|---|
| remarks | 62% | 89% | 95.7% | **96.6%** |
| penalty | 50% | 75% | 82.5% | **83.5%** |
| executor | 51% | 75% | 83.2% | **83.9%** |
| condition | 80% | 93% | 95.7% | **96.5%** |
| cycle | 20% | 37% | 42.8% | **44.6%** |

5. 갱신 규모: **1,539건 / 147개 법령**

### 4/24 오후 — 정순/역순 분석
- 빈 필드 0개(완전): 73% (1,683/2,291)
- NFTC/NFPC 98건이 품질 평균 깎음 (penalty 31%, executor 17%) — 설치기준이라 원래 과태료/주체 개념 약함
- COMMON 39건 critical, BUILDING 18건 critical
- INSPECT 룰의 37%가 penalty 빠짐, APPOINT의 34%가 executor 빠짐

### 4/24 오전 11시 — PENDING 일괄 등록
- PENDING 일반법령 49건 → 187건 master 등록 (36개 법령)
- PENDING NFTC 228건 → 191건 master 등록 (TECHNICAL_STANDARD)
- 70-79 신뢰도 → 155건 (48 condition있음 + 107 범용) master 등록
- **합계 +533건 신규 등록** → PENDING 546 → 45, 활성 룰 2,280 → **2,813**

### 4/25 오전 — 대표님 지적
- "처음부터 다시 했고, 이번이 마지막 작업, 하나도 놓치지 않아야 함, 이후부터 파이프라인으로 돌아가야 함"
- "이건 메모리하고, 파싱을 다시해야한다면 완벽해야 함, 정순+역순으로 한 번에"
- 클로드가 21개 0초안 법령 + REJECTED 1,284건 가설 제시 → SQL 1~4 즉시 실행 제안
- **대표님 정정: "두 개의 디비. Haiku 792는 이미 재파싱됨. 기존 작업내역 학습하고 다시 이야기"**
- 클로드 응답 미완성 → 새 창으로 인계

---

## 4. 현재 DB 상태 (2026-04-25 02:30 KST 검증)

### 활성 룰
- **2,813건** (커버 법령 158개)
- source_api: AI_GENERATED + TECHNICAL_STANDARD

### 드래프트 상태
| 상태 | 건수 | 비고 |
|---|---|---|
| APPROVED | (다수) | master 등록 완료분 |
| REJECTED 구 Haiku | **947** | 4/24 정리분, 909건이 article_id NULL (구 파이프라인) |
| REJECTED 범위외 | 559 | 4/2 정리분, 14개 법령 외 일괄거부 (재검토 가치 있음) |
| PENDING | 45 | 신뢰도 50 미만 8 + 50~69 37 |

### 품질 채움률
- condition_code: ~96.5%
- remarks: ~96.6%
- executor: ~83.9%
- penalty: ~83.5%
- inspect_cycle: ~44.6%

---

## 5. 진짜 미해결 갭 (남은 작업)

이전 분석에서 "묻혀 있다"고 잘못 진단했던 1,284건은 실은 이미 재파싱 완료된 잔재. 진짜 남은 갭은 다음 셋.

### 갭 A — NFTC 86건 미파싱
- 법령 매핑 실패로 auto_parse 처리 안 됨
- 위치: `law_article.ai_parsed_at IS NULL`
- 조치: M2max 로컬에서 auto_parse_all.py 86건만 재실행 (~2분)
- 우선순위: **낮음** (NFTC는 설치기준, 사업장 적용 조건이 약함)

### 갭 B — 21개 일반법령 0초안 (산업안전 외 의무)
파싱은 됐지만 AI가 "산업안전보건 관련 의무"에 집중하느라 다음 영역의 의무를 추출 못함:

| 영역 | 법령 (예시) | 사유 |
|---|---|---|
| 재난관리 | 재난 및 안전관리 기본법 (164조문) | 모든 사업장 재난 대비 의무 누락 |
| 파견근로 | 파견근로자 보호법 (58조문) | 파견 사용 사업장 안전 의무 누락 |
| 환경 | 탄소중립법, 토양환경, 잔류성오염, 악취 | TAI 산업 섹터 영향 있음에도 누락 |
| 주택 | 주택법 시리즈 (312조문) | 건물 섹터 영향 |

**조치 방안 (대표님 판단 필요):**
- 21개 법령 `ai_parsed_at` NULL 리셋 + 프롬프트 확장(`산업안전 + 재난관리 + 환경관리 + 근로자 보호`) → auto_parse 재실행
- 또는 핵심만 (재난법·파견법·주택법) 우선 처리

### 갭 C — REJECTED 범위외 559건 (4/2 정리분)
- 14개 법령만 타겟했을 때 일괄 거부했던 데이터
- 신 파이프라인은 182개 법령 전체 타겟이므로 일부는 정당한 룰일 가능성
- 조치: SQL로 PENDING 복원 후 신 파이프라인 자동승인 게이트(`condition_code IS NOT NULL`)에 통과시켜 등록

### 갭 D — INSPECT의 penalty 채움률 63%
- 점검 의무에 과태료 정보가 빠진 룰이 37%
- reparse-master로 빈 필드 채우기 가능 (Railway API)
- 우선순위: 중간 (소비자 전달 품질 개선)

---

## 6. 절대 하지 말 것 (이번 세션 학습)

- ❌ **REJECTED 구 Haiku 947건을 "복원+master 등록"** — 이미 재파싱됨, 복원 시 품질 망가짐
- ❌ **활성 룰 숫자 부풀리기 위한 일괄 SQL UPDATE** — 4/24 교훈: condition_code 없는 룰이 master에 들어가면 false positive
- ❌ **Railway reparse 2개 동시 실행** — DB 커넥션 풀 고갈, Supabase 과부하 → 메모리 두 배 업그레이드 필요했음
- ❌ **2개 reparse 돌고 있을 때 tai-api main 커밋** — 배포 = 서버 재시작 = BackgroundTask 사망

---

## 7. 다음 세션 시작 지점

이 핸드오프 문서를 읽고 시작하면 됩니다. 대표님이 결정해주셔야 할 것:

1. **갭 B (21개 0초안 법령)** — 전부 재파싱 vs 핵심만(재난법·파견법·주택법)?
2. **갭 C (범위외 559건)** — 복원 시도 vs 그대로 폐기?
3. **갭 A (NFTC 86)** — 지금 처리 vs 우선순위 낮으니 보류?

이 셋이 결정되면 "마지막 작업"으로 한 번에 처리하고, 이후부터는 `law_collector.py` → `auto_parse_parallel.py` → reparse-master 파이프라인을 정상 운영 모드로 돌리면 됩니다.

---

## 8. 관련 파일·엔드포인트

### 코드
- `routers/law_rule_generator.py` v1.5.0+ — Sonnet 파싱 + reparse + 품질게이트
- `services/rule_gen_svc.py`, `rule_gen_helpers.py`, `rule_gen_builders.py`, `rule_gen_reparse.py`, `rule_gen_prompts.py`, `rule_gen_ai.py` — 서비스 레이어 분리 (4/24 진행 중)
- `scripts/auto_parse_parallel.py` — M2max 로컬 실행용 일괄 파싱 (98분 소요)

### 엔드포인트
- `POST /law-rule-generator/auto-parse-and-approve`
- `POST /law-rule-generator/bulk-approve-unregistered`
- `POST /law-rule-generator/reparse-master` (sector별 limit)
- `GET /law-rule-generator/reparse-master/jobs`
- `GET /law-rule-generator/scorecard` (STEP 4)

### DB 함수
- `legal_engine_scorecard()` RPC — 단계별 ✅/🟡/🔴 집계

### 이슈
- GitHub `taiengineering/tai-api#24` — 법령엔진 파이프라인 보강 (소비자 전달 구조까지 포함)

---

**작성일**: 2026-04-25
**작성자**: Claude (TAI 기획009 → 다음 창 인계)
**참조**: `대화저장.rtf` (RTF 원본, 7,326 라인, 4/21~4/25 오전)
