# 2026-04-19 기획창 세션 작업 이력

## 완료 작업

### 1. 기안 PDF v6 개편 (PR#10 merged)
- 포지션: 품의서 첨부용 분석보고서 (결재란 없음, TAI SaaS 영업 없음)
- 과태료: penalty_sum (중대재해법 제외 합산)
- INDUSTRY 3등급 동등안내 (추천배지 없음)
- 활용포인트: "관공서 안전감독 시 법적 의무 이행 입증 근거자료"
- 도메인: taieng.co.kr 공식
- diagnosis_proposal.py v2.0.0 + proposal_pdf.html 612줄
- Supabase Storage proposals 버킷 (캐싱, 302 redirect)

### 2. Gotenberg PDF 엔진 교체 (Cursor 작업)
- xhtml2pdf → Gotenberg (Docker Chromium) 교체 완료
- tai-gotenberg Fly 앱: nrt 리전, 1GB, auto_stop
- diagnosis_proposal.py v2.1.0
- BUILDING 310KB / INDUSTRY 313KB, 4페이지
- 캐싱 302 redirect 정상 동작
- 비용: ~$5~7/월

#### Gotenberg 해결 이슈
- .internal DNS 해석 실패 → tai-gotenberg.fly.dev (public URL) 사용
- Chromium OOM → 512MB → 1GB 증량
- Cold start 실패 → CHROMIUM_AUTO_START=true + START_TIMEOUT=60s
- URL: safe.taieng.co.kr → https://taieng.co.kr 통일

#### Gotenberg 커밋 이력 (main)
| SHA | 내용 |
|---|---|
| 366bc8d | feat: Gotenberg Chromium PDF 엔진 적용 (v2.1.0) |
| c9bca5f | fix: httpx timeout 30s → 60s |
| 074ccc1 | fix: Gotenberg 메모리 512MB → 1GB |
| cdbf800 | fix: URL을 https://taieng.co.kr로 통일 |
| 54674e8 | fix: Chromium auto-start + startup timeout 60s |

### 3. 유료 진단 입력 폼 SaaS 일치 (Cursor + 기획창)
- DB 마이그레이션 실행 완료 (기획창 Supabase MCP)
  - PAID2: has_welding 등 8건 비활성화, process_list searchable_select로 수정
  - PAID3: has_crane 등 12건 비활성화, equipment_list (table, 40개 select) 신규
- Cursor 코드 작업 완료:
  - diagnosis_fields.py: /process-options, /equipment-options 엔드포인트 추가
  - diagnosis_integrated.py: tier/form_data 처리, 무료 tier 매핑 보정
  - legal_engine.py: equipment_list → has_crane 등 변환 로직
  - free-diagnosis.html: table 렌더링, searchable_select, system_codes 연동

### 4. 유료 진단 리포트 기획 시작
- full_result 데이터 구조 파악 완료 (25개 키, 72~101KB)
- 웹 요약(paid-diagnosis-result.html) + PDF(Gotenberg 20~28p) 2종 필요
- 상세 설계는 다음 세션에서 진행

## 미해결 이슈

### ISS-01: Gotenberg .internal DNS
- Fly.io 내부 DNS(tai-gotenberg.internal) 해석 안 됨
- 현재: tai-gotenberg.fly.dev (public URL) 사용 중
- 영향: 외부 경유로 ~50ms 지연 추가
- 조치: Fly 지원팀 확인 후 .internal 재시도 (비용 절감)

### ISS-02: 기안 PDF 4페이지 렌더링
- v6 mockup은 3페이지이나 실제 PDF는 4페이지
- 원인: P3 콘텐츠가 A4 한 장 초과
- 조치: Gotenberg CSS (@page, page-break) 활용한 템플릿 재디자인 (v7) 필요

### ISS-03: 연면적 0㎡ 표시
- FREE 진단 토큰으로 기안 PDF 생성 시 "입력 연면적 0㎡ 기준 자동 판정" 노출
- 원인: FREE 진단에서 total_floor_area 미입력
- 조치: 0일 때 "정보 없음" fallback 또는 FREE 토큰 기안 PDF 차단

### ISS-04: process_list → facility_ctx 매핑 미구현
- legal_engine.py에서 equipment_list → has_crane 등 변환은 완료
- process_list는 아직 facility_ctx에 매핑 안 됨
- 영향: 공정 기반 법령 매칭이 불완전할 수 있음
- 조치: 룰이 process_list를 직접 참조하면 별도 매핑 필요

### ISS-05: disclaimer_log_id 누락
- 유료 직입 runPaidDiagnosis에서 disclaimer_log_id 없이 호출 가능
- 백엔드가 면책 동의를 강제하면 에러 발생 가능
- 조치: 프론트에서 면책 체크박스 → log_id 전달 플로우 확인 필요

### ISS-06: 유료 PDF + 웹 요약 미구현
- 유료 진단 결과의 웹 표시(paid-diagnosis-result.html)와 PDF(diagnosis_report.py) 미완성
- 데이터 구조는 파악 완료 (full_result 25개 키)
- 조치: 다음 세션에서 설계 + 구현

## 참조 파일
- docs/proposal_pdf_v6/README.md — 종합 핸드오프
- docs/proposal_pdf_v6/01_backend_task.md — 백엔드 작업지시
- docs/proposal_pdf_v6/02_frontend_task.md — 프론트 작업지시
- /mnt/user-data/outputs/diagnosis_input_saas_align_task.md — 입력 폼 SaaS 일치 작업지시
- /mnt/user-data/outputs/gotenberg_migration_task.md — Gotenberg 교체 작업지시
