"""产生式规则推理：在抽取三元组上补少量可解释事实。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .records import TripleRecord
from .schema import DomainSchema


INFERRED_RELATION_LABELS = {
    "associated_with_place": "关联地点",
    "codebreaking_contribution": "参与密码破译",
}


def _entity_name(schema: DomainSchema, entity_id: str) -> str:
    entity = schema.entity_by_id.get(entity_id)
    return entity.name if entity else entity_id


def _inference_confidence(support_triples: list[TripleRecord], weight: float) -> float:
    if not support_triples:
        return 0.0
    return round(min(triple.confidence for triple in support_triples) * weight, 4)


def _build_inferred_triple(
    *,
    schema: DomainSchema,
    rule_id: str,
    relation_id: str,
    subject_entity_id: str,
    object_entity_id: str,
    support_triples: list[TripleRecord],
    confidence_weight: float,
) -> TripleRecord:
    support_ids = [triple.triple_id for triple in support_triples]
    support_text = "；".join(support_ids[:4])
    if len(support_ids) > 4:
        support_text += f"；... 共 {len(support_ids)} 条证据"
    return TripleRecord(
        triple_id=f"inferred:{rule_id}:{subject_entity_id}:{relation_id}:{object_entity_id}",
        sentence_id=f"inferred:{rule_id}",
        document_id="reasoning",
        relation_id=relation_id,
        relation_label=INFERRED_RELATION_LABELS[relation_id],
        subject_entity_id=subject_entity_id,
        subject_name=_entity_name(schema, subject_entity_id),
        object_entity_id=object_entity_id,
        object_name=_entity_name(schema, object_entity_id),
        evidence_sentence=f"由规则 {rule_id} 根据证据三元组推理得到：{support_text}",
        rule_pattern=rule_id,
        confidence=_inference_confidence(support_triples, confidence_weight),
        source="inferred",
        support_triple_ids=support_ids,
    )


def _merge_inferred_triples(triples: list[TripleRecord]) -> list[TripleRecord]:
    grouped: dict[tuple[str, str, str], TripleRecord] = {}
    for triple in triples:
        key = (triple.subject_entity_id, triple.relation_id, triple.object_entity_id)
        current = grouped.get(key)
        if current is None:
            grouped[key] = triple
            continue
        support_ids = [*current.support_triple_ids]
        for support_id in triple.support_triple_ids:
            if support_id not in support_ids:
                support_ids.append(support_id)
        grouped[key] = replace(
            current,
            confidence=max(current.confidence, triple.confidence),
            support_triple_ids=support_ids,
            evidence_sentence=(
                f"由规则 {current.rule_pattern} 根据证据三元组推理得到："
                + "；".join(support_ids[:4])
                + (f"；... 共 {len(support_ids)} 条证据" if len(support_ids) > 4 else "")
            ),
        )
    return sorted(grouped.values(), key=lambda item: item.triple_id)


class RuleReasoner:
    """产生式规则推理器：在抽取三元组上补少量可解释事实。"""

    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema

    def apply(
        self,
        asserted_triples: list[TripleRecord],
    ) -> tuple[list[TripleRecord], dict]:
        return apply_reasoning_rules(asserted_triples, self.schema)


def apply_reasoning_rules(
    asserted_triples: list[TripleRecord],
    schema: DomainSchema,
) -> tuple[list[TripleRecord], dict[str, object]]:
    """Apply a tiny set of deterministic rules over extracted triples."""

    by_relation: dict[str, list[TripleRecord]] = defaultdict(list)
    for triple in asserted_triples:
        by_relation[triple.relation_id].append(triple)

    located_by_org: dict[str, list[TripleRecord]] = defaultdict(list)
    for triple in by_relation["located_in"]:
        located_by_org[triple.subject_entity_id].append(triple)

    candidates: list[TripleRecord] = []

    for base_relation in ("studied_at", "worked_at"):
        rule_id = f"R1_{base_relation}_place"
        for relation_triple in by_relation[base_relation]:
            for location_triple in located_by_org.get(relation_triple.object_entity_id, []):
                candidates.append(
                    _build_inferred_triple(
                        schema=schema,
                        rule_id=rule_id,
                        relation_id="associated_with_place",
                        subject_entity_id=relation_triple.subject_entity_id,
                        object_entity_id=location_triple.object_entity_id,
                        support_triples=[relation_triple, location_triple],
                        confidence_weight=0.85,
                    )
                )

    if "event_world_war_ii" in schema.entity_by_id:
        for decrypted_triple in by_relation["decrypted"]:
            candidates.append(
                _build_inferred_triple(
                    schema=schema,
                    rule_id="R2_decrypted_enigma_wartime_contribution",
                    relation_id="codebreaking_contribution",
                    subject_entity_id=decrypted_triple.subject_entity_id,
                    object_entity_id="event_world_war_ii",
                    support_triples=[decrypted_triple],
                    confidence_weight=0.8,
                )
            )

    inferred_triples = _merge_inferred_triples(candidates)
    existing_keys = {
        (triple.subject_entity_id, triple.relation_id, triple.object_entity_id)
        for triple in asserted_triples
    }
    inferred_triples = [
        triple
        for triple in inferred_triples
        if (triple.subject_entity_id, triple.relation_id, triple.object_entity_id)
        not in existing_keys
    ]
    summary = {
        "rule_count": 3,
        "inferred_triple_count": len(inferred_triples),
        "inferred_relation_distribution": {
            relation_id: sum(1 for triple in inferred_triples if triple.relation_id == relation_id)
            for relation_id in sorted(INFERRED_RELATION_LABELS)
        },
        "rules": [
            {
                "id": "R1_studied_at_place",
                "template": "studied_at(Person, Organization) + located_in(Organization, Place) => associated_with_place(Person, Place)",
            },
            {
                "id": "R1_worked_at_place",
                "template": "worked_at(Person, Organization) + located_in(Organization, Place) => associated_with_place(Person, Place)",
            },
            {
                "id": "R2_decrypted_enigma_wartime_contribution",
                "template": "decrypted(Person, Artifact) => codebreaking_contribution(Person, World War II)",
            },
        ],
    }
    return inferred_triples, summary
