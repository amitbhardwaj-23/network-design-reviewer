"""
visual_graph.py — orchestrates image -> validated NetworkDiagramSpec.

Reuses diagram_renderer.schema and diagram_renderer.validate UNCHANGED — the
exact same auto-repair logic proven against text extraction applies
identically here, since the output schema is identical. Only the extraction
call itself differs (vision API vs. local Ollama text).

Uses the direct Anthropic API (anthropic_vision.py) rather than AWS Bedrock —
same image, same prompt, same validation; just a simpler credential story.

A bounded retry loop, same MAX_RETRIES discipline as every other module —
critical here specifically because each retry is a real, paid API call.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "diagram_renderer"))  # validate.py/render.py use bare `from schema import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagram_renderer.validate import validate_spec  # reused, unchanged
from diagram_renderer.render import render_xml         # reused, unchanged

from visual_prompts import build_visual_extraction_prompt
from anthropic_vision import call_anthropic_vision

MAX_RETRIES = 2  # kept low deliberately — each retry costs real money


def review_diagram_image(image_path: str, _vision_call=call_anthropic_vision) -> dict:
    """Full pipeline: image -> vision extraction -> validate/auto-repair
    -> render to .drawio (so the extracted topology can be visually compared
    against the original upload).

    _vision_call is injectable specifically so this can be tested with a mock
    response, with zero API dependency — see test_visual_pipeline.py.
    """
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = build_visual_extraction_prompt(retry_error=last_error)
        try:
            raw_output = _vision_call(image_path, prompt)
        except Exception as e:
            return {"failed": True, "last_error": f"Vision API call failed: {e}", "warnings": [], "spec": None}

        spec, error, warnings = validate_spec(raw_output)
        if error is None:
            xml_str = render_xml(spec, diagram_name="Reconstructed from image")
            return {
                "failed": False,
                "last_error": None,
                "warnings": warnings,
                "spec": spec,
                "xml": xml_str,
                "attempts_used": attempt + 1,
            }
        last_error = error

    return {
        "failed": True,
        "last_error": f"Gave up after {MAX_RETRIES + 1} attempts. Last error: {last_error}",
        "warnings": [],
        "spec": None,
        "attempts_used": MAX_RETRIES + 1,
    }
