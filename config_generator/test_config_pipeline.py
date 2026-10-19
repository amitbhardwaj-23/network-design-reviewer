"""
test_config_pipeline.py — proves config_schema.py, config_validate.py, and
config_render.py work correctly. Does NOT require Ollama.
Run from network-design-reviewer/config_generator/: python3 test_config_pipeline.py
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "diagram_renderer"))

from schema import NetworkDiagramSpec, Device, Link
from config_validate import validate_config_spec
from config_render import render_all_configs, write_configs_to_dir

# a small topology, same shape as what diagram_renderer would produce
diagram_spec = NetworkDiagramSpec(
    devices=[
        Device(id="core-sw-01", label="Core Switch 1", type="switch", tier="core"),
        Device(id="access-sw-01", label="Access Switch 1", type="switch", tier="access"),
        Device(id="fw-01", label="Perimeter Firewall", type="firewall", tier="edge"),
    ],
    links=[
        Link(source="fw-01", target="core-sw-01", label="1G"),
        Link(source="core-sw-01", target="access-sw-01", label="1G uplink"),
    ],
)
known_ids = {d.id for d in diagram_spec.devices}

# simulate what the LLM's config extraction SHOULD produce, including one
# deliberately bad device_id to prove auto-repair-by-omission works
SAMPLE_CONFIG_OUTPUT = json.dumps({
    "vlans": [
        {"vlan_id": 10, "name": "Management", "subnet": "10.0.10.0/24", "gateway": "10.0.10.1"},
        {"vlan_id": 20, "name": "Corporate", "subnet": "10.0.20.0/24", "gateway": "10.0.20.1"},
    ],
    "interfaces": [
        {"device_id": "core-sw-01", "interface_name": "Vlan10", "mode": "routed", "vlan_ids": [10], "ip_address": "10.0.10.1", "description": "Management SVI"},
        {"device_id": "access-sw-01", "interface_name": "GigabitEthernet1/0/1", "mode": "access", "vlan_ids": [20], "description": "End-device port"},
        {"device_id": "nonexistent-sw-99", "interface_name": "Gi1/0/1", "mode": "access", "vlan_ids": [20], "description": "Should be dropped"},
    ],
    "security": [
        {"device_id": "access-sw-01", "port_security": True, "port_security_max_mac": 2, "portfast_bpduguard": True, "dot1x": False, "snmp_version": "v2c"},
        {"device_id": "core-sw-01", "port_security": False, "portfast_bpduguard": False, "dot1x": False, "snmp_version": "v3", "hsrp_priority": 110},
    ],
    "routing_protocol": "static",
    "default_route_next_hop": "fw-01",
})


def run():
    print("=== validate config spec (with one intentionally bad device_id) ===")
    spec, error, warnings = validate_config_spec(SAMPLE_CONFIG_OUTPUT, known_ids)
    assert error is None, f"Unexpected failure: {error}"
    print(f"OK — {len(spec.vlans)} vlans, {len(spec.interfaces)} interfaces kept")
    print("Warnings (should mention the dropped nonexistent-sw-99):")
    for w in warnings:
        print(f"  ! {w}")
    assert len(spec.interfaces) == 2, "the bad device_id interface should have been dropped"
    print()

    print("=== render configs for all 3 devices ===")
    configs = render_all_configs(diagram_spec, spec)
    for device_id, text in configs.items():
        print(f"\n--- {device_id}.cfg ---")
        print(text)

    print("\n=== write to disk ===")
    paths = write_configs_to_dir(configs, output_dir="test_config_output")
    print(f"Written: {paths}")


if __name__ == "__main__":
    run()
