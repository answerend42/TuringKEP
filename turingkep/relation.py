"""基于规则的关系抽取模块。"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .records import MentionRecord, SentenceRecord, TripleRecord
from .schema import DomainSchema, EntityDefinition, RelationDefinition


@dataclass(frozen=True)
class TriggerMatch:
    pattern: str
    start: int
    end: int


def _entity_passes_tags(entity: EntityDefinition, required_tags: list[str]) -> bool:
    return not required_tags or bool(set(entity.tags) & set(required_tags))


def _entity_passes_types(
    mention: MentionRecord, relation: RelationDefinition, role: str, schema: DomainSchema
) -> bool:
    valid_types = relation.subject_types if role == "subject" else relation.object_types
    return schema.type_matches(mention.entity_type, valid_types)


def _gap_to_trigger(
    mention: MentionRecord,
    trigger_start: int,
    trigger_end: int,
    direction: str,
) -> int | None:
    if direction == "before":
        if mention.end <= trigger_start:
            return trigger_start - mention.end
        return None
    if direction == "after":
        if mention.start >= trigger_end:
            return mention.start - trigger_end
        return None
    if mention.end <= trigger_start:
        return trigger_start - mention.end
    if mention.start >= trigger_end:
        return mention.start - trigger_end
    return 0


def _trigger_matches(sentence_text: str, relation: RelationDefinition) -> list[TriggerMatch]:
    matches: list[TriggerMatch] = []
    for pattern in relation.patterns:
        for match in re.finditer(pattern, sentence_text):
            matches.append(TriggerMatch(pattern=pattern, start=match.start(), end=match.end()))
    matches.sort(key=lambda item: (item.start, item.end))
    return matches


def _candidate_mentions(
    mentions: list[MentionRecord],
    entity_by_id: dict[str, EntityDefinition],
    schema: DomainSchema,
    relation: RelationDefinition,
    role: str,
    trigger: TriggerMatch,
) -> list[tuple[int, MentionRecord]]:
    required_tags = relation.subject_tags if role == "subject" else relation.object_tags
    direction = relation.subject_direction if role == "subject" else relation.object_direction
    ranked: list[tuple[int, MentionRecord]] = []
    for mention in mentions:
        if mention.is_nil or mention.linked_entity_id is None:
            continue
        if not _entity_passes_types(mention, relation, role, schema):
            continue
        entity = entity_by_id[mention.linked_entity_id]
        if not _entity_passes_tags(entity, required_tags):
            continue
        gap = _gap_to_trigger(mention, trigger.start, trigger.end, direction)
        if gap is None or gap > relation.max_distance:
            continue
        ranked.append((gap, mention))
    ranked.sort(key=lambda item: (item[0], -item[1].link_score, item[1].start))
    return ranked


def _has_negative_pattern(
    relation: RelationDefinition,
    sentence_text: str,
    trigger: TriggerMatch,
    object_mention: MentionRecord,
) -> bool:
    if not relation.negative_patterns:
        return False
    left = min(trigger.start, object_mention.start)
    right = max(trigger.end, object_mention.end)
    snippet = sentence_text[left:right]
    return any(re.search(pattern, snippet) for pattern in relation.negative_patterns)


def _build_symmetric_triple(
    relation: RelationDefinition,
    sentence_record: SentenceRecord,
    mentions: list[MentionRecord],
    entity_by_id: dict[str, EntityDefinition],
    schema: DomainSchema,
    trigger: TriggerMatch,
) -> TripleRecord | None:
    ranked = _candidate_mentions(mentions, entity_by_id, schema, relation, "subject", trigger)
    usable = [mention for _, mention in ranked]
    for index, subject in enumerate(usable):
        for obj in usable[index + 1 :]:
            if subject.linked_entity_id == obj.linked_entity_id:
                continue
            subject_id = subject.linked_entity_id
            object_id = obj.linked_entity_id
            subject_name = subject.linked_entity_name or subject.text
            object_name = obj.linked_entity_name or obj.text
            if subject_id is None or object_id is None:
                continue
            if subject_id > object_id:
                subject_id, object_id = object_id, subject_id
                subject_name, object_name = object_name, subject_name
            return TripleRecord(
                triple_id=f"{sentence_record.sentence_id}:{relation.id}:{subject_id}:{object_id}",
                sentence_id=sentence_record.sentence_id,
                document_id=sentence_record.document_id,
                relation_id=relation.id,
                relation_label=relation.label,
                subject_entity_id=subject_id,
                subject_name=subject_name,
                object_entity_id=object_id,
                object_name=object_name,
                evidence_sentence=sentence_record.text,
                rule_pattern=trigger.pattern,
                confidence=round((subject.link_score + obj.link_score) / 2, 4),
            )
    return None


def _build_directional_triple(
    relation: RelationDefinition,
    sentence_record: SentenceRecord,
    mentions: list[MentionRecord],
    entity_by_id: dict[str, EntityDefinition],
    schema: DomainSchema,
    trigger: TriggerMatch,
) -> TripleRecord | None:
    subject_candidates = _candidate_mentions(mentions, entity_by_id, schema, relation, "subject", trigger)
    object_candidates = _candidate_mentions(mentions, entity_by_id, schema, relation, "object", trigger)

    for _, subject in subject_candidates:
        if subject.linked_entity_id is None:
            continue
        for _, obj in object_candidates:
            if obj.linked_entity_id is None:
                continue
            if subject.linked_entity_id == obj.linked_entity_id:
                continue
            if _has_negative_pattern(relation, sentence_record.text, trigger, obj):
                continue
            return TripleRecord(
                triple_id=f"{sentence_record.sentence_id}:{relation.id}:{subject.linked_entity_id}:{obj.linked_entity_id}",
                sentence_id=sentence_record.sentence_id,
                document_id=sentence_record.document_id,
                relation_id=relation.id,
                relation_label=relation.label,
                subject_entity_id=subject.linked_entity_id,
                subject_name=subject.linked_entity_name or subject.text,
                object_entity_id=obj.linked_entity_id,
                object_name=obj.linked_entity_name or obj.text,
                evidence_sentence=sentence_record.text,
                rule_pattern=trigger.pattern,
                confidence=round((subject.link_score + obj.link_score) / 2, 4),
            )
    return None


def resolve_relation_conflicts(triples: list[TripleRecord]) -> list[TripleRecord]:
    grouped: dict[tuple[str, str], list[TripleRecord]] = defaultdict(list)
    for triple in triples:
        grouped[(triple.subject_entity_id, triple.object_entity_id)].append(triple)

    resolved: list[TripleRecord] = []
    for pair, pair_triples in grouped.items():
        if len({triple.relation_id for triple in pair_triples}) <= 1:
            resolved.extend(pair_triples)
            continue
        pair_triples.sort(key=lambda item: (-item.confidence, item.relation_id))
        kept_ids: set[str] = set()
        for triple in pair_triples:
            if triple.relation_id in kept_ids:
                continue
            if kept_ids:
                break
            kept_ids.add(triple.relation_id)
            resolved.append(triple)
    resolved.sort(key=lambda item: item.triple_id)
    return resolved


class RelationExtractor:
    """基于规则的关系抽取器。"""

    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema

    def extract(
        self,
        linked_mentions: list[MentionRecord],
        sentences: list[SentenceRecord],
    ) -> list[TripleRecord]:
        return extract_relation_triples(linked_mentions, sentences, self.schema)


def extract_relation_triples(
    linked_mentions: list[MentionRecord],
    sentence_records: list[SentenceRecord],
    schema: DomainSchema,
) -> list[TripleRecord]:
    sentence_map = {sentence.sentence_id: sentence for sentence in sentence_records}
    mentions_per_sentence: dict[str, list[MentionRecord]] = defaultdict(list)
    for mention in linked_mentions:
        if not mention.is_nil:
            mentions_per_sentence[mention.sentence_id].append(mention)

    triples: list[TripleRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    entity_by_id = schema.entity_by_id

    for relation in schema.relations:
        for sentence_id, mentions in mentions_per_sentence.items():
            sentence_record = sentence_map[sentence_id]
            for trigger in _trigger_matches(sentence_record.text, relation):
                triple = (
                    _build_symmetric_triple(relation, sentence_record, mentions, entity_by_id, schema, trigger)
                    if relation.symmetric
                    else _build_directional_triple(relation, sentence_record, mentions, entity_by_id, schema, trigger)
                )
                if triple is None:
                    continue
                key = (
                    triple.sentence_id,
                    triple.subject_entity_id,
                    triple.relation_id,
                    triple.object_entity_id,
                )
                if key in seen:
                    continue
                seen.add(key)
                triples.append(triple)

    triples.sort(key=lambda item: item.triple_id)
    return resolve_relation_conflicts(triples)
