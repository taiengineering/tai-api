# Runtime Asset Reuse Implementation 핸드오프

## 2026-05-20

## 핵심

Runtime은 기존 시스템을 대체하지 않는다. 연결/상태화/투영만 수행.

## 12 Phase

1. 무료 진단 UI 재사용 + Candidate Preview
2. Activation CTA 연결
3. 유료 = 기존 Safe 세팅 재사용 + Runtime Hook
4. Cockpit = 기존 홈 + Runtime Feed
5. work_schedules 단방향 sync
6. inspection_sets 직접 연결
7. Evidence 연결 (document_forms + attachments)
8. Assignment 기존 구조 재사용
9. PDF Projection 재사용
10. Excel Projection 추가
11. Runtime Feed 강화
12. Virtual Runtime 검증

## 금지

새 Schedule/점검/문서/Assignment/인력/Cockpit/PDF 엔진 전부 금지.
기존 재사용만.

## 부족한 것

엔진/구조/DB 아님. **연결/Projection/운영 UX**.
