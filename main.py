import json
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


def is_zh_hans_or_en(label):
    if not label:
        return False
    for ch in label:
        if ch.isalpha() and not ("\u4e00" <= ch <= "\u9fff" or ch.isascii()):
            return False
    return True


def fetch_wikidata():
    url = "https://query.wikidata.org/sparql"
    values = " ".join(f"wd:{qid}" for qid in SEEDS)
    query = SPARQL % values
    r = requests.get(
        url,
        params={"query": query, "format": "json"},
        headers={"User-Agent": "TuringKEP/1.0"},
    )
    return r.json()["results"]["bindings"]


def fetch_vis_js():
    r = requests.get(VIS_JS_URL, headers={"User-Agent": "TuringKEP/1.0"})
    return r.text


def build_data(bindings, max_nodes=50):
    nodes = {
        qid: {"id": qid, "label": label, "group": "seed"}
        for qid, label in SEEDS.items()
    }
    edge_weights = {}
    node_info = {}

    for b in bindings:
        s = b["s"]["value"].split("/")[-1]
        o = b["o"]["value"].split("/")[-1]

        o_label = b.get("oLabel", {}).get("value", "")
        o_type = b.get("oType", {}).get("value", "").split("/")[-1]

        if not o_label or o_label.isdigit():
            continue
        if not is_zh_hans_or_en(o_label):
            continue
        if o in SEEDS:
            continue

        key = (s, o)
        edge_weights[key] = edge_weights.get(key, 0) + 1
        if o not in node_info:
            node_info[o] = {"label": o_label, "type": o_type}

    sorted_edges = sorted(edge_weights.items(), key=lambda x: -x[1])
    seen = set(SEEDS.keys())
    edges = []

    for (s, o), weight in sorted_edges:
        if len(seen) >= max_nodes and o not in seen:
            break
        seen.add(o)
        if o not in nodes:
            info = node_info[o]
            nodes[o] = {"id": o, "label": info["label"], "group": info["type"]}
        edges.append(
            {
                "from": s,
                "to": o,
                "value": weight,
            }
        )

    connected = set()
    for e in edges:
        connected.add(e["from"])
        connected.add(e["to"])
    nodes = {k: v for k, v in nodes.items() if k in connected}

    return list(nodes.values()), edges


def generate_html(nodes, edges, vis_js):
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
  #legend {{ position: fixed; bottom: 20px; left: 20px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; font-size: 12px; }}
  #legend div {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  #legend span {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<div id="header">
  <h1>Turing Knowledge Graph</h1>
  <p>Source: Wikidata | Nodes: {len(nodes)} | Edges: {len(edges)}</p>
</div>
<div id="mynetwork"></div>
<div id="legend">
  <div><span style="background:#ffd700"></span> Seed Entity</div>
  <div><span style="background:#ff7f7f"></span> Person</div>
  <div><span style="background:#7f7fff"></span> Organization</div>
  <div><span style="background:#7fff7f"></span> Place</div>
  <div><span style="background:#87ceeb"></span> Other</div>
</div>
<script>
{vis_js}
</script>
<script>
const DATA = {data_json};

const groupColors = {{
  seed: {{ background: '#ffd700', border: '#e6c200', highlight: '#ffe44d' }},
  Q5: {{ background: '#ff7f7f', border: '#e06060', highlight: '#ff9999' }},
  Q43229: {{ background: '#7f7fff', border: '#6060e0', highlight: '#9999ff' }},
  Q2221906: {{ background: '#7fff7f', border: '#60e060', highlight: '#99ff99' }},
  default: {{ background: '#87ceeb', border: '#6bb8d6', highlight: '#a8dff0' }},
}};

const visNodes = DATA.nodes.map(n => {{
  const g = n.group === 'seed' ? 'seed' : n.group;
  const c = groupColors[g] || groupColors.default;
  return {{
    ...n,
    color: {{ background: c.background, border: c.border, highlight: {{ background: c.highlight, border: c.border }} }},
    font: {{ color: '#e6edf3', size: 12, face: '-apple-system, sans-serif' }},
    shape: n.group === 'seed' ? 'diamond' : 'dot',
    size: n.group === 'seed' ? 20 : 10 + Math.min((DATA.edges.filter(e => e.from === n.id || e.to === n.id).length) * 2, 8),
  }};
}});

const visEdges = DATA.edges.map(e => ({{
  ...e,
  color: {{ color: '#30363d', highlight: '#58a6ff' }},
  width: Math.min(e.value, 3),
  smooth: {{ type: 'continuous' }},
}}));

const container = document.getElementById('mynetwork');
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

new vis.Network(container, data, options);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("Fetching vis-network library...")
    vis_js = fetch_vis_js()
    print(f"Got vis-network ({len(vis_js)} bytes)")

    print("Fetching from Wikidata...")
    bindings = fetch_wikidata()
    print(f"Got {len(bindings)} triples")

    print("Building graph...")
    nodes, edges = build_data(bindings)
    print(f"Graph: {len(nodes)} nodes, {len(edges)} edges")

    print("Generating visualization...")
    html = generate_html(nodes, edges, vis_js)
    with open("turing_kg.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Done -> turing_kg.html")
