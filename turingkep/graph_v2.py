"""Cytoscape.js 多 Tab 知识图谱可视化 — 保守 JS 兼容实现。"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any


_TYPE_COLORS = {
    "Person": "#e06c50", "Organization": "#5b9ecf", "Place": "#7db85e",
    "Artifact": "#a87dc2", "Concept": "#e8a838", "Event": "#3d8b8b",
    "Theory": "#8899aa",
}


def generate_graph_html_v2(
    graph_payload: dict[str, Any],
    ner_comparison: dict[str, Any] | None = None,
    reasoning_summary: dict[str, Any] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    title: str = "TuringKG",
) -> str:
    """生成 Cytoscape.js 多 Tab 页面。"""
    data_json = json.dumps(graph_payload, ensure_ascii=False).replace("</", r"<\/")
    nodes = graph_payload.get("nodes", [])
    edges = graph_payload.get("edges", [])

    ner = ner_comparison or {}
    reasoning = reasoning_summary or {}

    type_dist = Counter(n.get("group", "Unknown") for n in nodes)
    rel_dist = Counter(e.get("label", "?") for e in edges)

    def _tc(t: str) -> str:
        return _TYPE_COLORS.get(t, "#8899aa")

    # Legend
    legend_rows = "".join(
        f'<div class="flex items-center gap-2 mb-2 text-sm">'
        f'<span class="inline-block w-2.5 h-2.5 rounded-full" style="background:{_tc(t)}"></span> '
        f'{t}<span class="ml-auto" style="color:#8b9198">{c}</span></div>\n'
        for t, c in type_dist.most_common()
    )
    _REL_EDGE_COLORS = {
        "出生于": "#e8a838", "逝世于": "#999", "就读于": "#5b9ecf",
        "工作于": "#5b9ecf", "合作": "#7db85e", "提出或研制": "#a87dc2",
        "破译": "#e06c50", "位于": "#5b9ecf", "影响": "#e8a838",
        "指导": "#3d8b8b", "亲属": "#e06c50", "参与密码破译": "#6f4e7c",
        "参与": "#3d8b8b",
    }
    def _rel_color(r: str) -> str:
        return _REL_EDGE_COLORS.get(r, "#5b9ecf")

    rel_rows_html = "".join(
        f'<div class="flex items-center gap-2 text-sm mb-1"><span class="inline-block w-2 h-2 rounded-full flex-shrink-0" '
        f'style="background:{_rel_color(r)}"></span> '
        f'<span style="color:#8b9198">{r}</span>'
        f'<span class="ml-auto" style="color:#8b9198">{c}</span></div>\n'
        for r, c in rel_dist.most_common()
    )

    # Type CSS rules for Cytoscape stylesheet
    type_css = "".join(
        f"      {{selector:'.{t.lower()}',style:{{'background-color':'{c}'}}}},\n"
        for t, c in _TYPE_COLORS.items()
    )

    # Relation chart
    max_rel = max(rel_dist.values()) if rel_dist else 1
    rel_chart = "".join(
        f'<div class="flex items-center text-sm mb-2"><span class="w-24">{r}</span>'
        f'<div class="flex-1 mx-3 h-3 rounded" style="background:#222a3d">'
        f'<div class="h-3 rounded" style="width:{c * 100 // max_rel}%;background:#98cdf2"></div></div>'
        f'<span style="color:#8b9198">{c}</span></div>\n'
        for r, c in rel_dist.most_common()
    )

    # Type table
    type_rows = "".join(
        f'<tr><td class="p-2">{t}</td><td class="p-2 text-right">{c}</td></tr>\n'
        for t, c in type_dist.most_common()
    )
    rel_table = "".join(
        f'<tr><td class="p-2">{r}</td><td class="p-2 text-right">{c}</td></tr>\n'
        for r, c in rel_dist.most_common()
    )

    # Reasoning
    rule_count = reasoning.get("rule_count", 0)
    inferred_count = reasoning.get("inferred_triple_count", 0)
    show_reasoning = rule_count > 1 or inferred_count > 5
    rules_html = "".join(
        f'<div class="stat-card mb-3"><span class="chip" style="background:#457b9d;color:#98cdf2">'
        f'{r["id"]}</span> <span class="text-sm ml-2">{r["template"]}</span></div>\n'
        for r in reasoning.get("rules", [])
    )
    inf_dist_html = "".join(
        f'<div class="text-sm mb-1">{k}: <strong>{v}</strong></div>\n'
        for k, v in reasoning.get("inferred_relation_distribution", {}).items()
    )
    reasoning_tab_style = 'style="display:none"' if not show_reasoning else ""
    reasoning_btn_style = 'style="display:none"' if not show_reasoning else ""

    # NER comparison
    ner_methods = ner.get("method_stats", {})
    # Summary row
    ner_summary = ""
    method_names = list(ner_methods.keys())
    if method_names:
        ner_summary = '<div class="col-span-2"><table class="w-full text-sm stat-card"><tr class="font-semibold">'
        ner_summary += '<td class="p-2">Method</td><td class="p-2 text-right">Mentions</td><td class="p-2 text-right">Entities</td></tr>'
        for name, stats in ner_methods.items():
            types = stats.get("entity_type_distribution", {})
            ner_summary += f'<tr><td class="p-2 font-semibold">{name}</td><td class="p-2 text-right">{stats["mention_count"]}</td><td class="p-2 text-right">{sum(types.values())}</td></tr>'
        ner_summary += '</table></div>'

    ner_cards = ""
    for name, stats in ner_methods.items():
        dist = stats.get("entity_type_distribution", {})
        max_d = max(dist.values()) if dist else 1
        # Horizontal stacked bar
        total = sum(dist.values())
        bar = '<div class="flex h-4 rounded overflow-hidden mb-3">'
        for t, c in dist.items():
            pct = c * 100 // total if total else 0
            bar += f'<div style="width:{pct}%;background:{_tc(t)}" title="{t}: {c}"></div>'
        bar += '</div>'
        # Legend below bar
        leg = '<div class="flex flex-wrap gap-2 text-xs">'
        for t, c in dist.items():
            leg += f'<span><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:{_tc(t)}"></span>{t} {c}</span>'
        leg += '</div>'
        ner_cards += (
            f'<div class="stat-card"><h3 class="font-serif text-lg mb-2">{name}</h3>'
            f'<p class="text-sm mb-2" style="color:#8b9198">{stats["mention_count"]} mentions · {len(dist)} types</p>'
            f'{bar}{leg}</div>\n'
        )

    return f"""<!DOCTYPE html><html class="dark" lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Noto+Serif:wght@600;700&display=swap" rel="stylesheet">
<script>tailwind.config={{darkMode:"class",theme:{{extend:{{colors:{{surface:"#0b1326",background:"#0b1326","surface-container":"#171f33","on-surface":"#dae2fd","on-surface-variant":"#c1c7ce",primary:"#98cdf2","primary-container":"#457b9d",outline:"#8b9198"}},borderRadius:{{DEFAULT:"0.125rem",lg:"0.25rem"}},fontFamily:{{serif:["Noto Serif"],sans:["Inter"]}}}}}}}}</script>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Inter',sans-serif;background:#0b1326;color:#dae2fd}}
.tab-btn{{padding:10px 20px;font-size:.875rem;font-weight:600;border:none;cursor:pointer;background:transparent;color:#8b9198;transition:all .2s;border-bottom:2px solid transparent;letter-spacing:.02em}}
.tab-btn:hover{{color:#dae2fd}}.tab-btn.active{{color:#98cdf2;border-bottom-color:#98cdf2}}
.tab-content{{display:none}}.tab-content.active{{display:block}}
#cy{{width:100%;height:calc(100vh - 140px)}}
.stat-card{{background:#131b2e;border:1px solid #222a3d;border-radius:4px;padding:16px}}
.stat-value{{font-family:'Noto Serif',serif;font-size:1.75rem;font-weight:700}}
.chip{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:600;letter-spacing:.05em}}
</style></head><body>

<header class="border-b" style="border-color:#222a3d;background:#0f172a">
<div class="px-6 py-4 flex items-center justify-between">
<div><h1 class="font-serif text-2xl font-bold">{title}</h1><p class="text-sm mt-1" style="color:#8b9198">Knowledge Graph — Alan Turing Biographies</p></div>
<div class="flex gap-4 text-sm" style="color:#8b9198">
<span class="stat-card px-3 py-1" style="background:#0b1326">Entities: <strong class="text-white">{len(nodes)}</strong></span>
<span class="stat-card px-3 py-1" style="background:#0b1326">Triples: <strong class="text-white">{len(edges)}</strong></span>
<span class="stat-card px-3 py-1" style="background:#0b1326">Relations: <strong class="text-white">{len(rel_dist)}</strong></span>
</div></div>
<nav class="flex px-6" style="background:#0b1326">
<button class="tab-btn active" onclick="switchTab('graph')">知识图谱</button>
<button class="tab-btn" onclick="switchTab('relations')">关系分析</button>
<button class="tab-btn" onclick="switchTab('reasoning')" {reasoning_btn_style}>推理链</button>
<button class="tab-btn" onclick="switchTab('ner')">NER对比</button>
<button class="tab-btn" onclick="switchTab('analytics')">仪表盘</button>
</nav></header>

<div id="tab-graph" class="tab-content active"><div class="flex" style="height:calc(100vh - 140px)">
<aside class="p-4 overflow-y-auto" style="width:240px;background:#0f172a;border-right:1px solid #222a3d">
<input id="search-box" class="w-full px-3 py-2 mb-4 text-sm rounded" style="background:#0b1326;border:1px solid #222a3d;color:#dae2fd" placeholder="搜索节点..." oninput="searchNode(this.value)">
<h3 class="text-xs font-semibold uppercase tracking-wider mb-4" style="color:#8b9198">实体类型</h3>
{legend_rows}
<hr class="my-4" style="border-color:#222a3d">
<h3 class="text-xs font-semibold uppercase tracking-wider mb-4" style="color:#8b9198">关系</h3>
{rel_rows_html}
</aside>
<div id="cy" class="flex-1"></div>
<aside id="inspector" class="p-4 overflow-y-auto" style="width:300px;background:#0f172a;border-left:1px solid #222a3d">
<p class="text-sm" style="color:#8b9198">点击节点或边查看详情</p>
</aside>
</div></div>

<div id="tab-relations" class="tab-content p-6">
<h2 class="font-serif text-xl mb-6">关系分析</h2>
<div class="grid grid-cols-2 gap-6">
<div class="stat-card"><h3 class="text-sm font-semibold mb-4" style="color:#8b9198">关系分布</h3>{rel_chart}</div>
<div class="stat-card"><h3 class="text-sm font-semibold mb-4" style="color:#8b9198">置信度分布</h3><div id="conf-chart" class="text-sm space-y-1"></div></div>
</div></div>

<div id="tab-reasoning" class="tab-content p-6" {reasoning_tab_style}>
<h2 class="font-serif text-xl mb-6">推理链</h2>
<div class="grid grid-cols-3 gap-4 mb-6">
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">规则</div><div class="stat-value">{reasoning.get("rule_count",0)}</div></div>
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">推断</div><div class="stat-value">{reasoning.get("inferred_triple_count",0)}</div></div>
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">消解</div><div class="stat-value">{reasoning.get("conflicts_resolved",0)}</div></div>
</div>
<h3 class="text-sm font-semibold mb-3" style="color:#8b9198">规则</h3>
{rules_html}
<h3 class="text-sm font-semibold mb-3 mt-6" style="color:#8b9198">推断分布</h3>
{inf_dist_html}
</div>

<div id="tab-ner" class="tab-content p-6">
<h2 class="font-serif text-xl mb-2">NER 四方法对比</h2>
<p class="text-sm mb-6" style="color:#8b9198">最终流水线使用 <strong style="color:#98cdf2">四种方法合并</strong>（Gazetteer 词典 + CRF 条件随机场 + HMM 隐马尔可夫手写 + HMM hmmlearn），最长匹配去重后作为实体识别输出。</p>
<div class="grid grid-cols-2 gap-6" id="ner-grid">{ner_summary}{ner_cards}</div>
</div>

<div id="tab-analytics" class="tab-content p-6">
<h2 class="font-serif text-xl mb-6">分析仪表盘</h2>
<div class="grid grid-cols-4 gap-4 mb-6">
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">实体</div><div class="stat-value">{len(nodes)}</div></div>
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">三元组</div><div class="stat-value">{len(edges)}</div></div>
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">关系</div><div class="stat-value">{len(rel_dist)}</div></div>
<div class="stat-card text-center"><div class="text-xs" style="color:#8b9198">类型</div><div class="stat-value">{len(type_dist)}</div></div>
</div>
<div class="grid grid-cols-2 gap-6">
<div class="stat-card"><h3 class="text-sm font-semibold mb-4" style="color:#8b9198">实体类型</h3><table class="w-full text-sm">{type_rows}</table></div>
<div class="stat-card"><h3 class="text-sm font-semibold mb-4" style="color:#8b9198">关系类型</h3><table class="w-full text-sm">{rel_table}</table></div>
</div></div>

<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
<script>
function switchTab(name) {{
  var btns = document.querySelectorAll('.tab-btn');
  var contents = document.querySelectorAll('.tab-content');
  var tabs = ['graph','relations','reasoning','ner','analytics'];
  for (var i=0;i<btns.length;i++) btns[i].classList.remove('active');
  for (var i=0;i<contents.length;i++) contents[i].classList.remove('active');
  document.getElementById('tab-'+name).classList.add('active');
  for (var i=0;i<tabs.length;i++) if (tabs[i]===name) btns[i].classList.add('active');
  if (name==='graph' && typeof cy!=='undefined') {{ setTimeout(function(){{cy.resize();cy.fit();}},100); }}
}}

var DATA = {data_json};
var gc = {{Person:'#e06c50',Organization:'#5b9ecf',Place:'#7db85e',Artifact:'#a87dc2',Concept:'#e8a838',Event:'#3d8b8b',Theory:'#8899aa'}};

var cyNodes = DATA.nodes.map(function(n) {{
  return {{ data: {{id:n.id,label:n.label,group:n.group,value:n.value,title:n.title||''}}, classes:n.group.toLowerCase() }};
}});

var cyEdges = DATA.edges.map(function(e,i) {{
  return {{ data: {{id:'e'+i,source:e.from,target:e.to,label:e.label,confidence:e.avg_confidence,sourceType:e.source,title:e.title||''}} }};
}});

var cy = cytoscape({{
  container: document.getElementById('cy'),
  elements: cyNodes.concat(cyEdges),
  style: [
    {{selector:'node',style:{{'label':'data(label)','color':'#dae2fd','font-size':10,'font-family':'Inter','text-valign':'bottom','text-halign':'center','text-margin-y':6,'border-width':2,'text-background-color':'#0b1326','text-background-opacity':0.6,'text-background-padding':2}}}},
{type_css}
    {{selector:'edge',style:{{'line-color':'rgba(91,158,207,0.4)','target-arrow-shape':'triangle','target-arrow-color':'rgba(91,158,207,0.6)','curve-style':'bezier','width':1,'label':'data(label)','color':'#8b9198','font-size':8,'text-rotation':'autorotate','text-background-color':'#0b1326','text-background-opacity':0.6,'text-background-padding':1}}}},
    {{selector:'.neighbor',style:{{'opacity':1}}}},
    {{selector:'.hidden-edge',style:{{'display':'none'}}}},
    {{selector:'node:selected',style:{{'border-color':'#fff','border-width':3}}}},
    {{selector:'.dimmed',style:{{'opacity':0.15}}}},
  ],
  layout: {{name:'concentric',minNodeSpacing:50}}
}});

cy.on('tap','node',function(evt){{
  var n = evt.target; var i = document.getElementById('inspector');
  var c = gc[n.data('group')]||'#8899aa';
  i.innerHTML = '<h3 class=\"font-serif text-lg mb-1\">'+n.data('label')+'</h3><span class=\"chip text-xs\" style=\"background:'+c+'33;color:'+c+'\">'+n.data('group')+'</span><p class=\"text-sm mt-3\" style=\"color:#8b9198\">'+n.data('value')+' mentions</p><div class=\"mt-3 text-xs\" style=\"color:#c1c7ce\">'+(n.data('title')||'')+'</div><p class=\"text-xs mt-2\" style=\"color:#98cdf2;cursor:pointer\" onclick=\"resetHighlight()\">← 显示全部</p>';
  // Isolate neighborhood
  var neighborhood = n.closedNeighborhood();
  cy.elements().addClass('dimmed');
  neighborhood.removeClass('dimmed');
  neighborhood.edges().removeClass('hidden-edge');
  cy.elements().difference(neighborhood).edges().addClass('hidden-edge');
}});
cy.on('tap','edge',function(evt){{
  var e = evt.target, s = cy.getElementById(e.data('source')), t = cy.getElementById(e.data('target'));
  var i = document.getElementById('inspector');
  i.innerHTML = '<h3 class=\"font-serif text-lg mb-1\">'+e.data('label')+'</h3><p class=\"text-sm mt-2\">'+(s?s.data('label'):e.data('source'))+' → '+(t?t.data('label'):e.data('target'))+'</p><p class=\"text-xs mt-1\" style=\"color:#8b9198\">'+(e.data('sourceType')||'')+' &middot; conf:'+Math.round((e.data('confidence')||0)*100)+'%</p><div class=\"mt-2 text-xs\" style=\"color:#c1c7ce\">'+(e.data('title')||'')+'</div>';
}});
window.resetHighlight = function() {{
  cy.elements().removeClass('dimmed');
  cy.elements().removeClass('hidden-edge');
  document.getElementById('inspector').innerHTML='<p class=\"text-sm\" style=\"color:#8b9198\">点击节点或边查看详情</p>';
}};
cy.on('tap',function(evt){{ if(evt.target===cy) resetHighlight(); }});

window.searchNode = function(q) {{
  if (typeof cy==='undefined') return;
  cy.nodes().removeClass('dimmed');
  if (!q||q.length<1) return;
  var ql = q.toLowerCase();
  var found = cy.nodes().filter(function(n){{ return n.data('label').toLowerCase().indexOf(ql)>=0 || n.data('id').toLowerCase().indexOf(ql)>=0; }});
  cy.nodes().difference(found).addClass('dimmed');
  if (found.length) {{ cy.animate({{center:{{eles:found}}}}); }}
}};

var confs = DATA.edges.map(function(e){{return e.avg_confidence||0;}});
var buckets = [0,0.5,0.6,0.7,0.8,0.9];
var bkts = buckets.map(function(b,i){{ return confs.filter(function(c){{return c>=b&&(i===buckets.length-1||c<buckets[i+1]);}}).length; }});
var maxb = Math.max.apply(null,bkts.concat([1]));
var ch = '';
for (var i=0;i<buckets.length;i++) ch+='<div class="flex items-center text-sm"><span class="w-12">≥'+buckets[i].toFixed(1)+'</span><div class="flex-1 mx-2 h-4 rounded" style="background:#222a3d"><div class="h-4 rounded" style="width:'+(bkts[i]*100/maxb)+'%;background:#dd8b2f"></div></div><span style="color:#8b9198">'+bkts[i]+'</span></div>';
document.getElementById('conf-chart').innerHTML = ch;

console.log('TuringKG: '+cy.nodes().length+' nodes, '+cy.edges().length+' edges');
</script></body></html>"""
