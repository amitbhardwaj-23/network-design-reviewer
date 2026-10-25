"""
security_rules.py - deterministic security review of an ARGUS design.

Input  : the NetworkDiagramSpec (devices/links), the ConfigSpec (vlans/interfaces/security/
         routing) and, optionally, the rendered configs {device_id: text}.
Output : a sorted list of Finding objects (no LLM involved, same input -> same output).

Principles (same as the rest of ARGUS):
 * Never invent. A rule only fires on what the extraction actually captured. Where the
   LLD simply does not say something, the finding is labelled basis="not_stated" so the
   reader can tell "LLD says X is off" from "LLD is silent on X".
 * Rules are read-only checks over structured data; they cannot change a design or a config.
 * A rule that crashes becomes a visible INFO finding; it never aborts the review.
 * Every string placed in a finding is built from validated ids, numbers and fixed text.

Limits (stated on purpose): the rules see only what the extractors captured. Firewall policy,
ACLs, routing adjacencies and anything free-text in the LLD are NOT in the structured data,
so e.g. "guest VLAN not isolated" can only be flagged as "verify", not proven.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

try:                                    # reuse the generator's blocker scan when importable
    from config_sanitize import find_blockers as _find_blockers
except Exception:                       # pragma: no cover - fallback keeps the module standalone
    _find_blockers = None

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    detail: str
    recommendation: str
    reference: str
    devices: tuple = ()
    basis: str = "derived"            # "derived" | "not_stated"


@dataclass
class Context:
    devices: dict                      # id -> device object
    links: list
    cfg: object                        # ConfigSpec (or None)
    configs: dict                      # id -> rendered text
    adj: dict = field(default_factory=dict)
    lld_text: str = ""


def _tier(d):  return getattr(d, "tier", None)
def _type(d):  return getattr(d, "type", None)


def _build_context(diagram, cfg, configs, lld_text="") -> Context:
    devices = {d.id: d for d in getattr(diagram, "devices", [])}
    links = list(getattr(diagram, "links", []))
    adj: dict[str, set] = {i: set() for i in devices}
    for l in links:
        if l.source in adj and l.target in adj and l.source != l.target:
            adj[l.source].add(l.target)
            adj[l.target].add(l.source)
    return Context(devices, links, cfg, configs or {}, adj, lld_text or "")


def _ids(items: Iterable[str]) -> tuple:
    return tuple(sorted(set(items)))


def _by(ctx, **kw):
    return [d for d in ctx.devices.values()
            if all(getattr(d, k, None) == v for k, v in kw.items())]


# --------------------------------------------------------------------------- topology rules
def r_no_firewall(ctx):
    clouds = _by(ctx, type="cloud")
    if clouds and not _by(ctx, type="firewall"):
        return [Finding("NET-FW-01", "HIGH", "No firewall in the topology",
                        "The design has internet/cloud-facing connections but no firewall device.",
                        "Place a firewall between the WAN edge and internal networks.",
                        "NIST SP 800-53 SC-7 (boundary protection)", _ids(d.id for d in clouds))]
    return []


def r_single_firewall(ctx):
    """A firewall is 'single' unless another firewall is its HA peer: directly linked to it, or attached to
    exactly the same non-firewall neighbours (a typical dual-attached pair). Tier labels are not used:
    the extractor often tags an internal firewall with the perimeter tier."""
    fws = _by(ctx, type="firewall")
    fw_ids = {d.id for d in fws}
    def nbs(i): return ctx.adj.get(i, set()) - fw_ids
    out = []
    for fw in sorted(fws, key=lambda d: d.id):
        peer = any(o.id != fw.id and (o.id in ctx.adj.get(fw.id, set()) or (nbs(fw.id) and nbs(fw.id) == nbs(o.id)))
                   for o in fws)
        if not peer:
            out.append(Finding("NET-FW-02", "MEDIUM", f"{fw.id} is a single firewall, no high availability",
                               f"No second firewall is linked to {fw.id} or attached to the same devices; its failure "
                               "removes filtering or connectivity for everything behind it.",
                               "Deploy firewalls as an HA pair, or document the accepted risk.",
                               "Availability best practice (no single point of failure)", (fw.id,)))
    return out


def r_firewall_bypass(ctx):
    clouds = [d.id for d in _by(ctx, type="cloud")]
    fws = {d.id for d in _by(ctx, type="firewall")}
    if not clouds or not fws:
        return []
    targets = {d.id for d in ctx.devices.values() if _type(d) in ("switch", "server")}
    out, seen_paths = [], set()
    for start in clouds:
        prev = {start: None}
        q = deque([start])
        while q:
            n = q.popleft()
            for m in sorted(ctx.adj.get(n, ())):
                if m in prev or m in fws:
                    continue
                prev[m] = n
                q.append(m)
        hit = sorted(t for t in targets if t in prev)
        if hit:
            t, path = hit[0], []
            while t is not None:
                path.append(t); t = prev[t]
            path = tuple(reversed(path))
            if path not in seen_paths:
                seen_paths.add(path)
                out.append(Finding(
                    "NET-PATH-01", "HIGH", "A path from the internet reaches internal devices without crossing a firewall",
                    "Topology path: " + " -> ".join(path) + ". If traffic is forced through the firewall by "
                    "routing/policy that is not in the diagram, confirm that in the LLD.",
                    "Make the firewall inline for all north-south traffic, or document the forcing mechanism.",
                    "NIST SP 800-53 SC-7 (boundary protection)", _ids(path)))
    return out


def r_spof_devices(ctx):
    out = []
    for d in ctx.devices.values():
        t, ty = _tier(d), _type(d)
        if ty in ("cloud", "server", "vlan") or t == "access":
            continue
        internal = {n for n in ctx.adj.get(d.id, ()) if _type(ctx.devices[n]) != "cloud"}
        if len(internal) < 2:
            sev = "HIGH" if (ty in ("firewall", "router") or t == "core") else "MEDIUM"
            title = (f"{d.id} has no internal connection in the extracted topology" if not internal
                     else f"{d.id} has a single internal connection")
            note = (" A link may be missing from the extraction - check the topology section." if not internal else "")
            out.append(Finding("NET-SPOF-01", sev, title,
                               f"{d.id} ({ty}, {t}) connects to {len(internal)} internal device(s); "
                               "losing that link or neighbour isolates it." + note,
                               "Add a second path to a different device, or document the accepted risk.",
                               "Availability best practice (no single point of failure)", (d.id,)))
    return out


def r_tier_single_device(ctx):
    out = []
    for tier, sev in (("core", "HIGH"), ("distribution", "MEDIUM")):
        devs = [d for d in _by(ctx, tier=tier) if _type(d) == "switch"]
        if len(devs) == 1:
            out.append(Finding("NET-REDUND-02", sev, f"Only one {tier} switch",
                               f"{devs[0].id} is the only {tier} switch in the design.",
                               f"Add a second {tier} switch (VSS/MLAG/HSRP as appropriate).",
                               "Availability best practice (no single point of failure)", (devs[0].id,)))
    return out


def r_dual_homing(ctx):
    out = []
    for tier, above, sev in (("access", "distribution", "MEDIUM"), ("distribution", "core", "HIGH")):
        upper = {d.id for d in _by(ctx, tier=above) if _type(d) == "switch"}
        if len(upper) < 2:
            continue
        for d in _by(ctx, tier=tier):
            if _type(d) != "switch":
                continue
            up = ctx.adj.get(d.id, set()) & upper
            if len(up) < 2:
                out.append(Finding("NET-REDUND-01", sev, f"{d.id} is not dual-homed to the {above} layer",
                                   f"{d.id} reaches {len(up)} of {len(upper)} {above} switches "
                                   f"({', '.join(sorted(up)) or 'none'}).",
                                   f"Uplink to two different {above} switches.",
                                   "Availability best practice (no single point of failure)", (d.id,)))
    return out


# --------------------------------------------------------------------------- config-spec rules
def _sec(ctx):
    return list(getattr(ctx.cfg, "security", []) or []) if ctx.cfg is not None else []


def _access_ids(ctx):
    return [d.id for d in _by(ctx, tier="access") if _type(d) == "switch"]


def r_snmp(ctx):
    v2 = [s.device_id for s in _sec(ctx) if s.snmp_version == "v2c"]
    if not v2:
        return []
    extra = ""
    if any(re.search(r"snmp-server community (public|private)\b", t) for t in ctx.configs.values()):
        extra = " The generated config uses the well-known community string 'public'."
    return [Finding("CFG-SNMP-01", "HIGH", "SNMPv2c in use",
                    "SNMPv2c sends the community string in clear text and offers no per-user authentication."
                    + extra, "Use SNMPv3 with authPriv and unique credentials; restrict by ACL.",
                    "NIST SP 800-53 SC-8 / IA-5; CIS network device benchmarks", _ids(v2), "derived")]


def _missing_access_flag(ctx, attr):
    flagged = {s.device_id: s for s in _sec(ctx)}
    return [i for i in _access_ids(ctx) if not getattr(flagged.get(i), attr, False)]


def r_port_security(ctx):
    miss = _missing_access_flag(ctx, "port_security")
    return [Finding("CFG-ACCESS-01", "MEDIUM", "Port security not enabled on access switches",
                    "The extracted design does not enable port security on these access switches.",
                    "Enable port security with a small MAC limit and restrict/shutdown violation mode.",
                    "NIST SP 800-53 IA-3 / CM-7", _ids(miss), "not_stated")] if miss else []


def r_dot1x(ctx):
    miss = _missing_access_flag(ctx, "dot1x")
    return [Finding("CFG-ACCESS-02", "MEDIUM", "802.1X / NAC not enabled on access switches",
                    "The extracted design does not enable 802.1X on these access switches.",
                    "Enable 802.1X (or equivalent NAC) on end-device facing ports.",
                    "NIST SP 800-53 IA-3", _ids(miss), "not_stated")] if miss else []


def r_bpduguard(ctx):
    miss = _missing_access_flag(ctx, "portfast_bpduguard")
    return [Finding("CFG-ACCESS-03", "MEDIUM", "BPDU guard not enabled on access switches",
                    "The extracted design does not enable BPDU guard (PortFast alone leaves edge ports open to rogue switches and loops).",
                    "Enable PortFast + BPDU guard on edge ports to prevent rogue switches and loops.",
                    "CIS network device benchmarks (spanning-tree hardening)", _ids(miss), "not_stated")] if miss else []


def r_max_mac(ctx):
    bad = [s.device_id for s in _sec(ctx) if s.port_security and (s.port_security_max_mac or 0) > 5]
    return [Finding("CFG-ACCESS-04", "LOW", "Port-security MAC limit above 5",
                    "A high MAC limit weakens port security as a control.",
                    "Use 1-2 MACs per port unless a phone/PC pair needs more.",
                    "CIS network device benchmarks", _ids(bad))] if bad else []


def _vlans(ctx):
    return list(getattr(ctx.cfg, "vlans", []) or []) if ctx.cfg is not None else []


def r_mgmt_vlan(ctx):
    vl = _vlans(ctx)
    if vl and not any(re.search(r"manage|mgmt|oob", v.name, re.I) for v in vl):
        return [Finding("CFG-VLAN-01", "LOW", "No dedicated management VLAN identified",
                        "None of the extracted VLAN names indicates a management VLAN.",
                        "Place device management on a dedicated VLAN/VRF with restricted access.",
                        "NIST SP 800-53 AC-4 (information flow)", (), "not_stated")]
    return []


def r_guest_vlan(ctx):
    g = [v for v in _vlans(ctx) if re.search(r"guest", v.name, re.I)]
    if not g:
        return []
    return [Finding("CFG-VLAN-02", "MEDIUM", "Guest VLAN present - isolation is not provable from the data",
                    "VLAN " + ", ".join(str(v.vlan_id) for v in g) + " is a guest VLAN. The generated configs "
                    "contain no ACLs or firewall policy, so isolation from internal VLANs is unverified.",
                    "Enforce guest isolation on the firewall (internet-only) and verify with a test.",
                    "NIST SP 800-53 AC-4 / SC-7", ())]


def r_vlan1(ctx):
    ifaces = list(getattr(ctx.cfg, "interfaces", []) or []) if ctx.cfg is not None else []
    bad = [i.device_id for i in ifaces if 1 in (i.vlan_ids or [])]
    return [Finding("CFG-VLAN-03", "LOW", "VLAN 1 used for user or trunk traffic",
                    "VLAN 1 is the default VLAN and carries control-plane traffic.",
                    "Move user traffic to a non-default VLAN and leave VLAN 1 unused.",
                    "CIS network device benchmarks", _ids(bad))] if bad else []


def r_trunks(ctx):
    ifaces = list(getattr(ctx.cfg, "interfaces", []) or []) if ctx.cfg is not None else []
    bad = [i.device_id for i in ifaces if i.mode == "trunk" and not i.vlan_ids]
    return [Finding("CFG-TRUNK-01", "MEDIUM", "Trunk with no allowed-VLAN list",
                    "A trunk without a VLAN list permits all VLANs, including ones that should not traverse it.",
                    "Restrict each trunk to the VLANs it needs (switchport trunk allowed vlan).",
                    "NIST SP 800-53 CM-7 (least functionality)", _ids(bad), "not_stated")] if bad else []


def r_hsrp(ctx):
    bad = [s.device_id for s in _sec(ctx) if s.hsrp_priority is not None]
    return [Finding("CFG-L3-01", "LOW", "HSRP configured without authentication",
                    "The generator does not configure HSRP authentication, so a rogue device on the VLAN can "
                    "become active gateway.",
                    "Add HSRP authentication (MD5/key-chain) and limit who can reach the VLAN.",
                    "CIS network device benchmarks (FHRP)", _ids(bad))] if bad else []


def r_routing_auth(ctx):
    p = getattr(ctx.cfg, "routing_protocol", "none") if ctx.cfg is not None else "none"
    if p in ("ospf", "eigrp", "bgp"):
        return [Finding("CFG-ROUTE-01", "LOW", f"{p.upper()} routing: authentication and filtering not generated",
                        "The generator does not render routing-protocol configuration, so neighbour "
                        "authentication and prefix filters are not covered.",
                        "Use neighbour authentication and prefix/route filters; for BGP add max-prefix limits.",
                        "CIS network device benchmarks (routing protocol security)", ())]
    return []


# --------------------------------------------------------------------------- generated-config rules
_HARDENING = (
    ("SSH version 2", r"^ip ssh version 2$"),
    ("AAA", r"^aaa new-model$"),
    ("remote syslog", r"^logging host "),
    ("NTP", r"^ntp server "),
    ("login banner", r"^banner "),
)


def r_baseline_missing(ctx):
    if not ctx.configs:
        return []
    missing = [name for name, rx in _HARDENING
               if not any(re.search(rx, t, re.M) for t in ctx.configs.values())]
    if not missing:
        return []
    return [Finding("CFG-MGMT-01", "MEDIUM", "Management-plane hardening is not part of the generated configs",
                    "None of the generated configs contain: " + ", ".join(missing) + ". These must be added "
                    "(or applied from a baseline template) before deployment.",
                    "Apply an approved baseline: SSH v2 only, AAA, remote syslog, NTP, banner, no telnet.",
                    "NIST SP 800-53 AU-2/AU-12, IA-2, CM-6", _ids(ctx.configs))]


def r_deployability(ctx):
    if not ctx.configs or _find_blockers is None:
        return []
    per = {}
    for dev, text in ctx.configs.items():
        n = len(_find_blockers(text))
        if n:
            per[dev] = n
    if not per:
        return []
    return [Finding("CFG-DEPLOY-01", "INFO", "Generated configs are review drafts, not deployable",
                    f"{sum(per.values())} unresolved placeholder(s) or insecure default(s) across {len(per)} "
                    "device config(s). They are blocked from the push stage until resolved.",
                    "Resolve placeholders (credentials, next hops, interface names) and review defaults.",
                    "ARGUS push gate (assert_pushable)", _ids(per))]


# --------------------------------------------------------------------------- extraction coverage
# Device-like names in the LLD: hyphenated, ending in digits or a single letter (Core-FW-01, ISP-A).
# "north-south", "Low-Level" and similar prose do not match.
_DEVICE_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-(?:[0-9]+|[A-Za-z])(?![A-Za-z0-9_-])")


def r_extraction_coverage(ctx):
    """Names that appear in the LLD but not in the extracted topology: the extraction dropped them."""
    if not ctx.lld_text:
        return []
    named = {m.group(0).lower() for m in _DEVICE_TOKEN.finditer(ctx.lld_text)}
    known = {i.lower() for i in ctx.devices}
    missing = sorted(named - known)
    if not missing:
        return []
    return [Finding("EXT-COV-01", "MEDIUM", "Devices named in the LLD are missing from the extracted topology",
                    "These names appear in the LLD text but not in the topology the review used: "
                    + ", ".join(missing) + ". Topology findings (single points of failure, redundancy, "
                    "firewall path) may be wrong or missing for the same reason.",
                    "Re-run the extraction or correct the diagram, then re-run the security review.",
                    "ARGUS extraction check", (), "derived")]


RULES: list[Callable] = [
    r_no_firewall, r_single_firewall, r_firewall_bypass, r_spof_devices, r_tier_single_device,
    r_dual_homing, r_extraction_coverage, r_snmp, r_port_security, r_dot1x, r_bpduguard, r_max_mac, r_mgmt_vlan,
    r_guest_vlan, r_vlan1, r_trunks, r_hsrp, r_routing_auth, r_baseline_missing, r_deployability,
]


# --------------------------------------------------------------------------- public API
def run_security_review(diagram, config_spec=None, configs: Optional[dict] = None,
                        lld_text: str = "") -> list[Finding]:
    ctx = _build_context(diagram, config_spec, configs, lld_text)
    findings: list[Finding] = []
    for rule in RULES:
        try:
            findings.extend(rule(ctx))
        except Exception as e:           # a broken rule must be visible, never silent
            findings.append(Finding("SYS-RULE-ERR", "INFO", f"Rule {rule.__name__} could not run",
                                    f"{type(e).__name__}: {str(e)[:120]}", "Report this to the ARGUS maintainer.",
                                    "ARGUS internal"))
    findings.sort(key=lambda f: (_SEV_RANK[f.severity], f.rule_id, f.devices))
    return findings


def topology_markdown(diagram) -> str:
    """What the reviewer actually saw. Findings are only as good as the extraction - compare this to the LLD."""
    devs = list(getattr(diagram, "devices", []))
    links = list(getattr(diagram, "links", []))
    adj: dict = {d.id: set() for d in devs}
    for l in links:
        if l.source in adj and l.target in adj and l.source != l.target:
            adj[l.source].add(l.target); adj[l.target].add(l.source)
    lines = ["## Topology the reviewer saw", "",
             f"{len(devs)} devices, {len(links)} links. Check this against your LLD: a missing device or link "
             "here produces false findings above (and can hide real ones).", "",
             "| Device | Type | Tier | Connected to |", "|---|---|---|---|"]
    for d in sorted(devs, key=lambda x: x.id):
        peers = ", ".join(sorted(adj[d.id])) or "NONE"
        lines.append(f"| {d.id} | {getattr(d, 'type', '-')} | {getattr(d, 'tier', '-')} | {peers} |")
    return "\n".join(lines)


def risk_rating(findings: list[Finding]) -> str:
    """RED: any CRITICAL or 3+ HIGH. AMBER: any HIGH or 3+ MEDIUM. Otherwise GREEN."""
    c = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    if c["CRITICAL"] or c["HIGH"] >= 3:
        return "RED"
    if c["HIGH"] or c["MEDIUM"] >= 3:
        return "AMBER"
    return "GREEN"


def to_markdown(findings: list[Finding]) -> str:
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    lines = ["# Security Review (rule-based)", "",
             f"**Overall security posture: {risk_rating(findings)}**  ",
             " | ".join(f"{s}: {n}" for s, n in counts.items()), ""]
    if any(f.rule_id == "EXT-COV-01" for f in findings):
        lines += ["> **Warning: the topology extraction looks incomplete (see EXT-COV-01). Topology findings "
                  "may include false positives and miss real issues. Verify against your LLD.**", ""]
    lines += [
             "| ID | Severity | Finding | Devices | Recommendation | Reference |",
             "|---|---|---|---|---|---|"]
    for f in findings:
        title = f.title + (" *(not stated in LLD)*" if f.basis == "not_stated" else "")
        lines.append(f"| {f.rule_id} | {f.severity} | {title}: {f.detail} | "
                     f"{', '.join(f.devices) or '-'} | {f.recommendation} | {f.reference} |")
    lines += ["", "*Rules run only on what was extracted from the design. 'Not stated in LLD' means the "
              "design is silent, not that the control is confirmed absent. Firewall policy and ACLs are "
              "not in the structured data and are not assessed.*"]
    return "\n".join(l.replace("\n", " ") if l.startswith("|") else l for l in lines)
