#!/usr/bin/env python3
"""TAI Time Contract guard (tai-api) — stdlib only. EXACT ledger + no-expansion + coverage.
fingerprint = rule|relfile|canonical-token (NO enclosing symbol, line-independent)."""
import ast, os, sys, json, hashlib, argparse, subprocess, re
ROOT = os.environ.get("TIME_CONTRACT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "time_debt_baseline.json")
ALLOWLIST = os.path.join(ROOT, "time_exception_allowlist.json")
GUARD_MARKERS = ["scripts/check_time_contract.py", "scripts/check-time-contract.mjs"]
EXEMPT = ("services/time/", "tests/")
SKIP_DIRS = {".git","node_modules","__pycache__",".venv","venv","dist","build"}
def _fp(rule, rel, token):
    return hashlib.sha256(f"{rule}|{rel}|{token}".encode()).hexdigest()[:16]
def scan_py(rel, src):
    out=[]
    try: tree=ast.parse(src)
    except SyntaxError: return out
    def attr_chain(n):
        parts=[]
        while isinstance(n, ast.Attribute): parts.append(n.attr); n=n.value
        if isinstance(n, ast.Name): parts.append(n.id)
        return ".".join(reversed(parts))
    class V(ast.NodeVisitor):
        def visit_Call(self,node):
            f=node.func
            if isinstance(f,ast.Attribute):
                chain=attr_chain(f); tail=chain.split("."); rule=None
                if chain.endswith(".now") and tail[-2] in ("datetime","dt"): rule="PY_DIRECT_NOW"
                if chain.endswith(".utcnow"): rule="PY_UTCNOW"
                if chain.endswith(".today") and tail[-2] in ("datetime","dt"): rule="PY_DATETIME_TODAY"
                if chain.endswith(".today") and tail[-2]=="date": rule="PY_DATE_TODAY"
                if rule: out.append((rule, rule))
            if isinstance(f,ast.Name) and f.id=="ZoneInfo":
                if node.args and isinstance(node.args[0],ast.Constant) and str(node.args[0].value).upper() in ("UTC","ETC/UTC"):
                    out.append(("PY_ZONEINFO_UTC","ZoneInfo(UTC)"))
            self.generic_visit(node)
        def visit_Attribute(self,node):
            chain=attr_chain(node)
            if chain.endswith("timezone.utc") or chain=="timezone.utc": out.append(("PY_EXPLICIT_UTC","timezone.utc"))
            if chain in ("pytz.UTC","pytz.utc"): out.append(("PY_PYTZ_UTC","pytz.UTC"))
            self.generic_visit(node)
        def visit_Constant(self,node):
            if isinstance(node.value,str) and "timestamp without time zone" in node.value.lower():
                out.append(("SQL_NEW_NAIVE_TIMESTAMP","embedded"))
            self.generic_visit(node)
    V().visit(tree)
    return [(r,_fp(r,rel,tok)) for r,tok in out]
def _mask_sql(s): return re.sub(r"--[^\n]*"," ",re.sub(r"/\*[\s\S]*?\*/"," ",s))
SQL_PATTERNS=[
    ("SQL_NEW_NAIVE_TIMESTAMP", re.compile(r"timestamp\s+without\s+time\s+zone",re.I)),
    ("SQL_LOCALTIMESTAMP", re.compile(r"\blocaltimestamp\b",re.I)),
    ("SQL_CURRENT_DATE", re.compile(r"\bcurrent_date\b",re.I)),
    ("SQL_AT_TIME_ZONE_UTC", re.compile(r"at\s+time\s+zone\s+'utc'",re.I)),
    ("SQL_TIMEZONE_UTC", re.compile(r"timezone\s*\(\s*'utc'",re.I)),
]
def scan_sql(rel, src):
    m=_mask_sql(src); out=[]
    for rule,pat in SQL_PATTERNS:
        for _ in pat.finditer(m): out.append((rule,_fp(rule,rel,rule)))
    return out
def scan():
    out={}
    for dp,dns,fns in os.walk(ROOT):
        dns[:]=[d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            rel=os.path.relpath(os.path.join(dp,fn),ROOT).replace(os.sep,"/")
            if rel.startswith("scripts/check_time_contract") or rel.startswith("scripts/check_baseline"): continue
            if rel.startswith(EXEMPT): continue
            try: src=open(os.path.join(dp,fn),encoding="utf-8").read()
            except Exception: continue
            hits = scan_py(rel,src) if fn.endswith(".py") else (scan_sql(rel,src) if fn.endswith(".sql") else [])
            for _r,fp in hits: out[fp]=out.get(fp,0)+1
    return out
def load(p): return json.load(open(p)) if os.path.exists(p) else {}
def ms(d): return {k:(v if isinstance(v,int) else (v or {}).get("count",1)) for k,v in (d or {}).items()}
def git(a): return subprocess.check_output(["git",*a],cwd=ROOT,stderr=subprocess.DEVNULL).decode()
def ref_ok(r):
    try: git(["rev-parse","--verify",f"{r}^{{commit}}"]); return True
    except Exception: return False
def cat_ok(r,f):
    try: git(["cat-file","-e",f"{r}:{f}"]); return True
    except Exception: return False
def show_json(r,f):
    try: return json.loads(git(["show",f"{r}:{f}"]))
    except Exception: return {}
def check_exact(cur, base, allow):
    A=set(allow or {}); B=ms(base); fails=[]
    for fp in A:
        if fp in B: fails.append(f"INVALID POLICY {fp}")
    debt={fp:c for fp,c in cur.items() if fp not in A}
    for fp,c in debt.items():
        if fp not in B: fails.append(f"NEW {fp}")
        elif c>B[fp]: fails.append(f"COUNT+ {fp}")
    for fp,c in B.items():
        if fp not in debt: fails.append(f"STALE BASELINE {fp}")
        elif c>debt[fp]: fails.append(f"STALE count {fp}")
    for fp in A:
        if fp not in cur: fails.append(f"ORPHAN ALLOWLIST {fp}")
    return fails
def check_expand(ref, cb, ca):
    if not ref_ok(ref): return [f"TARGET REF UNAVAILABLE {ref}"]
    guard=any(cat_ok(ref,m) for m in GUARD_MARKERS); tb=cat_ok(ref,"time_debt_baseline.json"); cbase=os.path.exists(BASELINE)
    if not guard and not tb:
        if len(ca or {})>0: return ["BOOTSTRAP FAIL allowlist must be {}"]
        print("BASELINE BOOTSTRAP: target predates TIME CONTRACT"); return []
    if guard and not tb: return ["FAIL upstream reset"]
    if tb and not cbase: return ["FAIL PR delete reset"]
    oB=ms(show_json(ref,"time_debt_baseline.json")); nB=ms(cb); oA=show_json(ref,"time_exception_allowlist.json"); nA=ca or {}
    f=[]
    for k in nB:
        if k not in oB: f.append(f"debt NEW {k}")
        elif nB[k]>oB[k]: f.append(f"debt count+ {k}")
    for k in nA:
        if k not in oA: f.append(f"allowlist NEW {k}")
    return f
def main():
    ap=argparse.ArgumentParser()
    for x in ("scan","baseline","check"): ap.add_argument("--"+x,action="store_true")
    ap.add_argument("--check-expand",dest="expand",nargs="?",const="origin/main",default=None)
    a=ap.parse_args(); cur=scan(); rc=0
    if a.scan: print(json.dumps(cur,indent=2)); return 0
    if a.baseline:
        json.dump({fp:{"repo":"tai-api","fp":fp,"count":c} for fp,c in cur.items()},open(BASELINE,"w"),indent=2)
        print(f"baseline: {len(cur)} fp / {sum(cur.values())} occ"); return 0
    if a.check or a.expand is None:
        f=check_exact(cur,load(BASELINE),load(ALLOWLIST))
        if f: print("TIME GUARD FAIL:"); [print("  "+x) for x in f]; rc=1
        else: print(f"TIME GUARD PASS ({len(cur)} fp / {sum(cur.values())} occ)")
    if a.expand is not None:
        f=check_expand(a.expand,load(BASELINE),load(ALLOWLIST))
        if f: print("BASELINE EXPANSION BLOCKED:"); [print("  "+x) for x in f]; rc=1
        elif rc==0: print("baseline non-expansion OK")
    return rc
if __name__=="__main__": sys.exit(main())
