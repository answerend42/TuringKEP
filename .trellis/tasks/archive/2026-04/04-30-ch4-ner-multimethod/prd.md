# Ch4 实体识别：多方法对比

## Goal

实现 HMM（隐马尔可夫模型）实体识别器，与现有的 Gazetteer 和 CRF 构成三种方法的统一对比实验。每个方法独立可运行、独立可评测，输出可横向比较。

## What I already know

- 已有 `GazetteerExtractor`（词典匹配 + 最长匹配去重）和 `CRFExtractor`（sklearn-crfsuite 线性链 CRF）
- 两种方法已通过 `GazetteerExtractor.extract()` / `CRFExtractor.extract()` 暴露统一接口
- CRF 使用 BIO 标注、15 维特征模板，词典匹配结果作为弱监督标签训练 CRF
- 当前 merge_mentions 合并两种方法产出（词典优先 + 非重叠选择）
- 课程 Ch4 讲解了 HMM vs CRF 的理论对比：HMM 生成式模型（建模 P(X,Y)），CRF 判别式模型（建模 P(Y|X)）

## Requirements

### 1. HMM NER 实现

实现 `HMMExtractor` 类，接口与 `GazetteerExtractor` / `CRFExtractor` 统一：

```python
class HMMExtractor:
    def extract(self, sentences: list[SentenceRecord], gazetteer_mentions: list[MentionRecord]) -> CrfResult:
        ...
```

HMM 实现要点：
- 用词典弱监督标签作为训练数据（与 CRF 一致的训练方式）
- 三要素：初始概率 π、转移矩阵 A、发射矩阵 B
- 用维特比算法解码最优标签序列
- 发射概率基于词特征（词的表面形式 + 是否在词典中）
- 拉普拉斯平滑处理未登录词

### 2. 统一的评测对比

每种方法输出独立的指标（精确率、召回率、F1），生成对比报告到 `evaluation/ner_comparison.json`。

### 3. Pipeline 集成

`PipelineContext` 增加 `hmm_result: CrfResult | None` 字段。`run_ner_stage()` 增加可选的方法选择逻辑。

## Acceptance Criteria

- [ ] `HMMExtractor` 实现完毕，接口与 `CRFExtractor` 一致
- [ ] HMM 产出命名实体提及列表，数量与 CRF/词典可比
- [ ] 三种方法对比报告输出到 `evaluation/ner_comparison.json`
- [ ] `python main.py ner` 支持 `--method hmm/crf/gazetteer/all` 参数
- [ ] 所有方法可在 pipeline 中独立切换
- [ ] 快照保存到 `snapshots/task2-ch4-ner/`

## Decision

**HMM 实现方式**：双层对比 — 手写 `HMMExtractor`（纯 Python）和库版 `HMMLearnExtractor`（hmmlearn），两者接口统一，形成 HMM 家族内部的方法对比。最终对比矩阵：Gazetteer × CRF × 手写HMM × hmmlearnHMM。

## Out of Scope

- 不训练深度学习的 NER（LSTM/BERT）
- 不引入外部 NER 工具（HanLP/LAC）
- 不做开放域实体发现（那是 Ch3 的事）
