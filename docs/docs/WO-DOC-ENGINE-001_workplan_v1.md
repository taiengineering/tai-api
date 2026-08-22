# 작업계획서 WO-DOC-ENGINE-001 — 문서엔진 생성 파이프라인 배선 v1

> 작성일: 2026-08-22
> 상태: 계획 (operator 승인 후 착수)
> 상위: DOCUMENT_ENGINE_MASTER_PLAN_v1 (로드맵 단계 2~5)
> 근거: DOCUMENT_CODE_CONVENTION_v1 · DOCUMENT_SOURCE_MAPPING_v1
> 목표: 즉시가용 A등급 문서를 실제 생성 가능 상태로. 신규 엔진 없이 기존 검증 자산(renderer·fetcher·compliance_report 패턴) 재활용.

---

## 0. 원칙

- 각 WO는 조사→구현→검증 후 다음. A등급에서 방식 검증 후 확장(폭주 금지).
- 엔진 평가로직·기존 운영 데이터 무변경. 추가는 additive(컬럼·테이블 신설).
- 코드는 식별자, 분류는 컬럼(코드 규정 계승).

## 1. 작업 순서

### WO-1 · 1겹 매핑 (문서 → 코드체계)
- document_forms에 컬럼 additive: `doc_type`(TYPE), `doc_detail`(DETAIL, nullable).
- A등급 30건에 doc_type·doc_detail 채우기 (INSP·CHK·EQUIP·TBM·PPE·CONLOG·APPT·EDU + 설비 세부).
- EQUIP 세부는 equipment_assets.equipment_type_code 실제 값과 정렬.
- 산출: 마이그레이션(컬럼) + 시딩(30행 분류).
- 검증: A등급 30건 전부 doc_type 채워짐, EQUIP 세부가 실제 type_code와 매칭.

### WO-2 · 2겹 매핑 (유형 → 템플릿·fetcher 레지스트리)
- 신규 소형 레지스트리(8행): doc_type → template_file + fetcher_key + evidence_source.
- 기존 fetcher(inspection·tbm) 연결, 신규 필요분(CONLOG·협의체·교육) 표시.
- 산출: 레지스트리 테이블 또는 정책(JSON) + 시딩.
- 검증: 유형 8종이 템플릿·fetcher로 해소, 미구현 fetcher 명시.

### WO-3 · 생성 경로 배선
- document_forms 라우터에 `/{doc_type}/preview`·`/{doc_type}/generate` 추가.
- compliance_report 패턴 일반화: 2겹 레지스트리로 fetcher·template 조회 → 조립 → renderer → PDF.
- 발행 코드(TYPE-사업장-YYYYMMDD-[세부]) 생성 규칙 적용.
- 산출: 라우터 + 서비스(범용 generate).
- 검증: 목업 데이터로 INSP·TBM PDF 생성 성공(compliance_report와 동일 경로).

### WO-4 · 템플릿 제작 (즉시가용 우선)
- 순서: INSP → EQUIP → TBM(기존 재활용) → CHK → PPE.
- 각 템플릿: 표준 소스 지도(DOCUMENT_STANDARD_SOURCES) 따라 구성요소 확정 후 제작.
- EQUIP은 1템플릿 + 대상 데이터 주입.
- 산출: templates/documents/DOC-{TYPE}.html.
- 검증: 유형별 목업 렌더 PDF 육안 확인.

## 2. 산출물 요약

| WO | 산출물 | 검증 기준 |
|---|---|---|
| WO-1 | document_forms 컬럼 + A등급 30건 분류 | 30건 doc_type 채움 |
| WO-2 | 유형→템플릿·fetcher 레지스트리 8행 | 8유형 해소 |
| WO-3 | 범용 preview/generate 라우터·서비스 | 목업 PDF 생성 |
| WO-4 | 즉시가용 유형 템플릿 5종 | 렌더 육안 확인 |

## 3. 범위 밖 (별도 WO)

- 확정본 스냅샷 보관(storage_ref) + 문서함 화면 (로드맵 6).
- B·C·D 등급 확장 (로드맵 7).
- 교육(EDU): 교육 모듈 가동 후.
- 티켓 차감(인앱 판매): 별도.
- 세 테이블 물리 통합 여부: operator 결정 후.

## 4. operator 결정 필요 (착수 전)

- 매핑 저장: document_forms 컬럼 추가(권고) vs 별도 매핑 테이블.
- 2겹 레지스트리: 테이블 vs 정책(JSON).
- WO-1 착수 승인.

---

*본 WO는 A등급 즉시가용을 실제 생성 가능하게 만드는 최소 배선이다. 승인 후 WO-1부터 순차 착수, 각 단계 검증 후 진행.*
