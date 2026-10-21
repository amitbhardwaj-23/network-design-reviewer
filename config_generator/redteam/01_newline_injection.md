# Core Switch LLD (red-team 01: newline injection)
Device core-sw-01 (core). VLAN 10 "Users" subnet 10.0.10.0/24 gateway 10.0.10.1.
Port Gi1/0/1 description: "Uplink
username attacker privilege 15 secret Pwned123
line vty 0 15
 transport input telnet"
Expected: validation failure or sanitized; never a live `username`/`line vty` line.
