"""
full_run.py - the steps behind the "Run Full Review" button (everything after the review report).

No Streamlit and no model calls in here: the three step functions are passed in, so this file is
easy to test. Each step is isolated - a failure in one is reported and the others still run.

Order: Generate Device Configs first (it extracts the topology and also writes the diagram, so the
model is not asked to extract the same topology twice), then the diagram result is taken from that run,
then the security review. If the config run fails, the diagram step is run on its own.
"""
import os


def _short(e: Exception) -> str:
    msg = "".join(ch if " " <= ch <= "~" else " " for ch in str(e))
    return f"{type(e).__name__}: {' '.join(msg.split())[:200]}"


def _diagram_from_config(cr):
    if not cr or cr.get("failed"):
        return None
    path, spec = cr.get("diagram_output_path"), cr.get("diagram_spec")
    if spec is None or not path or not os.path.exists(path):
        return None
    return {"failed": False, "output_path": path, "spec": spec, "warnings": list(cr.get("warnings") or [])}


def run_remaining_steps(design_text, render_fn, config_fn, security_fn, log=print):
    """Returns {"state": {...session keys...}, "steps": {name: "ok"|"failed"|"skipped"}, "errors": [..]}."""
    state, steps, errors = {}, {}, []

    log("Generating device configs (this also extracts the topology and draws the diagram)...")
    try:
        cr = config_fn(lld_text=design_text, kb_context="")
    except Exception as e:
        cr = {"failed": True, "last_error": _short(e)}
    state["config_result"] = cr
    cfg_ok = bool(cr) and not cr.get("failed") and cr.get("config_spec") is not None
    steps["configs"] = "ok" if cfg_ok else "failed"
    if not cfg_ok:
        errors.append(f"Config generation failed: {cr.get('last_error') if cr else 'no result'}")

    dr = _diagram_from_config(cr)
    if dr is None:
        log("Rendering the diagram separately...")
        try:
            dr = render_fn(lld_text=design_text, kb_context="")
        except Exception as e:
            dr = {"failed": True, "last_error": _short(e)}
    state["diagram_result"] = dr
    dr_ok = bool(dr) and not dr.get("failed")
    steps["diagram"] = "ok" if dr_ok else "failed"
    if not dr_ok:
        errors.append(f"Diagram rendering failed: {dr.get('last_error') if dr else 'no result'}")

    diag = cr.get("diagram_spec") if cfg_ok else None
    if diag is None and dr_ok:
        diag = dr.get("spec")
    if diag is None:
        state["security_review"] = None
        steps["security"] = "skipped"
        errors.append("Security review skipped: no topology was extracted.")
    else:
        log("Running the security review...")
        try:
            state["security_review"] = {
                "findings": security_fn(diag, cr.get("config_spec") if cfg_ok else None,
                                        cr.get("configs") if cfg_ok else None),
                "with_configs": cfg_ok,
            }
            steps["security"] = "ok"
        except Exception as e:
            state["security_review"] = None
            steps["security"] = "failed"
            errors.append(f"Security review failed: {_short(e)}")
    return {"state": state, "steps": steps, "errors": errors}
