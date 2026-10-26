"""Offline tests for the Run Full Review steps. Run: python3 test_full_run.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_run import run_remaining_steps
PASS = FAIL = 0
def check(n, c, x=""):
    global PASS, FAIL
    if c: PASS += 1; print("  PASS ", n)
    else: FAIL += 1; print("  FAIL ", n, x)

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".drawio"); tmp.write(b"<x/>"); tmp.close()
calls = []
def cfg_ok(lld_text, kb_context):
    calls.append("cfg"); return {"failed": False, "config_spec": "CS", "configs": {"a": "x"}, "diagram_spec": "DS",
                                 "diagram_output_path": tmp.name, "warnings": ["w"]}
def render(lld_text, kb_context): calls.append("render"); return {"failed": False, "spec": "RS", "output_path": tmp.name}
def sec(d, c, k): calls.append(("sec", d, c, k)); return ["F"]

print("A. everything works")
r = run_remaining_steps("lld", render, cfg_ok, sec, log=lambda m: None)
check("all ok", r["steps"] == {"configs": "ok", "diagram": "ok", "security": "ok"}, r["steps"])
check("topology extracted once (render not called)", "render" not in calls)
check("diagram result built from config run", r["state"]["diagram_result"]["output_path"] == tmp.name)
check("security got topology, config spec and configs", ("sec", "DS", "CS", {"a": "x"}) in calls)
check("with_configs true", r["state"]["security_review"]["with_configs"] is True)
check("no errors", r["errors"] == [])

print("B. configs fail -> diagram runs on its own, security is topology-only")
calls.clear()
def cfg_bad(lld_text, kb_context): return {"failed": True, "last_error": "boom"}
r = run_remaining_steps("lld", render, cfg_bad, sec, log=lambda m: None)
check("render called as fallback", "render" in calls)
check("steps", r["steps"] == {"configs": "failed", "diagram": "ok", "security": "ok"}, r["steps"])
check("topology-only review", r["state"]["security_review"]["with_configs"] is False and ("sec", "RS", None, None) in calls)
check("error reported", any("boom" in e for e in r["errors"]))

print("C. a step raising does not stop the rest")
calls.clear()
def cfg_raise(lld_text, kb_context): raise ValueError("bad\nnewline")
r = run_remaining_steps("lld", render, cfg_raise, sec, log=lambda m: None)
check("continues", r["steps"]["diagram"] == "ok" and r["steps"]["security"] == "ok")
check("error text single line", all("\n" not in e for e in r["errors"]))
def sec_raise(d, c, k): raise RuntimeError("x")
r = run_remaining_steps("lld", render, cfg_ok, sec_raise, log=lambda m: None)
check("security failure recorded, others fine", r["steps"] == {"configs": "ok", "diagram": "ok", "security": "failed"} and r["state"]["security_review"] is None)

print("D. nothing extracted")
r = run_remaining_steps("lld", lambda **k: {"failed": True, "last_error": "e"}, cfg_bad, sec, log=lambda m: None)
check("security skipped", r["steps"]["security"] == "skipped" and r["state"]["security_review"] is None)

print("E. diagram file missing -> falls back to render")
calls.clear()
def cfg_nofile(lld_text, kb_context): return {"failed": False, "config_spec": "CS", "configs": {}, "diagram_spec": "DS", "diagram_output_path": "/no/such"}
run_remaining_steps("lld", render, cfg_nofile, sec, log=lambda m: None)
check("render used", "render" in calls)
os.unlink(tmp.name)
print(f"\n{PASS} passed, {FAIL} failed"); sys.exit(1 if FAIL else 0)
