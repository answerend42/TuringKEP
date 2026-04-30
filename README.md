# TuringKEP

基于图灵传记文本构建一个最小可解释的知识工程流水线。

## 现在做什么

项目默认从 `data/` 下的 EPUB/PDF 书籍中抽取文本，然后依次完成一个最小课程闭环：

1. 知识表示：`schema/turing_domain.json` 定义实体类型、实体清单、关系类型和规则触发词
2. 文本抽取：`EPUB/PDF -> 纯文本`
3. 分句与分词：`jieba`
4. 实体抽取：
   `词典弱标注 + CRF 风格序列标注`
5. 实体消歧：
   `别名候选生成 + TF-IDF 相似度打分 + NIL 阈值`
6. 关系抽取：
   `基于模板和关键词的限定域关系抽取`
7. 知识推理：
   `产生式规则` 从已抽取三元组推出少量新事实
8. 存储与检索：
   `JSONL/TSV/N-Triples` 本地图存储 + Cypher 风格查询样例
9. 图谱展示：
   `vis-network HTML 可视化`

整个流程会把中间结果落到 `outputs/`，方便检查每一步到底做了什么。

## 方法选择

- 知识体系：小型领域 schema / ontology
- 分词：`jieba`
- 实体抽取：`gazetteer baseline + sklearn-crfsuite`
- 实体消歧：`TF-IDF candidate ranking`
- 关系抽取：`pattern / rule based`
- 知识推理：`production rules`
- 存储检索：`property graph style JSONL + RDF-like N-Triples + query examples`

这些方法都偏经典、可解释、容易在课程报告里说明。

## 快速开始

```bash
uv run main.py
```

如果你想单独检查某一段，也可以按阶段运行：

```bash
uv run main.py extract
uv run main.py preprocess
uv run main.py ner
uv run main.py link
uv run main.py relation
uv run main.py reason
uv run main.py store
uv run main.py query
uv run main.py graph
uv run main.py metrics
```

运行结束后重点看这些文件：

- `outputs/01_extracted/documents.jsonl`
- `outputs/02_preprocessed/sentences.jsonl`
- `outputs/03_ner/entity_mentions.jsonl`
- `outputs/04_linking/linked_mentions.jsonl`
- `outputs/05_relations/triples.jsonl`
- `outputs/06_reasoning/inferred_triples.jsonl`
- `outputs/07_storage/entities.jsonl`
- `outputs/07_storage/facts.jsonl`
- `outputs/07_storage/query_examples.json`
- `outputs/08_graph/turing_kg.html`
- `evaluation/crf_metrics.json`
- `evaluation/pipeline_metrics.json`

项目根目录下的 `turing_kg.html` 会同步更新，方便直接打开预览。

## 怎么比较方案

`evaluation/pipeline_metrics.json` 里现在有两类可以直接横向比较的数字：

- 图谱质量代理指标：
  `conflict_pair_ratio`、`projected_center_component_ratio`、`single_support_edge_ratio`、`average_edge_support`
- 无人工标注的分词代理指标：
  `tokenizer_proxy.linked_mentions.boundary_alignment_rate`、
  `tokenizer_proxy.linked_mentions.fragmentation_mean`、
  `tokenizer_proxy.gazetteer_mentions.single_token_rate`

这套设计的意思很直接：

- 如果你以后替换分词器，不需要做人手标注，也能看实体边界是否更完整、碎片化是否更少。
- 如果你以后替换链接或关系模块，可以看冲突边、孤立点、单证据边是否下降。

## 为什么这是最小课程设计

这不是追求大模型效果的项目，而是把老师课件和助教反馈中最关键的知识工程步骤都做出可运行证据：

- 第 3 章知识体系：schema 明确约束实体类型、关系类型和关系方向。
- 第 4 章实体识别：从自然语言传记文本中抽取实体提及，不只是格式转换。
- 第 5 章实体消歧：每个 mention 都经过候选生成、相似度排序和 NIL 判断。
- 第 6 章关系抽取：从句子证据中生成结构化三元组。
- 第 8 章存储检索：导出实体表、事实表、RDF-like triples 和查询样例。
- 第 9 章知识推理：用产生式规则生成可解释的推理事实。

## 兼容旧方向

如果还想运行之前的 Wikidata 子图 demo，可以执行：

```bash
uv run main.py legacy-wikidata
```
