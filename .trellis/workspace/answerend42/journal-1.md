# Journal - answerend42 (Part 1)

> AI development session journal
> Started: 2026-04-30

---



## Session 1: Task 0: 骨架重构 — PipelineContext + 组件化 + CLI dispatch

**Date**: 2026-04-30
**Task**: Task 0: 骨架重构 — PipelineContext + 组件化 + CLI dispatch
**Branch**: `main`

### Summary

重构流水线骨架：引入 PipelineContext 替代 tuple 级联返回，8个阶段函数统一 (ctx)->None 签名。各阶段模块封装为可独立调用的组件类。CLI 改为 dispatch 表。初始化 Trellis 框架与 pipeline spec。提交完整项目源码。已知问题：schema 仅 21 实体/7关系，关系抽取产出受限，后续 task 解决。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `71cdd68` | (see git log) |
| `cfe5123` | (see git log) |
| `d86421c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Task 1: Ch2 知识表示 — 扩充本体与关系模式

**Date**: 2026-04-30
**Task**: Task 1: Ch2 知识表示 — 扩充本体与关系模式
**Branch**: `main`

### Summary

实体 21→44，关系 7→10 种，引入类型层级和实体属性。Schema 支持父类型匹配。新增 entity_discovery 半自动发现工具。三元组从 43 升至 110（+156%），涉及实体从 12 升至 28。已知：18 个概念/理论类实体仍未出现在关系中。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `05d70eb` | (see git log) |
| `e2dbbfa` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Task 1 补充: 段落级 TF-IDF + 停用词表 + 迭代日志

**Date**: 2026-04-30
**Task**: Task 1 补充: 段落级 TF-IDF + 停用词表 + 迭代日志
**Branch**: `main`

### Summary

Task 1 Ch2 知识表示：实体 21→46，关系 7→10，三元组 43→110。entity_discovery 演进至 v3（段落级 TF-IDF + POS + 共现增强），停用词表改为 goto456/stopwords。建立 experiments/iteration-journal.md 和 snapshots/ 快照系统。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `05d70eb` | (see git log) |
| `e2dbbfa` | (see git log) |
| `fc4ba69` | (see git log) |
| `143673e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Task 2: Ch4 实体识别 — 四方法对比（Gazetteer/CRF/HMM/hmmlearn）

**Date**: 2026-04-30
**Task**: Task 2: Ch4 实体识别 — 四方法对比（Gazetteer/CRF/HMM/hmmlearn）
**Branch**: `main`

### Summary

实现手写 HMM 和 hmmlearn 库版 HMM，四方法统一接口。手写版产出 9,893 提及，hmmlearn 版 436。Pipeline 支持 --method 切换。生成对比报告到 evaluation/ner_comparison.json。hmmlearn 特征桶化实验本身有方法论价值。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7fc4784` | (see git log) |
| `7ffe11e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
