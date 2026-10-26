# OBJ-REF-01 — 실무 역할×업무 발생시점 커버리지 검증 22
Date: 2026-10-08 / State: REF-01 OPEN / practitioner reverse research

## Source and confidence
S1 specialist warehouse operator's published WMS workflow https://mcp.me.kr/42 : arrival plan→receiving QA→location putaway→stock movements/count→picking/dispatch QA→shipment, dangerous-goods inventory and MSDS information linkage. This is **software process evidence**, not original paper form evidence.
S2 Odoo localized operational manual https://www.odoo.com/documentation/19.0/ko/applications/inventory_and_mrp/inventory/shipping_receiving/daily_operations/receipts_delivery_two_steps.html : inbound receipt and internal move, separate operational transaction documents.
S3 public private-form catalog https://www.docsbank.co.kr/formfile/ko/%EF%BF%BD%EF%BF%BD%EF%BF%BD%EF%BF%BD%2B%C3%A2%EF%BF%BD%EF%BF%BD%EF%BF%BD%EF%BF%BD%EF%BF%BD%EF%BF%BD-category-form-form-A11B18C14/30-imgs-1.html : publicly lists '원자재 재고현황표', '월간 원자재 재고현황표', '월간 자재관리대장', '자재 관리대장', but paid file interiors not inspected and cannot be copied.
S4 public logistics job ad https://zighang.com/recruitment/3475e94f-26a1-4f03-8427-2791dc937d72 : warehouse job tasks inbound QA, dispatch quantity checks, inventory check, labeling and storage housekeeping. Medical devices not chemical goods; job evidence is **analogical**, not proof of chemical regulation.
S5 previously committed direct practitioner and public source report docs/reference-forms/OBJ-REF-01-REVERSE-FIELD-PRACTICE-18.md, OBJ-REF-01-PRACTITIONER-ROLE-EXPANSION-19.md, OBJ-REF-01-PRACTITIONER-TIMING-FM-20.md, OBJ-REF-01-PRACTITIONER-MAINT-CHEM-WAREHOUSE-21.md.

## Matrix: roles and real work event -> independent document hypotheses
| Role | Planning | Before work / receipt | Operation | Exception | Completion | Period close | Evidence grade |
|---|---|---|---|---|---|---|---|
| Construction safety manager | next-day works and contractors | TBM / permit / worker onboarding | patrol + hazard flags | stop-work / remediation | signoff & handover | safety cost and monthly closure | document pages and public practitioner contents (reports 18,20) |
| Manufacturing EHS | risk control calendar | PTW and coordination | exposure / safety patrol | chemical release / CAPA | restoration evidence | monthly action register | partly job/workflow inference (reports 19,21) |
| Machine maintenance lead | preventive work orders | equipment release / isolation | repairs and check records | breakdown / lockout | restart test & handover | PM backlog analysis | private named maintenance form descriptions (report 21) |
| Building FM | annual inspection agenda | vendor entry / work authorization | facility operation diary | alarm / defect | repair confirmation | inspection deadline/report | private named daily maintenance form and public plan (report 20) |
| Research lab safety officer | registration + risk inventory | lab entry/training/experiment prereview | laboratory inspection | chemical spill / shutdown | corrective closeout | lab committee and cross-check | university actual workflows (report 19) |
| Chemical warehouse coordinator | purchase/expected receipt | receiving check, SDS availability | putaway, location transfer, issue | damaged item/quarantine | dispatch QA / return | cycle count, stock discrepancy | WMS real-workflow + commercial form titles (S1/S3) |
| Enterprise safety executive | policy/budget | owner/role designation | action assignment/oversight | major incident escalation | executive approval | committee/monthly KPI | statutory governance/process evidence, not sample executive form |

## Gap assessment — document artifacts newly justified to research
| ID | Proposed independent working document | Trigger | Operational purpose | Evidence level / cautions |
|---|---|---|---|---|
| PRA-22-01 | 화학물질 입고예정·검수 대조표 | order before receipt | compare expected and received goods and exception record | WMS feature confirmed, paper title TAI inference |
| PRA-22-02 | 화학물질 로케이션 적치·이동기록 | putaway/move | track changed storage zones with safety constraints | WMS location moves observed, exact paper form not observed |
| PRA-22-03 | 화학물질 출고검수·인계서 | release/dispatch | resolve requested/actual shipped quantity and recipient | WMS outbound QA observed; blank form hypothesis |
| PRA-22-04 | 화학물질 파손·누출품 격리 및 재고조정 승인서 | damage discovery | tie damage to physical hold and ledger correction | WMS damage management observed; title not observed |
| PRA-22-05 | 화학물질 재고실사 차이조사 및 조정대장 | cycle count | reconcile physical count, change approvals and inventory | WMS count plus private material-ledger catalog |
| PRA-22-06 | 설비 보전작업 완료·재가동 인계서 | maintenance close | separate technician completion and operating team acceptance | practitioner workflow hypothesis, source role confirms maintenance only |
| PRA-22-07 | 시설 외주업체 점검·정비 완료확인서 | vendor work complete | check scope, unresolved defects and requester acceptance | FM workflow hypothesis; original signed sample needed |
| PRA-22-08 | 연구실 사고·이상 발생 초동조치·종결 기록 | lab emergency | carry response into evidence and reopening decision | process hypothesis, institutional specimen unverified |
| PRA-22-09 | 현장 안전점검 사진·증빙 인계목록 | contractor closure | ensure actual evidence delivered and recorded | derived handover need, no exact paper specimen verified |
| PRA-22-10 | 안전관리 미종결과제 주간 인수인계표 | week/role transition | prevent open critical hazards from disappearing | derived governance need, no exact sample |

**The ten gaps overlap previous draft families; they are investigation tasks, not ten newly confirmed unique templates.**

## Distinct classification dimensions for REF-02 (NOT YET EXECUTED)
- Role: manager, inspector, maintenance, warehouse operator, contractor, medical professional.
- Event: plan, onboard, permit, execute, exception, handover, close, archive.
- Artifact: one-off approval, repetitive daily log, transaction ledger, checklist, technical drawing, official statutory original.
- Source confidence: actual named document, officially described process, vendor software workflow, TAI inference.
- LEG legal status and commercial reuse rights: UNVERIFIED; no presumption from web availability.
- A workflow can need a digital application rather than downloadable blank template. Mark such cases to avoid manufacturing low-value documents.

## REF-01 verdict
Role×event matrix recorded, but **not coverage-complete**. Actual full fields, industry breadth, rights, demand, and legal currentness not all established. REF-02 NOT STARTED; Owner approval and gates unchanged. Docs-only Git change. Production DB writes 0, service code 0, downloads 0, deploy 0.
