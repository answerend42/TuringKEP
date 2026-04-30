"""轻量图存储与查询示例导出。"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .reasoning import INFERRED_RELATION_LABELS
from .records import MentionRecord, TripleRecord
from .schema import DomainSchema
from .utils import ensure_parent, write_json, write_jsonl


def _write_tsv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _display_path(path: Path, root_dir: Path) -> str:
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


def _entity_rows(
    schema: DomainSchema,
    linked_mentions: list[MentionRecord],
    triples: list[TripleRecord],
) -> list[dict[str, Any]]:
    mention_counts = Counter(
        mention.linked_entity_id
        for mention in linked_mentions
        if mention.linked_entity_id
    )
    degree_counts: Counter[str] = Counter()
    for triple in triples:
        degree_counts[triple.subject_entity_id] += 1
        degree_counts[triple.object_entity_id] += 1

    rows = []
    for entity in schema.entities:
        rows.append(
            {
                "entity_id": entity.id,
                "name": entity.name,
                "type": entity.entity_type,
                "aliases": "|".join(entity.aliases),
                "description": entity.description,
                "mention_count": mention_counts.get(entity.id, 0),
                "degree": degree_counts.get(entity.id, 0),
            }
        )
    return rows


def _relation_rows(schema: DomainSchema, triples: list[TripleRecord]) -> list[dict[str, Any]]:
    triple_counts = Counter(triple.relation_id for triple in triples)
    rows = [
        {
            "relation_id": relation.id,
            "label": relation.label,
            "subject_types": "|".join(relation.subject_types),
            "object_types": "|".join(relation.object_types),
            "source": "schema",
            "triple_count": triple_counts.get(relation.id, 0),
        }
        for relation in schema.relations
    ]
    for relation_id, label in INFERRED_RELATION_LABELS.items():
        rows.append(
            {
                "relation_id": relation_id,
                "label": label,
                "subject_types": "",
                "object_types": "",
                "source": "reasoning",
                "triple_count": triple_counts.get(relation_id, 0),
            }
        )
    return rows


def _fact_rows(triples: list[TripleRecord]) -> list[dict[str, Any]]:
    return [
        {
            "triple_id": triple.triple_id,
            "subject_id": triple.subject_entity_id,
            "subject_name": triple.subject_name,
            "relation_id": triple.relation_id,
            "relation_label": triple.relation_label,
            "object_id": triple.object_entity_id,
            "object_name": triple.object_name,
            "confidence": triple.confidence,
            "source": triple.source,
            "document_id": triple.document_id,
            "sentence_id": triple.sentence_id,
            "evidence": triple.evidence_sentence,
            "support_triple_ids": "|".join(triple.support_triple_ids),
        }
        for triple in triples
    ]


def _rdf_lines(triples: list[TripleRecord]) -> list[str]:
    lines = set()
    for triple in triples:
        subject = f"<urn:turingkep:entity:{triple.subject_entity_id}>"
        predicate = f"<urn:turingkep:relation:{triple.relation_id}>"
        obj = f"<urn:turingkep:entity:{triple.object_entity_id}>"
        lines.add(f"{subject} {predicate} {obj} .")
    return sorted(lines)


def _query_examples(
    schema: DomainSchema,
    triples: list[TripleRecord],
) -> list[dict[str, Any]]:
    center_id = schema.central_entity_id
    center_neighbors = []
    if center_id:
        for triple in triples:
            if triple.subject_entity_id == center_id or triple.object_entity_id == center_id:
                center_neighbors.append(
                    {
                        "subject": triple.subject_name,
                        "relation": triple.relation_label,
                        "object": triple.object_name,
                        "source": triple.source,
                        "confidence": triple.confidence,
                    }
                )
    relation_distribution = Counter(triple.relation_id for triple in triples)
    inferred_facts = [
        {
            "subject": triple.subject_name,
            "relation": triple.relation_label,
            "object": triple.object_name,
            "support_count": len(triple.support_triple_ids),
            "support_triple_ids": triple.support_triple_ids[:5],
        }
        for triple in triples
        if triple.source == "inferred"
    ]
    evidence_by_relation: dict[str, list[dict[str, str]]] = defaultdict(list)
    for triple in triples:
        if len(evidence_by_relation[triple.relation_id]) >= 3:
            continue
        evidence_by_relation[triple.relation_id].append(
            {
                "triple": f"{triple.subject_name} -{triple.relation_label}-> {triple.object_name}",
                "evidence": triple.evidence_sentence,
            }
        )

    return [
        {
            "name": "center_neighborhood",
            "purpose": "检索中心实体的一跳关系，用于展示图灵相关知识子图。",
            "query": f"MATCH (n)-[r]-(m) WHERE n.id = '{center_id}' RETURN n,r,m",
            "result_count": len(center_neighbors),
            "results": center_neighbors[:20],
        },
        {
            "name": "relation_distribution",
            "purpose": "统计关系类型分布，用于检查抽取结果是否过度集中。",
            "query": "MATCH ()-[r]->() RETURN type(r), count(*) ORDER BY count(*) DESC",
            "result_count": len(relation_distribution),
            "results": dict(relation_distribution),
        },
        {
            "name": "inferred_facts",
            "purpose": "查看规则推理新增事实，体现知识推理章节内容。",
            "query": "MATCH ()-[r]->() WHERE r.source = 'inferred' RETURN r",
            "result_count": len(inferred_facts),
            "results": inferred_facts[:20],
        },
        {
            "name": "evidence_samples",
            "purpose": "按关系类型抽样查看文本证据，方便课程报告做误差分析。",
            "query": "MATCH ()-[r]->() RETURN type(r), r.evidence LIMIT 3",
            "result_count": sum(len(items) for items in evidence_by_relation.values()),
            "results": dict(evidence_by_relation),
        },
    ]


class GraphStore:
    """图存储导出器：将实体、关系、事实导出为 JSONL/TSV/RDF 等格式。"""

    def __init__(self, schema: DomainSchema, output_dir: Path) -> None:
        self.schema = schema
        self.output_dir = output_dir

    def export(
        self,
        linked_mentions: list[MentionRecord],
        asserted_triples: list[TripleRecord],
        inferred_triples: list[TripleRecord],
    ) -> dict:
        return export_graph_store(
            schema=self.schema,
            linked_mentions=linked_mentions,
            asserted_triples=asserted_triples,
            inferred_triples=inferred_triples,
            output_dir=self.output_dir,
        )


def export_graph_store(
    *,
    schema: DomainSchema,
    linked_mentions: list[MentionRecord],
    asserted_triples: list[TripleRecord],
    inferred_triples: list[TripleRecord],
    output_dir: Path,
) -> dict[str, Any]:
    triples = [*asserted_triples, *inferred_triples]
    entity_rows = _entity_rows(schema, linked_mentions, triples)
    relation_rows = _relation_rows(schema, triples)
    fact_rows = _fact_rows(triples)
    query_examples = _query_examples(schema, triples)

    entities_path = output_dir / "entities.jsonl"
    relations_path = output_dir / "relations.jsonl"
    facts_path = output_dir / "facts.jsonl"
    facts_tsv_path = output_dir / "facts.tsv"
    rdf_path = output_dir / "triples.nt"
    queries_path = output_dir / "query_examples.json"

    write_jsonl(entities_path, entity_rows)
    write_jsonl(relations_path, relation_rows)
    write_jsonl(facts_path, fact_rows)
    _write_tsv(
        facts_tsv_path,
        fact_rows,
        [
            "triple_id",
            "subject_id",
            "subject_name",
            "relation_id",
            "relation_label",
            "object_id",
            "object_name",
            "confidence",
            "source",
            "document_id",
            "sentence_id",
            "evidence",
            "support_triple_ids",
        ],
    )
    ensure_parent(rdf_path)
    rdf_path.write_text("\n".join(_rdf_lines(triples)) + "\n", encoding="utf-8")
    write_json(queries_path, query_examples)

    root_dir = output_dir.parent.parent
    summary = {
        "entity_count": len(entity_rows),
        "relation_count": len(relation_rows),
        "asserted_triple_count": len(asserted_triples),
        "inferred_triple_count": len(inferred_triples),
        "fact_count": len(fact_rows),
        "paths": {
            "entities": _display_path(entities_path, root_dir),
            "relations": _display_path(relations_path, root_dir),
            "facts_jsonl": _display_path(facts_path, root_dir),
            "facts_tsv": _display_path(facts_tsv_path, root_dir),
            "rdf_triples": _display_path(rdf_path, root_dir),
            "query_examples": _display_path(queries_path, root_dir),
        },
    }
    write_json(output_dir / "store_summary.json", summary)
    return summary
