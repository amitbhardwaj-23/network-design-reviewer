"""
config_validate.py — deterministic validation for the config extraction.
Same philosophy as diagram_renderer/validate.py: auto-repair rather than
hard-fail when the model references a device_id that isn't in the known set,
since we've proven this is a real, recurring small-model failure mode.

Also strips RFC 5737 documentation-only addresses (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24) on sight — these are never legitimate in a real design, and their
appearance means the model copied a prompt example rather than extracting real
data. This is a deterministic backstop, independent of how well the prompt itself
prevents it.
"""

import ipaddress
import json
import re
from pydantic import ValidationError

from config_schema import ConfigSpec

_DOC_ONLY_NETWORKS = [
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
]

_PLACEHOLDER_MARKERS = re.compile(
    r"\bxxx\b|\bexample\b|\breplace\b|\bplaceholder\b|\btbd\b|\btodo\b",
    re.IGNORECASE,
)


def _is_doc_only_address(addr_or_cidr: str | None) -> bool:
    if not addr_or_cidr:
        return False
    try:
        ip_str = addr_or_cidr.split("/")[0]
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in _DOC_ONLY_NETWORKS)
    except ValueError:
        return False


def _looks_like_placeholder(*texts: str | None) -> bool:
    """Catches copied prompt-example text on sight — e.g. 'VlanXXX', 'Example SVI',
    'replace entirely with real extracted data' — regardless of exactly which words
    a given model run happens to echo. Broader and more reliable than trying to word
    a prompt so no plausible-looking value survives."""
    for t in texts:
        if t and _PLACEHOLDER_MARKERS.search(t):
            return True
    return False


def validate_config_spec(
    raw_llm_output: str, known_device_ids: set[str]
) -> tuple[ConfigSpec | None, str | None, list[str]]:
    """Returns (spec, fatal_error, warnings)."""
    warnings: list[str] = []
    cleaned = raw_llm_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return None, f"Output was not valid JSON: {e}", warnings

    try:
        spec = ConfigSpec(**data)
    except ValidationError as e:
        return None, f"JSON did not match the required schema: {e}", warnings

    # Backstop 1: strip any RFC 5737 documentation-only addressing — its presence
    # means the model copied the prompt's example rather than extracting real data.
    kept_vlans = []
    for v in spec.vlans:
        if _is_doc_only_address(v.subnet) or _is_doc_only_address(v.gateway):
            warnings.append(
                f"VLAN {v.vlan_id} ('{v.name}') used a documentation-only address "
                f"(subnet={v.subnet}, gateway={v.gateway}) — this looks like a copied "
                f"prompt example, not real data. Subnet/gateway cleared; verify the LLD "
                f"actually specifies this VLAN."
            )
            v.subnet = None
            v.gateway = None
        kept_vlans.append(v)
    spec.vlans = kept_vlans

    for iface in spec.interfaces:
        if _is_doc_only_address(iface.ip_address):
            warnings.append(
                f"Interface {iface.interface_name} on '{iface.device_id}' had a "
                f"documentation-only IP ({iface.ip_address}) — looks like a copied "
                f"prompt example. IP cleared; verify against the actual LLD."
            )
            iface.ip_address = None

    # Backstop 2: drop any VLAN or interface whose text still contains a literal
    # placeholder marker (e.g. "VlanXXX", "Example SVI", "replace entirely...") —
    # broader net than the address check above, catches copied example STRUCTURE
    # even when no address is involved.
    kept_vlans2 = []
    for v in spec.vlans:
        if _looks_like_placeholder(v.name):
            warnings.append(
                f"VLAN {v.vlan_id} ('{v.name}') looks like copied prompt-example text, "
                f"not real data — dropped entirely."
            )
        else:
            kept_vlans2.append(v)
    spec.vlans = kept_vlans2

    kept_interfaces_pre = []
    for iface in spec.interfaces:
        if _looks_like_placeholder(iface.interface_name, iface.description):
            warnings.append(
                f"Interface '{iface.interface_name}' on '{iface.device_id}' looks like "
                f"copied prompt-example text, not real data — dropped entirely."
            )
        else:
            kept_interfaces_pre.append(iface)
    spec.interfaces = kept_interfaces_pre

    # Drop (don't fail on) interfaces/security entries for unknown device_ids —
    # these are additive detail on top of an already-validated topology, so a
    # bad device_id here should degrade gracefully, not block the whole thing.
    kept_interfaces = []
    for iface in spec.interfaces:
        if iface.device_id not in known_device_ids:
            warnings.append(
                f"Interface config for unknown device '{iface.device_id}' was dropped "
                f"(not present in the topology extracted earlier)."
            )
        else:
            kept_interfaces.append(iface)
    spec.interfaces = kept_interfaces

    kept_security = []
    for sec in spec.security:
        if sec.device_id not in known_device_ids:
            warnings.append(
                f"Security config for unknown device '{sec.device_id}' was dropped "
                f"(not present in the topology extracted earlier)."
            )
        else:
            kept_security.append(sec)
    spec.security = kept_security

    if spec.default_route_next_hop and spec.default_route_next_hop not in known_device_ids:
        warnings.append(
            f"Default route next-hop '{spec.default_route_next_hop}' is not a known device — cleared."
        )
        spec.default_route_next_hop = None

    return spec, None, warnings