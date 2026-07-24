# 발견 오류 처리 (2026-07-24)

## 1. PWA 매니페스트 아이콘 깨짐 — 수정·검증 완료
- 증상: `/app/manifest.json`이 `../assets/img/tai-icon-192/512.png`·`screenshot-{home,inspect}.png`를 참조하나 **리포에 부재**(import 시점부터 깨진 상태). PWA 설치 아이콘·리치 설치 UI 깨짐.
- 수정(커밋 `37033f3`, tai-admin main): icons/shortcut icons를 **이미 서빙 중인 `/images/branding/brand-img-light.png`(sizes: any)** 로 재지정, 깨진 `screenshots`(선택 필드) 제거.
- 검증: 배포 후 라이브 `/app/manifest.json`이 수정본 반영, 아이콘 경로 = 실제 서빙 파일(200). → **해소.**
- 후속: 정사각 마스커블 192/512 전용 아이콘은 PWA 분리(O6-V1x) 때 디자인 자산으로 최종 제공.

## 2. worker-check 백엔드 계약 부재 — 확정 (→ O6-V2)
- vue3 `src/pages/worker-check/*`가 호출하는 `/equipment-checks/template`·`/equipment-checks`(및 건설용 `/construction-worker-checks`)가 **tai-api 코드에 없음**(`equipment_checks`/`equipment-checks` .py 매치 0, 문서 1건 제외). 저장 시 404 예상.
- 성격: O6-V1 결정으로 **워커 정본 = 풀 PWA(`public/app`)**, vue3 `worker-check`는 QR 딥링크 보조폼. 따라서 이 페이지는 비정본·미완.
- 처리(O6-V2 결정 필요): (a) vue3 worker-check 라우트를 **폐기/보류** 하거나 (b) 백엔드에 해당 엔드포인트 신설. PWA(정본)는 확인된 엔드포인트(`/worker-check/submit`, `/inspection-sets…` 등) 사용 중이라 현장 워커 경로는 정상.
