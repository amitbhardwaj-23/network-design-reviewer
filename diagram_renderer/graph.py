"""
graph.py — LangGraph wiring for the LLD renderer, matching your existing
project's config pattern (reads OLLAMA_BASE_URL / OLLAMA_MODEL from .env,
same as retriever.py does for CHROMA_DB_PATH).

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

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
MAX_RETRIES = 2

_llm = ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, temperature=0)


class RendererState(TypedDict, total=False):
    lld_text: str
    kb_context: str
    retry_count: int
    last_error: Optional[str]
    raw_llm_output: Optional[str]
    spec: Optional[NetworkDiagramSpec]
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


def validate_spec_node(state: RendererState) -> RendererState:
    spec, error, warnings = validate_spec(state["raw_llm_output"])
    if error:
        retry_count = state.get("retry_count", 0) + 1
        return {**state, "spec": None, "last_error": error, "retry_count": retry_count}
    return {**state, "spec": spec, "last_error": None, "warnings": warnings}


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
    graph.add_node("render_xml", render_xml_node)
    graph.add_node("validate_xml", validate_xml_node)
    graph.add_node("write_file", write_file_node)
    graph.add_node("give_up", give_up_node)

    graph.set_entry_point("extract_json")
    graph.add_edge("extract_json", "validate_spec")
    graph.add_conditional_edges("validate_spec", route_after_validation, {
        "render": "render_xml",
        "retry": "extract_json",
        "give_up": "give_up",
    })
    graph.add_edge("render_xml", "validate_xml")
    graph.add_edge("validate_xml", "write_file")
    graph.add_edge("write_file", END)
    graph.add_edge("give_up", END)
    return graph.compile()


_app = _build_graph()


def render_lld_to_diagram(lld_text: str, kb_context: str = "") -> RendererState:
    """Entry point for app.py — runs the full extract -> validate -> render -> write pipeline."""
    initial: RendererState = {"lld_text": lld_text, "kb_context": kb_context, "retry_count": 0}
    return _app.invoke(initial)
