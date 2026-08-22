# 문서엔진 현황·자산 인벤토리 v1 (실측)

> 작성일: 2026-08-22
> 방식: GitHub 코드 + taieng DB(vwlahtguyggrhvslabax) 실측
> 목적: 기존 자산으로 실제 안전관리 문서를 제공하기 위한 현황 고정

---

## 0. 문서엔진은 둘이다 (혼동 방지)

| 엔진 | 위치 | 역할 | 상태 |
|---|---|---|---|
| tai-api 문서엔진 | taiengineering/tai-api | 법정 안전 서식·의무 문서의 생성·바인딩·라이프사이클 | 본 문서 대상 |
| eng:DOC | 45cminc/doc | 파일→텍스트 변환(디지털화) + 렌더 (federation) | 별도, Phase4 완료·Phase5 대기 |

> eng:DOC는 과거 제출 문서(스캔·한글·엑셀) 디지털화·보관에 활용 가능. 본 문서는 tai-api 문서엔진에 집중.

---

## 1. 자산 인벤토리 (실측)

| 자산 | 상태 | 실체 |
|---|---|---|
| 렌더 엔진 | 완전 구현 | services/document_engine/renderer.py (Jinja2 → Gotenberg PDF) |
| 증빙 리포트 생성 | 완전 동작 | routers/compliance_report.py (운영데이터 4종 집계→PDF) |
| 데이터 패처 | 2종만 | inspection, tbm (education 미구현) |
| 완성 템플릿 | 2개만 | DOC-OSH-056(TBM), DOC-COMPLIANCE-REPORT |
| 서식 카탈로그 조회 | 운영 중 | routers/engine_document.py v1.1.0 (2026-08-18) |
| 스키마 바인딩 엔진 | 엔진 완료·데이터 미확정 | document_schema/document_runtime, CANDIDATE 3,873필드 |

## 2. 3개 테이블 역할·건수 (실측)

| 테이블 | 건수 | 역할 |
|---|---|---|
| document_forms | 260 | 전수조사 카탈로그(무엇이 필요한지 지도) |
| form_templates | 11 | 법정 별지 서식(관공서 제출 HWP) |
| document_form_master | 63 | TAI 표준·자유서식 |

document_forms 260건 분포: 등급 A30/B75/C72/D37/X46 · 의무 법정필수170/의무83/권고7 · 섹터 BUILDING81/COMMON77/CONSTRUCTION71/INDUSTRIAL31.

## 3. 핵심 격차

| 단계 | 건수 | 근거 |
|---|---|---|
| 법이 요구(법정필수+의무) | 253 | obligation |
| 카탈로그 등록 | 260 | document_forms |
| TAI 자동화 가능(X 제외) | 214 | 등급 A~D |
| 즉시 가용(데이터 준비됨) | 25 | A등급 갭분석 |
| 실제 생성 가능(템플릿 완성) | 2 | templates/documents |

→ "무엇을 만들어야/만들 수 있는가"는 확정됨. 비어있는 것은 **실제 렌더링 템플릿**뿐.

## 4. 검증된 레퍼런스

compliance_report.py가 "운영데이터 조립 → 템플릿 렌더 → Gotenberg PDF"를 이미 성공. 이 패턴을 doc_id별로 일반화(document_forms에 /generate 추가 + doc_id↔fetcher↔template 배선)하는 것이 실제 문서 제공의 핵심 작업.

## 5. 관점 확정: 직접 점검 방식

안전관리자가 배당 없이 직접 점검하는 운영. 점검 주기 설정 = 문서 발생 스케줄. 점검하는 행위 자체가 문서가 되는 구조(compliance_report와 동형). 이 방식은 데이터 소스가 1인으로 단순해 문서엔진에 유리.

## 6. 미결(핸드오프)

- document_schema CANDIDATE 3,873건 미확정(Human Review 전)
- education_fetcher 미구현 · 보관현황(storage) Phase3 하드코딩
- document_schema/document_runtime 라우터 main.py 등록 여부 미확인
- admin/document-output 전용 라우터 부재

---

*실측 기준. 이후 작업은 이 현황 위에서 진행.*
