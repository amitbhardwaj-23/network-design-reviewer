"""Offline tests for the rule-based security reviewer. Run: python3 test_security_reviewer.py"""
import importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "config_generator"))
sys.path.insert(0, HERE)

from config_schema import ConfigSpec, VlanDef, InterfaceConfig, DeviceSecurityConfig
import config_render as R
import security_rules as S

spec = importlib.util.spec_from_file_location("ds", os.path.join(HERE, "..", "diagram_renderer", "schema.py"))
ds = importlib.util.module_from_spec(spec); spec.loader.exec_module(ds)

PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS  {name}")
    else: FAIL += 1; print(f"  FAIL  {name} {extra}")

def D(i, ty, t): return ds.Device(id=i, label=i, type=ty, tier=t)
def L(a, b): return ds.Link(source=a, target=b)

# ---- the Head Office sample LLD, as extracted --------------------------------------------
devs = [D("isp-a", "cloud", "edge"), D("isp-b", "cloud", "edge"), D("wan-rtr-01", "router", "edge"),
        D("fw-01", "firewall", "edge"), D("core-fw-01", "firewall", "distribution"),
        D("core-sw-01", "switch", "core"), D("core-sw-02", "switch", "core"),
        D("dist-sw-01", "switch", "distribution"), D("dist-sw-02", "switch", "distribution")]
devs += [D(f"access-sw-0{n}", "switch", "access") for n in range(1, 5)]
links = [L("isp-a", "wan-rtr-01"), L("isp-b", "wan-rtr-01"), L("wan-rtr-01", "core-sw-01"),
         L("fw-01", "core-sw-01"), L("core-sw-01", "core-sw-02"), L("core-fw-01", "dist-sw-01"),
         L("dist-sw-01", "core-sw-01"), L("dist-sw-02", "core-sw-02")]
for n in range(1, 5):
    links += [L(f"access-sw-0{n}", "dist-sw-01"), L(f"access-sw-0{n}", "dist-sw-02")]
diag = ds.NetworkDiagramSpec(devices=devs, links=links)

cfg = ConfigSpec(
    vlans=[VlanDef(vlan_id=10, name="Management"), VlanDef(vlan_id=20, name="Corporate Users"),
           VlanDef(vlan_id=40, name="Guest")],
    interfaces=[InterfaceConfig(device_id="dist-sw-01", mode="trunk", interface_name=None)],
    security=[DeviceSecurityConfig(device_id=i, snmp_version="v2c") for i in
              ("core-sw-01", "dist-sw-01")] +
             [DeviceSecurityConfig(device_id="dist-sw-02", hsrp_priority=100)],
    routing_protocol="bgp")
configs, _ = R.render_all_configs_with_warnings(diag, cfg)

F = S.run_security_review(diag, cfg, configs)
ids = {f.rule_id for f in F}
def has(rule, dev=None):
    return any(f.rule_id == rule and (dev is None or dev in f.devices) for f in F)

print("A. sample LLD findings")
check("single firewalls flagged (perimeter and internal)", has("NET-FW-02", "fw-01") and has("NET-FW-02", "core-fw-01"))
check("internet path bypasses firewall", has("NET-PATH-01"))
check("core-fw-01 single connection (HIGH)", any(f.rule_id == "NET-SPOF-01" and "core-fw-01" in f.devices and f.severity == "HIGH" for f in F))
check("wan-rtr-01 single internal connection", has("NET-SPOF-01", "wan-rtr-01"))
check("fw-01 single internal connection", has("NET-SPOF-01", "fw-01"))
check("dist-sw-01 not dual-homed to core", has("NET-REDUND-01", "dist-sw-01"))
check("dual-homed access switches NOT flagged", not has("NET-REDUND-01", "access-sw-01"))
check("two core switches NOT flagged as single", not has("NET-REDUND-02"))
check("SNMPv2c flagged with community note", any(f.rule_id == "CFG-SNMP-01" and "public" in f.detail for f in F))
check("access switches lack port security / dot1x / bpduguard",
      has("CFG-ACCESS-01", "access-sw-01") and has("CFG-ACCESS-02") and has("CFG-ACCESS-03"))
check("not_stated basis on absence findings", all(f.basis == "not_stated" for f in F if f.rule_id.startswith("CFG-ACCESS-0") and f.rule_id != "CFG-ACCESS-04"))
check("guest VLAN verify finding", has("CFG-VLAN-02"))
check("management VLAN present -> no CFG-VLAN-01", not has("CFG-VLAN-01"))
check("trunk without VLAN list", has("CFG-TRUNK-01", "dist-sw-01"))
check("HSRP no-auth finding", has("CFG-L3-01", "dist-sw-02"))
check("routing auth note for bgp", has("CFG-ROUTE-01"))
check("baseline hardening missing", has("CFG-MGMT-01"))
check("draft not deployable info", has("CFG-DEPLOY-01"))
check("posture is RED", S.risk_rating(F) == "RED")

print("B. determinism and ordering")
F2 = S.run_security_review(diag, cfg, configs)
check("same input -> identical output", F == F2)
rank = [S._SEV_RANK[f.severity] for f in F]
check("sorted most severe first", rank == sorted(rank))

print("C. edge cases")
check("empty design does not crash", S.run_security_review(ds.NetworkDiagramSpec(devices=[], links=[])) == [])
none_fw = ds.NetworkDiagramSpec(devices=[D("isp", "cloud", "edge"), D("sw-1", "switch", "core")], links=[L("isp", "sw-1")])
check("no firewall flagged", any(f.rule_id == "NET-FW-01" for f in S.run_security_review(none_fw)))
good = ds.NetworkDiagramSpec(
    devices=[D("isp", "cloud", "edge"), D("fw-a", "firewall", "edge"), D("fw-b", "firewall", "edge"),
             D("core-a", "switch", "core"), D("core-b", "switch", "core")],
    links=[L("isp", "fw-a"), L("isp", "fw-b"), L("fw-a", "core-a"), L("fw-a", "core-b"),
           L("fw-b", "core-a"), L("fw-b", "core-b"), L("core-a", "core-b")])
G = S.run_security_review(good)
check("well-formed redundant design: no firewall/path/SPOF findings",
      not any(f.rule_id in ("NET-FW-01", "NET-FW-02", "NET-PATH-01", "NET-SPOF-01", "NET-REDUND-02") for f in G), [f.rule_id for f in G])
check("posture GREEN when nothing found", S.risk_rating(G) == "GREEN")
check("no config spec given: topology rules still run", any(f.rule_id == "NET-FW-02" for f in S.run_security_review(diag)))

class Boom:                          # rule failures must be visible, not fatal
    devices = property(lambda s: (_ for _ in ()).throw(RuntimeError("x")))
    links = []
try:
    S.run_security_review(Boom()); check("bad input surfaces an error", False)
except Exception:
    check("bad input surfaces an error (caller sees it)", True)
orig = S.RULES[0]
def broken(ctx): raise ValueError("boom")
S.RULES[0] = broken
H = S.run_security_review(diag, cfg, configs)
S.RULES[0] = orig
check("a crashing rule becomes a visible INFO finding", any(f.rule_id == "SYS-RULE-ERR" for f in H) and len(H) > 5)

print("D. markdown output")
md = S.to_markdown(F)
check("markdown has posture, table and limits note", "Overall security posture: RED" in md and "| ID | Severity" in md and "not in the structured data" in md)
check("one table row per finding", sum(1 for l in md.split("\n") if l.startswith("| ") and not l.startswith("| ID")) == len(F))
check("not-stated marker shown", "not stated in LLD" in md)
check("all output ASCII", md.isascii())

print("E. topology section and wording")
tm = S.topology_markdown(diag)
check("topology lists every device", all(d.id in tm for d in diag.devices) and f"{len(diag.devices)} devices, {len(diag.links)} links" in tm)
check("topology shows NONE for an unlinked device",
      "NONE" in S.topology_markdown(ds.NetworkDiagramSpec(devices=[D("a-1", "switch", "core")], links=[])))
iso = ds.NetworkDiagramSpec(devices=[D("fw-9", "firewall", "edge"), D("sw-9", "switch", "core")], links=[])
Fi = S.run_security_review(iso)
check("zero connections is worded as 'no internal connection'", any("no internal connection" in f.title for f in Fi if f.rule_id == "NET-SPOF-01"))
check("topology markdown is ASCII", tm.isascii())

print("F. extraction coverage (real LLD vs the topology the local model actually produced)")
LLD = open(os.path.join(HERE, "head_office_lld.md")).read()
got_ids = ["access-sw-01","access-sw-02","access-sw-03","access-sw-04","core-sw-01","core-sw-02",
           "dist-sw-01","dist-sw-02","fw-01","wan-rtr-01"]
bad = ds.NetworkDiagramSpec(devices=[D(i, "switch", "core") for i in got_ids], links=[L("core-sw-01", "dist-sw-01")])
Fc = S.run_security_review(bad, lld_text=LLD)
cov = [f for f in Fc if f.rule_id == "EXT-COV-01"]
check("coverage finding fires on the incomplete extraction", len(cov) == 1)
check("names exactly the dropped devices", cov and all(n in cov[0].detail for n in ("core-fw-01", "isp-a", "isp-b")))
check("no false names (prose like north-south / Low-Level ignored)",
      cov and "north" not in cov[0].detail and "low-level" not in cov[0].detail and "east" not in cov[0].detail)
check("full topology -> no coverage finding", not any(f.rule_id == "EXT-COV-01" for f in S.run_security_review(diag, lld_text=LLD)))
check("no LLD text given -> rule silent", not any(f.rule_id == "EXT-COV-01" for f in S.run_security_review(bad)))
check("banner shown in markdown when coverage fails", "topology extraction looks incomplete" in S.to_markdown(Fc))
check("no banner when coverage ok", "extraction looks incomplete" not in S.to_markdown(F))
check("matching is case-insensitive", not any(f.rule_id == "EXT-COV-01" for f in S.run_security_review(
      ds.NetworkDiagramSpec(devices=[D("core-sw-01", "switch", "core")], links=[]), lld_text="CORE-SW-01 is the core.")))

print("G. firewall HA-peer logic (uses links, not tier labels)")
mix = ds.NetworkDiagramSpec(
    devices=[D("fw-01", "firewall", "edge"), D("core-fw-01", "firewall", "edge"), D("core-sw-01", "switch", "core"),
             D("dist-sw-01", "switch", "distribution"), D("dist-sw-02", "switch", "distribution")],
    links=[L("fw-01", "core-sw-01"), L("fw-01", "dist-sw-01"), L("fw-01", "dist-sw-02"), L("core-fw-01", "dist-sw-01")])
Fm = S.run_security_review(mix)
check("two firewalls mis-tagged with the same tier are still both flagged as single",
      {d for f in Fm if f.rule_id == "NET-FW-02" for d in f.devices} == {"fw-01", "core-fw-01"})
pair_linked = ds.NetworkDiagramSpec(devices=[D("fw-a", "firewall", "edge"), D("fw-b", "firewall", "edge"), D("sw", "switch", "core")],
                                    links=[L("fw-a", "fw-b"), L("fw-a", "sw")])
check("directly linked firewalls count as an HA pair", not any(f.rule_id == "NET-FW-02" for f in S.run_security_review(pair_linked)))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
