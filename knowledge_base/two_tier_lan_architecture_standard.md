# Two-Tier (Collapsed Core) LAN Architecture Standard

**Document ID:** STD-NET-002
**Supersedes:** N/A — companion standard to STD-NET-001 (Three-Tier LAN Architecture Standard)
**Applies to:** Branch offices, small-to-medium campus sites, and facilities with fewer than approximately 500 connected end-devices

---

## 1. Purpose and Scope

This standard defines the mandatory and recommended design requirements for a two-tier (collapsed core) LAN architecture. In a collapsed-core design, the Core and Distribution layers of the traditional three-tier model are merged into a single pair of switches that perform both inter-VLAN routing and network-wide aggregation, connecting directly to the Access layer without an intermediate Distribution tier.

This standard applies to any site where a full three-tier architecture (per STD-NET-001) would introduce unnecessary cost and complexity relative to the site's scale.

## 2. When to Use Two-Tier vs. Three-Tier

A two-tier collapsed-core design is the **required default** for sites meeting all of the following criteria:
- Fewer than 500 connected end-devices across all access switches
- Fewer than 8 access switches requiring uplink aggregation
- A single physical building or tightly clustered set of buildings (uplink cable runs under 300m)
- No requirement for more than two levels of hierarchical route summarization

Sites exceeding any of these thresholds **must** be designed per STD-NET-001 (Three-Tier LAN Architecture Standard) instead. A design that applies collapsed-core principles above these thresholds is a **CRITICAL** finding, as it creates a single aggregation point with insufficient headroom for growth and fault isolation.

## 3. Architecture Overview

The collapsed-core design consists of exactly two logical layers:

- **Collapsed Core Layer** — a pair of switches performing simultaneously: inter-VLAN routing, default gateway services (HSRP/VRRP), the network's Layer 2/Layer 3 boundary, and direct aggregation of all Access layer uplinks. This layer replaces both the Core and Distribution layers of the three-tier model.
- **Access Layer** — end-device connectivity, identical in function and requirements to the Access layer defined in STD-NET-001.

There is no intermediate Distribution layer. Every Access switch uplinks directly to the Collapsed Core pair.

## 4. Design Principles

### 4.1 Collapsed Core Redundancy (MANDATORY)
- The Collapsed Core **must** be deployed as a redundant pair, using either a stacking technology (e.g., StackWise Virtual, VSS) or independent chassis with a routed or switched inter-connect.
- A single, non-redundant Collapsed Core switch is a **CRITICAL** finding under all circumstances — this is the single most severe violation possible under this standard, since the Collapsed Core is simultaneously the routing boundary, the gateway, and the aggregation point; its failure takes down the entire site.

### 4.2 Access Layer Uplinks (MANDATORY)
- Every Access switch **must** have a minimum of two physical uplinks, each terminating on a **different** Collapsed Core switch.
- Uplink bandwidth must be provisioned at a maximum 8:1 oversubscription ratio relative to aggregate connected end-device bandwidth. A design exceeding 8:1 is a **HIGH** finding; exceeding 20:1 is a **CRITICAL** finding.
- A single uplink from any Access switch, or both uplinks terminating on the same Collapsed Core switch, is a **HIGH** finding — this eliminates the redundancy the Collapsed Core pair is intended to provide.

### 4.3 Inter-VLAN Routing (MANDATORY)
- All inter-VLAN routing **must** occur at the Collapsed Core layer. The Access layer must remain strictly Layer 2.
- HSRP or VRRP **must** be configured on every routed VLAN interface at the Collapsed Core, with both Collapsed Core switches participating.
- Static default gateway configuration without a first-hop redundancy protocol is a **HIGH** finding.

### 4.4 VLAN and Spanning Tree (MANDATORY)
- Access ports connecting end-devices must have PortFast (or equivalent) enabled.
- BPDU Guard must be enabled on all Access-layer end-device-facing ports.
- Trunked uplinks between Access and Collapsed Core must carry only the VLANs actually required at that Access switch — VLAN pruning is required, not optional. Carrying all VLANs on every trunk regardless of actual need is a **MEDIUM** finding.

### 4.5 Scalability Ceiling (MANDATORY)
- Because the Collapsed Core has no Distribution layer to absorb growth, this standard sets a hard ceiling: if a two-tier site's connected end-device count grows to exceed 500, or its access switch count exceeds 8, the site **must** be re-architected to a three-tier design per STD-NET-001 within the next planned refresh cycle. Continued operation as a two-tier design beyond these thresholds is a **HIGH** finding at any subsequent review.

## 5. Security Requirements

Security requirements mirror STD-NET-001 and NIST SP 800-207 (Zero Trust Architecture) in full — a collapsed-core design does not relax any security requirement relative to a three-tier design:

- OT/IT and any other required security zone boundaries must be enforced at the Collapsed Core via ACLs or a dedicated firewall context — never assumed to be implicit.
- Port security (maximum MAC address limits) must be enabled on all Access-layer end-device ports.
- 802.1X or an equivalent NAC mechanism is required for all corporate end-device VLANs; its absence is a **HIGH** finding.
- SNMP must use v3 exclusively; SNMPv2c with a community string is a **CRITICAL** finding regardless of tier architecture.
- Guest and corporate VLANs must be isolated from one another at the Collapsed Core firewall/ACL layer, not merely by separate VLAN numbering.

## 6. Management and Monitoring

- Syslog must be configured on both Collapsed Core switches, forwarding to a centralized log destination.
- Out-of-band management access is required for the Collapsed Core pair at minimum; its absence at a single-site collapsed-core deployment is a **MEDIUM** finding (versus **HIGH** at a three-tier site, reflecting the smaller blast radius of a branch/campus site).

## 7. Compliance Checklist

| # | Requirement | Severity if violated |
|---|---|---|
| 1 | Collapsed Core deployed as a redundant pair | CRITICAL |
| 2 | Every Access switch has 2 uplinks to 2 different Core switches | HIGH |
| 3 | Uplink oversubscription ≤ 8:1 | HIGH (>8:1) / CRITICAL (>20:1) |
| 4 | HSRP/VRRP configured on all routed VLANs | HIGH |
| 5 | PortFast + BPDU Guard on all access ports | MEDIUM |
| 6 | VLAN pruning on trunk uplinks | MEDIUM |
| 7 | Site within 500-device / 8-switch ceiling | HIGH |
| 8 | SNMPv3 only | CRITICAL |
| 9 | 802.1X/NAC on corporate VLANs | HIGH |
| 10 | Syslog centralized | MEDIUM |
| 11 | Out-of-band management present | MEDIUM |

---
*This standard is a companion to STD-NET-001 (Three-Tier LAN Architecture Standard). Where this document is silent on a topic, STD-NET-001 and the organization's Zero Trust segmentation policy apply.*
