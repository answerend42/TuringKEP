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
    by_sentence_mentions: dict[str, list[MentionRecord]] = defaultdict(list)
    for m in linked_mentions:
        if not m.is_nil and m.linked_entity_id:
            by_sentence[m.sentence_id].add(m.linked_entity_id)
            by_sentence_mentions[m.sentence_id].append(m)

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

            # 关键：检查是否至少有一句在实体之间包含关系触发词
            matched_sentences = []
            # 获取该实体对在每句中的位置
            for sid in sent_ids:
                st = sentence_map.get(sid)
                if st is None:
                    continue
                # 找到句中该实体对的 mention 位置
                sent_mentions = by_sentence_mentions.get(sid, [])
                pos_a = None
                pos_b = None
                for m in sent_mentions:
                    if m.linked_entity_id == eid_a:
                        pos_a = (m.start, m.end)
                    if m.linked_entity_id == eid_b:
                        pos_b = (m.start, m.end)
                if pos_a is None or pos_b is None:
                    continue
                left = min(pos_a[0], pos_b[0])
                right = max(pos_a[1], pos_b[1])
                between = st.text[left:right]
                for pattern in relation.patterns:
                    if pattern in between:
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
# 方法 B: spaCy 依存句法 SVO 关系抽取
# ============================================================================

# 动词 → 关系类型映射
VERB_RELATION_MAP = {
    "出生": "born_in", "生于": "born_in", "诞生": "born_in",
    "逝世": "died_in", "死于": "died_in", "去世": "died_in",
    "学习": "studied_at", "就读": "studied_at", "考入": "studied_at",
    "入学": "studied_at", "深造": "studied_at", "毕业": "studied_at",
    "工作": "worked_at", "任职": "worked_at", "加入": "worked_at",
    "任教": "worked_at", "供职": "worked_at",
    "合作": "collaborated_with", "共事": "collaborated_with",
    "提出": "developed", "发明": "developed", "设计": "developed",
    "研制": "developed", "开发": "developed", "建造": "developed",
    "破译": "decrypted", "破解": "decrypted", "解密": "decrypted",
    "位于": "located_in", "坐落": "located_in",
    "影响": "influenced", "启发": "influenced", "推动": "influenced",
    "指导": "supervised", "带领": "supervised",
}


def _spacy_svo_extract(
    text: str, entity_spans: list[tuple[int, int, str, str]]
) -> list[tuple[str, str, str, str]]:
    """用 spaCy 依存解析提取 (subject_id, verb, object_id, sentence_text)。"""
    import spacy
    try:
        nlp = spacy.load("zh_core_web_sm")
    except Exception:
        return []

    doc = nlp(text)

    # 建立 token 到实体 id 的映射
    token_entity: dict[int, str] = {}
    for start, end, eid, _ in entity_spans:
        for token in doc:
            if token.idx >= start and token.idx + len(token.text) <= end + 2:
                token_entity[token.i] = eid

    results: list[tuple[str, str, str, str]] = []
    for token in doc:
        if token.pos_ != "VERB":
            continue
        verb = token.text
        if verb not in VERB_RELATION_MAP:
            continue

        # 找主语和宾语
        subj_ids: set[str] = set()
        obj_ids: set[str] = set()
        for child in token.children:
            if child.dep_ in ("nsubj", "nsubjpass", "csubj"):
                # 递归收集主语子树中的实体
                for t in child.subtree:
                    if t.i in token_entity:
                        subj_ids.add(token_entity[t.i])
            elif child.dep_ in ("dobj", "obj", "obl", "nmod:prep"):
                for t in child.subtree:
                    if t.i in token_entity:
                        obj_ids.add(token_entity[t.i])

        rel_id = VERB_RELATION_MAP.get(verb)
        if rel_id and subj_ids and obj_ids:
            for sid in subj_ids:
                for oid in obj_ids:
                    if sid != oid:
                        results.append((sid, rel_id, oid, text[:150]))

    return results


def extract_by_dependency_path(
    linked_mentions: list[MentionRecord],
    sentence_records: list[SentenceRecord],
    schema: DomainSchema,
    min_pattern_support: int = 2,
) -> list[TripleRecord]:
    """spaCy 依存句法 SVO 关系抽取。

    对包含 2+ 个实体的句子做依存解析，提取主语-动词-宾语结构，
    将动词映射到关系类型。
    """
    sentence_map = {s.sentence_id: s for s in sentence_records}
    entity_by_id = schema.entity_by_id

    # 按句子组织实体 mention
    by_sentence: dict[str, list[MentionRecord]] = defaultdict(list)
    for m in linked_mentions:
        if not m.is_nil and m.linked_entity_id:
            by_sentence[m.sentence_id].append(m)

    triples: list[TripleRecord] = []
    seen: set[tuple[str, str, str]] = set()
    processed = 0

    for sent_id, mentions in by_sentence.items():
        if len(mentions) < 2:
            continue
        sent = sentence_map.get(sent_id)
        if not sent or len(sent.text) < 10:
            continue

        # 构建实体跨度
        entity_spans = [(m.start, m.end, m.linked_entity_id or "", m.text)
                        for m in mentions if m.linked_entity_id]

        svo_results = _spacy_svo_extract(sent.text, entity_spans)
        for subj_id, rel_id, obj_id, evidence in svo_results:
            key = (subj_id, rel_id, obj_id)
            if key in seen:
                continue
            if subj_id not in entity_by_id or obj_id not in entity_by_id:
                continue
            # 验证类型兼容
            subj_entity = entity_by_id[subj_id]
            obj_entity = entity_by_id[obj_id]
            rel = next((r for r in schema.relations if r.id == rel_id), None)
            if rel is None:
                continue
            if not (schema.type_matches(subj_entity.entity_type, rel.subject_types) and
                    schema.type_matches(obj_entity.entity_type, rel.object_types)):
                continue

            seen.add(key)
            triples.append(TripleRecord(
                triple_id=f"svo:{subj_id}:{rel_id}:{obj_id}",
                sentence_id=sent_id,
                document_id="spacy_svo",
                relation_id=rel_id,
                relation_label=rel.label,
                subject_entity_id=subj_id,
                subject_name=subj_entity.name,
                object_entity_id=obj_id,
                object_name=obj_entity.name,
                evidence_sentence=evidence,
                rule_pattern=f"svo({rel_id})",
                confidence=0.85,
                source="spacy_svo",
            ))
        processed += 1

    triples.sort(key=lambda t: t.triple_id)
    return triples
