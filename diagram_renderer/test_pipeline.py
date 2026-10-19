"""
test_pipeline.py — proves validate.py and render.py work correctly.
Does NOT require Ollama — this only tests the deterministic half.
Run: python test_pipeline.py
"""

import json
from validate import validate_spec, validate_xml
from render import render_xml

SAMPLE_LLM_OUTPUT = json.dumps({
    "devices": [
        {"id": "core-sw-1", "label": "Core Switch 1", "type": "switch", "tier": "core"},
        {"id": "core-sw-2", "label": "Core Switch 2", "type": "switch", "tier": "core"},
        {"id": "fw-1", "label": "Perimeter Firewall", "type": "firewall", "tier": "edge"},
        {"id": "dist-sw-1", "label": "Distribution Switch 1", "type": "switch", "tier": "distribution"},
        {"id": "acc-sw-1", "label": "Access Switch 1", "type": "switch", "tier": "access"},
    ],
    "links": [
        {"source": "fw-1", "target": "core-sw-1", "label": "10G"},
        {"source": "core-sw-1", "target": "core-sw-2", "label": "40G MLAG"},
        {"source": "core-sw-1", "target": "dist-sw-1", "label": "10G"},
        {"source": "dist-sw-1", "target": "acc-sw-1", "label": "1G"},
    ],
})


def run():
    print("=== validate (good sample) ===")
    spec, error = validate_spec(SAMPLE_LLM_OUTPUT)
    assert error is None, f"Unexpected failure: {error}"
    print(f"OK — {len(spec.devices)} devices, {len(spec.links)} links\n")

    print("=== render to XML ===")
    xml_str = render_xml(spec)
    print(f"Generated {len(xml_str)} chars\n")

    print("=== validate XML ===")
    ok, error = validate_xml(xml_str)
    assert ok, f"XML validation failed: {error}"
    print("OK\n")

    with open("test_output.drawio", "w") as f:
        f.write(xml_str)
    print("Written to test_output.drawio — open at app.diagrams.net to verify visually")


if __name__ == "__main__":
    run()
