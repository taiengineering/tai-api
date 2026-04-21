from types import SimpleNamespace

from routers import construction
from services import construction_svc


class _FakeQuery:
    def __init__(self, data=None, count=None):
        self._data = data or []
        self.count = count
        self._single = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        data = self._data[0] if (self._single and self._data) else self._data
        return SimpleNamespace(data=data, count=self.count)


class _FakeScheduleTable:
    def __init__(self):
        self.inserted_batches = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[])

    def insert(self, rows):
        self.inserted_batches.append(rows)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))


class _FakeSupabaseForSchedules:
    def __init__(self):
        self.work_schedules = _FakeScheduleTable()

    def table(self, name):
        if name == "work_schedules":
            return self.work_schedules
        raise AssertionError(f"unexpected table {name}")


class _FakeSupabaseForAuto:
    def table(self, name):
        if name == "factories":
            return _FakeQuery(data=[{"company_id": "co-1"}])
        raise AssertionError(f"unexpected table {name}")


def test_calc_safety_manager_building_amount_rule():
    out = construction.calc_safety_manager("BUILDING", 300, 10)
    assert out["required"] is True
    assert out["count"] == 2
    assert any("건축 도급금액" in r for r in out["reasons"])


def test_calc_safety_manager_worker_rule_even_without_amount():
    out = construction.calc_safety_manager("BUILDING", 100, 50)
    assert out["required"] is True
    assert out["count"] >= 1
    assert any("상시 근로자" in r for r in out["reasons"])


def test_site_create_keeps_coordinate_fields():
    body = construction.SiteCreate(
        company_id="co",
        site_name="현장",
        latitude=37.5665,
        longitude=126.9780,
    )
    dumped = body.model_dump(exclude_none=True)
    assert dumped["latitude"] == 37.5665
    assert dumped["longitude"] == 126.9780


def test_run_generate_schedules_includes_inspection_and_action_rules():
    sb = _FakeSupabaseForSchedules()
    rules = [
        {"rule_id": "R-INS-1", "obligation_type": "INSPECT", "obligation_summary": "점검"},
        {"rule_id": "R-ACT-1", "obligation_type": "ACTION", "obligation_summary": "조치"},
    ]
    out = construction._run_generate_schedules(sb, "factory-1", rules, "co-1")
    assert out["created"] == 2
    assert out["skipped"] == 0
    inserted = [r for batch in sb.work_schedules.inserted_batches for r in batch]
    inserted_codes = {r["rule_code"] for r in inserted}
    assert inserted_codes == {"R-INS-1", "R-ACT-1"}


def test_auto_diagnose_and_schedule_merges_inspection_and_action(monkeypatch):
    called = {}

    def _fake_run_diagnosis(_sb, _factory_id, _site):
        return {
            "applicable_count": 2,
            "result_data": {
                "inspection_required": [{"rule_id": "I-1"}],
                "action_required": [{"rule_id": "A-1"}],
            },
            "applicable_rules": [],
        }

    def _fake_run_generate_schedules(_sb, _factory_id, all_rules, _company_id):
        called["rule_ids"] = [r["rule_id"] for r in all_rules]
        return {"created": len(all_rules), "skipped": 0, "total_rules": len(all_rules)}

    monkeypatch.setattr(construction_svc, "run_diagnosis", _fake_run_diagnosis)
    monkeypatch.setattr(construction_svc, "run_generate_schedules", _fake_run_generate_schedules)

    out = construction._auto_diagnose_and_schedule(
        _FakeSupabaseForAuto(),
        "factory-1",
        {"site_name": "s"},
    )
    assert called["rule_ids"] == ["I-1", "A-1"]
    assert out["schedules"]["total_rules"] == 2


def test_penalty_like_fail_count_in_inspection_payload():
    body = construction.InspectionCreate(
        checklist_items=[
            {"result": "bad"},
            {"result": "ok"},
            {"result": "FAIL"},
        ]
    )
    checklist = body.model_dump(exclude_none=True)["checklist_items"]
    bad_items = [i for i in checklist if i.get("result") in ("bad", "fail", "이상", "FAIL")]
    assert len(bad_items) == 2
