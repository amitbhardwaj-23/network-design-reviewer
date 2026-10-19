"""
render.py — turns a validated NetworkDiagramSpec into draw.io XML.

Pure Python. No LLM calls happen here.
"""

from schema import NetworkDiagramSpec
from datetime import datetime, timezone

TIER_Y = {"edge": 40, "core": 160, "distribution": 300, "access": 440}

STYLE = {
    "router":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=12;",
    "switch":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=12;",
    "firewall": "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=12;",
    "server":   "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=12;",
    "cloud":    "ellipse;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=12;",
    "vlan":     "rounded=1;dashed=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=12;",
}

DEVICE_W, DEVICE_H = 140, 60
COL_SPACING = 200


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def render_xml(spec: NetworkDiagramSpec, diagram_name: str = "Network LLD") -> str:
    cells: list[str] = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

    tier_counts: dict[str, int] = {}
    y_lookup: dict[str, int] = {}
    for d in spec.devices:
        col = tier_counts.get(d.tier, 0)
        tier_counts[d.tier] = col + 1
        x = 40 + col * COL_SPACING
        y = TIER_Y.get(d.tier, 40)
        y_lookup[d.id] = y
        style = STYLE[d.type]
        cells.append(
            f'<mxCell id="{_esc(d.id)}" value="{_esc(d.label)}" style="{style}" '
            f'vertex="1" parent="1">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{DEVICE_W}" height="{DEVICE_H}" as="geometry"/>\n'
            f'</mxCell>'
        )

    for i, l in enumerate(spec.links):
        source_y = y_lookup.get(l.source, 0)
        target_y = y_lookup.get(l.target, 0)
        if source_y <= target_y:
            exit_pt, entry_pt = "exitX=0.5;exitY=1;", "entryX=0.5;entryY=0;"
        else:
            exit_pt, entry_pt = "exitX=0.5;exitY=0;", "entryX=0.5;entryY=1;"
        conn_style = f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;jettySize=auto;{exit_pt}exitDx=0;exitDy=0;{entry_pt}entryDx=0;entryDy=0;"
        cells.append(
            f'<mxCell id="edge-{i}" value="{_esc(l.label)}" '
            f'style="{conn_style}" '
            f'edge="1" parent="1" source="{_esc(l.source)}" target="{_esc(l.target)}">\n'
            f'  <mxGeometry relative="1" as="geometry"/>\n'
            f'</mxCell>'
        )

    body = "\n".join(cells)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    return f'''<mxfile host="network-design-copilot" modified="{timestamp}" version="24.0.0">
<diagram id="lld-diagram" name="{_esc(diagram_name)}">
<mxGraphModel dx="1024" dy="768" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
<root>
{body}
</root>
</mxGraphModel>
</diagram>
</mxfile>'''
