"""Stitch 设计系统 — 多 Tab 知识图谱可视化。"""

from __future__ import annotations

import json
from typing import Any

VIS_JS_URL = (
    "https://cdn.jsdelivr.net/npm/vis-network@9.1.6/standalone/umd/vis-network.min.js"
)

TAILWIND_CONFIG = """tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "surface": "#0b1326", "background": "#0b1326",
        "surface-container": "#171f33", "surface-container-high": "#222a3d",
        "surface-container-low": "#131b2e", "surface-container-lowest": "#060e20",
        "surface-container-highest": "#2d3449", "surface-bright": "#31394d",
        "surface-variant": "#2d3449", "surface-dim": "#0b1326",
        "on-surface": "#dae2fd", "on-surface-variant": "#c1c7ce",
        "on-background": "#dae2fd",
        "primary": "#98cdf2", "primary-container": "#457b9d",
        "on-primary": "#00344c", "on-primary-container": "#fffdff",
        "outline": "#8b9198", "outline-variant": "#41484d",
        "tax-person": "#c8553d", "tax-org": "#457b9d", "tax-place": "#6a994e",
        "tax-artifact": "#8a5aab", "tax-concept": "#dd8b2f", "tax-event": "#264653",
        "tax-theory": "#718096",
        "error": "#ffb4ab", "on-error": "#690005",
        "tertiary": "#a2d582", "secondary": "#ffb4a4",
      },
      borderRadius: { "DEFAULT": "0.125rem", "lg": "0.25rem", "xl": "0.5rem" },
      fontFamily: { "serif": ['Noto Serif'], "sans": ['Inter'] },
    }
  }
}"""


def generate_graph_html_v2(
    graph_payload: dict[str, Any],
    ner_comparison: dict[str, Any] | None = None,
    reasoning_summary: dict[str, Any] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    title: str = "TuringKG",
) -> str:
    """生成 stitch 设计系统的多 Tab 页面。"""
    data_json = json.dumps(graph_payload, ensure_ascii=False).replace("</", "<\\/")
    ner_json = json.dumps(ner_comparison or {}, ensure_ascii=False)
    reasoning_json = json.dumps(reasoning_summary or {}, ensure_ascii=False)
    snapshots_json = json.dumps(snapshots or [], ensure_ascii=False)

    nodes = graph_payload.get("nodes", [])
    edges = graph_payload.get("edges", [])
    node_count = len(nodes)
    edge_count = len(edges)

    # Entity type stats
    from collections import Counter
    type_dist = Counter(n.get("group", "Unknown") for n in nodes)
    type_rows = "".join(
        f'<tr><td class="p-2">{t}</td><td class="p-2 text-right">{c}</td></tr>'
        for t, c in type_dist.most_common()
    )

    # Relation stats from edges
    rel_dist = Counter(e.get("label", "?") for e in edges)
    rel_rows = "".join(
        f'<tr><td class="p-2">{r}</td><td class="p-2 text-right">{c}</td></tr>'
        for r, c in rel_dist.most_common()
    )

    return f"""<!DOCTYPE html>
<html class="dark" lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Knowledge Graph</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Noto+Serif:wght@600;700&display=swap" rel="stylesheet">
<script>{TAILWIND_CONFIG}</script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', sans-serif; background: #0b1326; color: #dae2fd; }}
  .tab-btn {{ padding: 10px 20px; font-size: 0.875rem; font-weight: 600; border: none; cursor: pointer; background: transparent; color: #8b9198; transition: all 0.2s; border-bottom: 2px solid transparent; letter-spacing: 0.02em; }}
  .tab-btn:hover {{ color: #dae2fd; }}
  .tab-btn.active {{ color: #98cdf2; border-bottom-color: #98cdf2; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  #mynetwork {{ width: 100%; height: calc(100vh - 140px); }}
  .stat-card {{ background: #131b2e; border: 1px solid #222a3d; border-radius: 4px; padding: 16px; }}
  .stat-value {{ font-family: 'Noto Serif', serif; font-size: 1.75rem; font-weight: 700; }}
  .chip {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.05em; }}
  .legend-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
</style>
</head>
<body>

<!-- Header + Tab Bar -->
<header class="border-b" style="border-color:#222a3d; background:#0f172a;">
  <div class="px-6 py-4 flex items-center justify-between">
    <div>
      <h1 class="font-serif text-2xl font-bold" style="font-family:'Noto Serif'">{title}</h1>
      <p class="text-sm mt-1" style="color:#8b9198">Knowledge Graph Extraction Pipeline — Alan Turing Biographies</p>
    </div>
    <div class="flex gap-4 text-sm" style="color:#8b9198">
      <span class="stat-card px-3 py-1" style="background:#0b1326">Entities: <strong class="text-white">{node_count}</strong></span>
      <span class="stat-card px-3 py-1" style="background:#0b1326">Triples: <strong class="text-white">{edge_count}</strong></span>
      <span class="stat-card px-3 py-1" style="background:#0b1326">Relations: <strong class="text-white">{len(rel_dist)}</strong></span>
    </div>
  </div>
  <nav class="flex px-6" style="background:#0b1326">
    <button class="tab-btn active" onclick="switchTab('graph')">知识图谱</button>
    <button class="tab-btn" onclick="switchTab('relations')">关系分析</button>
    <button class="tab-btn" onclick="switchTab('reasoning')">推理链</button>
    <button class="tab-btn" onclick="switchTab('ner')">NER 对比</button>
    <button class="tab-btn" onclick="switchTab('analytics')">分析仪表盘</button>
  </nav>
</header>

<!-- Tab 1: 知识图谱 -->
<div id="tab-graph" class="tab-content active">
  <div class="flex" style="height:calc(100vh - 140px)">
    <!-- Left Sidebar: Legend -->
    <aside class="p-4 overflow-y-auto" style="width:240px;background:#0f172a;border-right:1px solid #222a3d">
      <h3 class="text-xs font-semibold uppercase tracking-wider mb-4" style="color:#8b9198">实体类型</h3>
      {''.join(f'<div class="flex items-center gap-2 mb-2 text-sm"><span class="legend-dot" style="background:{{"Person":"#c8553d","Organization":"#457b9d","Place":"#6a994e","Artifact":"#8a5aab","Concept":"#dd8b2f","Event":"#264653","Theory":"#718096"}}.get("{t}","#8d99ae")}}"></span> {t}<span class="ml-auto" style="color:#8b9198">{c}</span></div>' for t,c in type_dist.most_common())}
      <hr class="my-4" style="border-color:#222a3d">
      <h3 class="text-xs font-semibold uppercase tracking-wider mb-4" style="color:#8b9198">关系类型</h3>
      {''.join(f'<div class="text-sm mb-1" style="color:#8b9198">{r} <span class="ml-auto">{c}</span></div>' for r,c in rel_dist.most_common())}
      <hr class="my-4" style="border-color:#222a3d">
      <div class="text-xs" style="color:#8b9198">
        <div class="mb-1"><span class="legend-dot" style="background:#9a8f82"></span> 抽取</div>
        <div class="mb-1"><span class="legend-dot" style="background:#6f4e7c"></span> 推理</div>
        <div class="mb-1"><span class="legend-dot" style="background:#e07a5f"></span> 共现</div>
      </div>
    </aside>
    <!-- Graph Canvas -->
    <div id="mynetwork" class="flex-1"></div>
    <!-- Right: Node Inspector -->
    <aside id="inspector" class="p-4 overflow-y-auto" style="width:300px;background:#0f172a;border-left:1px solid #222a3d">
      <p class="text-sm" style="color:#8b9198">点击节点或边查看详情</p>
    </aside>
  </div>
</div>

<!-- Tab 2: 关系分析 -->
<div id="tab-relations" class="tab-content p-6">
  <h2 class="font-serif text-xl mb-6">关系类型分布与置信度</h2>
  <div class="grid grid-cols-2 gap-6">
    <div class="stat-card">
      <h3 class="text-sm font-semibold mb-4" style="color:#8b9198">关系类型分布</h3>
      <div id="rel-chart" class="space-y-2 text-sm">
        {''.join(f'<div class="flex items-center"><span class="w-24">{r}</span><div class="flex-1 mx-3 h-3 rounded" style="background:#222a3d"><div class="h-3 rounded" style="width:{min(c*100//max(max(rel_dist.values()) if rel_dist else 1,1),100)}%;background:#98cdf2"></div></div><span style="color:#8b9198">{c}</span></div>' for r,c in rel_dist.most_common())}
      </div>
    </div>
    <div class="stat-card">
      <h3 class="text-sm font-semibold mb-4" style="color:#8b9198">边来源分布</h3>
      <div id="source-chart"></div>
    </div>
  </div>
  <div class="stat-card mt-6">
    <h3 class="text-sm font-semibold mb-4" style="color:#8b9198">三元组置信度分布</h3>
    <div id="confidence-chart" class="text-sm space-y-1"></div>
  </div>
</div>

<!-- Tab 3: 推理链 -->
<div id="tab-reasoning" class="tab-content p-6">
  <h2 class="font-serif text-xl mb-6">推理规则与证据链</h2>
  <div id="reasoning-content" class="space-y-4"></div>
</div>

<!-- Tab 4: NER 对比 -->
<div id="tab-ner" class="tab-content p-6">
  <h2 class="font-serif text-xl mb-6">NER 四方法对比</h2>
  <div id="ner-content" class="grid grid-cols-2 gap-6"></div>
</div>

<!-- Tab 5: 分析仪表盘 -->
<div id="tab-analytics" class="tab-content p-6">
  <h2 class="font-serif text-xl mb-6">知识图谱分析仪表盘</h2>
  <div class="grid grid-cols-4 gap-4 mb-6">
    <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">实体总数</div><div class="stat-value">{node_count}</div></div>
    <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">三元组总数</div><div class="stat-value">{edge_count}</div></div>
    <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">关系类型</div><div class="stat-value">{len(rel_dist)}</div></div>
    <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">实体类型</div><div class="stat-value">{len(type_dist)}</div></div>
  </div>
  <div class="grid grid-cols-2 gap-6">
    <div class="stat-card">
      <h3 class="text-sm font-semibold mb-4" style="color:#8b9198">实体类型分布</h3>
      <table class="w-full text-sm">{type_rows}</table>
    </div>
    <div class="stat-card">
      <h3 class="text-sm font-semibold mb-4" style="color:#8b9198">关系类型分布</h3>
      <table class="w-full text-sm">{rel_rows}</table>
    </div>
  </div>
</div>

<script src="{VIS_JS_URL}"></script>
<script>
// Tab switching
function switchTab(name) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector(`.tab-btn:nth-child(${{['graph','relations','reasoning','ner','analytics'].indexOf(name)+1}})`).classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'graph') setTimeout(() => network && network.redraw(), 100);
}}

// === Main Graph (vis-network) ===
const DATA = {data_json};
const groupColors = {{
  Person: '#c8553d', Organization: '#457b9d', Place: '#6a994e',
  Artifact: '#8a5aab', Concept: '#dd8b2f', Event: '#264653', Theory: '#718096',
  default: '#8d99ae',
}};

const shapeMap = {{ Person: 'dot', Organization: 'box', Place: 'diamond', Artifact: 'hexagon', Concept: 'triangle', Event: 'star', Theory: 'square', default: 'ellipse' }};

const visNodes = DATA.nodes.map(node => {{
  const color = groupColors[node.group] || groupColors.default;
  return {{
    ...node, shape: shapeMap[node.group] || shapeMap.default,
    color: {{ background: color, border: color, highlight: {{ background: color, border: '#fff' }} }},
    font: {{ color: '#dae2fd', size: 11 + Math.min(node.value/200, 8), face: 'Inter' }},
    size: 8 + Math.min(node.value/150, 20),
  }};
}});

const visEdges = {data_json}.edges.map(edge => {{
  const isInferred = edge.source === 'inferred';
  const isCooccur = !isInferred && edge.source !== 'extracted';
  return {{
    ...edge, arrows: {{ to: {{ enabled: true }} }},
    color: {{ color: isInferred ? '#6f4e7c' : isCooccur ? '#e07a5f' : '#9a8f82', highlight: '#98cdf2' }},
    width: Math.min(0.5 + edge.value/4, 4),
    dashes: isInferred || isCooccur,
    smooth: {{ type: 'dynamic' }},
  }};
}});

const container = document.getElementById('mynetwork');
let network = null;
if (container) {{
  network = new vis.Network(container, {{ nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) }}, {{
    physics: {{ stabilization: {{ iterations: 200 }}, barnesHut: {{ gravitationalConstant: -3000, springLength: 120, springConstant: 0.02 }} }},
    interaction: {{ hover: true, navigationButtons: true, keyboard: true }},
  }});
  network.on('click', function(params) {{
    const insp = document.getElementById('inspector');
    if (params.nodes.length) {{
      const node = DATA.nodes.find(n => n.id === params.nodes[0]);
      if (node) insp.innerHTML = `<h3 class=\"font-serif text-lg\">${{node.label}}</h3><p class=\"text-sm mt-2\" style=\"color:#8b9198\">${{node.group}} — ${{node.value}} mentions</p><div class=\"mt-3 text-xs\" style=\"color:#c1c7ce\">${{node.title || ''}}</div>`;
    }} else if (params.edges.length) {{
      const edge = DATA.edges[params.edges[0]];
      if (edge) insp.innerHTML = `<h3 class=\"font-serif text-lg\">${{edge.label}}</h3><p class=\"text-sm mt-2\">${{DATA.nodes.find(n=>n.id===edge.from)?.label || edge.from}} → ${{DATA.nodes.find(n=>n.id===edge.to)?.label || edge.to}}</p><p class=\"text-xs mt-1\" style=\"color:#8b9198\">confidence: ${{(edge.avg_confidence*100).toFixed(0)}}% · source: ${{edge.source}}</p><div class=\"mt-2 text-xs\" style=\"color:#c1c7ce\">${{edge.title || ''}}</div>`;
    }}
  }});
}}

// === Tab 2: Relations ===
(function() {{
  const edges = {data_json}.edges;
  const srcCounts = {{}};
  edges.forEach(e => srcCounts[e.source] = (srcCounts[e.source]||0)+1);
  document.getElementById('source-chart').innerHTML = Object.entries(srcCounts).map(([s,c]) =>
    `<div class="flex items-center text-sm mb-2"><span class="w-24">${{s}}</span><div class="flex-1 mx-3 h-3 rounded" style="background:#222a3d"><div class="h-3 rounded" style="width:${{c*100/Math.max(...Object.values(srcCounts))}}%;background:#a2d582"></div></div><span style="color:#8b9198">${{c}}</span></div>`
  ).join('');

  const confBuckets = [0,0.5,0.6,0.7,0.8,0.9,1.0];
  const confCounts = confBuckets.map((b,i) => edges.filter(e => e.avg_confidence >= b && (i===confBuckets.length-1 || e.avg_confidence < confBuckets[i+1])).length);
  const maxConf = Math.max(...confCounts, 1);
  document.getElementById('confidence-chart').innerHTML = confBuckets.map((b,i) =>
    `<div class="flex items-center"><span class="w-16">≥${{b.toFixed(1)}}</span><div class="flex-1 mx-3 h-4 rounded" style="background:#222a3d"><div class="h-4 rounded" style="width:${{confCounts[i]*100/maxConf}}%;background:#dd8b2f"></div></div><span style="color:#8b9198">${{confCounts[i]}}</span></div>`
  ).join('');
}})();

// === Tab 3: Reasoning ===
(function() {{
  const reasoning = {reasoning_json};
  const rules = reasoning.rules || [];
  const dist = reasoning.inferred_relation_distribution || {{}};
  document.getElementById('reasoning-content').innerHTML = `
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">推理规则</div><div class="stat-value">${{reasoning.rule_count || 0}}</div></div>
      <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">推断三元组</div><div class="stat-value">${{reasoning.inferred_triple_count || 0}}</div></div>
      <div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">冲突消解</div><div class="stat-value">${{reasoning.conflicts_resolved || 0}}</div></div>
    </div>
    <h3 class="text-sm font-semibold mb-3" style="color:#8b9198">推理规则</h3>
    ${{rules.map(r => `<div class="stat-card mb-3"><span class="chip" style="background:#457b9d;color:#98cdf2">${{r.id}}</span> <span class="text-sm ml-2">${{r.template}}</span></div>`).join('')}}
    <h3 class="text-sm font-semibold mb-3 mt-6" style="color:#8b9198">推断关系分布</h3>
    ${{Object.entries(dist).map(([k,v]) => `<div class="text-sm mb-1">${{k}}: <strong>${{v}}</strong></div>`).join('')}}
  `;
}})();

// === Tab 4: NER Comparison ===
(function() {{
  const ner = {ner_json};
  const methods = ner.method_stats || {{}};
  const entries = Object.entries(methods);
  document.getElementById('ner-content').innerHTML = entries.map(([name, stats]) => {{
    const dist = stats.entity_type_distribution || {{}};
    const maxD = Math.max(...Object.values(dist), 1);
    return `<div class="stat-card">
      <h3 class="font-serif text-lg mb-2">${{name}}</h3>
      <p class="text-sm mb-3" style="color:#8b9198">${{stats.mention_count}} mentions · ${{Object.keys(dist).length}} types</p>
      ${{Object.entries(dist).map(([t,c]) => `<div class="flex items-center text-xs mb-1"><span class="w-20">${{t}}</span><div class="flex-1 mx-2 h-2 rounded" style="background:#222a3d"><div class="h-2 rounded" style="width:${{c*100/maxD}}%;background:${{groupColors[t]||'#98cdf2'}}"></div></div><span>${{c}}</span></div>`).join('')}}
    </div>`;
  }}).join('');

  document.getElementById('ner-content').insertAdjacentHTML('beforeend',
    `<div class="col-span-2 mt-2 text-sm" style="color:#8b9198">
      Overlap Matrix: ${{JSON.stringify(ner.overlap_matrix || {{}}) }}
    </div>`
  );
}})();

// === Tab 5: Snapshots ===
(function() {{
  const snaps = {snapshots_json};
  if (snaps.length) {{
    const container = document.getElementById('tab-analytics');
    const html = `<div class="mt-6"><h3 class="text-sm font-semibold mb-3" style="color:#8b9198">迭代快照</h3><div class="space-y-2 text-sm">${{snaps.map(s => `<div class="stat-card flex justify-between"><span>${{s.task}}</span><span style="color:#8b9198">${{s.triples}} triples · ${{s.entities_in_triples}} entities</span></div>`).join('')}}</div></div>`;
    container.insertAdjacentHTML('beforeend', html);
  }}
}})();
</script>
</body>
</html>"""
