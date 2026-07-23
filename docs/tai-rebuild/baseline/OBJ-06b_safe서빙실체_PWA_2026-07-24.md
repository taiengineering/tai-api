# OBJ-06b — safe 서빙 실체 + 모바일 PWA 전수 (조사)

일자: 2026-07-24 · 대상: `taiengineering/tai-admin`@main `tadmin/full-version/` · READ-ONLY 조사
범위 결정(사용자): 모바일 PWA **포함** · 런타임 콘솔 **보류** · admin 화면(engine-monitoring/watch-engine) **admin 이관·safe 제거**.

## A. 데스크톱 리빌드 = 이미 LIVE(in-place)
결론: 메뉴가 링크하는 **평문 `X.html`이 곧 리빌드본**. `*.rebuild.html` 32개는 서빙 안 되는 스테이징 잔재.
근거:
- `assets/js/tai/menu-tadmin.js`(v6.2.0) 모든 href가 평문(.rebuild 없음): `href:'factory-list.html'`, `'my-company.html'`, `'construction-site-list.html'` … 각 항목 `rebuilt:true`는 파란점 UI 표시용 플래그.
- `_redirects`에 `X.html→X.rebuild.html` rewrite 없음(루트·checkin만). SPA fallback 의도적 제거.
- 평문 원본이 이미 리빌드 모듈 부팅: `factory-list.html` 하단 `<script type="module" src="../../assets/js/tai-rebuild/pages/factory-list/bootstrap.js">`.
- `.rebuild.html` 정확히 32개 = 메뉴 주석 "리빌드 완료 32" 일치.
- 미검증: 32개 평문 원본 각각의 in-place 부트스트랩 전수(1개=factory-list 직접 확인, 나머지는 카운트·정황 일치로 추정) → O6-b 실행 시 전수 스팟검증.

## B. 모바일 PWA(`app/`) 전수
Base: tai-api `https://api.taieng.co.kr`(`_utils.js` `API`/`apiFetch`). OTP 발송만 Supabase Edge `.../functions/v1/send-otp`.
인증: 전화 OTP. index는 tai-api `/auth/send-otp` 호출하나 `_utils.js`가 로드시 **Supabase Edge로 오버라이드**(Railway 우회). 검증 `/auth/verify-otp`→access_token localStorage. 이후 Bearer. 401→세션삭제·`/app/index.html`.

| 화면 | 엔드포인트 | 메서드 |
|---|---|---|
| index | `/auth/send-otp`(→Edge override), `/auth/verify-otp`, `/workers/fcm-token`, `/work-assignments?...`, `/users/{id}/signature` | POST/GET |
| attendance | `/attendance` | POST |
| inspect | `/inspection-sets/{sid}/items`, `/inspection-set-items?factory_id=`, `/worker-check/submit`, `/uploads/inspection-photo` | GET/POST |
| construction_inspect | `/construction/sites/{id}`, `/worker-check/submit`, `/uploads/inspection-photo` | GET/POST |
| risk | `/risk-assessments/{id}`, `/risk-assessments/participate` | GET/POST |
| tbm | `/tbm/{id}`, `/tbm?site_id=|factory_id=&status=ACTIVE`, `/tbm/sign` | GET/POST |
| education | `/education/{id}`, `/education/complete` | GET/POST |
| corrective | `/safety-reports/{id}`, `/safety-reports/{id}/confirm` | GET/POST |
| emergency | `/emergency/report` | POST |
| report | `/uploads/inspection-photo`, `/safety-reports` | POST |
| work_request | `/work-requests` | POST |
| history | `/worker-check/history?...` | GET |
| notifications | `/notifications?worker_id=&phone=&...` | GET |
| qr_scan | `/construction/sites/{id}`, `/attendance` | GET/POST |
| profile / install | 백엔드 호출 없음(localStorage/정적) | — |

엔진 호출 0건. 오프라인 큐(`queueFlush`)는 위 기존 엔드포인트 재전송(신규 없음).

## O6-b 실행 계획(초안)
1. **데스크톱 스테이징 잔재 정리**: `*.rebuild.html` 32개 참조 전수 확인 후 제거(단, 이들이 편집 원본인지 여부 사용자 확정 필요 — 아래 결정).
2. **admin 화면 이관**: `html/admin/engine-monitoring.html`, `watch-engine.html` → admin 소관으로 이동, safe 메뉴/파일에서 제거.
3. **평문 32화면 in-place 부트스트랩 전수 스팟검증**(회귀 방지).
4. **모바일 PWA**: OTP 정식 경로 확정(현 실사용=Supabase Edge), Firebase FCM 이관 범위 확인.
5. **공유 코어 dedup**(admin과): `api.js`/`auth-guard.js`/`config.js` 공유 패키지화(O6-c와 연계).
6. 런타임 콘솔(`html/runtime/` 9): 보류(별도 조사).

## 결정 필요
- **`*.rebuild.html` 32개**: 서빙 안 되는 잔재로 확인됨. (a) 제거 vs (b) 편집 원본이라 유지 — 어느 쪽인지 확정.
- **QR 체크인 진입점**(`/checkin`→데스크톱 `qr-check.html`): 데스크톱/모바일 소속.
