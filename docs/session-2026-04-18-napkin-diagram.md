# 세션 요약 — 2026-04-18 Napkin 다이어그램 25종 + Admin 갤러리

## 작업 내역

### 1. Napkin AI 다이어그램 25종 텍스트 제공
- #1~#25 순서대로 대표님에게 입력 텍스트 제공
- 대표님이 napkin.ai에서 직접 생성 후 SVG 다운로드

### 2. Supabase Storage 정리
- `diagrams` 버킷 생성 (public, SVG/PNG, 10MB)
- 26개 SVG 업로드 → 중복 발견 (#21/#22 동일)
- 파일명 한글 변환 완료 (01-중대재해처벌법-적용-흐름도.svg ~ 25-안전관리-분산구조도.svg)
- 최종 25개 파일

### 3. DB 구축
- `diagram_templates` 테이블 생성 (25행)
- `get_diagrams_for_diagnosis()` 함수 생성
  - 건물 → 11장, 산업 → 14장, 건설 → 12장, 기본 → 5장
- RLS 정책 + anon SELECT 권한 부여

### 4. Admin 갤러리 페이지
- `diagram-gallery.html` 신규 (Supabase REST API 직접 호출)
- `supabase-config.js` 신규 (올바른 anon key 관리)
- `menu-nav.js` 수정 (시스템관리 → 다이어그램 추가)
- globals.js 복원 (실수로 덮어쓴 것 원본 복구)

## Supabase 변경사항
- 버킷: `diagrams` (public)
- 테이블: `diagram_templates` (25행, RLS enabled, anon SELECT)
- 함수: `get_diagrams_for_diagnosis(sector, conditions)`
- 파일: 25개 SVG (한글 파일명)

## GitHub 커밋 (tai-admin main)
- feat: admin 다이어그램 갤러리 페이지 + 운영설정 메뉴 추가
- fix: 다이어그램을 시스템관리로 이동, 운영설정 섹션 삭제
- fix: diagram-gallery 에러 핸들링 강화
- fix: globals.js 원본 복원 + supabase-config.js 생성
- fix: diagram-gallery에서 supabase-config.js 참조

## GitHub 커밋 (tai-api dev)
- docs: Napkin AI 25종 다이어그램 Sonnet 작업 프롬프트

## PENDING
- [ ] 마케팅 사이트에 다이어그램 <img> 삽입 (1순위 활용)
- [ ] 법령진단 PDF에 다이어그램 자동 삽입 코드
- [ ] Phase B 착수 (7일 일정)
