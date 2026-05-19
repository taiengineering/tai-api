# Assignment Constraint Extraction 핸드오프

## 2026-05-20

## 구축 결과

### 신규 테이블
| 테이블 | 건수 | 역할 |
|---|---|---|
| runtime_assignment_requirement | **1,724** | 법령 기반 자격/기관/인원 요구조건 |

### 추출 결과
| 요구조건 유형 | 건수 | 설명 |
|---|---|---|
| professional_agency | 839 | 전문기관 요구 |
| staffing_count | 362 | 인원수 요구 (N명 이상) |
| dedication_required | 187 | 전담 요구 |
| appointment_required | 124 | 선임 필요 |
| presence_required | 99 | 상주/근무조건 |
| individual_qualification | 81 | 개인 자격명 |
| designated_agency | 32 | 지정기관 요구 |

### Runtime Task 연결
| 항목 | 건수 |
|---|---|
| Task에 연결된 requirement | 249 |
| 미연결 (범용 법령) | 1,475 |

### 기존 구조 재사용
| 기존 테이블 | 건수 | 재사용 |
|---|---|---|
| master_safety_manager_criteria | 19 | ✅ 선임기준 |
| fix_qualification_master | 58 | ✅ 자격사전 |
| safety_personnel | 0 (스키마만) | ✅ 인력프로필 |
| master_safety_certification | 50 | ✅ 설비인증 |

### Assignment Boundary
- Compiler: 요구조건 출력만
- Validation Layer: 충족 여부 확인 (미구현)
- Human: 최종 지정 (사람 승인)
