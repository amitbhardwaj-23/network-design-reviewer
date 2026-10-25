"""
graph.py - LangGraph wiring for the LLD renderer, matching your existing
project's config pattern (reads OLLAMA_BASE_URL / OLLAMA_MODEL from .env,
same as retriever.py does for CHROMA_DB_PATH).

CHANGE (extraction completeness): after the spec validates, a deterministic check compares the
device names in the LLD text with the extracted devices. If the model dropped any, it gets ONE extra
attempt with the missing names spelled out (COVERAGE_RETRIES). If it is still incomplete the run
continues with the best attempt and a visible warning - it never fails just because of coverage.
Devices that end up with no links are also reported as warnings.

Usage from app.py:

    from diagram_renderer.graph import render_lld_to_diagram

    result = render_lld_to_diagram(lld_text=approved_lld_text, kb_context=retrieved_context)
    if result["failed"]:
        st.error(f"Rendering failed: {result['last_error']}")
    else:
        st.success(f"Diagram written to {result['output_path']}")
        with open(result["output_path"], "rb") as f:
            st.download_button("Download .drawio", f, file_name="network_lld.drawio")
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import TypedDict, Optional
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END

from schema import NetworkDiagramSpec
from validate import validate_spec, validate_xml
from render import render_xml
from prompts import build_extraction_prompt
from topology_coverage import find_missing_devices, find_unlinked_devices
from link_pass import complete_links

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
MAX_RETRIES = 2
COVERAGE_RETRIES = 1     # extra attempts allowed when the LLD names devices the model left out
LINK_PASS = os.getenv("ARGUS_LINK_PASS", "1") != "0"   # section-by-section link completion; set 0 to disable

_llm = ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, temperature=0)


class RendererState(TypedDict, total=False):
    lld_text: str
    kb_context: str
    retry_count: int
    coverage_retries: int
    last_error: Optional[str]
    raw_llm_output: Optional[str]
    spec: Optional[NetworkDiagramSpec]
    candidate_spec: Optional[NetworkDiagramSpec]      # best valid-but-incomplete attempt so far
    candidate_warnings: list[str]
    xml: Optional[str]
    output_path: Optional[str]
    failed: bool
    warnings: list[str]


def extract_json(state: RendererState) -> RendererState:
    prompt = build_extraction_prompt(
        lld_text=state["lld_text"],
        kb_context=state.get("kb_context", ""),
        retry_error=state.get("last_error"),
    )
    response = _llm.invoke(prompt)
    raw_output = response.content
    return {**state, "raw_llm_output": raw_output}


def _size(spec) -> int:
    return len(spec.devices) + len(spec.links)


def _missing_warning(missing: list[str]) -> str:
    return ("Devices named in the LLD are missing from the extracted topology: "
            + ", ".join(missing) + ". The diagram, configs and security review may be incomplete.")


def _finish(spec, warnings: list[str], lld_text: str, extra: list[str] | None = None) -> dict:
    warnings = list(warnings) + list(extra or [])
    return {"spec": spec, "last_error": None, "warnings": warnings}


def validate_spec_node(state: RendererState) -> RendererState:
    lld = state.get("lld_text", "")
    cand = state.get("candidate_spec")
    cand_warn = state.get("candidate_warnings", [])
    spec, error, warnings = validate_spec(state["raw_llm_output"])

    if error:
        retry_count = state.get("retry_count", 0) + 1
        if cand is not None and retry_count >= MAX_RETRIES:
            # the coverage retry produced something unusable: keep the earlier valid attempt
            return {**state, **_finish(cand, cand_warn, lld, [_missing_warning(find_missing_devices(lld, cand))])}
        return {**state, "spec": None, "last_error": error, "retry_count": retry_count}

    missing = find_missing_devices(lld, spec)
    if missing:
        used = state.get("coverage_retries", 0)
        best, best_warn = spec, warnings
        if cand is not None and (len(find_missing_devices(lld, cand)), -_size(cand)) < (len(missing), -_size(spec)):
            best, best_warn = cand, cand_warn
        if used < COVERAGE_RETRIES:
            msg = ("The JSON is valid but incomplete. These devices are named in the LLD text and are missing "
                   "from your output: " + ", ".join(missing) + ". Add each one as a device, and add every link "
                   "the text describes for them (including ISP links, inter-switch links and second uplinks).")
            return {**state, "spec": None, "candidate_spec": best, "candidate_warnings": best_warn,
                    "last_error": msg, "coverage_retries": used + 1}
        return {**state, **_finish(best, best_warn, lld, [_missing_warning(find_missing_devices(lld, best))])}

    return {**state, **_finish(spec, warnings, lld)}


def link_pass_node(state: RendererState) -> RendererState:
    """Adds links the whole-document extraction missed, then reports devices that are still unlinked.
    Never fails the run: any problem here leaves the topology as it was, with a warning."""
    spec = state["spec"]
    warnings = list(state.get("warnings") or [])
    if LINK_PASS:
        try:
            new_links, notes = complete_links(spec, state.get("lld_text", ""),
                                              lambda prompt: _llm.invoke(prompt).content)
            if new_links:
                spec = NetworkDiagramSpec(devices=spec.devices, links=list(spec.links) + new_links)
            warnings += notes
        except Exception as e:
            warnings.append(f"The link-completion pass failed ({type(e).__name__}); the topology was left as extracted.")
    unlinked = find_unlinked_devices(spec)
    if unlinked:
        warnings.append("Devices with no links in the extracted topology: " + ", ".join(unlinked)
                        + ". A link may be missing from the extraction.")
    return {**state, "spec": spec, "warnings": warnings}


def route_after_validation(state: RendererState) -> str:
    if state.get("spec") is not None:
        return "render"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return "give_up"
    return "retry"


def render_xml_node(state: RendererState) -> RendererState:
    xml_str = render_xml(state["spec"], diagram_name="Network LLD")
    return {**state, "xml": xml_str}


def validate_xml_node(state: RendererState) -> RendererState:
    ok, error = validate_xml(state["xml"])
    if not ok:
        return {**state, "failed": True, "last_error": error}
    return state


def write_file_node(state: RendererState) -> RendererState:
    output_dir = os.getenv("DIAGRAM_OUTPUT_DIR", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "network_lld.drawio")
    with open(path, "w") as f:
        f.write(state["xml"])
    return {**state, "output_path": path, "failed": False}


def give_up_node(state: RendererState) -> RendererState:
    return {**state, "failed": True}


def _build_graph():
    graph = StateGraph(RendererState)
    graph.add_node("extract_json", extract_json)
    graph.add_node("validate_spec", validate_spec_node)
    graph.add_node("link_pass", link_pass_node)
    graph.add_node("render_xml", render_xml_node)
    graph.add_node("validate_xml", validate_xml_node)
    graph.add_node("write_file", write_file_node)
    graph.add_node("give_up", give_up_node)

    graph.set_entry_point("extract_json")
    graph.add_edge("extract_json", "validate_spec")
    graph.add_conditional_edges("validate_spec", route_after_validation, {
        "render": "link_pass",
        "retry": "extract_json",
        "give_up": "give_up",
    })
    graph.add_edge("link_pass", "render_xml")
    graph.add_edge("render_xml", "validate_xml")
    graph.add_edge("validate_xml", "write_file")
    graph.add_edge("write_file", END)
    graph.add_edge("give_up", END)
    return graph.compile()


_app = _build_graph()


def render_lld_to_diagram(lld_text: str, kb_context: str = "") -> RendererState:
    """Entry point for app.py - runs the full extract -> validate -> render -> write pipeline."""
    initial: RendererState = {"lld_text": lld_text, "kb_context": kb_context, "retry_count": 0}
    return _app.invoke(initial)
