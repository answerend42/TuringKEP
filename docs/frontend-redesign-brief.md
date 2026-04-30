# TuringKG 前端可视化重设计概要

## 项目背景

TuringKG 是一个知识图谱构建流水线，从两本艾伦·图灵传记（中文 EPUB/PDF）中自动提取实体和关系，生成交互式知识图谱 HTML 页面。

当前前端使用 vis-network.js 渲染力导向图，功能简陋，需要整体重新设计。

## 当前技术栈

- **渲染**: vis-network.js 9.1.6（CDN 加载）
- **数据格式**: 单页 HTML，JSON 内嵌在 `<script>` 标签中
- **后端**: Python，生成 `turingkep/graph.py` → HTML 字符串

## 数据结构

前端接收的 JSON 结构（由后端 Python 生成）：

```json
{
  "nodes": [
    {
      "id": "person_alan_turing",
      "label": "艾伦·图灵",
      "group": "Person",
      "title": "英国数学家、逻辑学家...<br/>mentions: 4876<br/>关系图中可见",
      "value": 4876
    }
  ],
  "edges": [
    {
      "from": "person_alan_turing",
      "to": "artifact_enigma",
      "label": "破译",
      "relation_id": "decrypted",
      "value": 21,
      "avg_confidence": 0.85,
      "source": "extracted",
      "title": "source: extracted<br/>evidence sentence..."
    }
  ]
}
```

**节点字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| label | string | 显示名称 |
| group | string | 实体类型：Person / Organization / Place / Artifact / Concept / Event / Theory |
| title | string | hover tooltip（HTML） |
| value | number | mention 次数，用于控制节点大小 |

**边字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| from/to | string | 节点 id |
| label | string | 关系名（中文） |
| relation_id | string | 关系类型 id |
| value | number | 三元组数量 |
| avg_confidence | float | 平均置信度 |
| source | string | 来源方法（extracted/cooccurrence/inferred） |
| title | string | hover tooltip（HTML） |

**实体类型及其颜色约定**:
| 类型 | 当前颜色 | 建议 |
|------|----------|------|
| Person | #c8553d 红棕 | 保留暖色 |
| Organization | #457b9d 蓝 | 保留冷色 |
| Place | #6a994e 绿 | 保留 |
| Artifact | #8a5aab 紫 | 保留 |
| Concept | #dd8b2f 橙 | 保留 |
| Event | #264653 深绿 | 保留 |
| Theory | — | 新增 |

**关系类型**（10 种）:
出生于、逝世于、就读于、工作于、合作、提出或研制、破译、位于、影响、指导

## 当前问题

### 1. 缺少节点释义图例
节点按实体类型着色，但页面上没有任何图例说明颜色-类型的对应关系。

### 2. 节点和边样式粗糙
- 节点仅 dot/ellipse 两种形状，纯色填充，无立体感
- 边统一灰色，推理边虽有虚线区分但颜色几乎一致
- 字体 Georgia + 奶油色背景，风格陈旧
- 节点大小差异不够显著（mention 次数 1 vs 4876 视觉差距小）

### 3. 节点重叠严重
- 无初始布局策略，所有节点随机散布后靠物理模拟收敛
- 中心节点（艾伦·图灵，degree=83）被周边节点淹没
- 高密度区域节点互相遮挡，label 无法辨认

### 4. 无分层结构
- 单层力导向图，所有节点平铺在同一平面
- 无法区分：核心实体 → 直接关联 → 外围实体
- 没有按类型分组或层级环形布局

### 5. 交互功能缺失
- 无搜索框快速定位节点
- 无法点击高亮某节点的邻域
- 无类型/关系筛选开关
- 缩放后无 "fit to screen" 按钮

## 期望效果

### 布局
- **中心辐射式**：艾伦·图灵固定在画布中央，关联实体按关系层级环形分布
- 第一环：直接关联（一度关系）
- 第二环：间接关联（二度关系）
- 可选：按实体类型分区（Person 左上、Org 右上、Place 下方等）

### 视觉
- 节点按类型使用不同形状 + 颜色（Person=圆形, Org=方形, Place=菱形等）
- 边按关系类型用不同颜色，而不是统一灰色
- 推断边（inferred）用虚线，抽取边（extracted）用实线
- 节点大小显著区分重要度（mention 次数）
- 图例固定在左上角或右上角

### 交互
- 顶部搜索框，输入关键词实时过滤/高亮节点
- 点击节点 → 高亮该节点及其一度邻域，其他节点半透明
- 左侧图例面板带类型筛选开关（show/hide Person/Org/...）
- 缩放/平移控件，fit-to-screen 按钮
- Hover 显示 tooltip（实体描述 + mention 次数 + 关系列表）
- 点击边显示 evidence sentence

### 技术建议
- 可以用 D3.js、Cytoscape.js、G6（蚂蚁可视化）、ECharts 等替代 vis-network
- 数据格式可与后端协商调整
- 保持单页 HTML 可部署，或接受前后端分离
- 移动端响应式（可选）

## 课程方法呈现（重要）

这是知识工程课程项目，前端需要能**展示知识图谱的构建方法**，而不仅仅是最终结果。以下方法需要在界面上有对应的呈现方式：

### 1. 实体识别多方法对比（Ch4）
后端用了四种 NER 方法：词典（Gazetteer）、CRF、HMM（手写）、HMM（hmmlearn）。每种方法的产出不同。建议设计一个**方法对比面板**：
- 显示每种方法发现的实体数量和类型分布
- 可以用 toggle 切换查看单一方法的产出 vs 合并结果
- 每条边/triple 标注来源方法

### 2. 关系抽取三方法来源（Ch6）
每条三元组来自三种方法之一：正则模式（extracted）、共现推断（cooccurrence）、推理（inferred）。当前已通过 `edge.source` 字段传递。建议：
- 边按 source 用不同线型/颜色区分（extracted=实线、cooccurrence=虚线、inferred=点线）
- 图例中标注每种 source 的含义和数量

### 3. 推理链展示（Ch9）
推理三元组的 `edge.title` 中包含推理规则名和支持证据。建议：
- 点击推理边可展开推理链面板，显示规则模板 + 证据三元组列表
- 例如：点击"参与密码破译"边 → 弹出 "R1: decrypted(P, Artifact) => codebreaking_contribution(P, WWII)，证据: 21 条"

### 4. 实体类型层级（Ch2）
后端定义了实体类型之间的层级关系（Person ⊂ Agent ⊂ Entity）。如果设计支持，可以在图例面板中展示这个层级结构。

### 5. 迭代快照对比（全局）
项目经过 6 个 task 迭代，每次迭代后知识图谱的规模和质量都不同。`snapshots/` 目录下有每次迭代的摘要 JSON。建议：
- 页面底部加一个简单的"迭代历史"时间线或数字条
- 显示每次迭代的三元组数/实体数变化
- 不需要交互式切换，静态展示即可

### 6. 整体指标面板
页面某个位置显示关键数字：
- 实体总数、三元组总数、关系类型数
- 推理三元组数量（区分于抽取三元组）
- NER 各方法贡献比例

## 后端接口

Python 端生成 JSON 文件在 `outputs/08_graph/graph.json`。如需调整数据格式、新增字段、或提供额外的统计 JSON，直接告诉我。

## 联系人

后端/数据侧：我来协调
前端设计：stitch
