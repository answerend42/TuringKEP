"""实体链接与消歧模块。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .records import MentionRecord, SentenceRecord
from .schema import DomainSchema


class EntityLinker:
    """Ch5 实体链接框架：候选生成 + 多特征排序 + 动态 NIL。"""

    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema
        self.entity_by_id = schema.entity_by_id
        self.exact_index: dict[str, list[str]] = defaultdict(list)
        self._entity_mention_count: dict[str, int] = defaultdict(int)
        alias_rows: list[tuple[str, str]] = []
        for entity in schema.entities:
            for alias in entity.all_names:
                key = alias.lower()
                if entity.id not in self.exact_index[key]:
                    self.exact_index[key].append(entity.id)
                alias_rows.append((entity.id, alias))

        self.alias_entity_ids = [entity_id for entity_id, _ in alias_rows]
        self.alias_texts = [alias for _, alias in alias_rows]
        self.alias_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.alias_matrix = self.alias_vectorizer.fit_transform(self.alias_texts)

        self.entity_profiles = [
            " ".join(jieba.lcut(" ".join([entity.name, *entity.aliases, entity.description])))
            for entity in schema.entities
        ]
        self.profile_vectorizer = TfidfVectorizer(tokenizer=str.split, lowercase=False)
        self.profile_matrix = self.profile_vectorizer.fit_transform(self.entity_profiles)
        self.profile_row_by_entity = {
            entity.id: index for index, entity in enumerate(schema.entities)
        }

        self._children_by_parent = schema.children_by_parent
        self._max_entity_count = 0

    def _type_compatibility(self, mention_type: str, entity_type: str) -> float:
        """Ch5 特征：类型兼容性评分。"""
        if mention_type == entity_type:
            return 0.30  # 精确匹配
        # 检查层级关系
        if (mention_type in self._children_by_parent and
                entity_type in self._children_by_parent[mention_type]):
            return 0.20  # 子类型→父类型
        if (entity_type in self._children_by_parent and
                mention_type in self._children_by_parent[entity_type]):
            return 0.15  # 父类型→子类型
        return 0.0  # 完全不兼容

    def _popularity_score(self, entity_id: str) -> float:
        """Ch5 特征：实体流行度（归一化对数频率）。"""
        if self._max_entity_count == 0:
            return 0.0
        count = self._entity_mention_count.get(entity_id, 1)
        import math
        return min(math.log(count + 1) / math.log(self._max_entity_count + 1), 1.0)

    def link(self, mention: MentionRecord, sentence_text: str) -> MentionRecord:
        """Ch5 完整链接：候选生成 → 多特征排序 → 动态 NIL。"""
        mention_text = mention.text.strip()
        mention_key = mention_text.lower()

        # Phase 1: 候选生成
        exact_candidates = list(self.exact_index.get(mention_key, []))
        alias_query = self.alias_vectorizer.transform([mention_text])
        alias_scores = cosine_similarity(alias_query, self.alias_matrix).ravel()

        candidate_scores: dict[str, float] = {}
        for entity_id in exact_candidates:
            candidate_scores[entity_id] = 1.0  # 精确匹配最高分

        top_indices = alias_scores.argsort()[::-1][:15]
        for index in top_indices:
            score = float(alias_scores[index])
            if score <= 0.1:
                continue
            entity_id = self.alias_entity_ids[index]
            candidate_scores[entity_id] = max(candidate_scores.get(entity_id, 0.0), score)

        if not candidate_scores:
            return replace(mention, is_nil=True, link_score=0.0)

        # Phase 2: 多特征排序
        context_tokens = " ".join(jieba.lcut(sentence_text))
        context_query = self.profile_vectorizer.transform([context_tokens])

        ranked: list[dict] = []
        for entity_id, alias_score in candidate_scores.items():
            entity = self.entity_by_id[entity_id]
            row_index = self.profile_row_by_entity[entity_id]
            context_score = float(
                cosine_similarity(context_query, self.profile_matrix[row_index]).ravel()[0]
            )
            type_score = self._type_compatibility(mention.entity_type, entity.entity_type)
            pop_score = self._popularity_score(entity_id)

            # 加权融合：字符串 0.4 + 上下文 0.2 + 类型 0.3 + 流行度 0.1
            final = 0.4 * alias_score + 0.2 * min(context_score, 1.0) + type_score + 0.1 * pop_score
            ranked.append({
                "entity_id": entity_id,
                "entity_name": entity.name,
                "entity_type": entity.entity_type,
                "alias_score": round(alias_score, 4),
                "context_score": round(context_score, 4),
                "type_score": round(type_score, 4),
                "pop_score": round(pop_score, 4),
                "final_score": round(final, 4),
            })

        ranked.sort(key=lambda x: float(x["final_score"]), reverse=True)

        # Phase 3: 动态 NIL 阈值
        if len(ranked) >= 2:
            top_scores = [float(r["final_score"]) for r in ranked[:3]]
            mean_top = sum(top_scores) / len(top_scores)
            nil_threshold = max(0.30, mean_top * 0.55)
        else:
            nil_threshold = 0.40

        top = ranked[0]
        accepted = float(top["final_score"]) >= nil_threshold

        return replace(
            mention,
            candidates=ranked[:5],
            linked_entity_id=top["entity_id"] if accepted else None,
            linked_entity_name=top["entity_name"] if accepted else None,
            link_score=float(top["final_score"]) if accepted else 0.0,
            is_nil=not accepted,
        )


def link_mentions(
    mentions: list[MentionRecord],
    sentence_records: list[SentenceRecord],
    schema: DomainSchema,
) -> list[MentionRecord]:
    sentence_map = {sentence.sentence_id: sentence for sentence in sentence_records}
    linker = EntityLinker(schema)
    return [
        linker.link(mention, sentence_map[mention.sentence_id].text)
        for mention in mentions
    ]
