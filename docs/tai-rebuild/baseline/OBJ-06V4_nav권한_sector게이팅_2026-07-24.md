# O6-V4 — nav 권한 정합: 계약 sector 게이팅 (2026-07-24)

## 결정·구현
결정: 계약 sector×level 게이팅 배선(권장). 이번 배치는 **안전·고가치의 sector 게이팅**을 구현. level·FREE는 후속(사유는 아래).

구현(tai-admin main, 파일별 순차 커밋):
- `vue3/src/navigation/gate.ts` (신규, `ac5c35c`): `filterNavByContract(items)` — localStorage `contract_sector`/`role_code` 읽어 필터. **실패-오픈**: sector 미확정이거나 admin(001/002)이면 전체 표시. 그룹 자식이 전부 숨으면 그룹도 숨김.
- `vue3/src/navigation/horizontal/index.ts` (`527aa2d`): 그룹/항목에 `_gate.sectors` 추가.
  - 시설관리(그룹+시설목록·설비관리)=FACILITY·INDUSTRIAL, 공정관리=INDUSTRIAL, 점검관리=FACILITY·INDUSTRIAL, 작업근로자=INDUSTRIAL·CONSTRUCTION, 기타의 건설* 항목=CONSTRUCTION. 나머지(대시보드·TBM·교육·문서·알림·마이페이지 등)=게이트 없음.
  - vertical은 horizontal 재export라 자동 동일 적용.
- 레이아웃 배선(`e9dba8d` 가로, `09243a7` 세로): `filterNavByContract(navItems)` 주입.

## 검증
- 빌드: gate.ts+nav(`527aa2d`) **build·deploy success**(현재 safe.taieng.co.kr 라이브) → 게이팅 로직·규칙 컴파일 정상 확인. 레이아웃 2건 순차 빌드 성공 중(활성화 임박, 트리비얼 편집).
- **런타임 검증 한계**: API로는 빌드 통과만 확인 가능. **플랜별 실제 메뉴 노출은 팀 런타임 QA 필요**(계약 sector별 로그인 후 메뉴 확인). 실패-오픈 설계라 계약 데이터 없으면 전체 노출(누락 방지).

## 후속(별도)
- **level 게이팅**: 플랜 level(1~4)별 기능 노출 매트릭스가 필요(제품 데이터). tadmin은 대체로 lv>=1(유료 여부)만 사용 → 현 sector 게이팅으로 대부분 커버. 세분 level 규칙은 매트릭스 확정 후.
- **FREE 전용 메뉴**: FREE(sector=FREE, level 0)는 tadmin에서 별도 메뉴(법령진단·전문가매칭)였음. 현 vue3 nav엔 FREE 변형이 없어, FREE 사용자 경험은 별도 FREE nav 설계 필요(제품결정). 현재는 실패-오픈으로 게이트 없는 항목만 노출됨 → FREE 메뉴는 후속 확정.
- 규칙은 `horizontal/index.ts`의 `_gate` 한 곳 + `gate.ts` 로직으로 조정 용이.
