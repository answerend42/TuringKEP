"""图谱聚合、投影与 HTML 渲染。"""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean
from typing import Any

from .records import MentionRecord, TripleRecord
from .schema import DomainSchema


VIS_JS_URL = (
    "https://cdn.jsdelivr.net/npm/vis-network@9.1.6/standalone/umd/vis-network.min.js"
)


def _component_from_center(
    node_ids: set[str], edges: list[dict[str, Any]], center_id: str | None
) -> set[str]:
    if not node_ids:
        return set()
    if center_id is None or center_id not in node_ids:
        return set(node_ids)

    adjacency = {node_id: set() for node_id in node_ids}
    for edge in edges:
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])

    seen = {center_id}
    stack = [center_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen


def _collect_linked_entity_counts(
    linked_mentions: list[MentionRecord],
) -> tuple[dict[str, int], set[str]]:
    mention_counts: dict[str, int] = defaultdict(int)
    linked_entity_ids: set[str] = set()
    for mention in linked_mentions:
        if mention.linked_entity_id:
            mention_counts[mention.linked_entity_id] += 1
            linked_entity_ids.add(mention.linked_entity_id)
    return mention_counts, linked_entity_ids


def _aggregate_edges(triples: list[TripleRecord]) -> list[dict[str, Any]]:
    edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for triple in triples:
        key = (
            triple.subject_entity_id,
            triple.object_entity_id,
            triple.relation_id,
        )
        current = edge_map.setdefault(
            key,
            {
                "from": triple.subject_entity_id,
                "to": triple.object_entity_id,
                "label": triple.relation_label,
                "relation_id": triple.relation_id,
                "count": 0,
                "confidences": [],
                "evidences": [],
                "sources": set(),
            },
        )
        current["count"] += 1
        current["confidences"].append(triple.confidence)
        current["sources"].add(triple.source)
        if len(current["evidences"]) < 3:
            current["evidences"].append(triple.evidence_sentence)

    raw_edges = [
        {
            "from": edge["from"],
            "to": edge["to"],
            "label": edge["label"],
            "relation_id": edge["relation_id"],
            "title": f"source: {'+'.join(sorted(edge['sources']))}<br/>"
            + "<br/>".join(edge["evidences"]),
            "value": edge["count"],
            "avg_confidence": round(mean(edge["confidences"]), 4),
            "source": "+".join(sorted(edge["sources"])),
        }
        for edge in edge_map.values()
    ]
    raw_edges.sort(key=lambda item: (-item["value"], item["label"], item["from"], item["to"]))
    return raw_edges


def _build_nodes(
    schema: DomainSchema,
    node_ids: set[str],
    mention_counts: dict[str, int],
    relation_node_ids: set[str],
) -> list[dict[str, Any]]:
    entity_by_id = schema.entity_by_id
    nodes = []
    for entity_id in sorted(node_ids):
        entity = entity_by_id[entity_id]
        relation_note = (
            "关系图中可见"
            if entity_id in relation_node_ids
            else "当前仅完成实体链接，尚未抽到关系边"
        )
        nodes.append(
            {
                "id": entity.id,
                "label": entity.name,
                "group": entity.entity_type,
                "title": (
                    f"{entity.description}<br/>mentions: {mention_counts.get(entity.id, 0)}"
                    f"<br/>{relation_note}"
                ),
                "value": max(1, mention_counts.get(entity.id, 1)),
            }
        )
    return nodes


def build_graph_payload(
    schema: DomainSchema,
    linked_mentions: list[MentionRecord],
    triples: list[TripleRecord],
    view: str = "focused",
) -> tuple[dict[str, Any], dict[str, Any]]:
    mention_counts, linked_entity_ids = _collect_linked_entity_counts(linked_mentions)
    raw_edges = _aggregate_edges(triples)

    raw_node_ids = {
        edge["from"] for edge in raw_edges
    } | {
        edge["to"] for edge in raw_edges
    }
    if view == "focused":
        node_ids = _component_from_center(
            raw_node_ids,
            raw_edges,
            schema.central_entity_id,
        )
        edges = [
            edge
            for edge in raw_edges
            if edge["from"] in node_ids and edge["to"] in node_ids
        ]
    elif view == "full":
        node_ids = set(linked_entity_ids) | raw_node_ids
        edges = list(raw_edges)
    else:
        raise ValueError(f"Unsupported graph view: {view}")

    nodes = _build_nodes(schema, node_ids, mention_counts, raw_node_ids)

    projection_stats = {
        "view": view,
        "raw_linked_entity_count": len(linked_entity_ids),
        "raw_triple_node_count": len(raw_node_ids),
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "isolated_node_count": len(node_ids - raw_node_ids),
        "removed_linked_entities": sorted(linked_entity_ids - node_ids),
        "center_entity_id": schema.central_entity_id,
    }
    return {"nodes": nodes, "edges": edges}, projection_stats


def generate_graph_html(
    graph_payload: dict[str, Any],
    title: str = "TuringKG Local Extraction Graph",
    subtitle: str = "Source: local EPUB/PDF biographies",
) -> str:
    data_json = json.dumps(graph_payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #f6f2e8; color: #2a241c; font-family: Georgia, "Times New Roman", serif; }}
  #header {{ padding: 24px 32px; border-bottom: 1px solid #d9cfbf; background: linear-gradient(135deg, #efe4d1, #f9f6ef); }}
  #header h1 {{ font-size: 24px; letter-spacing: 0.02em; }}
  #header p {{ margin-top: 8px; font-size: 14px; color: #5b5248; }}
  #mynetwork {{ width: 100%; height: calc(100vh - 92px); }}
</style>
</head>
<body>
<div id="header">
  <h1>{title}</h1>
  <p>{subtitle} | Nodes: {len(graph_payload['nodes'])} | Edges: {len(graph_payload['edges'])}</p>
</div>
<div id="mynetwork"></div>
<script src="{VIS_JS_URL}"></script>
<script>
const DATA = {data_json};
const groupColors = {{
  Person: '#c8553d',
  Organization: '#457b9d',
  Place: '#6a994e',
  Artifact: '#8a5aab',
  Concept: '#dd8b2f',
  Event: '#264653',
  default: '#8d99ae',
}};

const nodes = DATA.nodes.map((node) => {{
  const color = groupColors[node.group] || groupColors.default;
  return {{
    ...node,
    shape: node.group === 'Person' ? 'dot' : 'ellipse',
    color: {{
      background: color,
      border: color,
      highlight: {{ background: color, border: color }}
    }},
    font: {{ color: '#1f1b16', size: 14, face: 'Georgia, serif' }},
    size: 10 + Math.min(node.value * 2, 16),
  }};
}});

const edges = DATA.edges.map((edge) => ({{
  ...edge,
  color: {{ color: edge.source === 'inferred' ? '#6f4e7c' : '#9a8f82', highlight: '#2a9d8f' }},
  width: Math.min(1 + edge.value, 4),
  dashes: edge.source === 'inferred',
  font: {{ align: 'middle', color: '#5b5248', size: 11 }},
  smooth: {{ type: 'dynamic' }},
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.7 }} }},
}}));

new vis.Network(
  document.getElementById('mynetwork'),
  {{ nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }},
  {{
    physics: {{
      stabilization: {{ iterations: 150 }},
      barnesHut: {{ gravitationalConstant: -3500, springLength: 140, springConstant: 0.025 }}
    }},
    interaction: {{ hover: true, navigationButtons: true, keyboard: true }},
  }}
);
</script>
</body>
</html>"""
