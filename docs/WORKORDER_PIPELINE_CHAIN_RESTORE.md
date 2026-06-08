# 작업지시서: 3건 파이프라인 마지막 고리 연결

> 공통 패턴: 새 경로가 기존 엔진 체인의 마지막 고리를 빠뜨림
> 브랜치: feature/pipeline-chain-restore-20260608

## 3건

1. **Evidence Chain 복원 (CRITICAL)** — Compiler Core 경로에 evidence_chain 누락
   → 진단→점검항목 자동생성 끊김
   → anonymous_factory_service._compiler_result_to_step1_format에 evidence 추가

2. **Document 서식→소비자 연결 (HIGH)** — document_form_master ↔ runtime_form_schema 단절
   → 조사 먼저: 두 테이블 관계, 매핑 방법 결정 후 구현

3. **Equipment Checkin→Evidence (HIGH)** — equipment_checkins → evidence_bridge 미연결
   → 조사 먼저: evidence_bridge 인터페이스 확인 후 연결

## 원칙

- 기존 엔진 수정 금지. 빠진 고리만 연결.
- 각 항목: 조사 → 보고 → 구현
- Draft PR, merge 금지

상세: 로컬 WORKORDER_PIPELINE_CHAIN_RESTORE.md
