# 骨架重构

## Goal

重构 `turingkep` 流水线骨架，消除膨胀的 tuple 返回值和级联参数透传，建立统一的数据传递机制（PipelineContext），同时将各阶段模块化为可独立 import/run/评测的组件。这是 8 个 task 中的 Task 0，为后续逐章对齐课程方法论打下干净的架构基础。

## What I already know

- `pipeline.py` 8 个阶段函数，返回值从 2 元素增长到 9 元素 tuple
- 每个阶段检查参数是否为 None，是则级联调用上游——导致样板代码占函数体 50%+
- `cli.py` 12 个 if/elif 分支，每个手动调用阶段 + 手动 print 字段
- `linking.py` 已有 `EntityLinker` 类（好的方向），但 `ner.py`、`relation.py`、`reasoning.py` 都是裸函数集合
- `records.py` 的数据类（DocumentRecord、SentenceRecord、MentionRecord、TripleRecord）设计合理，保持不变
- 中间产物保存在 `outputs/01_extracted/` → `outputs/08_graph/`，路径定义在 `paths.py`

## Assumptions

- 外部 CLI 接口可改，只要流水线逻辑一致
- 中间产物格式可调整以适配新结构
- 各阶段可独立运行（不依赖级联调用）
- 重构后 `python main.py pipeline` 跑通即为验证通过

## Requirements

### 1. PipelineContext — 统一数据载体

用一个 `PipelineContext` dataclass 替代膨胀的 tuple 返回值：

```python
@dataclass
class PipelineContext:
    schema: DomainSchema | None = None
    documents: list[DocumentRecord] = field(default_factory=list)
    sentences: list[SentenceRecord] = field(default_factory=list)
    gazetteer_mentions: list[MentionRecord] = field(default_factory=list)
    crf_result: CrfResult | None = None
    merged_mentions: list[MentionRecord] = field(default_factory=list)
    linked_mentions: list[MentionRecord] = field(default_factory=list)
    asserted_triples: list[TripleRecord] = field(default_factory=list)
    inferred_triples: list[TripleRecord] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    store_summary: dict = field(default_factory=dict)
    graph_payload: dict = field(default_factory=dict)
```

每个阶段函数签名统一为 `(ctx: PipelineContext) -> PipelineContext`。

### 2. 阶段模块组件化

每个阶段模块暴露一个或多个 **统一接口的类**，可被独立 import 和运行：

- `ner.py` → `GazetteerExtractor`, `CRFExtractor` (未来可加 `HMMExtractor`)
- `linking.py` → `EntityLinker`（已有，接口微调）
- `relation.py` → `RelationExtractor`
- `reasoning.py` → `RuleReasoner`
- `storage.py` → `GraphStore`

每个 Extractor 有 `extract(ctx) -> PipelineContext` 或类似方法。

### 3. CLI dispatch 表

用 dict dispatch 替代 12 个 if/elif：

```python
COMMANDS = {
    "pipeline": run_full_pipeline,
    "extract": run_extract_stage,
    "preprocess": run_preprocess_stage,
    ...
}
handler = COMMANDS[args.command]
summary = handler()
```

### 4. 保持上游级联（但干净地实现）

`run_pipeline()` / `run_metrics_stage()` 仍然可以一键跑全流程，但改为各阶段顺序调用而非嵌套级联。

## Decision (ADR-lite)

**Context**: PipelineContext 设计需决定可变性策略
**Decision**: 采用 mutable 风格 — 各阶段函数原地修改 ctx，不返回新实例
**Consequences**: 代码简洁，无 replace 开销；ctx 生命周期仅限于单次流水线运行，无并发风险

## Technical Approach

**核心改动**：`pipeline.py` 完全重写，引入 `PipelineContext`，每个阶段函数改为 `(ctx) -> ctx`。`cli.py` 改为 dispatch 表。

**不改动**：`records.py`、`paths.py`、`schema.py`、`utils.py`、`ingestion.py`、`preprocess.py` 保持原样。

**微调**：各阶段模块（`ner.py`、`linking.py`、`relation.py`、`reasoning.py`、`storage.py`、`graph.py`、`evaluation.py`）的内部实现不动，只在外部包装统一接口。

## Acceptance Criteria

- [ ] `PipelineContext` dataclass 定义在 `pipeline.py`，包含所有阶段产物字段
- [ ] 所有阶段函数签名统一为 `(ctx) -> ctx`
- [ ] 无级联 None 检查——`run_pipeline()` 顺序调用各阶段
- [ ] CLI 使用 dispatch 表，无 if/elif 分支
- [ ] 每个阶段可独立运行（`python main.py ner` 不依赖前面的 CLI 命令）
- [ ] 各阶段模块有统一接口的类（`GazetteerExtractor`、`CRFExtractor`、`EntityLinker`、`RelationExtractor`、`RuleReasoner`、`GraphStore`）
- [ ] `python main.py pipeline` 端到端跑通，输出与重构前一致
- [ ] 类型检查通过（mypy/pyright）

## Expansion Sweep

1. **未来演进**: PipelineContext 用 `field(default_factory=list)` 可容纳后续 task 新增字段
2. **统一接口**: 每个 Extractor 同时有 `extract(ctx)` (流水线) 和独立调用方法 — 一次定型，7 个 task 复用
3. **回退策略**: 直接重写，不保留旧 pipeline.py

## Out of Scope

- 不增加新的 NER/链接/推理方法（留给后续 task）
- 不改 records.py / paths.py / schema.py / utils.py
- 不改可视化逻辑（graph.py 的 HTML 生成）
- 不写 Trellis spec 文件（Phase 3.3 做）

## Technical Notes

- `linking.py` 已有 `EntityLinker` 类，可作为组件化的参考模板
- `ner.py` 的三个核心操作：`find_gazetteer_mentions` → `train_and_predict_crf` → `merge_mentions`，可封装为 `GazetteerExtractor` + `CRFExtractor`
- `relation.py` 的核心：`extract_relation_triples`，封装为 `RelationExtractor`
- `reasoning.py` 的核心：`apply_reasoning_rules`，封装为 `RuleReasoner`
- `storage.py` 的核心：`export_graph_store`，封装为 `GraphStore`
- 每个阶段 CLI 命令独立运行时，需要能加载上游中间产物文件（`load_document_records` 等已在 `records.py` 中定义），阶段类应接受文件路径或已加载数据
