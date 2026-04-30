"""产生式规则推理：扩展规则库 + 冲突消解 + 传递推理。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .records import TripleRecord
from .schema import DomainSchema


INFERRED_RELATION_LABELS = {
    "associated_with_place": "关联地点",
    "codebreaking_contribution": "参与密码破译",
    "shared_affiliation": "同机构",
    "indirect_influence": "间接影响",
    "likely_colleague": "可能同事",
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

    # --- R1: studied_at/worked_at + located_in → associated_with_place ---
    located_by_org: dict[str, list[TripleRecord]] = defaultdict(list)
    for t in by_rel["located_in"]:
        located_by_org[t.subject_entity_id].append(t)

    for base in ("studied_at", "worked_at"):
        rid = f"R1_{base}_place"
        for rt in by_rel[base]:
            for lt in located_by_org.get(rt.object_entity_id, []):
                candidates.append(_build(schema=schema, rule_id=rid, relation_id="associated_with_place",
                    subj=rt.subject_entity_id, obj=lt.object_entity_id,
                    support_triples=[rt, lt], weight=0.85))
    rules.append({"id": "R1", "template": "studied_at/worked_at(P,Org) + located_in(Org,Place) => associated_with_place(P,Place)"})

    # --- R2: decrypted → codebreaking_contribution ---
    if "event_world_war_ii" in schema.entity_by_id:
        for dt in by_rel["decrypted"]:
            candidates.append(_build(schema=schema, rule_id="R2_codebreaking", relation_id="codebreaking_contribution",
                subj=dt.subject_entity_id, obj="event_world_war_ii",
                support_triples=[dt], weight=0.80))
    rules.append({"id": "R2", "template": "decrypted(Person,Artifact) => codebreaking_contribution(Person,WWII)"})

    # --- R3: supervised + developed → indirect_influence ---
    for st in by_rel["supervised"]:
        for dt in by_rel["developed"]:
            if st.object_entity_id == dt.subject_entity_id:
                candidates.append(_build(schema=schema, rule_id="R3_supervisor_influence", relation_id="indirect_influence",
                    subj=st.subject_entity_id, obj=dt.object_entity_id,
                    support_triples=[st, dt], weight=0.75))
    rules.append({"id": "R3", "template": "supervised(A,B) + developed(B,C) => indirect_influence(A,C)"})

    # --- R4: developed by same person → shared_affiliation between artifacts/concepts ---
    person_developed: dict[str, list[TripleRecord]] = defaultdict(list)
    for dt in by_rel["developed"]:
        person_developed[dt.subject_entity_id].append(dt)
    for person, devs in person_developed.items():
        for i in range(len(devs)):
            for j in range(i + 1, len(devs)):
                a, b = devs[i].object_entity_id, devs[j].object_entity_id
                if a != b:
                    candidates.append(_build(schema=schema, rule_id="R4_shared_creator", relation_id="shared_affiliation",
                        subj=a, obj=b, support_triples=[devs[i], devs[j]], weight=0.70))
    rules.append({"id": "R4", "template": "developed(P,A) + developed(P,B) => shared_affiliation(A,B)"})

    # --- R5: org co-members → likely_colleague ---
    org_members: dict[str, list[TripleRecord]] = defaultdict(list)
    for base in ("worked_at", "studied_at"):
        for t in by_rel[base]:
            org_members[t.object_entity_id].append(t)
    for org, members in org_members.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i].subject_entity_id, members[j].subject_entity_id
                if a != b:
                    candidates.append(_build(schema=schema, rule_id="R5_co_member", relation_id="likely_colleague",
                        subj=a, obj=b, support_triples=[members[i], members[j]], weight=0.65))
    rules.append({"id": "R5", "template": "worked_at/studied_at(A,Org) + worked_at/studied_at(B,Org) => likely_colleague(A,B)"})

    # --- R6: developed → influenced (概念影响) ---
    for dt in by_rel["developed"]:
        candidates.append(_build(schema=schema, rule_id="R6_developer_influence", relation_id="indirect_influence",
            subj=dt.subject_entity_id, obj=dt.object_entity_id,
            support_triples=[dt], weight=0.70))
    rules.append({"id": "R6", "template": "developed(Person,Concept) => indirect_influence(Person,Concept)"})

    # --- R7: born_in Person + located_in Place → associated_with_place ---
    for bt in by_rel["born_in"]:
        for lt in by_rel["located_in"]:
            candidates.append(_build(schema=schema, rule_id="R7_birthplace", relation_id="associated_with_place",
                subj=bt.subject_entity_id, obj=lt.object_entity_id,
                support_triples=[bt, lt], weight=0.60))
    rules.append({"id": "R7", "template": "born_in(P,Place1) + located_in(Org,Place2) => associated_with_place(P,Place2)"})

    # --- R8: influenced 传递 ---
    by_subj: dict[str, list[TripleRecord]] = defaultdict(list)
    for t in by_rel["influenced"]:
        by_subj[t.subject_entity_id].append(t)
    for t1 in by_rel["influenced"]:
        for t2 in by_subj.get(t1.object_entity_id, []):
            if t1.subject_entity_id != t2.object_entity_id:
                candidates.append(_build(schema=schema, rule_id="R8_transitive_influence", relation_id="indirect_influence",
                    subj=t1.subject_entity_id, obj=t2.object_entity_id,
                    support_triples=[t1, t2], weight=0.55))
    rules.append({"id": "R8", "template": "influenced(A,B) + influenced(B,C) => indirect_influence(A,C)"})

    # 合并去重
    inferred = _merge(candidates)
    existing = {(t.subject_entity_id, t.relation_id, t.object_entity_id) for t in asserted_triples}
    inferred = [t for t in inferred if (t.subject_entity_id, t.relation_id, t.object_entity_id) not in existing]

    rel_dist = defaultdict(int)
    for t in inferred:
        rel_dist[t.relation_id] += 1

    summary = {
        "rule_count": 8,
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
