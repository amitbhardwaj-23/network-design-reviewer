"""
validate.py — deterministic validation, no LLM involved.

1. validate_spec()  — is the LLM's JSON output structurally sound?
                       Also auto-repairs links that reference an undeclared
                       device, rather than failing outright — this is a
                       known small-model failure mode (it uses a device in
                       a link but forgets to list it), and auto-repair is
                       far more reliable than hoping a retry fixes it.
2. validate_xml()   — is the generated .drawio XML structurally sound?
"""

import json
import re
import xml.etree.ElementTree as ET
from pydantic import ValidationError

from schema import NetworkDiagramSpec, Device


def _guess_type_and_tier(device_id: str) -> tuple[str, str]:
    """Best-effort inference for an auto-repaired device, from its id text alone."""
    s = device_id.lower()
    if any(k in s for k in ("fw", "firewall")):
        return "firewall", "edge"
    if any(k in s for k in ("wan", "rtr", "router", "isp")):
        return "router", "edge"
    if any(k in s for k in ("srv", "server")):
        return "server", "access"
    if any(k in s for k in ("core",)):
        return "switch", "core"
    if any(k in s for k in ("dist",)):
        return "switch", "distribution"
    if any(k in s for k in ("access", "acc-")):
        return "switch", "access"
    return "switch", "edge"


def validate_spec(raw_llm_output: str) -> tuple[NetworkDiagramSpec | None, str | None, list[str]]:
    """Returns (spec, fatal_error, warnings). fatal_error is None on success —
    warnings lists anything auto-repaired, so callers can surface it to the user."""
    warnings: list[str] = []
    cleaned = raw_llm_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return None, f"Output was not valid JSON: {e}", warnings

    try:
        spec = NetworkDiagramSpec(**data)
    except ValidationError as e:
        return None, f"JSON did not match the required schema: {e}", warnings

    if not spec.devices:
        return None, "No devices were extracted — the device list is empty.", warnings

    ids = spec.device_ids()
    missing_ids = set()
    for l in spec.links:
        if l.source not in ids:
            missing_ids.add(l.source)
        if l.target not in ids:
            missing_ids.add(l.target)

    if missing_ids:
        for mid in sorted(missing_ids):
            guessed_type, guessed_tier = _guess_type_and_tier(mid)
            label = re.sub(r"[-_]+", " ", mid).strip().title() + " (auto-added)"
            spec.devices.append(Device(id=mid, label=label, type=guessed_type, tier=guessed_tier))
            warnings.append(
                f"Device '{mid}' was referenced in a link but never declared by the model — "
                f"auto-added as type={guessed_type}, tier={guessed_tier}. Verify this is correct."
            )
        ids = spec.device_ids()

    return spec, None, warnings


def validate_xml(xml_str: str) -> tuple[bool, str]:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        return False, f"XML did not parse: {e}"

    cells = root.findall(".//mxCell")
    ids = {c.get("id") for c in cells}

    if "0" not in ids or "1" not in ids:
        return False, "Missing mandatory structural cells (mxCell id='0' and id='1')."

    vertex_ids = {c.get("id") for c in cells if c.get("vertex") == "1"}
    edges = [c for c in cells if c.get("edge") == "1"]
    dangling = [
        e.get("id") for e in edges
        if e.get("source") not in vertex_ids or e.get("target") not in vertex_ids
    ]
    if dangling:
        return False, f"Edges with dangling source/target: {dangling}"

    return True, ""
