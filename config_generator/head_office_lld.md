# Low-Level Design - Campus Network Infrastructure
## Site: Head Office | Version: 1.0 | Date: July 2026

---

## 1. Executive Summary

This document describes the low-level network design for the Head Office campus network. The design implements a three-tier architecture comprising Core, Distribution, and Access layers, with perimeter security and WAN connectivity. This LLD is submitted for architecture design review and sign-off.

---

## 2. Physical Topology

### 2.1 Core Layer
Two Core switches (Core-SW-01 and Core-SW-02) operate in High Availability using HSRP and spanning Tree. Both Core switches are connected to each other via 2*40G chassis to chassis link. Core-SW-01 and Core-SW-02 each carry uplinks from all Distribution switches.

### 2.2 Distribution Layer
Two Distribution switches (Dist-SW-01 and Dist-SW-02) aggregate all Access layer uplinks. Each Distribution switch has two 10G uplinks - both uplinks from Dist-SW-01 terminate on Core-SW-01, and both uplinks from Dist-SW-02 terminate on Core-SW-02. HSRP is configured on Distribution switches for VLAN gateway redundancy. Inter-VLAN routing is performed at the Distribution layer.

### 2.3 Access Layer
Four Access switches (Access-SW-01 through Access-SW-04) provide end-device connectivity. Each Access switch has two uplinks with 1st 1G uplink terminating on Dist-SW-01 and 2nd 1G uplink terminating on Dist-SW-02. PortFast is enabled on all end-device facing ports.

### 2.4 WAN and Perimeter
A single WAN Router (WAN-RTR-01) connects to two ISPs (ISP-A and ISP-B) for internet redundancy. BGP is configured on WAN-RTR-01 with both ISP peers. The LAN-facing interface of WAN-RTR-01 terminates on Core-SW-01 only via a single 1G link. Static routing is used throughout the LAN domain.

### 2.5 Perimeter Firewall
A single Perimeter Firewall (FW-01) controls all north-south traffic between the WAN and LAN domains. FW-01 has its inside interface connected to Core-SW-01 only. No WAF or web proxy is deployed. East-west traffic between VLANs traverses the Distribution layer without firewall inspection.

### 2.6 Core Firewall
A single Core Firewall (Core-FW-01) is deployed for internal zone segmentation. Core-FW-01 is uplinked to Dist-SW-01 only via a single 10G link. No redundant uplink or failover path is provisioned for Core-FW-01.

---

## 3. VLAN Design

| VLAN | Name | Subnet | Gateway |
|---|---|---|---|
| 10 | Management | 10.0.10.0/24 | 10.0.10.1 |
| 20 | Corporate Users | 10.0.20.0/23 | 10.0.20.1 |
| 30 | Servers | 10.0.30.0/24 | 10.0.30.1 |
| 40 | Guest | 10.0.40.0/24 | 10.0.40.1 |
| 50 | VoIP | 10.0.50.0/24 | 10.0.50.1 |

---

## 4. Routing Design

Static routing is configured throughout the LAN domain. Default route points from Core switches toward FW-01. WAN-RTR-01 runs BGP with both ISP-A (AS 65001) and ISP-B (AS 65002). No dynamic routing protocol (OSPF, EIGRP) is deployed on the LAN side. Route summarisation toward WAN is not configured.

---

## 5. Management and Monitoring

SNMPv2c with community string "public" is configured on all network devices for monitoring. No SNMPv3 is deployed. Syslog is not configured on any device. No centralised log management or SIEM integration is in place. Out-of-band management is not provisioned.

---

## 6. Security Posture

Perimeter Firewall FW-01 inspects all north-south traffic. No east-west microsegmentation is implemented between VLANs. Port security is not configured on Access layer ports. 802.1X / NAC is not deployed. Guest VLAN 40 is not isolated from Corporate VLAN 20 at the firewall level. No web application firewall or proxy is in scope for this design.

---
*Document prepared for architecture review. Findings to be addressed prior to implementation sign-off.*
