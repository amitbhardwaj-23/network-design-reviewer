"""
config_provenance.py - "never invent" enforced in code, not just in the prompt.

After the model extracts config parameters, every concrete value must be traceable to the LLD text:
  * an interface IP address must appear in the text            -> otherwise the IP is cleared
  * an interface name must appear (or its slot numbers, so "Gi0/1" may be expanded to
    "GigabitEthernet0/1"; "VlanNN" is allowed when VLAN NN appears)   -> otherwise it is cleared, and the
    renderer assigns its visible placeholder + warning as usual
  * VLAN ids, gateways and subnets must appear                 -> VLAN dropped / gateway or subnet cleared
  * HSRP priority and port-security MAC limit must appear NEAR their keyword -> otherwise cleared
Everything cleared is reported as a warning. Nothing is invented or repaired; values are only removed.
Limit: text matching cannot understand negation or paraphrase ("not configured"); it only stops values that
have no basis in the text at all.
"""
import ipaddress
import re


def _num_in(text: str, n) -> bool:
    return re.search(rf"(?<![0-9]){re.escape(str(n))}(?![0-9])", text) is not None


def _num_near(text: str, n, keywords, window: int = 60) -> bool:
    """Small numbers (2, 100) appear somewhere in almost any document, so require the number to sit close
    to a keyword that gives it meaning (e.g. 'priority' for HSRP, 'mac'/'port-security' for the MAC limit)."""
    tl = text.lower()
    for m in re.finditer(rf"(?<![0-9]){re.escape(str(n))}(?![0-9])", text):
        around = tl[max(0, m.start() - window): m.end() + window]
        if any(k in around for k in keywords):
            return True
    return False


def _ip_in(text: str, value: str) -> bool:
    addr = re.split(r"[/ ]", value.strip())[0]
    return re.search(rf"(?<![0-9.]){re.escape(addr)}(?![0-9])", text) is not None


def _iface_ok(text_l: str, text: str, name: str) -> bool:
    if name.lower() in text_l:
        return True
    m = re.fullmatch(r"(?i)vlan(\d+)", name)
    if m:
        return _num_in(text, m.group(1))
    slots = re.findall(r"\d+(?:/\d+)+", name)
    return bool(slots) and all(s in text for s in slots)


def drop_unsupported_values(spec, lld_text: str):
    """Returns (new_spec, warnings). Does not mutate `spec`."""
    text, text_l = lld_text or "", (lld_text or "").lower()
    warnings = []

    vlans = []
    for v in spec.vlans:
        if not _num_in(text, v.vlan_id):
            warnings.append(f"VLAN {v.vlan_id} does not appear in the LLD text - dropped.")
            continue
        upd = {}
        if v.gateway and not _ip_in(text, v.gateway):
            warnings.append(f"VLAN {v.vlan_id}: gateway {v.gateway} does not appear in the LLD text - cleared.")
            upd["gateway"] = None
        if v.subnet and v.subnet not in text:
            warnings.append(f"VLAN {v.vlan_id}: subnet {v.subnet} does not appear in the LLD text - cleared.")
            upd["subnet"] = None
        vlans.append(v.model_copy(update=upd) if upd else v)

    ifaces = []
    for i in spec.interfaces:
        upd = {}
        if i.ip_address and not _ip_in(text, i.ip_address):
            warnings.append(f"{i.device_id}: IP address {i.ip_address} does not appear in the LLD text - cleared.")
            upd["ip_address"] = None
        if i.interface_name and not _iface_ok(text_l, text, i.interface_name):
            warnings.append(f"{i.device_id}: interface name {i.interface_name} does not appear in the LLD text - "
                            "cleared (a placeholder is used instead).")
            upd.update(interface_name=None, interface_stated=False)
        ifaces.append(i.model_copy(update=upd) if upd else i)

    sec = []
    for s in spec.security:
        upd = {}
        if s.hsrp_priority is not None and not _num_near(text, s.hsrp_priority, ("priority", "hsrp")):
            warnings.append(f"{s.device_id}: HSRP priority {s.hsrp_priority} does not appear in the LLD text - cleared.")
            upd["hsrp_priority"] = None
        if s.port_security_max_mac is not None and not _num_near(
                text, s.port_security_max_mac, ("mac", "port-security", "port security", "maximum")):
            warnings.append(f"{s.device_id}: port-security MAC limit {s.port_security_max_mac} does not appear in "
                            "the LLD text - cleared.")
            upd["port_security_max_mac"] = None
        sec.append(s.model_copy(update=upd) if upd else s)

    return spec.model_copy(update={"vlans": vlans, "interfaces": ifaces, "security": sec}), warnings
