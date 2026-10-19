"""
agent.py — LangGraph agentic review pipeline.
Usage: python agent.py path/to/design.md
"""
import os, sys
from typing import TypedDict, Annotated, List
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

from retriever import retrieve_standards
from parser import parse_design_doc, load_document

LLM_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
llm = ChatOllama(model=LLM_MODEL, temperature=0)

class ReviewState(TypedDict):
    design_text: str
    design_sections: List[dict]
    retrieved_standards: List[dict]
    report: str
    messages: Annotated[list, "append"]

@tool
def search_architectural_standards(query: str) -> str:
    """Search the knowledge base for relevant architectural standards and principles."""
    results = retrieve_standards(query, k=4)
    return "\n\n".join(f"[{r['source']} | score:{r['score']}]\n{r['content']}" for r in results)

@tool
def flag_finding(section: str, issue: str, severity: str, reference: str, recommendation: str) -> str:
    """Record a design finding. severity must be: CRITICAL | HIGH | MEDIUM | LOW"""
    return f"Finding recorded: [{severity}] {section} — {issue}"

tools = [search_architectural_standards, flag_finding]
llm_with_tools = llm.bind_tools(tools)

def parse_node(state: ReviewState) -> ReviewState:
    sections = parse_design_doc(state["design_text"])
    return {**state, "design_sections": sections}

def retrieve_node(state: ReviewState) -> ReviewState:
    all_standards = []
    for s in state["design_sections"]:
        query = f"{s['title']}: {s['content'][:200]}"
        results = retrieve_standards(query, k=3)
        all_standards.append({"section": s["title"], "standards": results})
    return {**state, "retrieved_standards": all_standards}

def review_node(state: ReviewState) -> ReviewState:
    system = SystemMessage(content="""You are a Senior Enterprise Architect conducting a formal design review.
Review each section against the retrieved architectural standards.
Use search_architectural_standards to find additional relevant standards.
Use flag_finding to record every gap or compliance issue you identify.
Severity: CRITICAL (security/availability risk), HIGH (significant gap), MEDIUM (best practice), LOW (minor).
Be specific. Reference the exact standard being violated. Do not flag issues without retrieving standards first.""")

    context = "\n\n---\n\n".join(
        f"Section: {item['section']}\nStandards:\n" +
        "\n".join(s['content'][:300] for s in item['standards'])
        for item in state["retrieved_standards"]
    )

    user = HumanMessage(content=f"""Review this design document.

DESIGN DOCUMENT:
{state['design_text'][:5000]}

RETRIEVED STANDARDS:
{context[:3000]}

Review each section, search for additional standards as needed, and flag all findings.""")

    messages = [system, user]
    response = llm_with_tools.invoke(messages)
    messages.append(response)
    return {**state, "messages": messages}

def report_node(state: ReviewState) -> ReviewState:
    synthesis = HumanMessage(content="""Based on your review, produce a structured report with:

1. EXECUTIVE SUMMARY (3-4 sentences, board-level language)
2. FINDINGS TABLE (| Section | Severity | Issue | Standard Reference | Recommendation |)
3. OVERALL RISK RATING: RED / AMBER / GREEN with one-line justification
4. TOP 3 PRIORITY ACTIONS for the design team before sign-off

Format in clean Markdown.""")

    messages = state["messages"] + [synthesis]
    response = llm.invoke(messages)
    return {**state, "report": response.content}

def should_continue(state: ReviewState) -> str:
    last = state["messages"][-1] if state["messages"] else None
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "report"

def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("parse",    parse_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("review",   review_node)
    g.add_node("tools",    ToolNode(tools))
    g.add_node("report",   report_node)
    g.set_entry_point("parse")
    g.add_edge("parse",    "retrieve")
    g.add_edge("retrieve", "review")
    g.add_conditional_edges("review", should_continue, {"tools": "tools", "report": "report"})
    g.add_edge("tools",    "review")
    g.add_edge("report",   END)
    return g.compile()

def review_design(document_path: str) -> str:
    text = load_document(document_path)
    app  = build_graph()
    initial = ReviewState(
        design_text=text, design_sections=[], retrieved_standards=[],
        report="", messages=[]
    )
    final = app.invoke(initial, config={"recursion_limit": 15})
    return final["report"]

if __name__ == "__main__":
    doc = sys.argv[1] if len(sys.argv) > 1 else "sample_designs/campus_hld_sample.md"
    print(f"\nReviewing: {doc}\n")
    print(review_design(doc))
