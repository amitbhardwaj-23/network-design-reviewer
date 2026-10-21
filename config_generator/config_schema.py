"""
config_schema.py — the config-relevant data contract, layered on top of the
diagram_renderer's NetworkDiagramSpec (devices/links/tiers).

The LLM's job here is small and bounded, same philosophy as the diagram
renderer: extract per-device config PARAMETERS (VLANs, IPs, routing,
security settings) as structured JSON. It never writes actual config syntax —
that's render.py's job, deterministically, so output is always syntactically
valid regardless of model quality.

CHANGE (interface-level fidelity): interface_name and vlan allow-list fidelity
depend entirely on what the LLD actually states. interface_name is now
Optional[str] — None means "the LLD didn't specify a port/interface name,"
not "make one up." The interface_stated flag records this explicitly so
render.py can apply a clearly-marked placeholder and emit a warning, the same
auto-repair-with-warning pattern already used in diagram_renderer/validate.py
for undeclared devices. Nothing downstream should treat interface_name as
real unless interface_stated is True.

CHANGE (security hardening): every string that render.py writes into device
config is validated here against a strict allowlist (see config_sanitize.py).
The model's output is untrusted input: a newline inside a "description" would
otherwise become a new CLI command. Validation FAILS (it does not strip or
repair), so the pipeline's existing retry loop gets one more chance and then
stops. Numeric fields are range-checked (VLAN 1-4094, HSRP priority 0-255, ...).
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Literal, Optional

from config_sanitize import (
    check_free_text,
    check_int_range,
    check_interface_ip,
    check_interface_name,
    check_ipv4_host,
    check_name,
    check_subnet_chars,
    check_vlan_id,
)

RoutingProtocol = Literal["static", "ospf", "eigrp", "bgp", "none"]


class VlanDef(BaseModel):
    vlan_id: int
    name: str
    subnet: Optional[str] = None       # e.g. "10.0.20.0/23" — None if not stated in the LLD
    gateway: Optional[str] = None      # e.g. "10.0.20.1"

    @field_validator("vlan_id")
    @classmethod
    def _vlan_id(cls, v):
        return check_vlan_id(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return check_free_text(v, "VLAN name", max_len=64)

    @field_validator("subnet")
    @classmethod
    def _subnet(cls, v):
        return None if v is None else check_subnet_chars(v)

    @field_validator("gateway")
    @classmethod
    def _gateway(cls, v):
        return None if v is None else check_ipv4_host(v, "gateway")


class InterfaceConfig(BaseModel):
    device_id: str                     # must match a device id from NetworkDiagramSpec
    interface_name: Optional[str] = None   # e.g. "GigabitEthernet1/0/1" — None if the LLD did NOT state it
    interface_stated: bool = True          # derived, not trusted from input — see validator below
    mode: Literal["access", "trunk", "routed"]
    vlan_ids: list[int] = []           # access: single vlan; trunk: allowed vlans
    ip_address: Optional[str] = None   # only for routed/L3 interfaces
    description: str = ""

    @field_validator("device_id")
    @classmethod
    def _device_id(cls, v):
        return check_name(v, "device_id")

    @field_validator("interface_name")
    @classmethod
    def _interface_name(cls, v):
        return None if v is None else check_interface_name(v)

    @field_validator("vlan_ids")
    @classmethod
    def _vlan_ids(cls, v):
        if len(v) > 4094:
            raise ValueError("too many VLAN ids")
        return [check_vlan_id(x) for x in v]

    @field_validator("ip_address")
    @classmethod
    def _ip_address(cls, v):
        return None if v is None else check_interface_ip(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v):
        return check_free_text(v, "description", max_len=200)

    @model_validator(mode="after")
    def _derive_interface_stated(self) -> "InterfaceConfig":
        # Never trust an upstream-set True/False for this flag — derive it from
        # interface_name itself so it can't drift out of sync (e.g. a caller or
        # a slightly malformed model response setting interface_stated=True
        # while interface_name is null, which would defeat the whole point).
        object.__setattr__(self, "interface_stated", self.interface_name is not None)
        return self


class DeviceSecurityConfig(BaseModel):
    device_id: str
    port_security: bool = False
    port_security_max_mac: Optional[int] = None
    portfast_bpduguard: bool = False
    dot1x: bool = False
    snmp_version: Literal["v2c", "v3", "none"] = "none"
    hsrp_priority: Optional[int] = None   # only meaningful on routed VLAN interfaces

    @field_validator("device_id")
    @classmethod
    def _device_id(cls, v):
        return check_name(v, "device_id")

    @field_validator("port_security_max_mac")
    @classmethod
    def _max_mac(cls, v):
        return None if v is None else check_int_range(v, 1, 1024, "port_security_max_mac")

    @field_validator("hsrp_priority")
    @classmethod
    def _hsrp(cls, v):
        return None if v is None else check_int_range(v, 0, 255, "hsrp_priority")


class ConfigSpec(BaseModel):
    vlans: list[VlanDef] = []
    interfaces: list[InterfaceConfig] = []
    security: list[DeviceSecurityConfig] = []
    routing_protocol: RoutingProtocol = "static"
    default_route_next_hop: Optional[str] = None   # device id, e.g. "fw-01"

    @field_validator("default_route_next_hop")
    @classmethod
    def _next_hop(cls, v):
        return None if v is None else check_name(v, "default_route_next_hop")
