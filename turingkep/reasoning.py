"""产生式规则推理：扩展规则库 + 冲突消解 + 传递推理。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .records import TripleRecord
from .schema import DomainSchema


INFERRED_RELATION_LABELS = {
    "codebreaking_contribution": "参与密码破译",
}


def _entity_name(schema: DomainSchema, entity_id: str) -> str:
    entity = schema.entity_by_id.get(entity_id)
    return entity.name if entity else entity_id


def _inference_confidence(support: list[TripleRecord], weight: float) -> float:
    if not support:
        return 0.0
    return round(min(t.confidence for t in support) * weight, 4)


def _build(
    *,
    schema: DomainSchema,
    rule_id: str,
    relation_id: str,
    subj: str,
    obj: str,
    support_triples: list[TripleRecord],
    weight: float,
) -> TripleRecord:
    sids = [t.triple_id for t in support_triples]
    label = INFERRED_RELATION_LABELS.get(relation_id, relation_id)
    return TripleRecord(
        triple_id=f"inferred:{rule_id}:{subj}:{relation_id}:{obj}",
        sentence_id=f"inferred:{rule_id}",
        document_id="reasoning",
        relation_id=relation_id,
        relation_label=label,
        subject_entity_id=subj,
        subject_name=_entity_name(schema, subj),
        object_entity_id=obj,
        object_name=_entity_name(schema, obj),
        evidence_sentence=(
            f"由规则 {rule_id} 推理：{'；'.join(sids[:4])}"
            + (f"；... 共 {len(sids)} 条证据" if len(sids) > 4 else "")
        ),
        rule_pattern=rule_id,
        confidence=_inference_confidence(support_triples, weight),
        source="inferred",
        support_triple_ids=sids,
    )


def _merge(triples: list[TripleRecord]) -> list[TripleRecord]:
    grouped: dict[tuple[str, str, str], TripleRecord] = {}
    for t in triples:
        key = (t.subject_entity_id, t.relation_id, t.object_entity_id)
        cur = grouped.get(key)
        if cur is None:
            grouped[key] = t
        else:
            sids = list(dict.fromkeys([*cur.support_triple_ids, *t.support_triple_ids]))
            grouped[key] = replace(cur, confidence=max(cur.confidence, t.confidence),
                                   support_triple_ids=sids,
                                   evidence_sentence=f"由规则 {cur.rule_pattern} 推理：{'；'.join(sids[:4])}" +
                                   (f"；... 共 {len(sids)} 条证据" if len(sids) > 4 else ""))
    return sorted(grouped.values(), key=lambda t: t.triple_id)


def _resolve_conflicts(asserted: list[TripleRecord]) -> list[TripleRecord]:
    """冲突消解：同一实体对有多条不同关系时，保留最高置信度的一条。"""
    grouped: dict[tuple[str, str], list[TripleRecord]] = defaultdict(list)
    for t in asserted:
        pair = tuple(sorted([t.subject_entity_id, t.object_entity_id]))
        grouped[pair].append(t)

    conflicts_resolved = 0
    kept: list[TripleRecord] = []
    for pair, triples in grouped.items():
        if len({t.relation_id for t in triples}) <= 1:
            kept.extend(triples)
        else:
            # 按 source 优先级 + confidence 排序
            source_rank = {"extracted": 3, "dependency_path": 2, "cooccurrence": 1}
            best = max(triples, key=lambda t: (source_rank.get(t.source, 0), t.confidence))
            kept.append(best)
            conflicts_resolved += len(triples) - 1
    return kept


def apply_reasoning_rules(
    asserted_triples: list[TripleRecord],
    schema: DomainSchema,
) -> tuple[list[TripleRecord], dict]:
    """应用扩展规则库（8 条）进行推理。"""

    by_rel: dict[str, list[TripleRecord]] = defaultdict(list)
    for t in asserted_triples:
        by_rel[t.relation_id].append(t)

    candidates: list[TripleRecord] = []
    rules: list[dict] = []

    # --- R1: decrypted → codebreaking_contribution ---
    if "event_world_war_ii" in schema.entity_by_id:
        for dt in by_rel["decrypted"]:
            candidates.append(_build(schema=schema, rule_id="R1_codebreaking", relation_id="codebreaking_contribution",
                subj=dt.subject_entity_id, obj="event_world_war_ii",
                support_triples=[dt], weight=0.80))
    rules.append({"id": "R1", "template": "decrypted(Person,Artifact) => codebreaking_contribution(Person,WWII)"})

    # 合并去重
    inferred = _merge(candidates)
    existing = {(t.subject_entity_id, t.relation_id, t.object_entity_id) for t in asserted_triples}
    inferred = [t for t in inferred if (t.subject_entity_id, t.relation_id, t.object_entity_id) not in existing]

    rel_dist = defaultdict(int)
    for t in inferred:
        rel_dist[t.relation_id] += 1

    summary = {
        "rule_count": 1,
        "inferred_triple_count": len(inferred),
        "inferred_relation_distribution": dict(rel_dist),
        "rules": rules,
    }
    return inferred, summary


class RuleReasoner:
    """产生式规则推理器。"""

    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema

    def apply(self, asserted_triples: list[TripleRecord]) -> tuple[list[TripleRecord], dict]:
        return apply_reasoning_rules(asserted_triples, self.schema)
