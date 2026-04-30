"""Ch5 实体消歧：TF-IDF 词袋向量 + 余弦相似度聚类 + 碎片合并。"""

from __future__ import annotations

from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .records import MentionRecord
from .schema import DomainSchema


def build_mention_context_vectors(
    mentions: list[MentionRecord],
    sentence_map: dict[str, str],
) -> tuple[list[str], list[str], "np.ndarray"]:
    """为每个 mention 构建 TF-IDF 上下文向量。

    Returns: (mention_ids, context_texts, similarity_matrix)
    """
    import numpy as np
    mention_ids: list[str] = []
    contexts: list[str] = []
    for m in mentions:
        if not m.linked_entity_id:
            continue
        text = sentence_map.get(m.sentence_id, "")
        if not text:
            continue
        # 上下文窗口：mention 前后各 50 字符
        start = max(0, m.start - 50)
        end = min(len(text), m.end + 50)
        context = text[start:end]
        mention_ids.append(m.mention_id)
        contexts.append(context)

    if len(contexts) < 2:
        return mention_ids, contexts, np.array([[]])

    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(2, 3), max_features=500
    )
    matrix = vectorizer.fit_transform(contexts)
    return mention_ids, contexts, matrix


def cluster_entity_fragments(
    linked_mentions: list[MentionRecord],
    sentence_map: dict[str, str],
    schema: DomainSchema,
    threshold: float = 0.75,
) -> dict[str, str]:
    """基于 TF-IDF 余弦相似度聚类，将碎片实体合并到完整实体。

    规则：
    - 如果实体 A 是实体 B 的子串（名称上），且 A 的 mentions 与 B 的 mentions
      上下文相似度 > threshold，则将 A 合并到 B
    - 返回 {fragment_id: canonical_id} 映射

    这是 Ch5 聚类消歧的直接应用：词袋模型 + 余弦相似度。
    """
    entity_by_id = schema.entity_by_id
    all_entities = {m.linked_entity_id for m in linked_mentions if m.linked_entity_id}

    # 找出潜在的母子串关系
    entity_names: dict[str, str] = {}
    for eid in all_entities:
        entity = entity_by_id.get(eid)
        if entity:
            entity_names[eid] = entity.name

    # 收集每个实体的 mention 上下文
    entity_contexts: dict[str, list[str]] = defaultdict(list)
    for m in linked_mentions:
        if not m.linked_entity_id or m.linked_entity_id not in all_entities:
            continue
        text = sentence_map.get(m.sentence_id, "")
        if text:
            start = max(0, m.start - 40)
            end = min(len(text), m.end + 40)
            entity_contexts[m.linked_entity_id].append(text[start:end])

    # 对每个短实体（名称长度 ≤ 2），找是否被长实体包含
    merges: dict[str, str] = {}
    short_entities = [
        eid for eid in all_entities
        if eid in entity_names and len(entity_names[eid]) <= 2
        and eid.startswith("discovered_")
    ]
    long_entities = [
        eid for eid in all_entities
        if eid in entity_names and len(entity_names[eid]) >= 3
    ]

    for short_eid in short_entities:
        short_name = entity_names[short_eid]
        short_contexts = entity_contexts[short_eid]
        if len(short_contexts) < 2:
            continue

        # 找包含 short_name 的长实体
        candidates = [
            leid for leid in long_entities
            if short_name in entity_names[leid]
        ]
        if not candidates:
            continue

        best_sim = 0.0
        best_candidate = None
        for leid in candidates:
            long_contexts = entity_contexts[leid]
            if len(long_contexts) < 2:
                continue
            # 计算两个实体上下文的平均相似度
            try:
                vectorizer = TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(2, 3), max_features=200
                )
                all_contexts = short_contexts + long_contexts
                matrix = vectorizer.fit_transform(all_contexts)
                n_short = len(short_contexts)
                sim_matrix = cosine_similarity(
                    matrix[:n_short], matrix[n_short:]
                )
                avg_sim = float(sim_matrix.mean())
                if avg_sim > best_sim:
                    best_sim = avg_sim
                    best_candidate = leid
            except Exception:
                continue

        if best_candidate and best_sim >= threshold:
            merges[short_eid] = best_candidate

    return merges
