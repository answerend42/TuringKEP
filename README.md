# TuringKG — 图灵知识图谱构建流水线

从两本艾伦·图灵中文传记（EPUB/PDF）出发，自动构建知识图谱。

## 查看知识图谱

👉 **[点击这里直接查看交互式知识图谱](https://refined-github-html-preview.kidonng.workers.dev/answerend42/TuringKEP/raw/refs/heads/main/turing_kg.html)**

> 或克隆仓库后，用浏览器打开 `turing_kg.html`。运行 `python main.py pipeline` 可重新生成。

图谱基于 Cytoscape.js 渲染，包含 5 个 Tab：知识图谱主视图（点击节点高亮邻域＋搜索）、关系分析（分布图＋置信度）、推理链、NER 四方法对比、分析仪表盘。

## 快速开始

```bash
# 安装依赖
uv pip install -e .

# 下载 spaCy 中文模型（首次）
python -m spacy download zh_core_web_sm

# 运行完整流水线
python main.py pipeline
```

产出在 `outputs/08_graph/turing_kg.html`（多 Tab 可视化）和 JSONL 中间文件。

## 流水线架构

```
EPUB/PDF 传记
    │
    ▼
[01 文本抽取] ── EPUB/PDF → 纯文本
    │
    ▼
[02 预处理] ─── 分句 + jieba 分词
    │
    ▼
[03 实体识别] ─ 词典(Gazetteer) + CRF + HMM(手写) + HMM(hmmlearn) 四方法合并
    │
    ▼
[04 实体链接] ─ 候选生成 + 多特征排序(TF-IDF/类型/流行度) + 动态NIL
    │
    ▼
[05 关系抽取] ─ 正则模式 + 实体共现(触发词验证) + spaCy SVO
    │
    ▼
[06 知识推理] ─ 产生式规则(参与密码破译) + 冲突消解
    │
    ▼
[07 存储导出] ─ JSONL / TSV / N-Triples
    │
    ▼
[08 可视化] ── Cytoscape.js 交互式多 Tab 页面
```

每个阶段生成独立中间文件（`outputs/0X_*/`），可单独运行和检查。

## 单独运行某个阶段

```bash
python main.py extract      # 文本抽取
python main.py preprocess   # 预处理
python main.py ner          # 实体识别（支持 --method all/gazetteer/crf/hmm/hmmlearn）
python main.py link         # 实体链接
python main.py relation     # 关系抽取
python main.py reason       # 推理
python main.py store        # 存储导出
python main.py graph        # 可视化
python main.py metrics      # 指标评估
```

## 迭代过程

本项目经过多轮方法迭代，每轮解决一个具体问题：

| 轮次 | 课程章节 | 目标 | 关键方法 | 效果 |
|------|----------|------|----------|------|
| 骨架重构 | — | 消除 tuple 级联返回 | PipelineContext 数据载体 | 架构清晰可扩展 |
| Ch2 知识表示 | 本体设计 | 扩充实体和关系 | 段落级 TF-IDF + POS 实体发现 | 21→46 实体, 43→110 三元组 |
| Ch4 实体识别 | NER 方法 | 多方法对比实验 | Gazetteer/CRF/HMM(手写)/HMM(hmmlearn) | 四方法统一接口可切换 |
| 开放域发现 | Ch4 扩展 | 打破封闭世界假设 | spaCy NER + 实体共现增强 | 发现 61 个高质量候选 |
| Ch6 关系抽取 | RE 方法 | 提升实体共现→三元组转换 | 正则 + 共现(触发词约束) + SVO | 转换率 7%→20%+ |
| Ch9 知识推理 | 推理 | 从已有知识推断新事实 | 产生式规则 + 冲突消解 | 8 条推理规则 |
| Ch5 实体消歧 | 消歧 | 清除碎片和假实体 | 自引用检测 + citation 过滤 | 垃圾实体清零, 孤立 35%→28% |

## 知识图谱现状

| 指标 | 数值 |
|------|------|
| Schema 实体 | 46 个（6 种类型 + 层级关系） |
| 关系类型 | 12 种 |
| 抽取三元组 | ~90 条 |
| 推理三元组 | ~5 条 |
| 语料规模 | 2 本书, 14,728 句 |

## 技术栈

- 中文分词: jieba
- NER: spaCy zh_core_web_sm + sklearn-crfsuite + 手写 HMM + hmmlearn
- 实体链接: TF-IDF 向量 + 余弦相似度 + 多特征排序
- 关系抽取: 正则模式 + 共现推断 + spaCy 依存句法
- 推理: 产生式规则
- 可视化: Cytoscape.js + Tailwind CSS

## 目录结构

```
├── turingkep/            # 核心代码
│   ├── pipeline.py       # PipelineContext + 流水线编排
│   ├── ner.py            # NER (Gazetteer/CRF)
│   ├── hmm_ner.py        # HMM (手写 + hmmlearn)
│   ├── linking.py        # 实体链接
│   ├── relation.py       # 关系抽取(正则)
│   ├── relation_methods.py # 关系抽取(共现/SVO)
│   ├── reasoning.py      # 产生式规则推理
│   ├── entity_discovery.py # 无监督实体发现
│   ├── open_entity.py    # 开放域实体发现 + 验证
│   ├── disambiguation.py # TF-IDF 聚类消歧
│   ├── graph_v2.py       # Cytoscape.js 可视化生成
│   └── records.py        # 数据记录类型
├── schema/               # 领域本体定义
├── data/                 # 原始语料 + 停用词表
├── experiments/          # 迭代日志
├── snapshots/            # 各轮迭代快照
│   ├── task1-ch2-schema/
│   ├── task2-ch4-ner/
│   ├── task3-open-discovery/
│   ├── task4-relation/
│   ├── task5-reasoning/
│   └── task6-disambiguation/
└── evaluation/           # 评估指标
```

## 依赖

```
beautifulsoup4, ebooklib, jieba, pypdf, requests,
scikit-learn, sklearn-crfsuite, hmmlearn, spacy
```

Python >= 3.12。

## 课程覆盖

- Ch2 知识表示: 本体设计, 类型层级, 实体属性
- Ch3 知识体系构建与融合: 实体验证, citation 过滤
- Ch4 实体识别: 词典/CRF/HMM 多方法对比
- Ch5 实体消歧: TF-IDF 聚类, 候选排序, NIL 判定
- Ch6 关系抽取: 正则模式, 远程监督, 依存句法
- Ch9 知识推理: 产生式规则, 冲突消解
