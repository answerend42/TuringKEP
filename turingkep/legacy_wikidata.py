from __future__ import annotations

import json
from pathlib import Path

import requests


SEEDS = {
    "Q7251": "Alan Turing",
    "Q179211": "Enigma",
    "Q193518": "Bletchley Park",
    "Q193517": "Turing test",
}

SPARQL = """
SELECT DISTINCT ?s ?p ?o ?oLabel ?oType WHERE {
  VALUES ?s { %s }
  ?s ?p ?o .
  OPTIONAL { ?o wdt:P31 ?oType . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh-hans,en". }
}
"""

VIS_JS_URL = (
    "https://cdn.jsdelivr.net/npm/vis-network@9.1.6/standalone/umd/vis-network.min.js"
)


def is_zh_hans_or_en(label: str) -> bool:
    if not label:
        return False
    for char in label:
        if char.isalpha() and not ("\u4e00" <= char <= "\u9fff" or char.isascii()):
            return False
    return True


def fetch_wikidata() -> list[dict[str, dict[str, str]]]:
    values = " ".join(f"wd:{qid}" for qid in SEEDS)
    query = SPARQL % values
    response = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": query, "format": "json"},
        headers={"User-Agent": "TuringKEP/1.0"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def fetch_vis_js() -> str:
    response = requests.get(VIS_JS_URL, headers={"User-Agent": "TuringKEP/1.0"}, timeout=60)
    response.raise_for_status()
    return response.text


def build_data(bindings: list[dict[str, dict[str, str]]], max_nodes: int = 50) -> tuple[list[dict[str, str]], list[dict[str, str | int]]]:
    nodes = {
        qid: {"id": qid, "label": label, "group": "seed"}
        for qid, label in SEEDS.items()
    }
    edge_weights: dict[tuple[str, str], int] = {}
    node_info: dict[str, dict[str, str]] = {}

    for binding in bindings:
        subject = binding["s"]["value"].split("/")[-1]
        obj = binding["o"]["value"].split("/")[-1]
        obj_label = binding.get("oLabel", {}).get("value", "")
        obj_type = binding.get("oType", {}).get("value", "").split("/")[-1]

        if not obj_label or obj_label.isdigit():
            continue
        if not is_zh_hans_or_en(obj_label):
            continue
        if obj in SEEDS:
            continue

        key = (subject, obj)
        edge_weights[key] = edge_weights.get(key, 0) + 1
        if obj not in node_info:
            node_info[obj] = {"label": obj_label, "type": obj_type}

    sorted_edges = sorted(edge_weights.items(), key=lambda item: -item[1])
    seen = set(SEEDS.keys())
    edges: list[dict[str, str | int]] = []

    for (subject, obj), weight in sorted_edges:
        if len(seen) >= max_nodes and obj not in seen:
            break
        seen.add(obj)
        if obj not in nodes:
            info = node_info[obj]
            nodes[obj] = {"id": obj, "label": info["label"], "group": info["type"]}
        edges.append({"from": subject, "to": obj, "value": weight})

    connected: set[str] = set()
    for edge in edges:
        connected.add(str(edge["from"]))
        connected.add(str(edge["to"]))

    filtered_nodes = {key: value for key, value in nodes.items() if key in connected}
    return list(filtered_nodes.values()), edges


def generate_html(nodes: list[dict[str, str]], edges: list[dict[str, str | int]], vis_js: str) -> str:
    data_json = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Turing Knowledge Graph</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0d1117; color: #e6edf3; font-family: -apple-system, sans-serif; }}
  #header {{ padding: 20px 30px; border-bottom: 1px solid #21262d; }}
  #header h1 {{ font-size: 20px; font-weight: 600; }}
  #header p {{ font-size: 13px; color: #8b949e; margin-top: 4px; }}
  #mynetwork {{ width: 100%; height: calc(100vh - 80px); }}
</style>
</head>
<body>
<div id="header">
  <h1>Turing Knowledge Graph</h1>
  <p>Source: Wikidata | Nodes: {len(nodes)} | Edges: {len(edges)}</p>
</div>
<div id="mynetwork"></div>
<script>{vis_js}</script>
<script>
const DATA = {data_json};
const groupColors = {{
  seed: {{ background: '#ffd700', border: '#e6c200', highlight: '#ffe44d' }},
  Q5: {{ background: '#ff7f7f', border: '#e06060', highlight: '#ff9999' }},
  Q43229: {{ background: '#7f7fff', border: '#6060e0', highlight: '#9999ff' }},
  Q2221906: {{ background: '#7fff7f', border: '#60e060', highlight: '#99ff99' }},
  default: {{ background: '#87ceeb', border: '#6bb8d6', highlight: '#a8dff0' }},
}};
const visNodes = DATA.nodes.map((node) => {{
  const group = node.group === 'seed' ? 'seed' : node.group;
  const color = groupColors[group] || groupColors.default;
  return {{
    ...node,
    color: {{ background: color.background, border: color.border, highlight: {{ background: color.highlight, border: color.border }} }},
    font: {{ color: '#e6edf3', size: 12, face: '-apple-system, sans-serif' }},
    shape: node.group === 'seed' ? 'diamond' : 'dot',
  }};
}});
const visEdges = DATA.edges.map((edge) => ({{
  ...edge,
  color: {{ color: '#30363d', highlight: '#58a6ff' }},
  width: Math.min(edge.value, 3),
  smooth: {{ type: 'continuous' }},
}}));
const data = {{ nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) }};
const options = {{
  physics: {{
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -50,
      centralGravity: 0.02,
      springLength: 100,
      springConstant: 0.05,
      damping: 0.4,
    }},
    stabilization: {{ iterations: 200, fit: true }},
  }},
  interaction: {{ hover: true, tooltipDelay: 50, navigationButtons: true, keyboard: true }},
}};
new vis.Network(document.getElementById('mynetwork'), data, options);
</script>
</body>
</html>"""


def run_legacy_demo(output_path: Path | None = None) -> Path:
    destination = output_path or Path("turing_kg.html")
    vis_js = fetch_vis_js()
    bindings = fetch_wikidata()
    nodes, edges = build_data(bindings)
    html = generate_html(nodes, edges, vis_js)
    destination.write_text(html, encoding="utf-8")
    return destination
