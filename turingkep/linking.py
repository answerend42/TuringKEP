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
    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema
        self.entity_by_id = schema.entity_by_id
        self.exact_index: dict[str, list[str]] = defaultdict(list)
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

    def link(self, mention: MentionRecord, sentence_text: str) -> MentionRecord:
        mention_text = mention.text.strip()
        mention_key = mention_text.lower()
        exact_candidates = list(self.exact_index.get(mention_key, []))

        alias_query = self.alias_vectorizer.transform([mention_text])
        alias_scores = cosine_similarity(alias_query, self.alias_matrix).ravel()

        candidate_scores: dict[str, float] = {}
        for entity_id in exact_candidates:
            candidate_scores[entity_id] = 1.0

        top_indices = alias_scores.argsort()[::-1][:12]
        for index in top_indices:
            score = float(alias_scores[index])
            if score <= 0:
                continue
            entity_id = self.alias_entity_ids[index]
            candidate_scores[entity_id] = max(candidate_scores.get(entity_id, 0.0), score)

        context_tokens = " ".join(jieba.lcut(sentence_text))
        context_query = self.profile_vectorizer.transform([context_tokens])

        ranked_candidates: list[dict[str, float | str]] = []
        for entity_id, alias_score in candidate_scores.items():
            entity = self.entity_by_id[entity_id]
            row_index = self.profile_row_by_entity[entity_id]
            context_score = float(
                cosine_similarity(context_query, self.profile_matrix[row_index]).ravel()[0]
            )
            type_bonus = 0.15 if mention.entity_type == entity.entity_type else 0.0
            final_score = 0.7 * alias_score + 0.3 * context_score + type_bonus
            ranked_candidates.append(
                {
                    "entity_id": entity_id,
                    "entity_name": entity.name,
                    "entity_type": entity.entity_type,
                    "alias_score": round(alias_score, 4),
                    "context_score": round(context_score, 4),
                    "final_score": round(final_score, 4),
                }
            )

        ranked_candidates.sort(key=lambda item: float(item["final_score"]), reverse=True)
        top_candidate = ranked_candidates[0] if ranked_candidates else None
        accepted = top_candidate is not None and float(top_candidate["final_score"]) >= 0.35

        return replace(
            mention,
            candidates=ranked_candidates[:5],
            linked_entity_id=top_candidate["entity_id"] if accepted and top_candidate else None,
            linked_entity_name=top_candidate["entity_name"] if accepted and top_candidate else None,
            link_score=float(top_candidate["final_score"]) if accepted and top_candidate else 0.0,
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
