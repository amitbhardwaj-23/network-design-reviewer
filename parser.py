"""parser.py — splits design documents into typed sections for the agent."""
import re
from typing import List
from pathlib import Path

SECTION_TYPE_MAP = {
    "executive summary": "executive", "objective": "executive", "scope": "executive",
    "topology": "physical_design", "physical": "physical_design",
    "logical": "logical_design",
    "ip addressing": "ip_design", "addressing": "ip_design",
    "routing": "routing", "bgp": "routing", "ospf": "routing", "mpls": "routing",
    "vlan": "switching", "switching": "switching",
    "vxlan": "overlay", "evpn": "overlay", "aci": "overlay",
    "security": "security", "firewall": "security",
    "zero trust": "zero_trust", "segmentation": "zero_trust",
    "vpn": "remote_access", "remote access": "remote_access", "sase": "remote_access",
    "sd-wan": "wan", "wan": "wan",
    "cloud": "cloud", "azure": "cloud", "aws": "cloud", "hybrid": "cloud",
    "high availability": "availability", "redundancy": "availability",
    "ha ": "availability", "disaster recovery": "availability",
    "management": "operations", "monitoring": "operations",
    "observability": "operations", "ntp": "operations", "dns": "operations",
    "qos": "qos", "quality of service": "qos",
}

def parse_design_doc(text: str) -> List[dict]:
    sections = _parse_markdown(text)
    if len(sections) <= 1:
        sections = _parse_paragraphs(text)
    for s in sections:
        s["type"] = _infer_type(s["title"])
        s["word_count"] = len(s["content"].split())
    return [s for s in sections if s["word_count"] >= 15]

def _parse_markdown(text: str) -> List[dict]:
    matches = list(re.finditer(r'^(#{1,3})\s+(.+)$', text, re.MULTILINE))
    if not matches:
        return [{"title": "Document", "content": text}]
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        sections.append({"title": m.group(2).strip(), "content": text[start:end].strip()})
    return sections

def _parse_paragraphs(text: str) -> List[dict]:
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    sections, title, content, wc = [], "Introduction", [], 0
    for p in paras:
        if len(p) < 80 and (p.isupper() or re.match(r'^[A-Z][^.!?]*$', p)):
            if content: sections.append({"title": title, "content": "\n\n".join(content)})
            title, content, wc = p, [], 0
        else:
            content.append(p); wc += len(p.split())
            if wc > 350:
                sections.append({"title": title, "content": "\n\n".join(content)})
                content, wc = [], 0
    if content: sections.append({"title": title, "content": "\n\n".join(content)})
    return sections

def _infer_type(title: str) -> str:
    t = title.lower()
    for kw, tp in SECTION_TYPE_MAP.items():
        if kw in t: return tp
    return "general"

def load_document(path: str) -> str:
    fp = Path(path)
    if not fp.exists(): raise FileNotFoundError(f"Not found: {path}")
    if fp.suffix in (".md", ".txt"):
        return fp.read_text(encoding="utf-8", errors="replace")
    elif fp.suffix == ".docx":
        from docx import Document
        return "\n\n".join(p.text for p in Document(str(fp)).paragraphs if p.text.strip())
    raise ValueError(f"Unsupported file type: {fp.suffix} (use .md, .txt, or .docx)")
