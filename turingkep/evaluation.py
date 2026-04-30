"""自动化质量指标，便于横向比较实验方案。"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .records import MentionRecord, SentenceRecord, TokenRecord, TripleRecord
from .schema import DomainSchema


def _component_ratio(
    node_ids: set[str], edges: list[tuple[str, str]], center_id: str | None
) -> float:
    if not node_ids:
        return 0.0
    if center_id is None or center_id not in node_ids:
        return 0.0
    adjacency = {node_id: set() for node_id in node_ids}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen = {center_id}
    stack = [center_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return round(len(seen) / len(node_ids), 4)


def _overlapping_tokens(
    tokens: list[TokenRecord], start: int, end: int
) -> list[TokenRecord]:
    return [
        token
        for token in tokens
        if token.start < end and token.end > start
    ]


def _token_boundary_metrics(
    sentence_records: list[SentenceRecord],
    mentions: list[MentionRecord],
) -> dict[str, float]:
    sentence_map = {
        sentence.sentence_id: sentence
        for sentence in sentence_records
    }
    aligned_count = 0
    fragmented_counts: list[int] = []
    for mention in mentions:
        sentence = sentence_map.get(mention.sentence_id)
        if sentence is None:
            continue
        overlapping = _overlapping_tokens(sentence.tokens, mention.start, mention.end)
        if not overlapping:
            continue
        fragmented_counts.append(len(overlapping))
        if overlapping[0].start == mention.start and overlapping[-1].end == mention.end:
            aligned_count += 1

    mention_count = len(fragmented_counts)
    return {
        "count": mention_count,
        "boundary_alignment_rate": round(aligned_count / mention_count, 4)
        if mention_count
        else 0.0,
        "fragmentation_mean": round(mean(fragmented_counts), 4)
        if fragmented_counts
        else 0.0,
        "single_token_rate": round(
            sum(1 for value in fragmented_counts if value == 1) / mention_count,
            4,
        )
        if mention_count
        else 0.0,
    }


def compute_pipeline_metrics(
    schema: DomainSchema,
    sentence_records: list[SentenceRecord],
    linked_mentions: list[MentionRecord],
    triples: list[TripleRecord],
    graph_payload: dict[str, Any],
    projection_stats: dict[str, Any],
) -> dict[str, Any]:
    linked_entity_ids = {
        mention.linked_entity_id
        for mention in linked_mentions
        if mention.linked_entity_id
    }
    triple_node_ids = {
        triple.subject_entity_id for triple in triples
    } | {
        triple.object_entity_id for triple in triples
    }

    pair_relations: dict[tuple[str, str], set[str]] = defaultdict(set)
    for triple in triples:
        pair_relations[(triple.subject_entity_id, triple.object_entity_id)].add(triple.relation_id)
    conflicting_pairs = {
        f"{left}->{right}": sorted(relations)
        for (left, right), relations in pair_relations.items()
        if len(relations) > 1
    }

    final_edges = graph_payload["edges"]
    final_nodes = graph_payload["nodes"]
    support_values = [edge["value"] for edge in final_edges]
    link_scores = [mention.link_score for mention in linked_mentions if not mention.is_nil]
    linked_non_nil_mentions = [mention for mention in linked_mentions if not mention.is_nil]
    gazetteer_mentions = [mention for mention in linked_mentions if mention.source == "gazetteer"]

    raw_graph_edges = [(triple.subject_entity_id, triple.object_entity_id) for triple in triples]
    final_graph_edges = [(edge["from"], edge["to"]) for edge in final_edges]
    tokenizer_proxy = {
        "linked_mentions": _token_boundary_metrics(sentence_records, linked_non_nil_mentions),
        "gazetteer_mentions": _token_boundary_metrics(sentence_records, gazetteer_mentions),
        "token_count": sum(len(sentence.tokens) for sentence in sentence_records),
        "average_sentence_tokens": round(
            mean(len(sentence.tokens) for sentence in sentence_records),
            4,
        )
        if sentence_records
        else 0.0,
    }

    metrics = {
        "linked_entity_count": len(linked_entity_ids),
        "triple_node_count": len(triple_node_ids),
        "triple_count": len(triples),
        "triple_source_distribution": dict(Counter(triple.source for triple in triples)),
        "relation_distribution": dict(Counter(triple.relation_id for triple in triples)),
        "nil_rate": round(
            sum(1 for mention in linked_mentions if mention.is_nil) / len(linked_mentions),
            4,
        )
        if linked_mentions
        else 0.0,
        "average_link_score": round(mean(link_scores), 4) if link_scores else 0.0,
        "raw_orphan_node_ratio": round(
            len(linked_entity_ids - triple_node_ids) / len(linked_entity_ids),
            4,
        )
        if linked_entity_ids
        else 0.0,
        "raw_center_component_ratio": _component_ratio(
            linked_entity_ids,
            raw_graph_edges,
            schema.central_entity_id,
        ),
        "projected_orphan_node_ratio": 0.0,
        "projected_center_component_ratio": _component_ratio(
            {node["id"] for node in final_nodes},
            final_graph_edges,
            schema.central_entity_id,
        ),
        "conflict_pair_ratio": round(
            len(conflicting_pairs) / len(pair_relations),
            4,
        )
        if pair_relations
        else 0.0,
        "conflicting_pairs": conflicting_pairs,
        "single_support_edge_ratio": round(
            sum(1 for value in support_values if value == 1) / len(support_values),
            4,
        )
        if support_values
        else 0.0,
        "average_edge_support": round(mean(support_values), 4) if support_values else 0.0,
        "tokenizer_proxy": tokenizer_proxy,
        "projection": projection_stats,
    }
    return metrics
