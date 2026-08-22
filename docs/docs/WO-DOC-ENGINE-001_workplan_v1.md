# 작업계획서 WO-DOC-ENGINE-001 — 문서엔진 생성 파이프라인 배선 v1

> 작성일: 2026-08-22
> 상태: 진행중 (WO-1·WO-2 완료, WO-3 대기)
> 상위: DOCUMENT_ENGINE_MASTER_PLAN_v1 (로드맵 단계 2~5)
> 근거: DOCUMENT_CODE_CONVENTION_v1 · DOCUMENT_SOURCE_MAPPING_v1
> 목표: 즉시가용 A등급 문서를 실제 생성 가능 상태로. 신규 엔진 없이 기존 검증 자산(renderer·fetcher·compliance_report 패턴) 재활용.

## 결정 (operator 2026-08-22)
- 매핑 저장 = **별도 테이블**.
- 2겹 레지스트리 = **테이블**.
- WO-1 착수 승인 완료.

---

## 0. 원칙

- 각 WO는 조사→구현→검증 후 다음. A등급에서 방식 검증 후 확장(폭주 금지).
- 엔진 평가로직·기존 운영 데이터 무변경. 추가는 additive(테이블 신설).
- 코드는 식별자, 분류는 컬럼(코드 규정 계승).

## 1. 작업 순서·상태

### WO-1 · 1겹 매핑 (문서 → 코드체계) — ✅ 완료
- **별도 테이블** `document_type_mapping` 신설(doc_id·doc_type·doc_detail·source_note).
- A등급 30건 시딩 완료: EQUIP 15(세부 채움)·INSP 4·EDU 3·TBM 2·APPT 2·CHK 2·PPE 1·CONLOG 1.
- EQUIP 세부(DETAIL)는 **문서명 기준** 부여. equipment_type_code 정렬은 별건(§4 참조).
- 검증: 30건 전량 분류, 8유형 커버, EQUIP 세부 정상.

### WO-2 · 2겹 매핑 (유형 → 템플릿·fetcher 레지스트리) — ✅ 완료
- **테이블** `document_type_registry` 신설(8행): doc_type → template_file·fetcher_key·evidence_source·fetcher_status.
- fetcher_status 실측 결과:
  - EXISTING(기존 fetcher 즉시): INSP·EQUIP·TBM·CHK·PPE = **24건**.
  - NEW_NEEDED: CONLOG·EDU.
  - NO_SOURCE(입력폼): APPT.
- 검증: 8유형 등록, 1겹 매핑 30건과 조인 정합.

### WO-3 · 생성 경로 배선 — 대기
- document_forms(또는 신규) 라우터에 `/{doc_type}/preview`·`/{doc_type}/generate` 추가.
- compliance_report 패턴 일반화: registry로 fetcher·template 조회 → 조립 → renderer → PDF.
- 발행 코드(TYPE-사업장-YYYYMMDD-[세부]) 생성 규칙 적용.
- 우선 대상: fetcher_status=EXISTING 24건(INSP·EQUIP·TBM·CHK·PPE).
- 검증: 목업 데이터로 INSP·TBM PDF 생성 성공(compliance_report와 동일 경로).

### WO-4 · 템플릿 제작 (즉시가용 우선) — 대기
- 순서: INSP → EQUIP → TBM(기존 재활용) → CHK → PPE.
- 각 템플릿: 표준 소스 지도(DOCUMENT_STANDARD_SOURCES) 따라 구성요소 확정 후 제작.
- EQUIP은 1템플릿 + 대상 데이터 주입.
- 검증: 유형별 목업 렌더 PDF 육안 확인.

## 2. 산출물 요약

| WO | 산출물 | 검증 기준 | 상태 |
|---|---|---|---|
| WO-1 | document_type_mapping + 30건 분류 | 30건 doc_type 채움 | ✅ |
| WO-2 | document_type_registry 8행 | 8유형 해소 | ✅ |
| WO-3 | 범용 preview/generate 라우터·서비스 | 목업 PDF 생성 | 대기 |
| WO-4 | 즉시가용 유형 템플릿 5종 | 렌더 육안 확인 | 대기 |

## 3. 범위 밖 (별도 WO)

- 확정본 스냅샷 보관(storage_ref) + 문서함 화면 (로드맵 6).
- B·C·D 등급 확장 (로드맵 7).
- 교육(EDU): 교육 모듈 가동 후.
- 티켓 차감(인앱 판매): 별도.
- 세 테이블 물리 통합 여부: operator 결정 후.

## 4. 별건 이슈 (분리 확정 2026-08-22)

- **type_code 데이터 정비(설비자산 도메인)**: equipment_assets.equipment_type_code가 목업 혼재(숫자·영문 대/소문자 3체계). 단, 이 컬럼은 법령진단 엔진(legal_engine_svc·trigger_applicability_adapter 등 34곳)의 입력이라 **삭제·격리 불가**(엔진 평가로직 불변). 오픈 전 설비 마스터 데이터 정비로 값만 정합화. 문서엔진 EQUIP DETAIL과는 별개 체계이며, 런타임 필터 연결이 필요하면 매핑 테이블로 잇는다.
- 이 이슈는 문서엔진 스코프 밖, 설비자산 도메인 별도 WO로 처리.

## 5. git 고정 (operator 후속, BKP-004)

- 적용된 마이그레이션: create_document_type_mapping · create_document_type_registry (실DB 반영됨).
- supabase/migrations git 파일 고정은 R-005 보호경로 → operator.

---

*WO-1·WO-2 완료. 다음 WO-3(생성 배선)은 EXISTING 24건 우선. 각 단계 검증 후 진행.*
