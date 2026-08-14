# -*- coding: utf-8 -*-
"""_save_member_inquiry title 회귀 테스트 — fake supabase/slack (외부비용 0).

- /me/inquiries 경로: title 전달 시 저장 보존
- support HANDOFF 경로: title 미전달 시 NULL(None) 유지
실제 routers.member_inquiries._save_member_inquiry 를 import 해 검증한다.
"""
import types

from routers.member_inquiries import _save_member_inquiry

results = []


def check(name, cond):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


class _FakeTable:
    def __init__(self, store):
        self.store = store

    def insert(self, row):
        self.store["row"] = row
        return self

    def execute(self):
        return types.SimpleNamespace(data=[dict(self.store["row"])])


class FakeSupabase:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(self.store)


# 1) /me/inquiries 경로: title 전달 → 보존
saved = _save_member_inquiry(FakeSupabase(), user_id="U-1", company_id="C-1", name="홍길동",
                             question="문의", page_url="/p", context=None, title="제목입니다")
check("1 title 전달->보존", saved["title"] == "제목입니다")

# 1b) title 공백만 → None
saved = _save_member_inquiry(FakeSupabase(), user_id="U-1", company_id=None, name=None,
                             question="q", page_url=None, context=None, title="   ")
check("1b title 공백->None", saved["title"] is None)

# 2) support HANDOFF 경로: title 미전달 → None(NULL) 유지
saved = _save_member_inquiry(FakeSupabase(), user_id="U-1", company_id="C-1", name=None,
                             question="이관", page_url="/p", context={"factory_id": "F"},
                             handoff_reason="no evidence found")
check("2 title 미전달->None(NULL)", saved["title"] is None)

# 3) 다른 필드 회귀 없음
check("3 content/user/context/source 유지",
      saved["content"] == "이관" and saved["user_id"] == "U-1" and saved["context"] == {"factory_id": "F"}
      and saved["source"] == "saas" and saved["is_member"] is True)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
