# 03 — Check Result Storage Design

Check가 돌려준 `EvidenceReport`를 진단 실행 단위로 TAI 저장소에 보관하는 설계.

저장소: Supabase `taieng` 프로젝트(`vwlahtguyggrhvslabax`). tai-api에는 이미 `db/`, `supabase/`, `sql/`가 존재. **본 문서는 스키마 설계만** 제시한다(마이그레이션 적용은 별도 승인 작업).

## 1. 저장 원칙

- Check 결과는 **관측 기록(observation)** 이다. 사업적 의미가 아니라 구조 상태값이다.
- Check가 산출한 **결정적 id(`report_id`)** 를 멱등 키로 사용한다. 동일 진단 실행 입력 → 동일 report_id → upsert(last-write-wins, Check 결정성과 일치).
- Check는 도메인 데이터를 만들지 않으므로, **도메인 조인은 `obligation_id`** 로 TAI/LEG 의무 테이블과 연결한다.
- 전체 EvidenceReport 원본(jsonb)을 보관해 감사/재현(replay) 가능하게 한다.

## 2. 테이블 (제안)

### `check_reports`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| report_id | text PK | Check 산출 결정적 id (멱등 키) |
| tenant_id | uuid | 테넌트(RLS 기준) |
| diagnosis_run_id | text | TAI 진단 실행 id |
| scope_ref | text | `leg:diag:{tenant}:{run}` |
| engine_version | text | EvidenceReport.metadata.engine_version |
| schema_version | text | "v1" |
| generated_at | timestamptz | = input.now |
| inventory | jsonb | EvidenceReport.inventory |
| status_summary | jsonb | EvidenceReport.status_summary |
| raw_report | jsonb | EvidenceReport 전체(감사/재현) |
| created_at | timestamptz | 저장 시각 |

UNIQUE(report_id). INDEX(tenant_id, diagnosis_run_id).

### `check_observation_records`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| report_id | text FK→check_reports | |
| tenant_id | uuid | RLS |
| claim_ref | text | `leg:obligation:{obligation_id}` |
| obligation_id | text | 도메인 조인 키(역정규화) |
| claim_status | text | CLAIM_PRESENT/REF_MISSING/OUT_OF_SCOPE |
| chain_status | text | EVIDENCE_CHAIN_* |
| evidence_chain_ref | text null | |
| evidence_statuses | jsonb | [{evidence_ref, status}] |
| observed_at | timestamptz | = input.now |

INDEX(report_id), INDEX(tenant_id, obligation_id), INDEX(chain_status).

> MVP에서는 evidence_matrix를 별도 테이블 없이 record의 jsonb로 보관. 행 단위 분석이 필요해지면 `check_evidence_status`로 정규화(후속).

## 3. 도메인 조인

- Check 저장물에는 도메인 의미가 없다. 사람 검토 화면(05)은 `obligation_id`로 LEG/TAI 의무 데이터(법령명·조문·의무유형·completeness)를 조인해 함께 보여준다.
- 조인은 **읽기 시점**에 수행. Check 테이블은 도메인 값을 복제하지 않는다(LEG completeness 등 미저장; 필요 시 진단 스냅샷 테이블에서 조인).

## 4. 보안/RLS (필수)

- `taieng` 프로젝트에는 RLS 미적용 테이블 이슈가 있음(별도 인지된 보안 항목). **본 신규 테이블은 생성 시점부터 tenant_id 기반 RLS를 적용**한다. RLS 없이 생성 금지.

## 5. 보존/이력

- 진단 실행마다 `scope_ref`에 run_id가 포함되어 `report_id`가 달라짐 → 실행별 이력이 자연 누적된다.
- 동일 실행 재계산은 동일 report_id로 upsert(중복 누적 없음).
- 보존 기간/아카이브 정책은 제품 정책에 따름(미정 → 후속 결정).

## 6. 경계

- Check 결과 저장은 **TAI 책임**. Check는 저장을 모른다(consume-only).
- 저장 계층은 어떤 판단도 하지 않는다. 검토 우선순위·표시는 05 문서의 별도 계층에서.
