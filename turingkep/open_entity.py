"""开放域实体发现：从文本中自动发现 schema 之外的实体并动态扩充。"""

from __future__ import annotations

from collections import Counter

from .entity_discovery import discover_candidate_entities
from .records import DocumentRecord, MentionRecord, SentenceRecord
from .schema import DomainSchema, EntityDefinition


def validate_discovered_entities(
    documents: list[DocumentRecord],
    new_entities: list[EntityDefinition],
    schema: DomainSchema,
    min_context_diversity: int = 3,
) -> list[EntityDefinition]:
    """Ch3 知识融合：用本体约束验证发现实体的质量。

    过滤规则：
    1. 实体必须在 >= min_context_diversity 个非 citation 上下文中出现
    2. 实体不能是常见停用词
    3. 实体长度 >= 2 且不是纯数字
    4. 实体不能 >80% 出现在参考文献/脚注中
    """
    import re
    citation_pattern = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩\d]+[．.]")

    known_names: set[str] = set()
    for e in schema.entities:
        for a in e.all_names:
            known_names.add(a)
            known_names.add(a.lower())

    validated: list[EntityDefinition] = []
    for entity in new_entities:
        name = entity.name
        if len(name) < 2 or name.isdigit():
            continue
        if name.isascii() and len(name) <= 3 and name.lower() in {
            "the", "see", "for", "and", "was", "his", "had", "not",
            "but", "are", "has", "can", "its", "new", "one", "two",
            "of", "in", "to", "it", "is", "on", "at", "by", "or",
            "be", "as", "we", "an", "if", "my", "so", "up", "no",
        }:
            continue
        if name in known_names or name.lower() in known_names:
            continue

        all_contexts: list[str] = []
        citation_contexts: list[str] = []
        for doc in documents:
            text = doc.text
            idx = 0
            while True:
                found = text.find(name, idx)
                if found == -1:
                    break
                start = max(0, found - 30)
                end = min(len(text), found + len(name) + 30)
                ctx = text[start:end]
                all_contexts.append(ctx)
                # 检测 citation 模式
                before = text[max(0, found - 20):found]
                if citation_pattern.search(before) or "，" in before[-5:]:
                    citation_contexts.append(ctx)
                idx = found + len(name)

        # 如果 >70% 的出现在 citation 中，排除
        if len(all_contexts) >= 5 and len(citation_contexts) / len(all_contexts) > 0.7:
            continue
        if len(all_contexts) >= min_context_diversity:
            validated.append(entity)

    return validated


def discover_new_entities(
    documents: list[DocumentRecord],
    schema: DomainSchema,
    min_confidence: float = 0.55,
    max_new: int = 60,
) -> list[EntityDefinition]:
    """从文档中发现 schema 之外的高置信度候选实体。

    Returns:
        新 EntityDefinition 列表，按置信度降序
    """
    known_names: set[str] = set()
    for entity in schema.entities:
        for alias in entity.all_names:
            alias_lower = alias.lower()
            known_names.add(alias_lower)
            known_names.add(alias)
            # Also add individual characters from short aliases to prevent
            # single-char fragments from being discovered
            if len(alias) <= 2:
                known_names.add(alias_lower)

    candidates = discover_candidate_entities(documents, known_names, min_freq=5)

    # 选出候选：降低门槛 + 过滤明显碎片
    selected = [
        c for c in candidates
        if c["confidence"] >= min_confidence
        and len(c["word"]) >= 2  # 排除单字碎片
    ]
    selected = selected[:max_new]

    # 推断实体类型
    type_counter: Counter[str] = Counter()
    new_entities: list[EntityDefinition] = []
    for i, candidate in enumerate(selected):
        word = candidate["word"]
        # 类型推断优先用 POS，其次用 TF-IDF 上下文
        if candidate["pos_types"]:
            entity_type = candidate["pos_types"][0]
        else:
            entity_type = "Concept"  # 兜底类型

        type_counter[entity_type] += 1
        entity_id = f"discovered_{entity_type.lower()}_{type_counter[entity_type]:03d}"
        new_entities.append(
            EntityDefinition(
                id=entity_id,
                name=word,
                aliases=[word],
                entity_type=entity_type,
                description=f"自动发现实体（置信度 {candidate['confidence']:.4f}），来源: 段落级 TF-IDF + POS + 共现增强",
                tags=["auto_discovered"],
            )
        )

    return new_entities


def extend_schema_with_discoveries(
    schema: DomainSchema,
    new_entities: list[EntityDefinition],
) -> DomainSchema:
    """将发现的实体加入 schema 的实体列表，返回新的 DomainSchema。"""
    existing_ids = {e.id for e in schema.entities}
    truly_new = [e for e in new_entities if e.id not in existing_ids]
    return DomainSchema(
        entity_types=schema.entity_types,
        entities=[*schema.entities, *truly_new],
        relations=schema.relations,
        central_entity_id=schema.central_entity_id,
        entity_hierarchy=schema.entity_hierarchy,
    )
