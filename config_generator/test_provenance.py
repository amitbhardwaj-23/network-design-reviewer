"""Offline tests: values must be traceable to the LLD text; cloud devices get no config. Run: python3 test_provenance.py"""
import importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config_schema import ConfigSpec, VlanDef, InterfaceConfig, DeviceSecurityConfig
import config_provenance as P
import config_render as R
import config_prompts as CP

spec_ = importlib.util.spec_from_file_location("ds", os.path.join(HERE, "..", "diagram_renderer", "schema.py"))
ds = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(ds)

PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS  {name}")
    else: FAIL += 1; print(f"  FAIL  {name} {extra}")

LLD = open(os.path.join(HERE, "head_office_lld.md")).read()

print("A. the real wan-rtr-01 case from the last run")
spec = ConfigSpec(
    vlans=[VlanDef(vlan_id=20, name="Corporate Users", subnet="10.0.20.0/23", gateway="10.0.20.1"),
           VlanDef(vlan_id=999, name="Invented", gateway="203.0.113.1")],
    interfaces=[InterfaceConfig(device_id="wan-rtr-01", interface_name="GigabitEthernet0/0/0", mode="routed",
                                ip_address="10.0.20.2"),
                InterfaceConfig(device_id="core-sw-01", interface_name="Vlan20", mode="routed", ip_address="10.0.20.1"),
                InterfaceConfig(device_id="dist-sw-01", interface_name=None, mode="trunk", vlan_ids=[20])],
    security=[DeviceSecurityConfig(device_id="dist-sw-01", hsrp_priority=100, port_security=True, port_security_max_mac=2),
              DeviceSecurityConfig(device_id="access-sw-01", snmp_version="v2c")])
new, w = P.drop_unsupported_values(spec, LLD)
wan = next(i for i in new.interfaces if i.device_id == "wan-rtr-01")
check("invented IP 10.0.20.2 is cleared", wan.ip_address is None)
check("invented interface name is cleared and flagged as not stated", wan.interface_name is None and wan.interface_stated is False)
check("both are reported", any("10.0.20.2" in x for x in w) and any("GigabitEthernet0/0/0" in x for x in w))
check("invented VLAN 999 is dropped", [v.vlan_id for v in new.vlans] == [20])
v20 = new.vlans[0]
check("real gateway and subnet are kept", v20.gateway == "10.0.20.1" and v20.subnet == "10.0.20.0/23")
check("Vlan20 SVI name and its stated IP are kept", any(i.interface_name == "Vlan20" and i.ip_address == "10.0.20.1" for i in new.interfaces))
sec = next(s for s in new.security if s.device_id == "dist-sw-01")
check("HSRP priority 100 is not in the LLD -> cleared", sec.hsrp_priority is None)
check("MAC limit 2 is not in the LLD -> cleared", sec.port_security_max_mac is None)
check("input spec is not mutated", any(i.ip_address == "10.0.20.2" for i in spec.interfaces))

print("B. legitimate values survive")
txt = "Port Gi0/1 on Access-SW-01 is a trunk. Gateway 10.1.1.1 for VLAN 77 (10.1.1.0/24). HSRP priority 110. Port-security max 2."
ok = ConfigSpec(vlans=[VlanDef(vlan_id=77, name="X", subnet="10.1.1.0/24", gateway="10.1.1.1")],
                interfaces=[InterfaceConfig(device_id="access-sw-01", interface_name="GigabitEthernet0/1", mode="trunk"),
                            InterfaceConfig(device_id="core-sw-01", interface_name="Gi0/1", mode="routed", ip_address="10.1.1.1/24")],
                security=[DeviceSecurityConfig(device_id="core-sw-01", hsrp_priority=110, port_security_max_mac=2)])
n2, w2 = P.drop_unsupported_values(ok, txt)
check("expanded interface name (Gi0/1 -> GigabitEthernet0/1) is accepted", n2.interfaces[0].interface_name == "GigabitEthernet0/1")
check("IP with prefix length is matched on its address", n2.interfaces[1].ip_address == "10.1.1.1/24")
check("stated numbers are kept and nothing is warned", n2.security[0].hsrp_priority == 110 and n2.security[0].port_security_max_mac == 2 and w2 == [], w2)
check("10.1.1.1 must not match inside 110.1.1.15", P._ip_in("host 110.1.1.15", "10.1.1.1") is False)
check("VLAN 7 must not match inside VLAN 77", P._num_in("VLAN 77", 7) is False)
check("a stray digit is not a MAC limit, but a stated one is",
      P._num_near("see 2.1 Core", 2, ("mac",)) is False and P._num_near("max 2 MAC addresses", 2, ("mac",)))

print("C. renderer: cleared values flow into the visible placeholder path")
diag = ds.NetworkDiagramSpec(devices=[ds.Device(id="wan-rtr-01", label="WAN Router 1", type="router", tier="edge"),
                                      ds.Device(id="isp-a", label="ISP A", type="cloud", tier="edge")],
                             links=[ds.Link(source="wan-rtr-01", target="isp-a")])
cfgs, warns = R.render_all_configs_with_warnings(diag, new)
check("cloud device gets no config", "isp-a" not in cfgs and "wan-rtr-01" in cfgs)
check("wan-rtr-01 uses the placeholder name and has no invented IP",
      "interfaceUNSPECIFIED" in cfgs["wan-rtr-01"] and "10.0.20.2" not in cfgs["wan-rtr-01"])
check("a placeholder warning is produced", any("wan-rtr-01" in x for x in warns))

print("D. prompt")
p = CP.build_config_extraction_prompt("x", ["a-1"])
check("'applies to ALL devices' rule is in the prompt", "ALL network devices" in p and "EVERY device id" in p)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
