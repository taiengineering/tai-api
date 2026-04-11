# TAI 기획 세션 메모리 — 2026-04-11

> 다음 세션 인수인계용

---

## 오늘 확정된 사항

1. **공급자 등록 플로우**: 간편 가입 → 마이페이지 검증 방식 확정
2. **본인인증**: KG이니시스 직계약 (본인확인 기능), 신청 이메일 발송
3. **안전정보 메뉴 구조**: taieng(유입) vs safe(개인화) 역할 분리 확정
4. **특허 6건 출원 완료**: 5건 특허 + 1건 상표
5. **기상청 API 3종 신청 완료**: 단기예보·특보·특보구역 (KMA_SERVICE_KEY 별도)
6. **근로복지공단 산재판례 API 신청 완료**
7. **백업 정책 확인**: Supabase Pro 7일 자동 백업 정상 운영 중

---

## 미완료 작업지시 (PENDING)

### 백엔드창 (tai-api)
- [ ] weather.py — 기상청 API Hub 403 이슈 해결 (API Hub 활용신청 or Supabase Edge Function 프록시)
- [ ] precedent_api.py — 판례 검색 결과 0건 해결 (LAW_API_OC 확인)
- [ ] DATA_GOV_SERVICE_KEY Railway 환경변수 추가
- [ ] KCSC_SYNC 크론 FAILED 원인 조사
- [ ] LAW_COLLECT_MISSING 크론 FAILED 원인 조사

### 프론트엔드창 (taieng)
- [ ] nexas/patents.html 신규 생성 (특허증 스타일, 5건)
- [ ] nexas/assets/js/footer.js 수정 ("기술 혁신" 메뉴 + 특허 표기)
- [ ] nexas/index-5.html 판례검색 UI (검색창 중심)
- [ ] nexas/safety-news.html API 연동 (하드코딩 제거)
- [ ] safe 안전정보 페이지 신규

### 신청 필요
- [ ] Railway 환경변수 1Password 백업
- [ ] KG이니시스 이용계약서 우편 발송 (신청 이메일 후 계약서 도착 시)
- [ ] Q-Net API 기업 신청 (hrdkorea.or.kr, 공급자 검증 구현 전)
- [ ] 대법원 판례 API (data.go.kr)

---

## 참고 문서 위치 (docs/)

| 파일 | 내용 |
|---|---|
| TAI_공급자검증정책_확정_20260411.md | 자격 미검증 시 매칭 불가 원칙 |
| TAI_공급자등록플로우_확정_20260411.md | 가입→마이페이지 검증 플로우 |
| TAI_이니시스본인인증_신청_20260411.md | KG이니시스 직계약 신청 내역 |
| TAI_안전정보메뉴구조_확정_20260411.md | taieng vs safe 메뉴 배치 |
| TAI_안전정보_콘텐츠전략_20260411.md | 5종 콘텐츠 + 데이터 소스 |
| TAI_API신청현황_20260411.md | 전체 API 신청·개발 현황 |
| TAI_백업정책_20260411.md | 백업 현황 및 방법 |
| TAI_특허출원현황_20260411.md | 특허 6건 현황 |
| TAI_QNet_API_활용분석_20260411.md | Q-Net 활용 가능 항목 |
| TASK_안전정보_백엔드_20260411.md | weather.py + precedent_api.py |
| TASK_안전정보_프론트엔드_20260411.md | safety-news / index-5 / safe |
| TASK_특허페이지_프론트엔드_20260411.md | patents.html + footer.js |
| TASK_산재판례API_백엔드_20260411.md | precedent_api.py 상세 |
