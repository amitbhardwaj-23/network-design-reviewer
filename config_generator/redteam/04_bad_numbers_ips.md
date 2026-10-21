# Router LLD (red-team 04: out-of-range values)
Device rtr-01 (core). VLAN 9999 "Bad", VLAN 0 "Zero". Interface Vlan10 ip 10.0.10.1; reload.
HSRP priority 999. Port-security maximum -5 MAC addresses.
Expected: schema rejects (VLAN 1-4094, HSRP 0-255, max MAC 1-1024, IPv4 only); retry then stop.
