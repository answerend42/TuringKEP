# TuringKEP

从 Wikidata 构建图灵知识图谱。

## 预览

[打开知识图谱 →](https://htmlpreview.github.io/?https://github.com/answerend42/TuringKEP/blob/main/turing_kg.html)

## 怎么来的

不从头做 NLP 实体抽取，而是直接从已有的大规模知识图谱（Wikidata）中抽取子图。

1. **种子实体**：选定 4 个核心实体（Alan Turing、Enigma、Bletchley Park、Turing test）
2. **SPARQL 查询**：通过 Wikidata API 获取这些实体的直接邻居
3. **剪枝过滤**：只保留中英文标签，按边权重排序取前 50 个节点
4. **可视化**：Python 生成 JSON 数据，vis.js 渲染交互式 HTML

## 快速开始

```bash
uv run main.py
```

生成 `turing_kg.html`，浏览器打开即可查看。
