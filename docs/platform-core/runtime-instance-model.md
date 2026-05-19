# Runtime Instance Model

## runtime_task vs runtime_instance

| | runtime_task | runtime_instance |
|---|---|---|
| 성격 | 정적 운영 정의 | 실제 실행 건 |
| 예시 | 정기안전보건교육 | 2026-Q2 정기교육 |
| 수명 | 영구적 | 실행 1회 |
| 상태 | candidate/assigned | scheduled/pending/completed |

## 예시

```
정기안전보건교육 (runtime_task)
  └─ 2026-Q1 정기교육 (runtime_instance) → completed
  └─ 2026-Q2 정기교육 (runtime_instance) → scheduled
  └─ 2026-Q3 정기교육 (runtime_instance) → (Worker가 생성 예정)
```

## Evidence Completeness

```
required = runtime_instance_evidence WHERE state='missing'
uploaded = runtime_instance_evidence WHERE state='uploaded'
validated = runtime_instance_evidence WHERE state='validated'

completeness = validated / required * 100
```

## Execution Snapshot

실행 순간의 WHO/HOW/WHEN/CONDITION/SCHEDULE/Evidence를 고정 저장.
법령이 변경되어도 당시 기준 보존.
