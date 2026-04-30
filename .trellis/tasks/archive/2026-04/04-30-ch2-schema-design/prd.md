# Ch2 知识表示：扩充领域本体与关系模式库

## Goal

扩充 `schema/turing_domain.json` 的实体定义和关系模板，使知识图谱覆盖更丰富的图灵相关概念。当前 schema 仅 21 个实体和 7 种关系——这是流水线产出受限的根因。

## What I already know

- 当前 21 实体覆盖 6 人、5 机构、3 地点、3 工件、3 概念、1 事件
- 7 种关系每种只有 2-3 个中文模式词，实际语言表达远超此范围
- 两本图灵传记共 14728 句，NER 识别了 5707 个提及但链接只能到 20 个预定义实体
- `located_in` 0 条三元组、"克里斯托弗·莫克姆"被识别但无关系关联——说明模式词覆盖不足
- 课程 Ch2 要求体现：经典知识表示理论、语义网标准（RDF/OWL）、知识图谱表示方法

## Assumptions

- 实体扩充来源：两本传记文本 + 图灵生平常识 + 现有 NER 提及中的高频未链接词
- 关系模式扩充来源：分析现有文本中实体共现的上下文
- 可新增 schema 字段（实体属性、类型层级、约束等）

## Requirements (evolving)

### 1. 扩充实体清单
从 21 → 50+ 实体，覆盖：
- 更多人物（图灵亲属、同事、导师、学生）
- 更多地点（曼彻斯特、舍伯恩、布莱切利等）
- 更多组织（国家物理实验室、舍伯恩学校等）
- 更多概念（停机问题、丘奇-图灵论题等）

### 2. 丰富关系模式
每种关系增加 8-15 个中文模式词，并新增 2-3 种关系类型

### 3. 添加实体属性
为 Person 类型增加出生/逝世日期、国籍等结构化属性

## Acceptance Criteria

- [ ] schema 实体 ≥ 50 个，类型分布合理
- [ ] 每种关系模式词 ≥ 8 个
- [ ] 新增 ≥ 2 种关系类型
- [ ] `python main.py pipeline` 三元组数量显著增长
- [ ] 所有 21 个原有实体在关系三元组中出现

## Out of Scope

- 不引入外部知识库（DBpedia/Wikidata）自动扩充——保持手工设计以体现方法论
- 不改变 schema 文件格式

## Decision

**Entity discovery strategy**: 混合方案 C — 先半自动从文本中发现候选实体，人工审核确认后手工补充不足。

## Decision

**类型层级**: 引入 `Entity → Agent/PhysicalEntity/AbstractEntity/Location → Person/Organization/Artifact/Concept/Event/Place` 层级。关系定义中 subject_types/object_types 支持父类型匹配。

**Entity discovery strategy**: 混合方案 C — 先半自动从文本中发现候选实体，人工审核确认后手工补充不足。
**类型层级**: 引入 `Entity → Agent/PhysicalEntity/AbstractEntity/Location → Person/Organization/Artifact/Concept/Event/Place` 层级。关系定义中 subject_types/object_types 支持父类型匹配。
**实体属性**: 嵌入 `EntityDefinition` 的 `attributes` 字段，与实体定义放在一起。

## Requirements (final)
