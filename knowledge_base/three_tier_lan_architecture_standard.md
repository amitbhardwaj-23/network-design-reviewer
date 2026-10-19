# Three-Tier Campus LAN Architecture Standard

## Purpose

This standard defines mandatory design requirements for three-tier campus LAN
architectures (Core / Distribution / Access). It is used as a reference during
architecture design review to validate that submitted HLDs and LLDs comply
with redundancy, scalability, and operational resilience requirements before
sign-off.

---

## 1. Layer Presence — Mandatory

### 1.1 Three distinct layers required
A compliant three-tier design MUST contain three logically and physically
distinct layers:

- **Core layer** — high-speed backbone switching, no policy enforcement,
  no end-device connectivity.
- **Distribution layer** — aggregation point for access layer uplinks,
  inter-VLAN routing, policy enforcement (ACLs, QoS), and the boundary
  between Layer 2 and Layer 3 domains.
- **Access layer** — end-device connectivity (workstations, phones, APs,
  printers, IoT devices). No inter-VLAN routing performed at this layer.

**Finding trigger:** If a submitted design collapses Core and Distribution
into a single layer ("collapsed core") without explicit justification
(e.g. small site, <3 distribution blocks), flag as MEDIUM and request
justification. If Access devices connect directly to Core (bypassing
Distribution), flag as CRITICAL — this violates the layered model entirely.

### 1.2 No layer-skipping
Access layer switches MUST uplink to Distribution layer switches only.
Access switches MUST NOT have direct uplinks to Core layer switches.
Distribution layer switches MUST uplink to Core layer switches only.

**Finding trigger:** Any direct Access-to-Core link present in the topology
description is a CRITICAL finding — this defeats the purpose of the
distribution layer (policy enforcement, route summarisation, fault
isolation) and creates an inconsistent failure domain.

---

## 2. Layer-Specific Responsibilities

### 2.1 Core layer responsibilities
- High-speed transit only — no packet manipulation, no ACLs, no QoS policy
  enforcement at Core.
- Core MUST run Layer 3 with fast-converging routing (OSPF, EIGRP, or
  static routes with BFD) — Core should not run Spanning Tree Protocol
  as the primary loop-prevention mechanism if Layer 3 core is in use.
- Core switches MUST NOT terminate end-user VLANs directly.

**Finding trigger:** If the design shows ACLs, firewall policy, or QoS
marking being performed at the Core layer, flag as HIGH — this violates
separation of concerns and risks introducing latency/CPU load at the
most traffic-dense point in the network.

### 2.2 Distribution layer responsibilities
- Boundary for Layer 2 (toward Access) and Layer 3 (toward Core).
- Performs inter-VLAN routing for all VLANs aggregated from downstream
  Access switches.
- Enforces routing policy: route summarisation toward Core, route
  filtering, and VLAN-based ACLs.
- First-Hop Redundancy Protocol (HSRP, VRRP, or GLBP) MUST be configured
  at Distribution for every VLAN gateway, with sub-second failover
  (BFD-enabled where supported).

**Finding trigger:** If a design specifies a Distribution layer with no
FHRP (HSRP/VRRP/GLBP) configured, flag as CRITICAL — single point of
failure for every downstream VLAN's default gateway. If route
summarisation toward Core is not mentioned, flag as MEDIUM — this
risks routing table bloat and unnecessarily widens the Core's failure
domain awareness.

### 2.3 Access layer responsibilities
- End-device connectivity only.
- Implements port security, 802.1X (or equivalent NAC), and storm
  control at the edge.
- VLANs are defined and assigned here; trunking to Distribution carries
  the necessary VLAN set only (no unnecessary VLANs trunked).
- Spanning Tree PortFast (or equivalent) MUST be enabled on all
  end-device-facing ports to avoid unnecessary STP convergence delay.

**Finding trigger:** If port security / 802.1X / NAC is not mentioned for
Access layer ports, flag as HIGH in any design touching guest, BYOD, or
public-facing network segments. If PortFast/edge-port equivalent is not
configured on access ports, flag as LOW (operational best practice, not
a hard failure).

---

## 3. Uplink Redundancy — Mandatory

### 3.1 Minimum uplink count
**Every device at every layer (Access, Distribution, Core) MUST have a
minimum of two (2) physical uplinks to the layer above it.**

A single uplink from any Access switch to Distribution, or any
Distribution switch to Core, is a single point of failure and is
NON-COMPLIANT regardless of link speed or quality.

**Finding trigger:** Any device description showing only one uplink
("single 10G uplink to distribution") is a CRITICAL finding. Reference
this clause explicitly in the finding.

### 3.2 Diverse uplink requirement
**The two (or more) uplinks from a device MUST terminate on two
different upstream devices — not two ports on the same upstream
device.**

Two uplinks from an Access switch both terminating on the same
Distribution switch (even on different line cards or different ports)
do NOT satisfy this requirement, because the failure of that single
upstream device still results in total loss of upstream connectivity
for the downstream device.

Compliant pattern:
```
Access-SW-01  --uplink-1-->  Dist-SW-A
Access-SW-01  --uplink-2-->  Dist-SW-B
```

Non-compliant pattern (flag as CRITICAL even though 2 uplinks exist):
```
Access-SW-01  --uplink-1-->  Dist-SW-A (port Gi1/0/1)
Access-SW-01  --uplink-2-->  Dist-SW-A (port Gi1/0/2)
```

**Finding trigger:** If a design has two uplinks but both terminate on
the same named device, flag as CRITICAL with explicit note: "Uplink
count satisfies redundancy in quantity but not in diversity — both
uplinks share fate with a single upstream device."

### 3.3 Diverse physical pathing (where stated)
Where the design specifies physical pathway information (conduit,
riser, fibre route), the two diverse uplinks SHOULD also take physically
diverse paths between the IDF/MDF locations, to protect against a single
physical cut event (e.g. construction damage, fibre cut) taking down
both links simultaneously.

**Finding trigger:** If physical pathing is described and both uplinks
share the same conduit/riser/path, flag as HIGH. If physical pathing is
not mentioned at all, flag as LOW (informational — recommend the
designer confirm physical diversity, do not assume non-compliance).

### 3.4 Uplink load distribution
Where multiple diverse uplinks exist, the design SHOULD specify whether
they operate in active/active (e.g. via MLAG, VSS, StackWise Virtual, or
ECMP) or active/standby (e.g. via STP blocking or HSRP-only failover).
Active/active is preferred for bandwidth efficiency; active/standby is
acceptable but should be explicitly stated as a deliberate design choice.

**Finding trigger:** If uplink behaviour (active/active vs
active/standby) is not specified, flag as MEDIUM — ambiguous failover
and bandwidth behaviour, request the designer to clarify intended
operation.

---

## 4. Distribution and Core Layer Cross-Connect

### 4.1 Distribution-to-Distribution peer link
Where two or more Distribution switches serve the same Access layer
segment, a direct peer link (or virtual chassis / stacking technology)
between the Distribution switches SHOULD be present to support FHRP
state synchronisation and faster convergence during single-uplink
failure scenarios.

**Finding trigger:** Absence of a Distribution peer link in a
dual-Distribution-switch design is a MEDIUM finding — not strictly
required if FHRP and routing alone provide adequate convergence, but
the designer should confirm this was a deliberate choice.

### 4.2 Core layer full mesh or equivalent
Core layer switches (where more than one exists) MUST be fully meshed
or interconnected via a resilient topology (e.g. via redundant
high-speed links or fabric technology) such that the failure of any
single Core switch does not partition the Distribution layer.

**Finding trigger:** Any Core topology where the failure of one Core
device isolates a subset of Distribution switches from the rest of the
network is a CRITICAL finding.

---

## 5. Summary Checklist for Design Review

When reviewing a three-tier campus design, confirm and report status
against each item below:

| # | Requirement | Severity if absent |
|---|---|---|
| 1 | Three distinct layers present (Core, Distribution, Access) | CRITICAL |
| 2 | No Access-to-Core direct links (layer skipping) | CRITICAL |
| 3 | Core performs no policy enforcement (ACL/QoS) | HIGH |
| 4 | FHRP configured at Distribution for every VLAN gateway | CRITICAL |
| 5 | Route summarisation toward Core from Distribution | MEDIUM |
| 6 | Port security / 802.1X / NAC at Access edge | HIGH |
| 7 | PortFast / edge-port on all Access end-device ports | LOW |
| 8 | Minimum 2 uplinks per device at every layer | CRITICAL |
| 9 | Uplinks terminate on 2 different upstream devices (diversity) | CRITICAL |
| 10 | Physically diverse pathing for uplinks (where stated) | HIGH |
| 11 | Uplink active/active vs active/standby behaviour specified | MEDIUM |
| 12 | Distribution peer link present (dual-Distribution designs) | MEDIUM |
| 13 | Core layer fully meshed / no single point of partition | CRITICAL |

---

## 6. Reference Citation Format

When citing this standard in a design review finding, use the format:

`Three-Tier LAN Architecture Standard §<section> — <requirement summary>`

Example:
> [CRITICAL] Access Layer — Access-SW-04 has two uplinks but both
> terminate on Dist-SW-A. Reference: Three-Tier LAN Architecture
> Standard §3.2 — Uplinks must terminate on two different upstream
> devices. Two uplinks to the same device satisfy quantity but not
> diversity, and do not protect against upstream device failure.
> Recommendation: Reroute one uplink from Access-SW-04 to Dist-SW-B.
