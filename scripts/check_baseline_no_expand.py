#!/usr/bin/env python3
import sys, json, subprocess, os
ref = sys.argv[1] if len(sys.argv)>1 else "origin/main"
def exists_on_ref(path):
    try:
        subprocess.check_output(["git","show",f"{ref}:{path}"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
def load_ref(path):
    try: return json.loads(subprocess.check_output(["git","show",f"{ref}:{path}"]))
    except Exception: return {}
def ms(d): return {k:v.get("count",1) for k,v in d.items()}
def check(path, label):
    # First introduction on a branch that origin/main does not yet carry: not expansion.
    if not exists_on_ref(path):
        return []
    old=ms(load_ref(path)); new=ms(json.load(open(path)) if os.path.exists(path) else {})
    fails=[f"{label} NEW baseline fp {k}" for k in new if k not in old]
    fails+=[f"{label} baseline count+ {k} {old[k]}->{new[k]}" for k in new if k in old and new[k]>old[k]]
    return fails
f=check("time_debt_baseline.json","debt")+check("time_exception_allowlist.json","allowlist")
if f: print("BASELINE EXPANSION BLOCKED:"); [print("  "+x) for x in f]; sys.exit(1)
print("baseline non-expansion OK")
