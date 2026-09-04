# 02 — LEG → Check Adapter Design

TAI 측 **결정적(deterministic) 매핑 어댑터** 설계. LEG 어댑터 출력(`obligations[]`)을 Check의 `CheckInput`으로 변환한다. **Check는 변경하지 않는다.**

위치(예정): `services/leg_to_check_adapter.py` (TAI host). 이 문서는 설계만 다룬다.

## 1. 매핑 원칙

- 어댑터는 **순수 변환**이다. 판단/추론/문구생성 없음.
- LEG의 도메인 필드(who/what/condition/completeness/의무유형/title/법령 텍스트)는 **Check로 보내지 않는다**(domain-blind 유지).
- 모든 `*_ref`/`scope_ref`는 TAI가 부여하는 **불투명 문자열**. Check는 동등성·존재 비교만 한다.
- 동일 진단 실행(diagnosis run) → 동일 `CheckInput` → 동일 `report_id` (결정성 유지).

## 2. 매핑 표

| LEG 출력 | Check 입력 | 규칙 |
|----------|-----------|------|
| 진단 실행(run)/테넌트 | `scope.scope_ref` | `leg:diag:{tenant_id}:{run_id}` |
| obligation (obligation_id) | `Claim` | `claim_ref = leg:obligation:{obligation_id}` (없으면 candidate_id→rule_id 순 fallback, LEG dedup 키와 일치) |
| obligation.evidence.chain[] 의 각 요소 | `Evidence` | `evidence_ref = leg:evidence:{obligation_id}:{element_key}` |
| obligation 단위 근거 연결 | `EvidenceChain` | `evidence_chain_ref = leg:chain:{obligation_id}`, `claim_ref`=위 claim, `evidence_refs`=해당 의무의 evidence_ref 목록 |

주입 필드(host 고정):

```
request_ref   = "leg:diag:{run_id}"
runtime_owner = "host:tai-api"
observer      = "check@tai-api"
now           = 진단 실행 타임스탬프 (host 주입; Check는 시계를 읽지 않음)
```

## 3. `attached` 판정 (핵심)

`Evidence.attached`는 **TAI가 그 근거 산출물을 실제로 보유/확인했는지** 여부다. 이는 LEG의 의미가 아니라 **TAI host의 사실 지식**이다(문서 업로드 여부, Task 완료 기록, 제출 기록 등 TAI 저장소 기준).

- 실제 보유 → `attached = true` → Check: `EVIDENCE_ATTACHED`
- 미보유 + 대체/파생 참조 있음(`resolves_to_ref`) → 대상 존재 시 `EVIDENCE_REF_RESOLVED`, 부재 시 `EVIDENCE_REF_MISSING`
- 미보유 + 참조 없음 → `EVIDENCE_NOT_ATTACHED`
- chain이 참조하지만 evidence 풀에 없음 → `EVIDENCE_REF_MISSING` + 체인 `BROKEN`

→ 이 판정이 LEG `completeness`(텍스트 자가평가)와 **독립적인 구조 신호**를 만든다.

## 4. 체인 선언 매핑 규칙 (명시적 결정)

- LEG 의무가 **근거 체인을 선언**(evidence.chain 비어있지 않음) → Check `EvidenceChain` 생성.
  - 모든 evidence_ref가 풀에 존재 → `EVIDENCE_CHAIN_COMPLETE`
  - 하나라도 부재 → `EVIDENCE_CHAIN_BROKEN`
- LEG가 **근거 체인을 선언하지 않음**(chain 없음) → Check 체인 미생성 → `EVIDENCE_CHAIN_NOT_DECLARED`. 의미: "LEG가 이 의무에 대해 근거 연결을 선언하지 않았다"(사람 검토 신호로 유효).
- 빈 evidence_refs 체인을 선언한 경우 → Check 정의상 `COMPLETE`(끊긴 링크 없음). TAI는 이 경우를 "근거 없이 완결 선언"으로 보아 검토 우선순위에서 별도 표시(05 문서).

## 5. 드롭되는 LEG 필드 (Check 미전달, 명시)

`who/when/where/what/how/why`, `condition`, `의무유형`, `status.completeness`, `title`, `signals`, 법령 본문 텍스트 — 전부 Check로 보내지 않는다. 이 값들은 TAI 저장소에서 obligation_id로 별도 보관/조인한다(03 문서).

## 6. 결정성/경계 체크리스트

| 항목 | 보장 |
|------|------|
| 동일 run → 동일 CheckInput | ref 파생·정렬 안정화로 보장 |
| Check 계약/상태값 변경 | 없음 (기존 CheckInput/EvidenceReport·기존 상태값만 사용) |
| 도메인 의미 전달 | 없음 (ref/구조만) |
| 어댑터의 판단 | 없음 (순수 매핑) |
| LEG 수정 | 없음 (LEG 출력 read-only 소비) |

## 7. 의사 매핑 (설명용, 구현 아님)

```
for ob in leg_ui_ready["obligations"]:
    claim_ref = f"leg:obligation:{ob['obligation_id']}"
    claims.append({ "claim_ref": claim_ref, "scope_ref": scope })
    refs = []
    for i, el in enumerate(ob.get("evidence", {}).get("chain", [])):
        ev_ref = f"leg:evidence:{ob['obligation_id']}:{element_key(el, i)}"
        evidence.append({
            "evidence_ref": ev_ref, "scope_ref": scope,
            "attached": tai_holds(el),                 # TAI host 사실
            "resolves_to_ref": derived_ref(el) or None, # 선택
        })
        refs.append(ev_ref)
    if ob.get("evidence", {}).get("chain") is not None and len(refs) >= 0 and declared(ob):
        chains.append({ "evidence_chain_ref": f"leg:chain:{ob['obligation_id']}",
                        "claim_ref": claim_ref, "evidence_refs": refs, "scope_ref": scope })
# → runCheck({scope, claims, evidence, evidence_chains, request_ref, runtime_owner, observer, now})
```
`element_key()`/`tai_holds()`/`declared()`는 TAI가 정의(01 문서의 공백 항목). Check는 결과만 받는다.
