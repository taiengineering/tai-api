# Virtual Runtime World

## 개념

TAI 전체 Runtime 구조를 가상의 산업 세계로 시뮬레이션하는 운영 시뮬레이터.
단순 목업이 아니라, Runtime 흐름 / 병목 / Assignment / Evidence / Overdue / Qualification 문제를 분석할 수 있는 시스템.

---

## 산업 시나리오 (10개)

| # | 시나리오 | 업종 | 인원 | 특징 |
|---|---|---|---|---|
| 1 | 건설현장 A | 건설업 | 180명 | 아파트 120억, 협력사 22 |
| 2 | 사출공장 B | 플라스틱 제조 | 300명 | 2교대, 사출기 28대 |
| 3 | 화학공장 C | 석유화학 | 150명 | 위험물, 3000kVA |
| 4 | 물류창고 D | 대형물류 | 80명 | 지게차 중심 |
| 5 | 소규모제조 E | 금속가공 | 35명 | 안전관리자 선임 면제 |
| 6 | 식품공장 F | 식품제조 | 200명 | 보건관리자 필수 |
| 7 | 병원 G | 종합병원 | 500명 | 위험물+소방 |
| 8 | 데이터센터 H | IDC | 50명 | 고전압 5000kVA |
| 9 | 발전설비 I | 열병합 | 100명 | 특수시설물 10000kVA |
| 10 | 다사업장 J | 본사+3공장 | 400명 | 다사업장 관리 |

---

## Runtime Variation

| 상태 | 비율 | 역할 |
|---|---|---|
| completed | 12.5% | 정상 완료 |
| in_progress | 12.5% | 실행 중 |
| pending | 12.5% | 대기 |
| scheduled | 25% | 예정 |
| overdue | 25% | **기한초과** |
| cancelled | 12.5% | 취소 |

---

## Evidence Variation

| 상태 | 비율 |
|---|---|
| missing | 75% |
| uploaded | 12.5% |
| validated | 12.5% |

---

## Personnel Variation

| 상태 | 인원 | 설명 |
|---|---|---|
| VERIFIED | 12 | 정상 |
| PENDING | 2 | 검증 대기 (미등록기관 포함) |
| EXPIRED | 1 | 자격 만료 |
| 개인 자격자 | 12 | 기사/산업기사/지도사 |
| 기관 | 3 | 안전관리전문기관, 보건관리전문기관 |

---

## 운영 메트릭

| 메트릭 | 값 | 해석 |
|---|---|---|
| Assignment Coverage | **0%** | 담당자 전체 미지정 (P0 blocker) |
| Qualification Compliance | **80%** | 15명 중 12명 정상 |
| Overdue Ratio | **25%** | 80건 중 20건 기한초과 |
| Evidence Completion | **12.5%** | 80건 중 10건만 검증완료 |
| Runtime Completion | **12.5%** | 80건 중 10건 완료 |
| Unresolved Ratio | **37.5%** | overdue + cancelled |

---

## 실제 데이터 보호

- 모든 virtual 데이터는 `[VIRTUAL]` 마커 포함
- `virtual_world_registry` 테이블에 등록
- `source_engine='virtual_world_generator'`로 구분
- `remarks LIKE '%VIRTUAL%'`로 필터 가능
- reset 시 virtual 데이터만 삭제

---

## Virtual Time Engine

```sql
-- +30일 시뮬레이션: overdue 증가 예측
SELECT instance_state, count(*)
FROM runtime_instance
WHERE instance_label LIKE '%VIRTUAL%'
AND scheduled_at < (CURRENT_DATE + 30)
AND instance_state IN ('scheduled','pending')
GROUP BY instance_state;
-- → 이 건들이 overdue로 전환될 예정
```

---

## 병목 분석

| 병목 | 원인 | 영향 |
|---|---|---|
| Assignment 0% | 담당자 전혀 지정 안 됨 | 실행 주체 없음 |
| Evidence 75% missing | 증빗 업로드 미연결 | 완료 판정 불가 |
| Overdue 25% | 스케줄 기한 초과 | 법적 리스크 |
| 자격만료 1건 | 산업안전산업기사 만료 | 선임 무효 위험 |
