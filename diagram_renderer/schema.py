"""
schema.py — the intermediate data contract for the LLD renderer.

This is the ONLY thing the LLM has to get right. Everything downstream
(layout, XML, file writing) is deterministic Python and never needs the model.
"""

from pydantic import BaseModel, field_validator
from typing import Literal

DeviceType = Literal["router", "switch", "firewall", "server", "cloud", "vlan"]
Tier = Literal["core", "distribution", "access", "edge"]


class Device(BaseModel):
    id: str          # short, stable, unique — e.g. "core-sw-1"
    label: str       # human-readable — e.g. "Core Switch 1"
    type: DeviceType
    tier: Tier

    @field_validator("id")
    @classmethod
    def id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError(f"device id '{v}' must not contain spaces — use hyphens")
        return v


class Link(BaseModel):
    source: str
    target: str
    label: str = ""


class NetworkDiagramSpec(BaseModel):
    devices: list[Device]
    links: list[Link]

    def device_ids(self) -> set[str]:
        return {d.id for d in self.devices}
