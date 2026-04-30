# Ch4 开放域实体发现

## Goal

打破封闭世界假设——在 NER 阶段内嵌开放域实体发现，从传记文本中自动识别 schema 之外的实体，动态扩充本体，使知识图谱节点数量实质性增长。

## Approach

不改 pipeline 阶段数，在 `run_ner_stage` 完成后：
1. 用 `entity_discovery.py` 从文本发现候选实体（段落 TF-IDF + POS + 共现）
2. 高置信度候选（≥0.55）自动加入临时扩充 schema
3. 对新实体做第二轮 gazetteer 识别
4. 合并所有 mention，新实体标注 source="discovered"

## Acceptance Criteria

- [ ] 发现的新实体数量 ≥ 20 个
- [ ] 三元组数量增长 ≥ 30%
- [ ] 图谱节点数（关系中实体数）增长 ≥ 50%
- [ ] `python main.py pipeline` 端到端通过
- [ ] 快照保存
