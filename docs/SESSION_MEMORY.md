# TAI Safe Backend (tai-api) - Session Memory
**마지막 업데이트: 2026-04-06**

**제품·아키텍처 공유 (다른 창·에이전트 참조)**: [`docs/TAI_전체_작업_정리_공유용.md`](./TAI_전체_작업_정리_공유용.md)

---

## ✅ 최근 완료된 작업

### 2026-04-06
- ✅ AI 생성 룰 937개 비활성화 (condition_code 미설정 → is_active=false)
- ✅ `GET /drafts` has_condition 필터 추가 (law_rule_generator v1.5.0)
- ✅ `main.py` v5.6.0 업데이트
- ✅ 데이터 분석: PENDING 262개 / BUILDING 섹터 완성도 / inspection_sets 미생성 50건
- ✅ condition_code 입력 우선순위 목록 작성

### 2026-04-05
- ✅ `contract_kmong.py` v1.0.0 — 크몽 법령진단 API 5개
- ✅ `law_rule_generator.py` v1.5.0 — has_condition 필터
- ✅ `main.py` v5.5.5 → v5.6.0

### 2026-04-02~03
- ✅ `engine_document.py` v1.0.0 — 문서메뉴 API 4개
- ✅ `legal_engine.py` v5.4.2 — 섹터 필터, 건설 필드 추가
- ✅ `document_form_master` 테이블 생성, TAI표준서식 10종 INSERT
- ✅ 법령 파싱 3,986조문 100% 완료
- ✅ master_building_legal_rules 2,080개

---

## 📋 현재 DB 상태

| 테이블 | 현황 |
|--------|------|
| `master_building_legal_rules` | 2,080개 (active 1,143 / inactive 1,144) |
| `law_rule_drafts` | APPROVED 1,330 / PENDING 262 / REJECTED 559 |
| `inspection_sets` | 68개 활성 일정 |
| `document_form_master` | 10종 (TAI표준서식) |

## 🚨 즉시 처리 필요

1. **rule_type_code=NULL 52개** → 진단 사용 불가. 분류 작업 선행
2. **승강기 안전관리법 INSPECT 12건** → inspection_sets 즉시 생성 가능
3. **고압가스 안전관리법 42건 PENDING** → condition_code `gas_capacity_kg` 일괄 입력

## 📋 다음 작업 (우선순위순)

1. rule_type_code=NULL 52개 분류
2. condition_code 입력 (고압가스 → 시설물 → 도시가스 순)
3. PENDING 262개 수동 검토
4. inspection_sets 자동 생성 (승강기 12건 우선)
5. 공지예외주장 제출 기한: **2026-04-28**

---

## 🔐 인증 / 계정
- **Admin**: hetto@kakao.com (role 001)
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v5.6.0)

## 📌 주의사항
1. **API 사이즈 제한**: `size <= 100` (pagination 필수)
2. **라우트 순서**: 구체적 경로(/bulk, /stats)를 /{id} 앞에 선언
3. **SHA 필수**: create_or_update_file 시 현재 SHA 먼저 조회
