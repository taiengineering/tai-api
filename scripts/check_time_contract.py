#!/usr/bin/env python3
"""TAI Time Contract guard (tai-api) — stdlib only, AST fingerprint multiset ratchet."""
import ast, os, sys, json, hashlib, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "time_debt_baseline.json")
ALLOWLIST = os.path.join(ROOT, "time_exception_allowlist.json")
EXEMPT_PREFIXES = ("services/time/", "tests/")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
CALL_RULES = {("datetime","now"):"PY_DIRECT_NOW",("datetime","utcnow"):"PY_UTCNOW",
              ("datetime","today"):"PY_DATETIME_TODAY",("date","today"):"PY_DATE_TODAY"}
def _enclosing(parents):
    for p in reversed(parents):
        if isinstance(p,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): return p.name
    return "<module>"
def scan_file(relpath, src):
    viols=[]
    try: tree=ast.parse(src)
    except SyntaxError: return viols
    stack=[]
    class V(ast.NodeVisitor):
        def generic_visit(self,n): stack.append(n); super().generic_visit(n); stack.pop()
        def visit_Call(self,node):
            f=node.func; rule=None
            if isinstance(f,ast.Attribute):
                base=f.value
                if isinstance(base,ast.Name):
                    rule=CALL_RULES.get((base.id,f.attr))
                    if not rule and f.attr in ("now","utcnow","today") and base.id in ("dt","datetime"):
                        rule=CALL_RULES.get(("datetime",f.attr))
                elif isinstance(base,ast.Attribute) and isinstance(base.value,ast.Name):
                    rule=CALL_RULES.get((base.attr,f.attr))
            if rule:
                sym=_enclosing(stack)
                fp=hashlib.sha256(f"{rule}|{relpath}|{sym}|{ast.dump(node.func)}".encode()).hexdigest()[:16]
                viols.append({"rule":rule,"repo":"tai-api","file":relpath,"symbol":sym,"fp":fp})
            self.generic_visit(node)
        def visit_Constant(self,node):
            if isinstance(node.value,str) and "timestamp without time zone" in node.value.lower():
                fp=hashlib.sha256(f"SQL_NEW_NAIVE_TIMESTAMP|{relpath}".encode()).hexdigest()[:16]
                viols.append({"rule":"SQL_NEW_NAIVE_TIMESTAMP","repo":"tai-api","file":relpath,"symbol":"<sql>","fp":fp})
            self.generic_visit(node)
    V().visit(tree); return viols
def collect():
    out={}
    for dp,dns,fns in os.walk(ROOT):
        dns[:]=[d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(".py"): continue
            rel=os.path.relpath(os.path.join(dp,fn),ROOT).replace(os.sep,"/")
            if rel.startswith("scripts/check_time_contract"): continue
            if rel.startswith(EXEMPT_PREFIXES): continue
            for v in scan_file(rel, open(os.path.join(dp,fn),encoding="utf-8").read()):
                out.setdefault(v["fp"],{**v,"count":0}); out[v["fp"]]["count"]+=1
    return out
def ms(d): return {k:v["count"] for k,v in d.items()}
def load(p): return json.load(open(p)) if os.path.exists(p) else {}
def main():
    ap=argparse.ArgumentParser()
    for x in ("scan","baseline","check"): ap.add_argument("--"+x,action="store_true")
    a=ap.parse_args(); cur=collect()
    if a.scan: print(json.dumps(cur,indent=2,ensure_ascii=False)); return 0
    if a.baseline: json.dump(cur,open(BASELINE,"w"),indent=2,ensure_ascii=False); print(f"baseline: {len(cur)} fp / {sum(ms(cur).values())} occ"); return 0
    if a.check:
        base=load(BASELINE); allow=load(ALLOWLIST); cms=ms(cur); bms=ms(base); allow_fps=set(allow) if isinstance(allow,dict) else set()
        fails=[]
        for fp,c in cms.items():
            if fp in allow_fps: continue
            b=bms.get(fp,0)
            if fp not in bms: fails.append(f"NEW {fp} {cur[fp]['rule']} {cur[fp]['file']}::{cur[fp]['symbol']}")
            elif c>b: fails.append(f"COUNT+ {fp} {b}->{c} {cur[fp]['file']}")
        if fails: print("TIME GUARD FAIL:"); [print("  "+f) for f in fails]; return 1
        print(f"TIME GUARD PASS ({len(cms)} fp / {sum(cms.values())} occ)"); return 0
    ap.print_help(); return 0
if __name__=="__main__": sys.exit(main())
