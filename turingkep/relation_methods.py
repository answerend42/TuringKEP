"""关系抽取多方法：共现统计 + 依存句法路径，补充正则模式匹配。"""

from __future__ import annotations

from collections import Counter, defaultdict

from .records import MentionRecord, SentenceRecord, TripleRecord
from .schema import DomainSchema, RelationDefinition


# ============================================================================
# 方法 A: 实体共现统计推断
# ============================================================================


def extract_by_cooccurrence(
    linked_mentions: list[MentionRecord],
    sentence_records: list[SentenceRecord],
    schema: DomainSchema,
    min_cooccur: int = 3,
) -> list[TripleRecord]:
    """基于实体共现 + 模式词验证的远程监督关系抽取。

    要求：两个实体在 >= min_cooccur 个句子中共现，且至少其中一句
    同时包含该关系的触发模式词。纯共现不产生三元组。
    """
    import re

    sentence_map = {s.sentence_id: s for s in sentence_records}

    # 统计实体对共现
    pair_sentences: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_sentence: dict[str, set[str]] = defaultdict(set)
    for m in linked_mentions:
        if not m.is_nil and m.linked_entity_id:
            by_sentence[m.sentence_id].add(m.linked_entity_id)

    for sent_id, eids in by_sentence.items():
        eid_list = list(eids)
        for i in range(len(eid_list)):
            for j in range(i + 1, len(eid_list)):
                pair = (eid_list[i], eid_list[j])
                pair_sentences[pair].append(sent_id)

    entity_by_id = schema.entity_by_id
    triples: list[TripleRecord] = []
    seen: set[tuple[str, str, str]] = set()

    for (eid_a, eid_b), sent_ids in pair_sentences.items():
        if len(sent_ids) < min_cooccur:
            continue

        entity_a = entity_by_id.get(eid_a)
        entity_b = entity_by_id.get(eid_b)
        if not entity_a or not entity_b:
            continue

        for relation in schema.relations:
            # 确定方向
            if schema.type_matches(entity_a.entity_type, relation.subject_types) and \
               schema.type_matches(entity_b.entity_type, relation.object_types):
                subj, obj = eid_a, eid_b
                subj_name, obj_name = entity_a.name, entity_b.name
            elif schema.type_matches(entity_b.entity_type, relation.subject_types) and \
                 schema.type_matches(entity_a.entity_type, relation.object_types):
                subj, obj = eid_b, eid_a
                subj_name, obj_name = entity_b.name, entity_a.name
            else:
                continue

            # 关键：检查是否至少有一句同时包含 实体对 + 模式词
            matched_sentences = []
            for sid in sent_ids:
                st = sentence_map.get(sid)
                if st is None:
                    continue
                for pattern in relation.patterns:
                    if pattern in st.text:
                        matched_sentences.append((sid, pattern))
                        break

            if not matched_sentences:
                continue  # 无模式词验证 → 跳过

            # 置信度：共现数 + 模式匹配句子数
            confidence = min(0.5 + 0.05 * len(matched_sentences), 0.90)
            sid, pattern = matched_sentences[0]
            evidence = sentence_map[sid].text[:150] if sid in sentence_map else ""

            key = (subj, relation.id, obj)
            if key in seen:
                continue
            seen.add(key)

            triples.append(TripleRecord(
                triple_id=f"cooccur:{subj}:{relation.id}:{obj}",
                sentence_id=sid,
                document_id="cooccurrence",
                relation_id=relation.id,
                relation_label=relation.label,
                subject_entity_id=subj,
                subject_name=subj_name,
                object_entity_id=obj,
                object_name=obj_name,
                evidence_sentence=evidence,
                rule_pattern=f"cooccur+trigger({pattern},{len(matched_sentences)})",
                confidence=round(confidence, 4),
                source="cooccurrence",
            ))

    triples.sort(key=lambda t: (t.confidence, t.triple_id), reverse=True)
    return triples


# ============================================================================
# 方法 B: 实体间词序列作为关系模式（简易依存路径）
# ============================================================================


def extract_by_dependency_path(
    linked_mentions: list[MentionRecord],
    sentence_records: list[SentenceRecord],
    schema: DomainSchema,
    min_pattern_support: int = 2,
) -> list[TripleRecord]:
    """提取实体间的词序列作为关系触发模式。

    对于每个句子中两个已链接实体之间的词序列，收集为候选模式。
    当同一模式在 >= min_pattern_support 对不同实体对之间出现时，
    生成三元组。
    """
    sentence_map = {s.sentence_id: s for s in sentence_records}

    # 收集每句中实体对及其之间的词序列
    by_sentence: dict[str, list[MentionRecord]] = defaultdict(list)
    for m in linked_mentions:
        if not m.is_nil and m.linked_entity_id:
            by_sentence[m.sentence_id].append(m)

    # pattern → [(eid_a, eid_b, sentence_id)]
    pattern_pairs: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    entity_by_id = schema.entity_by_id

    for sent_id, mentions in by_sentence.items():
        sent = sentence_map.get(sent_id)
        if not sent:
            continue

        for i in range(len(mentions)):
            for j in range(i + 1, len(mentions)):
                m_a, m_b = mentions[i], mentions[j]
                if m_a.linked_entity_id == m_b.linked_entity_id:
                    continue
                if not m_a.linked_entity_id or not m_b.linked_entity_id:
                    continue

                # 提取两实体之间（或附近）的词
                left = min(m_a.start, m_b.start)
                right = max(m_a.end, m_b.end)
                between_text = sent.text[left:right].strip()

                if 2 <= len(between_text) <= 30:
                    pattern_pairs[between_text].append(
                        (m_a.linked_entity_id, m_b.linked_entity_id, sent_id)
                    )

    # 用高频模式生成三元组
    triples: list[TripleRecord] = []
    seen: set[tuple[str, str, str, str]] = set()

    for pattern, pairs in pattern_pairs.items():
        if len(pairs) < min_pattern_support:
            continue

        for eid_a, eid_b, sent_id in pairs[:5]:
            entity_a = entity_by_id.get(eid_a)
            entity_b = entity_by_id.get(eid_b)
            if not entity_a or not entity_b:
                continue

            # 尝试匹配关系类型
            matched_relation = None
            for relation in schema.relations:
                if (schema.type_matches(entity_a.entity_type, relation.subject_types) and
                        schema.type_matches(entity_b.entity_type, relation.object_types)):
                    matched_relation = relation
                    break

            if matched_relation is None:
                continue

            key = (sent_id, eid_a, matched_relation.id, eid_b)
            if key in seen:
                continue
            seen.add(key)

            sample_sent = sentence_map.get(sent_id)
            evidence = sample_sent.text[:120] if sample_sent else ""
            triples.append(TripleRecord(
                triple_id=f"deppath:{eid_a}:{matched_relation.id}:{eid_b}",
                sentence_id=sent_id,
                document_id="dependency_path",
                relation_id=matched_relation.id,
                relation_label=matched_relation.label,
                subject_entity_id=eid_a,
                subject_name=entity_a.name,
                object_entity_id=eid_b,
                object_name=entity_b.name,
                evidence_sentence=evidence,
                rule_pattern=f"deppath({pattern[:40]})",
                confidence=round(min(len(pairs) / 5, 0.90), 4),
                source="dependency_path",
            ))

    triples.sort(key=lambda t: t.triple_id)
    return triples
