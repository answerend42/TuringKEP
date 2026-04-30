# Ch5 实体消歧 + Ch3 知识融合

## Goal

用 TF-IDF 聚类消歧（Ch5 方法）合并碎片实体、提升实体质量，解决四大问题。

## Approach

1. **聚类消歧**：对每个 mention 构建 TF-IDF 上下文向量，短实体与其共现长实体计算余弦相似度 >0.8 → 合并
2. **放松发现门槛**：min_freq 15→5, confidence 0.60→0.50
3. **碎片过滤**：长度 ≤2 且不是已知实体别名的发现实体 → 标记为 uncertain
4. **异常关系标记**：含 uncertain 实体的三元组 → suspicious_triples.json

## AC

- [ ] 实体数从 64 → 80+
- [ ] 碎片实体合并率 ≥ 50%
- [ ] 异常关系（含碎片实体）自动排除
- [ ] `python main.py pipeline` 通过
