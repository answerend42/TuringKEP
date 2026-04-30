"""流水线编排：按阶段组织整个 TuringKG 实验。"""

from __future__ import annotations

from dataclasses import dataclass, field

import jieba

from .evaluation import compute_pipeline_metrics
from .graph import build_graph_payload, generate_graph_html
from .ingestion import discover_book_files, extract_documents
from .linking import link_mentions
from .hmm_ner import HMMExtractor, HMMLearnExtractor
from .ner import CrfResult, GazetteerExtractor, CRFExtractor, merge_mentions
from .ner_comparison import compute_ner_comparison
from .open_entity import discover_new_entities, extend_schema_with_discoveries, validate_discovered_entities
from .disambiguation import cluster_entity_fragments
from .relation_methods import extract_by_cooccurrence, extract_by_dependency_path
from .paths import (
    EVALUATION_DIR,
    EXTRACTED_DIR,
    GRAPH_DIR,
    LINKING_DIR,
    NER_DIR,
    OUTPUT_DIR,
    PREPROCESSED_DIR,
    REASONING_DIR,
    RELATION_DIR,
    ROOT_DIR,
    STORAGE_DIR,
    ensure_runtime_dirs,
)
from .preprocess import build_sentence_records
from .records import DocumentRecord, MentionRecord, SentenceRecord, TripleRecord, save_records
from .relation import RelationExtractor
from .reasoning import RuleReasoner, _resolve_conflicts
from .schema import DomainSchema, load_domain_schema
from .storage import GraphStore
from .utils import write_json


@dataclass
class PipelineContext:
    """流水线上下文：存储所有阶段的输入输出数据。

    各阶段函数通过修改此上下文对象来传递数据，避免级联参数透传。
    """

    schema: DomainSchema | None = None
    documents: list[DocumentRecord] = field(default_factory=list)
    sentences: list[SentenceRecord] = field(default_factory=list)
    gazetteer_mentions: list[MentionRecord] = field(default_factory=list)
    crf_result: CrfResult | None = None
    hmm_result: CrfResult | None = None
    hmmlearn_result: CrfResult | None = None
    ner_method: str = "all"
    discovered_entity_count: int = 0
    discovered_mention_count: int = 0
    fragment_merge_count: int = 0
    merged_mentions: list[MentionRecord] = field(default_factory=list)
    linked_mentions: list[MentionRecord] = field(default_factory=list)
    asserted_triples: list[TripleRecord] = field(default_factory=list)
    inferred_triples: list[TripleRecord] = field(default_factory=list)
    all_triples: list[TripleRecord] = field(default_factory=list)
    crf_metrics: dict[str, Any] = field(default_factory=dict)
    reasoning_summary: dict[str, Any] = field(default_factory=dict)
    store_summary: dict[str, Any] = field(default_factory=dict)
    graph_payload: dict[str, Any] = field(default_factory=dict)
    projection_stats: dict[str, Any] = field(default_factory=dict)
    relation_stats: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


def run_extract_stage(ctx: PipelineContext) -> None:
    """抽取阶段：发现并读取 EPUB/PDF 文档。"""
    book_paths = discover_book_files()
    if not book_paths:
        raise FileNotFoundError("No EPUB/PDF book files found under data/.")
    ctx.documents = extract_documents(book_paths)
    save_records(EXTRACTED_DIR / "documents.jsonl", ctx.documents)


def run_preprocess_stage(ctx: PipelineContext) -> None:
    """预处理阶段：分句与分词。"""
    ctx.sentences = build_sentence_records(ctx.documents)
    save_records(PREPROCESSED_DIR / "sentences.jsonl", ctx.sentences)


def run_ner_stage(ctx: PipelineContext) -> None:
    """实体识别阶段：词典 + CRF + HMM（手写） + HMM（hmmlearn）。"""
    gazetteer_ext = GazetteerExtractor(ctx.schema)
    ctx.gazetteer_mentions = gazetteer_ext.extract(ctx.sentences)
    save_records(NER_DIR / "gazetteer_mentions.jsonl", ctx.gazetteer_mentions)

    crf_ext = CRFExtractor()
    ctx.crf_result = crf_ext.extract(ctx.sentences, ctx.gazetteer_mentions)
    write_json(EVALUATION_DIR / "crf_metrics.json", ctx.crf_result.metrics)
    save_records(NER_DIR / "crf_mentions.jsonl", ctx.crf_result.mentions)

    hmm_ext = HMMExtractor(alpha=0.01)
    ctx.hmm_result = hmm_ext.extract(ctx.sentences, ctx.gazetteer_mentions)
    save_records(NER_DIR / "hmm_mentions.jsonl", ctx.hmm_result.mentions)

    hmmlearn_ext = HMMLearnExtractor(random_state=42)
    ctx.hmmlearn_result = hmmlearn_ext.extract(ctx.sentences, ctx.gazetteer_mentions)
    save_records(NER_DIR / "hmmlearn_mentions.jsonl", ctx.hmmlearn_result.mentions)

    # 四方法合并
    method = ctx.ner_method
    if method == "gazetteer":
        ctx.merged_mentions = ctx.gazetteer_mentions
    elif method == "crf":
        ctx.merged_mentions = ctx.crf_result.mentions
    elif method == "hmm":
        ctx.merged_mentions = ctx.hmm_result.mentions
    elif method == "hmmlearn":
        ctx.merged_mentions = ctx.hmmlearn_result.mentions
    else:
        ctx.merged_mentions = merge_mentions(
            ctx.gazetteer_mentions,
            ctx.crf_result.mentions,
            ctx.hmm_result.mentions,
            ctx.hmmlearn_result.mentions,
        )
    save_records(NER_DIR / "entity_mentions.jsonl", ctx.merged_mentions)
    ctx.crf_metrics = ctx.crf_result.metrics

    # 生成四方法对比报告
    ner_report = compute_ner_comparison(
        ctx.gazetteer_mentions,
        ctx.crf_result.mentions,
        ctx.hmm_result.mentions,
        ctx.hmmlearn_result.mentions,
        ctx.merged_mentions,
    )
    write_json(EVALUATION_DIR / "ner_comparison.json", ner_report)

    # 开放域实体发现 + 验证
    candidates = discover_new_entities(
        ctx.documents, ctx.schema, min_confidence=0.45, max_new=80
    )
    new_entities = validate_discovered_entities(
        ctx.documents, candidates, ctx.schema, min_context_diversity=3
    )
    if new_entities:
        extended_schema = extend_schema_with_discoveries(ctx.schema, new_entities)
        # 对新实体做第二轮 gazetteer 识别
        gazetteer2 = GazetteerExtractor(extended_schema)
        discovered_mentions = gazetteer2.extract(ctx.sentences)
        # 标记来源
        discovered_ids = {e.id for e in new_entities}
        for m in discovered_mentions:
            if m.entity_type and m.text not in {e.name for e in ctx.schema.entities}:
                pass  # keep as-is
        save_records(NER_DIR / "discovered_mentions.jsonl", discovered_mentions)
        ctx.discovered_entity_count = len(new_entities)
        ctx.discovered_mention_count = len(discovered_mentions)
        # 将发现实体加入合并池
        ctx.merged_mentions = merge_mentions(
            ctx.merged_mentions,
            discovered_mentions,
        )
        # 更新 schema 引用
        ctx.schema = extended_schema
    else:
        ctx.discovered_entity_count = 0
        ctx.discovered_mention_count = 0


def run_linking_stage(ctx: PipelineContext) -> None:
    """实体链接 + Ch5 聚类消歧：碎片实体合并到规范实体。"""
    ctx.linked_mentions = link_mentions(ctx.merged_mentions, ctx.sentences, ctx.schema)

    # TF-IDF 聚类消歧：合并碎片实体
    sent_map = {s.sentence_id: s.text for s in ctx.sentences}
    merges = cluster_entity_fragments(
        ctx.linked_mentions, sent_map, ctx.schema, threshold=0.75
    )
    if merges:
        ctx.fragment_merge_count = len(merges)
        # 重定向 linked_mentions
        from dataclasses import replace as dreplace
        redirected = []
        for m in ctx.linked_mentions:
            if m.linked_entity_id and m.linked_entity_id in merges:
                redirected.append(dreplace(m, linked_entity_id=merges[m.linked_entity_id]))
            else:
                redirected.append(m)
        ctx.linked_mentions = redirected
        # 从 schema 中移除被合并的碎片实体
        ctx.schema = DomainSchema(
            entity_types=ctx.schema.entity_types,
            entities=[e for e in ctx.schema.entities if e.id not in merges],
            relations=ctx.schema.relations,
            central_entity_id=ctx.schema.central_entity_id,
            entity_hierarchy=ctx.schema.entity_hierarchy,
        )

    # 后处理：移除只链接到自己的发现实体
    removed = _remove_self_linking_discoveries(ctx)
    ctx.fragment_merge_count = len(removed)

    save_records(LINKING_DIR / "linked_mentions.jsonl", ctx.linked_mentions)


def run_relation_stage(ctx: PipelineContext) -> None:
    """关系抽取阶段：规则模式 + 共现统计 + 依存句法路径。"""
    # 方法 1: 正则模式匹配（原有）
    relation_ext = RelationExtractor(ctx.schema)
    pattern_triples = relation_ext.extract(ctx.linked_mentions, ctx.sentences)
    # 方法 2: 实体共现推断
    cooccur_triples = extract_by_cooccurrence(
        ctx.linked_mentions, ctx.sentences, ctx.schema, min_cooccur=3
    )
    # 方法 3: 依存句法路径
    deppath_triples = extract_by_dependency_path(
        ctx.linked_mentions, ctx.sentences, ctx.schema, min_pattern_support=2
    )

    # 合并去重
    merged: dict[tuple[str, str, str], TripleRecord] = {}
    for triple in pattern_triples + cooccur_triples + deppath_triples:
        key = (triple.subject_entity_id, triple.relation_id, triple.object_entity_id)
        existing = merged.get(key)
        if existing is None or triple.confidence > existing.confidence:
            merged[key] = triple

    # 碎片过滤：标记并排除含碎片实体的三元组
    entity_names = {e.id: e.name for e in ctx.schema.entities}
    suspicious: list[dict] = []
    clean: list[TripleRecord] = []
    for t in merged.values():
        subj_name = entity_names.get(t.subject_entity_id, "")
        obj_name = entity_names.get(t.object_entity_id, "")
        # 碎片标记：实体名 ≤2 字且是另一个更长实体名的子串
        is_fragment = False
        if len(subj_name) <= 2 and t.subject_entity_id.startswith("discovered_"):
            for other_name in entity_names.values():
                if subj_name in other_name and other_name != subj_name:
                    is_fragment = True
                    break
        if len(obj_name) <= 2 and t.object_entity_id.startswith("discovered_"):
            for other_name in entity_names.values():
                if obj_name in other_name and other_name != obj_name:
                    is_fragment = True
                    break
        if is_fragment:
            suspicious.append({
                "subject": t.subject_name, "relation": t.relation_label,
                "object": t.object_name, "source": t.source,
                "confidence": t.confidence, "evidence": t.evidence_sentence[:100],
            })
        else:
            clean.append(t)

    ctx.asserted_triples = sorted(clean, key=lambda t: t.triple_id)
    ctx.relation_stats = {
        "pattern": len(pattern_triples), "cooccurrence": len(cooccur_triples),
        "dependency_path": len(deppath_triples), "merged": len(merged),
        "suspicious_filtered": len(suspicious), "clean": len(clean),
    }
    write_json(EVALUATION_DIR / "suspicious_triples.json", suspicious)
    save_records(RELATION_DIR / "triples.jsonl", ctx.asserted_triples)


def run_reasoning_stage(ctx: PipelineContext) -> None:
    """推理阶段：冲突消解 + 产生式规则推理。"""
    pre_count = len(ctx.asserted_triples)
    ctx.asserted_triples = _resolve_conflicts(ctx.asserted_triples)
    conflicts_resolved = pre_count - len(ctx.asserted_triples)

    reasoner = RuleReasoner(ctx.schema)
    ctx.inferred_triples, ctx.reasoning_summary = reasoner.apply(ctx.asserted_triples)
    ctx.reasoning_summary["conflicts_resolved"] = conflicts_resolved

    ctx.all_triples = [*ctx.asserted_triples, *ctx.inferred_triples]
    save_records(REASONING_DIR / "inferred_triples.jsonl", ctx.inferred_triples)
    save_records(REASONING_DIR / "triples_all.jsonl", ctx.all_triples)
    write_json(REASONING_DIR / "reasoning_summary.json", ctx.reasoning_summary)


def run_storage_stage(ctx: PipelineContext) -> None:
    """存储阶段：导出图存储文件。"""
    store = GraphStore(ctx.schema, STORAGE_DIR)
    ctx.store_summary = store.export(
        ctx.linked_mentions,
        ctx.asserted_triples,
        ctx.inferred_triples,
    )


def run_graph_stage(ctx: PipelineContext) -> None:
    """图可视化阶段：生成图谱 HTML 与 JSON 载荷。"""
    full_graph_payload, full_graph_stats = build_graph_payload(
        ctx.schema,
        ctx.linked_mentions,
        ctx.all_triples,
        view="full",
    )
    ctx.graph_payload, ctx.projection_stats = build_graph_payload(
        ctx.schema,
        ctx.linked_mentions,
        ctx.all_triples,
        view="focused",
    )

    write_json(GRAPH_DIR / "graph.json", full_graph_payload)
    write_json(GRAPH_DIR / "graph_full.json", full_graph_payload)
    write_json(GRAPH_DIR / "graph_focus.json", ctx.graph_payload)
    write_json(GRAPH_DIR / "projection.json", ctx.projection_stats)
    write_json(GRAPH_DIR / "graph_full_stats.json", full_graph_stats)

    full_html = generate_graph_html(
        full_graph_payload,
        title="TuringKG Full Graph",
        subtitle="Source: local EPUB/PDF biographies | full linked-entity overview",
    )
    graph_html_path = GRAPH_DIR / "turing_kg.html"
    graph_html_path.write_text(full_html, encoding="utf-8")
    (ROOT_DIR / "turing_kg.html").write_text(full_html, encoding="utf-8")

    focused_html = generate_graph_html(
        ctx.graph_payload,
        title="TuringKG Focus Graph",
        subtitle="Source: local EPUB/PDF biographies | centered on Alan Turing",
    )
    focused_graph_path = GRAPH_DIR / "turing_kg_focus.html"
    focused_graph_path.write_text(focused_html, encoding="utf-8")
    (ROOT_DIR / "turing_kg_focus.html").write_text(focused_html, encoding="utf-8")


def run_metrics_stage(ctx: PipelineContext) -> None:
    """指标评估阶段：计算流水线质量指标并输出摘要。"""
    metrics = compute_pipeline_metrics(
        schema=ctx.schema,
        sentence_records=ctx.sentences,
        linked_mentions=ctx.linked_mentions,
        triples=ctx.all_triples,
        graph_payload=ctx.graph_payload,
        projection_stats=ctx.projection_stats,
    )
    write_json(EVALUATION_DIR / "pipeline_metrics.json", metrics)

    ctx.summary = {
        "document_count": len(ctx.documents),
        "sentence_count": len(ctx.sentences),
        "entity_mention_count": len(
            [m for m in ctx.linked_mentions if m.source in {"gazetteer", "crf"}]
        ),
        "linked_mention_count": sum(1 for m in ctx.linked_mentions if not m.is_nil),
        "triple_count": len(ctx.all_triples),
        "asserted_triple_count": metrics["triple_source_distribution"].get("extracted", 0),
        "inferred_triple_count": metrics["triple_source_distribution"].get("inferred", 0),
        "graph_html": str((GRAPH_DIR / "turing_kg.html").relative_to(ROOT_DIR)),
        "documents_path": str((EXTRACTED_DIR / "documents.jsonl").relative_to(ROOT_DIR)),
        "sentences_path": str((PREPROCESSED_DIR / "sentences.jsonl").relative_to(ROOT_DIR)),
        "triples_path": str((RELATION_DIR / "triples.jsonl").relative_to(ROOT_DIR)),
        "inferred_triples_path": str(
            (REASONING_DIR / "inferred_triples.jsonl").relative_to(ROOT_DIR)
        ),
        "store_path": str(STORAGE_DIR.relative_to(ROOT_DIR)),
        "metrics_path": str((EVALUATION_DIR / "pipeline_metrics.json").relative_to(ROOT_DIR)),
        "crf_metrics_path": str((EVALUATION_DIR / "crf_metrics.json").relative_to(ROOT_DIR)),
        "focused_graph_html": str(
            (GRAPH_DIR / "turing_kg_focus.html").relative_to(ROOT_DIR)
        ),
        "raw_orphan_node_ratio": metrics["raw_orphan_node_ratio"],
        "projected_center_component_ratio": metrics["projected_center_component_ratio"],
        "conflict_pair_ratio": metrics["conflict_pair_ratio"],
        "single_support_edge_ratio": metrics["single_support_edge_ratio"],
        "linked_boundary_alignment_rate": metrics["tokenizer_proxy"]["linked_mentions"][
            "boundary_alignment_rate"
        ],
        "linked_fragmentation_mean": metrics["tokenizer_proxy"]["linked_mentions"][
            "fragmentation_mean"
        ],
        "gazetteer_single_token_rate": metrics["tokenizer_proxy"]["gazetteer_mentions"][
            "single_token_rate"
        ],
        "reasoning": ctx.reasoning_summary,
        "storage": ctx.store_summary,
    }
    write_json(GRAPH_DIR / "summary.json", ctx.summary)
    write_json(OUTPUT_DIR / "summary.json", ctx.summary)


def run_pipeline(ner_method: str = "all") -> dict:
    """运行完整流水线：所有阶段顺序执行。"""
    ensure_runtime_dirs()
    jieba.initialize()
    ctx = PipelineContext(schema=load_domain_schema(), ner_method=ner_method)
    run_extract_stage(ctx)
    run_preprocess_stage(ctx)
    run_ner_stage(ctx)
    run_linking_stage(ctx)
    run_relation_stage(ctx)
    run_reasoning_stage(ctx)
    run_storage_stage(ctx)
    run_graph_stage(ctx)
    run_metrics_stage(ctx)
    return ctx.summary


def _remove_self_linking_discoveries(ctx: PipelineContext) -> set[str]:
    """移除只链接到自己的发现实体（仅当无其他实体交互时）。"""
    from collections import defaultdict
    by_eid: dict[str, list[MentionRecord]] = defaultdict(list)
    for m in ctx.linked_mentions:
        if m.linked_entity_id:
            by_eid[m.linked_entity_id].append(m)

    to_remove: set[str] = set()
    for eid, mentions in by_eid.items():
        if not eid.startswith("discovered_"):
            continue
        entity = ctx.schema.entity_by_id.get(eid)
        if not entity:
            continue
        self_match = sum(1 for m in mentions if m.text.strip() == entity.name)
        # 更激进的条件：>95% 的 mention 是自我匹配，且总数 >= 5
        if len(mentions) >= 5 and self_match / len(mentions) > 0.95:
            to_remove.add(eid)

    if to_remove:
        ctx.linked_mentions = [
            m for m in ctx.linked_mentions
            if m.linked_entity_id not in to_remove
        ]
        ctx.schema = DomainSchema(
            entity_types=ctx.schema.entity_types,
            entities=[e for e in ctx.schema.entities if e.id not in to_remove],
            relations=ctx.schema.relations,
            central_entity_id=ctx.schema.central_entity_id,
            entity_hierarchy=ctx.schema.entity_hierarchy,
        )
    return to_remove
