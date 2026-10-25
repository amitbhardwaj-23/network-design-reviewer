"""
config_render.py — turns a validated ConfigSpec + the topology's
NetworkDiagramSpec into Cisco-IOS-style device configuration text.

Pure Python string templating. No LLM calls happen here — same principle as
diagram_renderer/render.py: the model's job was just to produce checkable
structured data; assembling the actual syntax is deterministic and can't
produce invalid output.

CHANGE (interface-level fidelity): interface_name can now be None when the
LLD didn't state a port/interface identifier (see config_schema.py). This
file is the one place that turns that gap into something renderable — it
never invents a name silently. When interface_stated is False, a clearly
marked placeholder (interfaceUNSPECIFIED-N) is assigned, a "! WARNING" line
is written directly into the config text immediately above that interface
stanza, and the same warning is added to a collected warnings list — same
"visible, not buried" pattern diagram_renderer/validate.py already uses for
auto-repaired devices.
"""

from config_schema import ConfigSpec
from config_sanitize import ConfigSecurityError, assert_safe_config, check_name, comment_text
from datetime import datetime, timezone

# SECURITY NOTE: every string below that ends up in the config text is either
#   (a) a fixed literal in this file,
#   (b) a field already validated by config_schema.py / config_sanitize.py, or
#   (c) passed through check_name() / comment_text() here.
# render_device_config() then runs assert_safe_config() over the finished text, which
# does not trust (a)-(c): any line outside the generator's own allowlist fails the
# device with ConfigSecurityError. Generated text is also ASCII-only on purpose
# (non-ASCII in a CLI paste can be mangled or rejected by the device).


def _resolve_interface_name(iface, device_id: str, device_label: str,
                             counters: dict, warnings: list) -> tuple[str, bool]:
    """Returns (name_to_render, was_placeholder). Never trusts a bare
    iface.interface_name truthiness check alone — goes by interface_stated,
    which config_schema.py derives deterministically from whether a name was
    actually given."""
    if iface.interface_stated and iface.interface_name:
        return iface.interface_name, False

    counters[device_id] = counters.get(device_id, 0) + 1
    placeholder = f"interfaceUNSPECIFIED-{counters[device_id]}"
    warnings.append(
        f"Device '{device_id}' ({device_label}): no interface/port name was stated in the "
        f"LLD for a {iface.mode} port (vlan_ids={iface.vlan_ids or 'n/a'}) — auto-assigned "
        f"placeholder '{placeholder}'. Verify the real port before deployment."
    )
    return placeholder, True


def _vlan_block(vlans) -> str:
    lines = []
    for v in vlans:
        lines.append(f"vlan {v.vlan_id}")
        lines.append(f" name {v.name}")
    return "\n".join(lines)


def _svi_block(device_id: str, device_label: str, spec: ConfigSpec,
               counters: dict, warnings: list) -> str:
    lines = []
    for iface in spec.interfaces:
        if iface.device_id != device_id or iface.mode != "routed":
            continue
        name, is_placeholder = _resolve_interface_name(iface, device_id, device_label, counters, warnings)
        if is_placeholder:
            lines.append(f"! WARNING: interface name not stated in LLD - auto-assigned placeholder. Verify before deployment.")
        lines.append(f"interface {name}")
        if iface.description:
            lines.append(f" description {iface.description}")
        if iface.ip_address:
            lines.append(f" ip address {iface.ip_address}")
        sec = next((s for s in spec.security if s.device_id == device_id), None)
        if sec and sec.hsrp_priority is not None and iface.vlan_ids:
            vlan_def = next((v for v in spec.vlans if v.vlan_id == iface.vlan_ids[0]), None)
            if vlan_def and vlan_def.gateway:
                lines.append(f" standby 1 ip {vlan_def.gateway}")
                lines.append(f" standby 1 priority {sec.hsrp_priority}")
                lines.append(" standby 1 preempt")
        lines.append(" no shutdown")
        lines.append("!")
    return "\n".join(lines)


def _access_interface_block(device_id: str, device_label: str, spec: ConfigSpec,
                             counters: dict, warnings: list) -> str:
    lines = []
    sec = next((s for s in spec.security if s.device_id == device_id), None)
    for iface in spec.interfaces:
        if iface.device_id != device_id or iface.mode == "routed":
            continue
        name, is_placeholder = _resolve_interface_name(iface, device_id, device_label, counters, warnings)
        if is_placeholder:
            lines.append(f"! WARNING: interface name not stated in LLD - auto-assigned placeholder. Verify before deployment.")
        lines.append(f"interface {name}")
        if iface.description:
            lines.append(f" description {iface.description}")
        if iface.mode == "access":
            if iface.vlan_ids:
                lines.append(f" switchport access vlan {iface.vlan_ids[0]}")
            lines.append(" switchport mode access")
            if sec and sec.portfast_bpduguard:
                lines.append(" spanning-tree portfast")
                lines.append(" spanning-tree bpduguard enable")
            if sec and sec.port_security:
                lines.append(" switchport port-security")
                if sec.port_security_max_mac:
                    lines.append(f" switchport port-security maximum {sec.port_security_max_mac}")
                lines.append(" switchport port-security violation restrict")
            if sec and sec.dot1x:
                lines.append(" authentication port-control auto")
                lines.append(" dot1x pae authenticator")
        elif iface.mode == "trunk":
            lines.append(" switchport mode trunk")
            if iface.vlan_ids:
                allowed = ",".join(str(v) for v in iface.vlan_ids)
                lines.append(f" switchport trunk allowed vlan {allowed}")
        lines.append(" no shutdown")
        lines.append("!")
    return "\n".join(lines)


def _snmp_block(device_id: str, spec: ConfigSpec) -> str:
    sec = next((s for s in spec.security if s.device_id == device_id), None)
    if not sec or sec.snmp_version == "none":
        return ""
    if sec.snmp_version == "v2c":
        return "! WARNING: SNMPv2c requested - insecure, not recommended. Consider SNMPv3.\nsnmp-server community public RO"
    return "snmp-server group ARGUS-SNMPv3 v3 priv\nsnmp-server user argus-admin ARGUS-SNMPv3 v3 auth sha AUTH_PASSWORD priv aes 128 PRIV_PASSWORD"


def _routing_block(device_id: str, spec: ConfigSpec, topology_devices: dict) -> str:
    if spec.routing_protocol != "static" or not spec.default_route_next_hop:
        return ""
    # only emit a default route on devices that actually route (core/distribution tier, or explicitly routed interfaces)
    tier = topology_devices.get(device_id, {}).get("tier")
    if tier not in ("core", "distribution"):
        return ""
    next_hop_id = check_name(spec.default_route_next_hop, "default_route_next_hop")
    return f"! Default route toward {next_hop_id} - replace with actual next-hop IP\nip route 0.0.0.0 0.0.0.0 <{next_hop_id}-ip>"


def render_device_config(device_id: str, device_label: str, spec: ConfigSpec,
                          topology_devices: dict, counters: dict, warnings: list) -> str:
    """Renders one device's full config block as text.
    counters/warnings are shared across the whole render_all_configs() call so
    placeholder numbering is unique per device and every warning is collected
    in one place."""
    # hostname is rendered as a live command: reject anything that is not a plain identifier.
    try:
        device_id = check_name(device_id, "device_id")
    except ValueError as e:
        raise ConfigSecurityError(f"Refusing to render config: {e}") from None

    # the label only appears inside a '!' comment: flatten it to one line of printable ASCII
    # (a newline here would otherwise start a brand-new, live command).
    safe_label = comment_text(device_label) or device_id
    if safe_label != device_label:
        warnings.append(
            f"Device '{device_id}': label contained characters not allowed in config comments "
            f"(newlines, control or non-ASCII characters) - sanitized to '{safe_label}'."
        )
    device_label = safe_label

    sections = [
        f"! ==========================================================",
        f"! Configuration for {device_label} ({device_id})",
        f"! Generated by ARGUS Config Generator - review before deployment",
        f"! ==========================================================",
        f"hostname {device_id}",
        "!",
    ]

    vlan_block = _vlan_block(spec.vlans)
    if vlan_block and any(iface.device_id == device_id and iface.mode == "routed" for iface in spec.interfaces):
        sections.append(vlan_block)
        sections.append("!")

    svi = _svi_block(device_id, device_label, spec, counters, warnings)
    if svi:
        sections.append(svi)

    access_ifaces = _access_interface_block(device_id, device_label, spec, counters, warnings)
    if access_ifaces:
        sections.append(access_ifaces)

    routing = _routing_block(device_id, spec, topology_devices)
    if routing:
        sections.append(routing)
        sections.append("!")

    snmp = _snmp_block(device_id, spec)
    if snmp:
        sections.append(snmp)
        sections.append("!")

    sections.append("end")
    text = "\n".join(sections)

    # Last gate: independent of every check above. Raises ConfigSecurityError on any line
    # the generator itself could not have produced. Deliberately NOT auto-repaired.
    assert_safe_config(text, device_id)
    return text


def render_all_configs_with_warnings(diagram_spec, config_spec: ConfigSpec) -> tuple[dict[str, str], list[str]]:
    """Same as render_all_configs(), but also returns the collected list of
    auto-repair warnings (placeholder interface names assigned). Prefer this
    entry point in new code so warnings aren't only buried in config-file
    comments."""
    topology_devices = {d.id: {"tier": d.tier, "type": d.type, "label": d.label} for d in diagram_spec.devices}
    counters: dict = {}
    warnings: list = []
    configs = {}
    for device in diagram_spec.devices:
        if getattr(device, "type", None) == "cloud":
            continue        # ISPs / cloud are not devices we configure
        configs[device.id] = render_device_config(
            device.id, device.label, config_spec, topology_devices, counters, warnings
        )
    return configs, warnings


def render_all_configs(diagram_spec, config_spec: ConfigSpec) -> dict[str, str]:
    """diagram_spec is the NetworkDiagramSpec from diagram_renderer.schema.
    Returns {device_id: config_text} for every device in the topology.

    Kept for backward compatibility with existing callers (app.py,
    test_config_pipeline.py) — the return shape is unchanged. Any auto-repair
    warnings are still visible as "! WARNING" comment lines inside the
    returned config text itself, even though this entry point discards the
    separate warnings list. New code should call
    render_all_configs_with_warnings() instead to get the list explicitly."""
    configs, _warnings = render_all_configs_with_warnings(diagram_spec, config_spec)
    return configs


def write_configs_to_dir(configs: dict[str, str], output_dir: str = "outputs/configs") -> list[str]:
    import os
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for device_id, text in configs.items():
        path = os.path.join(output_dir, f"{device_id}.cfg")
        with open(path, "w") as f:
            f.write(text)
        paths.append(path)
    return paths
