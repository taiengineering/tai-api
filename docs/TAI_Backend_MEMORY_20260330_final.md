# TAI Backend MEMORY — 2026-03-30 (Final)

## 현재 API 버전
- **main.py**: v4.3.3
- **legal_engine.py**: v4.3.3
- **engine_equipment.py**: v4.3.2
- **law_collector.py**: v2.0.3 (data.go.kr 기반)
- **Railway**: 정상 배포 (healthy)

---

## 오늘 완료된 작업 (2026-03-30)

### 1. Railway 빌드 안정화 ✅
- Dockerfile (python:3.11-slim + libcairo2-dev) 운영 중
- nixpacks.toml 비활성화 상태

### 2. 법령 12개 수집 완료 ✅ (로컬 collect_laws.py 실행)
| 법령 | 조문 수 |
|------|---------|
| 근로기준법 | 145개 |
| 소음·진동관리법 | 84개 |
| 악취방지법 | 44개 |
| 토양환경보전법 | 80개 |
| 하수도법 | 109개 |
| 소방기본법 | 100개 |
| 소방시설공사업법 | 71개 |
| 수도법 | 132개 |
| 주차장법 | 79개 |
| 환경기술 및 환경산업 지원법 | 85개 |
| 장애인·노인·임산부 편의증진법 | 45개 |
| 의료기기법 | 106개 |

- **수집 방법**: 로컬 Mac (211.193.39.137) → open.law.go.kr IP 등록 후 law.go.kr/DRF API 직접 호출
- Railway 서버 IP가 배포마다 변경되어 law.go.kr/DRF 사용 불가 (IP 등록 필요)
- data.go.kr API (apis.data.go.kr/1170000/law)는 serviceKey만 필요하나 파라미터명 미확인 상태

### 3. P2 — 신고/보고 구분 분리 ✅ (Supabase MCP)
- `master_building_legal_rules`에 컬럼 추가:
  - `notify_required BOOLEAN DEFAULT false`
  - `obligation_type VARCHAR(20)`
- 분류 결과: ACTION(158), REPORT(110), INSPECT(125), APPOINT(45), NOTIFY(17)
- obligation_summary 업데이트: 산업재해→보고의무, 안전관리자선임→신고의무, 중대재해→즉시보고

### 4. engine_equipment.py v4.3.2 신규 API ✅
- **GET /engine-equipment/stats**: asset 통계 5개 필드 추가
  - `asset_registered_total`, `asset_no_model`, `asset_no_inspection`
  - `legal_inspection_target_count`, `legal_inspection_unmapped`
- **GET /engine-equipment/assets-list**: 신규 (필터: search/has_model/no_inspection/is_legal_target/equipment_type_code)
- **PATCH /engine-equipment/assets/{asset_id}**: 신규 (Pydantic AssetPatchBody)

### 5. 섹터 편중 룰 복제 ✅ (Supabase MCP)
5개 법령(산안법기준규칙, 시행규칙, 안전보건교육규정, 근로기준법, 산재보상보험법)을
BUILDING → MANUFACTURING + CONSTRUCTION 복제

### 6. 룰 없는 법령 13개 판정룰 추가 ✅ (Supabase MCP)
- CONSTRUCTION 3개 법령 (건설기술 진흥법 시행령/규칙, 건설산업기본법 시행규칙)
- SPECIAL_FACILITY 10개 법령 (의료법/노인복지법/사회복지사업법/다중이용업소법/어린이놀이시설법/학교안전법/공공보건의료법)
- diagnosis_stage=1 업데이트, obligation_summary 공백 채우기 완료

### 7. legal_engine.py v4.3.2 step1 개선 ✅
- `factory_id` Optional (없으면 익명 진단)
- flat body 파라미터 수용 (employee_count, floor_area 등 직접 전달)
- obligation_type 완전 반영 (DB값 우선 + 플래그 fallback)
- summary.report / summary.notify 분리

### 8. legal_engine.py v4.3.3 summary.notify 버그 수정 ✅
- **원인**: `_classify_rules_db`에서 notify_required=true 룰이 action으로 분류됨
- **수정**: notify_required / obligation_type=="NOTIFY" 분기 추가 → triggered["notify"] 별도 버킷
- **결과**: summary.notify = 14 (이전: 0), NOTIFY 룰 = 6개

---

## 현재 DB 상태 (master_building_legal_rules)

| 섹터 | 룰 수 |
|------|-------|
| BUILDING | 400 |
| MANUFACTURING | 108 |
| CONSTRUCTION | 120 |
| SPECIAL_FACILITY | 45 |
| **전체** | **673** |

무결성:
- 미매핑룰: 0 ✅
- summary공백: 0 ✅
- 항파싱0개법령: 0 ✅

---

## 법령 수집 관련 핵심 원칙

### law.go.kr/DRF API
- OC(사용자ID) + **서버 IP 등록 필수**
- Railway IP가 배포마다 바뀜 → 사실상 Railway에서 사용 불가
- 로컬 Mac에서 collect_laws.py로 수집 후 Supabase에 직접 저장하는 방법 유효
- 로컬 IP(211.193.39.137) open.law.go.kr에 등록됨

### data.go.kr/1170000/law API
- serviceKey만 필요, IP 제한 없음 → Railway에서 사용 가능
- lawSearchList.do 파라미터명 미확인 (resultCode 03 오류)
- 향후 파라미터 확인 후 law_collector.py 완전 전환 필요

### 로컬 수집 스크립트
- 파일: `collect_laws.py` (로컬 다운로드용)
- 실행: `python3 ~/Downloads/collect_laws.py`
- Supabase URL/KEY 하드코딩 (anon key)

---

## 주요 원칙 (누적)
- **PostgreSQL 컬럼명**: 항상 소문자
- **main.py 수정**: 반드시 단독 `create_or_update_file`로
- **Railway PDF**: xhtml2pdf 사용 (Dockerfile로 libcairo2-dev 설치)
- **law.go.kr DRF**: Railway IP 변동으로 사용 불가 → 로컬 수집 or data.go.kr
- **diagnosis_stage**: 신규 INSERT 룰은 반드시 diagnosis_stage=1 설정
- **obligation_type**: DB값 우선, 없으면 플래그(notify_required > report_required > ...) fallback
- **_classify_rules_db**: notify_required 분기가 report_required보다 먼저 체크되어야 함
