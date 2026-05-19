# Runtime Metadata Resolution Layer

## 작업일: 2026-05-19
## 목표: 법령 구조 내부 운영 메타데이터 deterministic 복원

---

## DB 4테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| appendix_runtime_metadata | 16 | 별표 Runtime 메타데이터 |
| legal_delegation_graph | 15 | 위임조항 역추적 그래프 |
| runtime_schedule_pattern | 20 | 스케줄 구조화 패턴 |
| runtime_metadata_resolution | 7 | Runtime 메타데이터 해결 결과 |

## 검증 결과

### Metadata Resolution Coverage (7개 핵심 Runtime)

| Metadata | Resolved | Ratio |
|---|---|---|
| WHO | 7/7 | **100%** |
| WHEN | 7/7 | **100%** |
| HOW | 7/7 | **100%** |
| CONDITION | 6/7 | **86%** |
| SCHEDULE | 6/7 | **86%** |
| EVIDENCE | 4/7 | **57%** |

### Operationalization Verification

| Runtime | completeness | candidate 생성 |
|---|---|---|
| 안전관리자 선임 | 100% | ✅ 가능 |
| 위험성평가 | 100% | ✅ 가능 |
| 작업계획서 | 100% | ✅ 가능 |
| 정기안전보건교육 | 91.7% | ✅ 가능 |
| 사출기 방호장치 | 91.7% | ✅ 가능 |
| 밀폐공간 측정 | 91.7% | ✅ 가능 |
| 위험물 정기점검 | 83.3% | ⚠️ PARTIAL (시행규칙 위임) |

평균 completeness: **94.1%**

### Schedule Structuring Coverage

20개 패턴 중 HIGH confidence: 19개 (95%)

### Structural vs Operational Boundary

**법령 내부 (구조적 해결 가능):**
- 선임기준, 교육시간, 작업전점검, 보존기간, 위험물질 분류, 건설기계 유형, 화학설비 유형

**법령 외부 (수동 매핑 필요):**
- 사진증빙 형식, 체크리스트 UX, 모바일 입력 UX, 산업 관행

## 결론

Hybrid Runtime 구조 확정.
법령 구조 내부만으로 WHO/WHEN/HOW/CONDITION/SCHEDULE 94% 복원 가능.
EVIDENCE 형식만 법령 외부 사전 필요.
