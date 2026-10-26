#!/usr/bin/env python3
"""
Adds an extra "Run Full Review" button to app.py (the existing buttons are untouched).
Run from the project root:  python3 patch_full_review.py
Needs full_run.py in the project root. Each anchor must match exactly once or NOTHING is written.
Backup: app.py.pre_fullrun
"""
import sys, py_compile, tempfile, os
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
app = root / "app.py"
if not (root / "full_run.py").exists():
    sys.exit("ABORT: full_run.py is not in the project root. Copy it there first.")
t = app.read_text()
if "run_remaining_steps" in t:
    sys.exit("Already patched - nothing to do.")

def once(text, a, b, label):
    n = text.count(a)
    if n != 1:
        sys.exit(f"ABORT: anchor for {label} matched {n} times (expected 1). Nothing was changed.")
    return text.replace(a, b)

t = once(t, "import zipfile\nimport io\n",
         "import zipfile\nimport io\nfrom full_run import run_remaining_steps\n", "import")

t = once(t, '''    run = st.button("Run Review", type="primary",
                    disabled=(not uploaded and not pasted.strip()),
                    use_container_width=True)
''', '''    run = st.button("Run Review", type="primary",
                    disabled=(not uploaded and not pasted.strip()),
                    use_container_width=True)
    run_all = st.button("Run Full Review (report + diagram + configs + security)",
                        disabled=(not uploaded and not pasted.strip()),
                        use_container_width=True)
''', "button")

t = once(t, "if run:\n    if uploaded:\n", "if run or run_all:\n    if uploaded:\n", "run condition")

BLOCK = '''    if report:
        st.session_state["report"] = report
        st.session_state["design_text"] = design_text

    if run_all:
        if not report:
            st.session_state["report"] = "_The review report failed (see the error above). The other steps were still run._"
            st.session_state["design_text"] = design_text
        if design_text:
            with col2:
                _full = st.status("Running configs, diagram and security review...", expanded=True)
                with _full:
                    _res = run_remaining_steps(design_text, render_lld_to_diagram,
                                               generate_configs_for_lld, run_security_review, log=st.write)
                    for _e in _res["errors"]:
                        st.write(_e)
                for _k, _v in _res["state"].items():
                    st.session_state[_k] = _v
                _bad = [k for k, v in _res["steps"].items() if v != "ok"]
                _full.update(label="Full review complete" if not _bad
                             else "Full review finished with problems in: " + ", ".join(_bad),
                             state="complete" if not _bad else "error")
        else:
            st.warning("Run Full Review needs a .md or .txt file, or pasted text (a .docx cannot be read for the diagram and configs).")
'''
t = once(t, '''    if report:
        st.session_state["report"] = report
        st.session_state["design_text"] = design_text
''', BLOCK, "after review")

with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    f.write(t)
try:
    py_compile.compile(f.name, doraise=True)
except py_compile.PyCompileError as e:
    sys.exit(f"ABORT: patched app.py would not compile ({e}). Nothing was changed.")
finally:
    os.unlink(f.name)
Path(str(app) + ".pre_fullrun").write_text(app.read_text())
app.write_text(t)
print("Patched app.py (backup app.py.pre_fullrun). Restart: sudo systemctl restart argus")
