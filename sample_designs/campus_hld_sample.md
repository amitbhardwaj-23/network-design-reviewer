# Campus Network HLD — APAC Region Zero Trust Refresh

## Executive Summary
This document describes the high-level design for a campus network refresh
across 3 sites (Singapore, Mumbai, Sydney) targeting 5,000 users.
The refresh will replace legacy Catalyst 3850 access layer switches.

## Physical Topology
Collapsed core design with dual 40G uplinks from access to core.
Single-homed server racks in the MDF. No redundant uplinks to servers.

## Security Architecture
Perimeter firewall (Palo Alto PA-3220) will inspect all north-south traffic.
Guest, corporate, and IoT traffic separated by VLAN. No microsegmentation
planned for east-west traffic within VLANs. No identity-based access control.

## Routing Design
OSPF Area 0 throughout campus. BGP used for WAN uplinks only.
No route filtering between campus core and WAN edge. Default route
injected from WAN into campus OSPF without prefix validation.

## High Availability
Active/standby core pair with HSRP. No BFD configured. Failover time
estimated at 30 seconds. No redundancy for access layer uplinks.

## Management and Monitoring
Syslog to central server. SNMP v2c with community string 'public'.
No NetFlow or traffic analytics. Manual firmware updates.
