# Runtime Compiler Projection Migration

## 2026-05-20

## 핵심 전환

기존 diagnosis engine → Runtime Compiler Projection

### 데이터 소스 변경

| 기존 | 신규 |
|---|---|
| diagnosis_result.summary | runtime_metadata_resolution |
| rules_table (hardcoded) | facility_applicability + metadata_resolution |
| key_obligations (manual) | runtime_task + metadata |
| old law grouping | metadata.source_law 기반 |

### Projection Boundary

| ✅ 표시 (진단) | ❌ 금지 (Runtime) |
|---|---|
| 의무명 + WHO/HOW/WHEN/SCHEDULE | overdue |
| Assignment Requirement | completed |
| Evidence Requirement | uploaded |
| 반복주기 규칙 | reviewer |
| 리스크 등급 | escalation |
| 과태료 | runtime health |

### API 엔드포인트

| API | 역할 |
|---|---|
| `GET /projection/factory/{id}` | 사업장 기반 Projection |
| `GET /projection/token/{token}` | 토큰 기반 Projection |
| `GET /diagnosis/paid-result/{token}` | 기존 호환 API (유지) |

### 테스트 토큰

| Token | CASE | 데이터 |
|---|---|---|
| runtime-case1-construction | 건설현장 78억 | 17건 metadata_resolution 기반 |
| runtime-case2-injection | 사출공장 250명 | 100건 runtime_task 기반 |

### P0 완료
- ✅ Projection API 라우터 생성
- ✅ CASE1 토큰 metadata_resolution 기반 강화
- ✅ Runtime Boundary 준수 (state 필드 제거)
- ✅ 기존 UI 유지

### P1 다음 작업
- [ ] 전체 3,395건 metadata_resolution → 사업장별 Projection
- [ ] Assignment Requirement Projection 컴포넌트
- [ ] Evidence Requirement Projection 컴포넌트
- [ ] 운영 계획서 PDF 재구성
- [ ] Excel Projection 5시트 구현
- [ ] Activation CTA 연결
