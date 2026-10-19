from graph import extract_json, validate_spec_node, RendererState
from validate import validate_spec

LLD_TEXT = """## 1. Executive Summary

This document describes the low-level network design for the Head Office campus network. The design implements a three-tier architecture comprising Core, Distribution, and Access layers, with perimeter security and WAN connectivity. This LLD is submitted for architecture design review and sign-off.

---

## 2. Physical Topology

### 2.1 Core Layer
Two Core switches (Core-SW-01 and Core-SW-02) operate in High Availability using VSS (Virtual Switching System). Both Core switches are fully meshed via a 40G inter-chassis link. Core-SW-01 and Core-SW-02 each carry uplinks from all Distribution switches.

### 2.2 Distribution Layer
Two Distribution switches (Dist-SW-01 and Dist-SW-02) aggregate all Access layer uplinks. Each Distribution switch has two 10G uplinks — both uplinks from Dist-SW-01 terminate on Core-SW-01, and both uplinks from Dist-SW-02 terminate on Core-SW-02. HSRP is configured on Distribution switches for VLAN gateway redundancy. Inter-VLAN routing is performed at the Distribution layer.

### 2.3 Access Layer
Twelve Access switches (Access-SW-01 through Access-SW-12) provide end-device connectivity. Each Access switch has a single 1G uplink terminating on Dist-SW-01. No secondary uplinks are provisioned at the Access layer. PortFast is enabled on all end-device facing ports.

### 2.4 WAN and Perimeter
A single WAN Router (WAN-RTR-01) connects to two ISPs (ISP-A and ISP-B) for internet redundancy. BGP is configured on WAN-RTR-01 with both ISP peers. The LAN-facing interface of WAN-RTR-01 terminates on Core-SW-01 only via a single 1G link. Static routing is used throughout the LAN domain.

### 2.5 Perimeter Firewall
A single Perimeter Firewall (FW-01) controls all north-south traffic between the WAN and LAN domains. FW-01 has its inside interface connected to Core-SW-01 only. No WAF or web proxy is deployed. East-west traffic between VLANs traverses the Distribution layer without firewall inspection.

### 2.6 Core Firewall
A single Core Firewall (Core-FW-01) is deployed for internal zone segmentation. Core-FW-01 is uplinked to Dist-SW-01 only via a single 10G link. No redundant uplink or failover path is provisioned for Core-FW-01.
"""

MAX_ATTEMPTS = 4

state: RendererState = {"lld_text": LLD_TEXT, "kb_context": "", "retry_count": 0}

for attempt in range(1, MAX_ATTEMPTS + 1):
    print(f"\n{'='*20} ATTEMPT {attempt} {'='*20}")
    state = extract_json(state)
    print("--- RAW MODEL OUTPUT ---")
    print(state["raw_llm_output"])

    spec, error, warnings = validate_spec(state["raw_llm_output"])
    if error:
        print(f"\n--- VALIDATION FAILED ---\n{error}")
        state["last_error"] = error
        state["retry_count"] = attempt
    else:
        print(f"\n--- VALIDATION PASSED ---")
        if warnings:
            print("--- AUTO-REPAIR WARNINGS ---")
            for w in warnings:
                print(f"  ! {w}")
        print(f"Devices ({len(spec.devices)}): {[d.id for d in spec.devices]}")
        print(f"Links ({len(spec.links)}):")
        for l in spec.links:
            print(f"  {l.source} -> {l.target}  ({l.label})")
        break
else:
    print(f"\n{'='*20} GAVE UP after {MAX_ATTEMPTS} attempts {'='*20}")
