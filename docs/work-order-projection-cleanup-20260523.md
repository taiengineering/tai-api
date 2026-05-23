# Runtime Projection 품질 안정화 (2026-05-23)

## 구현

| 파일 | 역할 |
|------|------|
| `services/projection_cleanup.py` | label cleanup, summary stabilize, dedup, sort, article flood |
| `services/legal_step1_builder.py` | `rules_table` 조립 직후 cleanup 연결 |
| `scripts/collect_projection_samples.py` | 24건 4단계 샘플 수집 |
| `scripts/detect_projection_anomalies.py` | anomaly catalog + before/after |
| `tests/test_projection_cleanup.py` | 단위 테스트 |
| `GET /debug/projection-stats` | cleanup 품질 지표 |

## 환경변수

`TAI_PROJECTION_CLEANUP=true` (기본값)

## 검증

```bash
pytest tests/test_projection_cleanup.py -q
python3 scripts/collect_projection_samples.py
python3 scripts/detect_projection_anomalies.py
```

2026-05-23 실행: 24 samples, **HIGH anomaly 0건**, PENALTY_FALLBACK만 LOW로 다수(허용).
