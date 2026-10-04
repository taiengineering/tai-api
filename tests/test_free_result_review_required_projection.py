"""
tests/test_free_result_review_required_projection.py
WO-CONSUMER-PIPELINE-FREE-PROFILE-001 PHASE 5A

C9 FREE-only safe count projection of review_required.
Pure helper unit tests — DB/network 불필요.

Contract:
  review_required_count = len(full_result["review_required"])  iff list, else 0
  Source: full_result["review_required"] array (C8 read-only)
  Internal scalars (review_required_count, unconfirmed_count) ignored.
  Raw review_required array NOT exposed in public payload.
  PAID payload unchanged.
"""
import ast
import pathlib

from routers.diagnosis_result_web import _review_required_count

# ── R-01 normal list ────────────────────────────────────────────────────────

def test_r01_normal_list():
    full_result = {"review_required": [{}, {}, {}]}
    assert _review_required_count(full_result) == 3


# ── R-02 empty list ─────────────────────────────────────────────────────────

def test_r02_empty_list():
    full_result = {"review_required": []}
    assert _review_required_count(full_result) == 0


# ── R-03 key missing ────────────────────────────────────────────────────────

def test_r03_key_missing():
    assert _review_required_count({}) == 0
    assert _review_required_count({"other_key": [1, 2]}) == 0


# ── R-04 null value ─────────────────────────────────────────────────────────

def test_r04_null_value():
    assert _review_required_count({"review_required": None}) == 0


# ── R-05 malformed dict value ───────────────────────────────────────────────

def test_r05_malformed_object():
    assert _review_required_count({"review_required": {}}) == 0


# ── R-06 malformed string ───────────────────────────────────────────────────

def test_r06_malformed_string():
    assert _review_required_count({"review_required": "3"}) == 0
    assert _review_required_count({"review_required": "[]"}) == 0


# ── R-07 scalar disagreement — C8 stored scalar ignored ─────────────────────

def test_r07_scalar_ignored():
    full_result = {
        "review_required": [{}, {}],
        "review_required_count": 999,
        "unconfirmed_count": 999,
        "unconfirmed": [{}] * 10,
    }
    assert _review_required_count(full_result) == 2


# ── R-08 confirmed count independent ────────────────────────────────────────

def test_r08_confirmed_independent():
    # free_obligation_count tracks rules_table rows (C8 obligations_raw path).
    # review_required_count tracks review_required array. They are independent.
    # This test verifies: helper returns only review_required length, not sum.
    full_result = {"review_required": [{}, {}, {}]}
    review_count = _review_required_count(full_result)
    free_obligation_count = 5  # hypothetical confirmed count
    assert review_count == 3
    assert free_obligation_count == 5
    # 8 is NOT produced by this helper — no sum contract.
    assert review_count != free_obligation_count + review_count


# ── R-09 raw array not exposed — helper returns int ─────────────────────────

def test_r09_no_raw_array_exposure():
    full_result = {"review_required": [{"atom_id": "x"}, {"reason_code": "y"}]}
    result = _review_required_count(full_result)
    assert isinstance(result, int)
    # raw items never returned
    assert result == 2


# ── R-10 paid unchanged — projection only in is_free branch (code structure) ─

def test_r10_paid_payload_unchanged_structure():
    """review_required_count is assigned only inside the is_free branch.

    Parses diagnosis_result_web.py and verifies that the assignment to
    payload["data"]["review_required_count"] appears inside the AST node
    for 'if is_free:' and not at module/function top-level outside it.
    """
    src = pathlib.Path("routers/diagnosis_result_web.py").read_text()
    tree = ast.parse(src)

    is_free_assigns: list[int] = []   # line numbers inside if is_free
    top_level_assigns: list[int] = []  # outside

    def _is_rrc_assign(node):
        # payload["data"]["review_required_count"] = ...
        if not isinstance(node, ast.Assign):
            return False
        t = node.targets[0] if node.targets else None
        if not isinstance(t, ast.Subscript):
            return False
        slice_val = t.slice
        if isinstance(slice_val, ast.Constant) and slice_val.value == "review_required_count":
            return True
        return False

    def _walk_if_is_free(stmts, inside_is_free=False):
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                # check if test is 'is_free'
                test = stmt.test
                this_is_free = isinstance(test, ast.Name) and test.id == "is_free"
                _walk_if_is_free(stmt.body, inside_is_free or this_is_free)
                _walk_if_is_free(stmt.orelse, inside_is_free)
            else:
                if _is_rrc_assign(stmt):
                    if inside_is_free:
                        is_free_assigns.append(stmt.lineno)
                    else:
                        top_level_assigns.append(stmt.lineno)
                for child in ast.iter_child_nodes(stmt):
                    if isinstance(child, ast.stmt):
                        _walk_if_is_free([child], inside_is_free)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_result_payload":
            _walk_if_is_free(node.body)

    assert len(is_free_assigns) >= 1, "review_required_count must be assigned inside if is_free"
    assert len(top_level_assigns) == 0, (
        f"review_required_count assigned outside is_free branch at lines {top_level_assigns}"
    )
