# 세션 로그 — 2026-04-28 (기획창)

## Supabase 서울 이전 마무리 작업 (#58)

NEXT_SESSION_PROMPT.md 기반 잔여 작업 전부 완료.

### 1. 프론트엔드 Supabase URL+키 교체 (tai-admin)

검색 결과 운영 파일 5개 확인, 3커밋으로 교체 완료.

| 파일 | 변경 내용 | 커밋 |
|---|---|---|
| `admin/full-version/config.js` | URL + sb_publishable key | c2e09db |
| `tadmin/full-version/config.js` | URL + sb_publishable key | c2e09db |
| `admin/full-version/assets/js/tai/supabase-config.js` | URL + JWT anon key | c2e09db |
| `auto-qa-dashboard.html` | 인라인 SB_URL + SB_KEY | c44a303 |
| `diagram-gallery.html` | 폴백 URL | b8f810c |

교체 값:
- URL: `xntdkrjhgcscmqctdzyo.supabase.co` → `vwlahtguyggrhvslabax.supabase.co`
- sb_publishable: `pUs9aJ...` → `r0qsGe...`
- JWT anon: 구 프로젝트 ref → 신 프로젝트 ref

### 2. Edge Function Secrets 6개 — 대표 수동 완료

새 프로젝트 대시보드에서 수동 입력 완료:
- MESSAGEME_API_KEY, MESSAGEME_SENDER, TAI_INTERNAL_KEY
- KMA_SERVICE_KEY, LAW_API_OC, TAI_COLLECT_SECRET

### 3. Storage 파일 51개 이전

Chrome JavaScript로 구 프로젝트 public URL → 신 프로젝트 Storage API 업로드.

| 버킷 | 파일 수 | 결과 |
|---|---|---|
| diagrams | 28 | ✅ |
| site-assets | 17 | ✅ |
| app | 4 | ✅ |
| proposals | 2 | ✅ |
| **합계** | **51** | **51/51 성공, 0 실패** |

`diagram_templates.public_url` 25건도 신 프로젝트 URL로 PATCH 갱신 완료.

### 4. 기존 프로젝트 IPv4 비활성화 — 대표 수동 완료

$4/월 절약.

### 5. Claude 프로젝트 Supabase MCP 프로젝트 ID 교체 — 대표 수동 완료

단, 이 대화 세션에서는 캐시로 인해 구 프로젝트 응답이 유지됨.
다음 대화부터 `vwlahtguyggrhvslabax` 정상 반영 예상.

### 6. 구 프로젝트 정리 사항

- `copy-storage` Edge Function이 구 프로젝트에 잘못 배포됨 (MCP 캐시 이슈) → 삭제 필요
- 구 프로젝트 전체 삭제: 1주일 후 (2026-05-04 이후)

---

## 이슈 처리

| 이슈 | 상태 |
|---|---|
| #58 Supabase 서울 이전 | ✅ 전체 완료 (삭제만 1주 후) |

---

## 메모리 업데이트

- #12: 인프라 현황 → Supabase 서울 이전 완료 반영, project ID: vwlahtguyggrhvslabax
- #30: diagrams 버킷 URL → 신 프로젝트 URL 패턴으로 변경, Storage 이전 필요 표시 → 완료
