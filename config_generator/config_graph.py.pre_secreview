"""
config_graph.py — orchestrates config generation.

Deliberately reuses diagram_renderer.graph.render_lld_to_diagram() for the
topology (devices/links/tiers) rather than re-extracting it — one design
submission now produces BOTH a diagram AND a set of device configs from the
same underlying extraction, benefiting from all of today's reliability work
(prompt fixes, auto-repair) automatically.

The config-parameter extraction below uses a simple bounded retry loop
rather than a second full LangGraph StateGraph — this is a deliberate
simplification given its retry logic is the same shape as the diagram
renderer's but doesn't need its own graph to express that.
"""

import os
import sys
from pathlib import Path

# make diagram_renderer importable as a sibling package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from langchain_ollama import ChatOllama

from diagram_renderer.graph import render_lld_to_diagram

from config_schema import ConfigSpec
from config_validate import validate_config_spec
from config_prompts import build_config_extraction_prompt
from config_render import render_all_configs, write_configs_to_dir

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
MAX_RETRIES = 2

_llm = ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, temperature=0)


def _extract_config_spec(lld_text: str, known_device_ids: list[str]) -> dict:
    """Bounded retry loop: extract -> validate -> retry on error, up to MAX_RETRIES."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = build_config_extraction_prompt(lld_text, known_device_ids, retry_error=last_error)
        response = _llm.invoke(prompt)
        spec, error, warnings = validate_config_spec(response.content, set(known_device_ids))
        if error is None:
            return {"spec": spec, "warnings": warnings, "failed": False, "last_error": None}
        last_error = error
    return {"spec": None, "warnings": [], "failed": True, "last_error": last_error}


def generate_configs_for_lld(lld_text: str, kb_context: str = "") -> dict:
    """Full pipeline: topology (reused from diagram_renderer) -> config params -> rendered configs.

    Returns a dict with: failed, last_error, warnings (list, combined from both stages),
    diagram_output_path, config_paths (list of per-device .cfg file paths).
    """
    topology_result = render_lld_to_diagram(lld_text=lld_text, kb_context=kb_context)
    if topology_result.get("failed"):
        return {
            "failed": True,
            "last_error": f"Topology extraction failed: {topology_result.get('last_error')}",
            "warnings": [],
            "diagram_output_path": None,
            "config_paths": [],
        }

    diagram_spec = topology_result["spec"]
    topology_warnings = topology_result.get("warnings", []) or []
    known_ids = [d.id for d in diagram_spec.devices]

    config_result = _extract_config_spec(lld_text, known_ids)
    if config_result["failed"]:
        return {
            "failed": True,
            "last_error": f"Config parameter extraction failed: {config_result['last_error']}",
            "warnings": topology_warnings,
            "diagram_output_path": topology_result.get("output_path"),
            "config_paths": [],
        }

    config_spec: ConfigSpec = config_result["spec"]
    configs = render_all_configs(diagram_spec, config_spec)
    config_paths = write_configs_to_dir(configs, output_dir=os.getenv("CONFIG_OUTPUT_DIR", "outputs/configs"))

    all_warnings = topology_warnings + config_result.get("warnings", [])

    return {
        "failed": False,
        "last_error": None,
        "warnings": all_warnings,
        "diagram_output_path": topology_result.get("output_path"),
        "config_paths": config_paths,
    }
