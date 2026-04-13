# safe.taieng.co.kr 현장 앱 백엔드 작업 지시서
> 2026-04-13 기획창 분석. 상세는 tai-admin/docs/workorder-safe-app-analysis.md 참고.

---

## 백엔드 작업 항목

### BUG-02: TBM 하드코딩 제거 ██ HIGH
- TBM 생성/조회 API가 construction_site_id에 하드코딩
- factory_id 기반으로 동작하도록 변경
- construction_site_id는 건설 유형(sector=construction)일 때만 사용

### BUG-03: 알림 발송 확인 ██ HIGH
- notifications 112건 중 실제 발송 0건
- send_status=SUCCESS인데 sent_at이 NULL인지 확인
- Railway cron HTTP 405 오류와 연관 여부
- SMS/카카오톡 API 키 설정 확인

### BUG-04: 점검항목 일괄생성 ██ HIGH
- inspection_sets 304개 / inspection_set_items 67개 (부족)
- `/inspection-sets/generate-all-items` 엔드포인트 실행 확인

### API 추가 필요
1. **유형별 데이터 필터링** — 모든 리스트 API에 `sector` 파라미터 지원
2. **작업자 전용 API** — 오늘의 할일(배정된 점검/TBM/교육) 한번에 반환
3. **QR 스쳪 → 점검** — equipment_id로 해당 설비 점검세트 반환
4. **점검 사진 업로드** — Supabase Storage 업로드 + 점검결과 연결

### DB 현황 (참고)
- work_schedules: 268건 (전부 MANUAL, ENGINE=0)
- work_assignments: 2,881건 (배정 892, 미배정 1,989)
- 미배정은 안전관리자가 최초 1회 배정 안 한 상태 (정상 흐름)
- notifications: 112건 (send_status=SUCCESS, 실제 발송 0)
- construction 관련 테이블: 모두 0건 (미구축)
