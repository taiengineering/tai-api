# 세션10 작업내역 (2026-04-25)

**창**: 기획창 (TAI 기획10)
**범위**: 문서 스토리지 설계 + 이미지 압축 + 인프라 점검 + 이슈 정리

---

## 1. 통합 문서 스토리지 시스템 구축

### 배경
SaaS에서 자동생성 문서 저장 + 기존 문서 업로드가 필요. Supabase Storage 용량 분석 → Pro 100GB로 충분 확인.

### DB (Supabase Migration 실행 완료)
- `documents` 테이블 (33컬럼) — 통합 문서 메타데이터
- `doc_category` ENUM (13종: inspection, certificate, education, safety_plan, risk_assessment, msds, corrective, report, contract, tbm, equipment, facility_drawing, general)
- `doc_source` ENUM (USER_UPLOAD, AUTO_GENERATED, MIGRATED)
- `company-docs` 버킷 (private, 50MB 제한, RLS 경로 격리)
- DB RLS 정책 4개 + Storage RLS 정책 4개
- 인덱스 8개 (GIN full-text search 포함)
- 뷰 2개: `v_document_stats`, `v_documents_expiring`
- `updated_at` 자동갱신 트리거

### 코드 (Cursor에서 구현 완료)
- `services/document_svc.py` — 업로드/자동생성 등록/목록/signed URL/삭제/통계
- `routers/documents.py` — REST API 10개 엔드포인트
- `main.py` v5.36.0 — router 등록
- `tai-document.js` (tai-admin) — 프론트 문서 모듈 + 압축 연동 + UI 위젯
- `tai-image-compress.js` (tai-admin) — 이미지 압축 독립 모듈

### 경로 규칙
```
company-docs/{company_id}/{category}/{YYYY-MM}/{uuid}.{ext}
```

### 문서 (GitHub dev 브랜치)
- `docs/DOCUMENT_STORAGE_DESIGN.md` — 전체 아키텍처 설계서
- `docs/DOCUMENT_UPLOAD_REFERENCE.md` — 통합 레퍼런스 (전 창 공용)
- `docs/work-order-document-module.md` — 백엔드+프론트 구현 작업지시서
- `docs/work-order-image-compress-integration.md` — 압축 연동 작업지시서
- `docs/work-order-upload-migration.md` — 기존 10개 파일 마이그레이션 작업지시서

---

## 2. 이미지 압축 모듈

### tai-image-compress.js (tai-admin main 배포 완료)
- 카테고리별 프리셋: inspection(1920px/80%), corrective(1920px/80%), tbm(1280px/75%), certificate(2560px/85%)
- facility_drawing 압축 안 함 (도면 원본 보존)
- 안전장치: 이미지 아님→원본, HEIC→원본, 이미 작음→원본, 압축 후 더 큼→원본
- tai-document.js 없이도 단독 사용 가능
- 효과: 8MB JPEG → 300KB WebP (95% 절감)

---

## 3. 기존 파일 업로드 전체 스캔

### 결과 (10개 파일 수정 필요)

**프론트엔드 (tai-admin) 7개:**
- F1: `app/inspect.html` — 점검 사진 (PWA)
- F2: `app/construction_inspect.html` — 건설 점검 사진 (PWA)
- F3: `app/_utils.js` — FormData 유틸
- F4: `my-company.html` — 업체 로고/문서
- F5: `worker-list.html` — 작업자 자격증
- F6: `construction-inspection-list.html` — 건설 점검 첨부
- F7: `education-list.page.js` — 교육 자료

**백엔드 (tai-api) 3개:**
- B1: `services/upload_service.py` — 구 업로드 서비스 → deprecated
- B2: `routers/contacts.py` — 문의 첨부
- B3: `routers/education.py` — 교육 자료

**수정 불필요:** mail.page.js (내부 메일 시스템)

---

## 4. 인프라 확인

### Supabase 리전 확인
- **도쿄 (ap-northeast-1)** 확인 (IPv6 `2406:da18:243` = AWS ap-northeast-1)
- 기존 메모리에 "미국 동부 추정"으로 잘못 기록 → 정정 완료

### Railway 리전 현실
- Railway는 **아시아에 싱가포르만 제공** (도쿄 없음)
- 4개 리전: us-west1, us-east4, europe-west4, asia-southeast1
- 도쿄 이전하려면 Railway를 떠나야 함 (Fly.io 도쿄 등)
- 현재 ~200ms 지연은 B2B SaaS에 당장 치명적이지 않음
- 시점: 기능 완성 후 고객 피드백에서 속도 이슈 나오면 검토

### Supabase Storage 현황
- 현재: 27MB / 50파일 (개발 자산만)
- 4개 시스템 버킷 유지: site-assets, diagrams, app, proposals
- 7개 구 버킷 → company-docs로 통합 예정
- Pro 100GB 범위 내 고객 ~650개소까지 추가 비용 없음

---

## 5. 개정법령 페이지 점검 (law-updates.html)

### 구조 파악
- `law_revision_board` 테이블(28컬럼, 0건) 사용 안 함
- `law_version` + `law_master` + `master_building_legal_rules` 3테이블 Supabase REST API 직접 조회
- 2025년 49건 + 2026년 65건 = 114건 데이터 확인

### 버그 수정 (즉시 실행)
- `master_building_legal_rules` RLS 정책 누락 → `public_read_legal_rules` + `service_role_full` 추가
- 이전에 RLS 켜져있으나 정책 0개여서 anon 접근 차단 → 규칙 수/섹터 표시 안 됨 → 수정 완료

### 이슈 #54 등록
- `[파이프라인] 개정법령 자동 수집 + 즉시 노출 파이프라인 구축`
- P1: revision_type_code 빈 값 27건 보정
- P2: pg_cron + Edge Function 자동 수집
- P3: 안전관리자 알림 연동 (#30과 연결)

---

## 6. 이슈 정리

### 닫은 이슈 4건
| 레포 | # | 제목 | 사유 |
|---|---|---|---|
| tai-api | #52 | 세션9 완료 로그 | 기록 완료 |
| tai-api | #36 | XML 파싱 파편화 | #37과 중복 |
| tai-admin | #1 | KG이니시스 차단 해제 | 코드 완료 |
| tai-admin | #2 | safe 로그인 리디자인 | 완료 |

### 현재 열린 이슈 8건 + PR 1건
| 트랙 | 이슈 |
|---|---|
| 법령엔진 | PR#53, #54, #46, #37 |
| 결제 | #45 (외부 대기) |
| 보안 | #43 |
| 기능 | #30 |
| 데이터/리팩토링 | #33, #29 |

---

## 7. 메모리 업데이트
- #12 교체: Supabase 도쿄 확인 + 문서 스토리지 구축 완료 + 마이그레이션 작업지시서 기록

---

## 다음 세션 할 일

### 즉시
- **safe.taieng.co.kr 전체 점검** — 별도 프론트창에서 브라우저 자동화로 진행
  - 로그인 → 전 페이지 순회 → 목업 데이터 → 콘솔 에러 → UX 분석
  - 프롬프트: 아래 참조

### 이후
- PR #53 머지 → auto_parse 실행 (갭 B 법령 파싱)
- reparse job 완료 확인 (현재 80/1000 진행 중)
- 기존 업로드 10개 파일 마이그레이션 (`docs/work-order-upload-migration.md`)

---

## safe.taieng.co.kr 전체 점검 프론트창 프롬프트

```
safe.taieng.co.kr 전체 기능 점검 세션입니다.
레포: taiengineering/tai-admin, 경로: tadmin/full-version/html/horizontal-menu-template/
참조: docs/DOCUMENT_UPLOAD_REFERENCE.md (tai-api dev)

[목표] 안전관리자 시각으로 전체 페이지 점검 + 목업 데이터 투입

[점검 범위]
1. 로그인 → 대시보드 진입
2. 전체 메뉴 순회 (모든 페이지 접속 + 스크린샷)
3. 목업 데이터 투입:
   - 업체 1개 + 공장 2개 + 작업자 5명
   - 점검 3건 + 시정조치 1건 + TBM 1건
   - 교육 1건 + 위험성평가 1건
4. 각 페이지별:
   - 기능 동작 여부 (버튼, 폼, 링크)
   - 콘솔 에러
   - 네트워크 실패
   - 데이터 표시 정확도
   - 모바일 반응형 (375px)
5. PWA 앱 (safe.taieng.co.kr/app/) 16개 페이지도 포함

[결과 형식]
페이지별: 상태(✅/⚠️/❌) + 이슈 목록 + 개선 제안
최종: 우선순위별 종합 보고서
```
