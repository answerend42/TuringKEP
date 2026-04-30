"""流水线编排：按阶段组织整个 TuringKG 实验。"""

from __future__ import annotations

from dataclasses import dataclass, field

import jieba

from .evaluation import compute_pipeline_metrics
from .graph import build_graph_payload, generate_graph_html
from .ingestion import discover_book_files, extract_documents
from .linking import link_mentions
from .ner import CrfResult, GazetteerExtractor, CRFExtractor, merge_mentions
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
from .reasoning import RuleReasoner
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
    """实体识别阶段：词典匹配 + CRF 弱监督。"""
    gazetteer_ext = GazetteerExtractor(ctx.schema)
    ctx.gazetteer_mentions = gazetteer_ext.extract(ctx.sentences)
    save_records(NER_DIR / "gazetteer_mentions.jsonl", ctx.gazetteer_mentions)

    crf_ext = CRFExtractor()
    ctx.crf_result = crf_ext.extract(ctx.sentences, ctx.gazetteer_mentions)
    write_json(EVALUATION_DIR / "crf_metrics.json", ctx.crf_result.metrics)
    save_records(NER_DIR / "crf_mentions.jsonl", ctx.crf_result.mentions)

    ctx.merged_mentions = merge_mentions(ctx.gazetteer_mentions, ctx.crf_result.mentions)
    save_records(NER_DIR / "entity_mentions.jsonl", ctx.merged_mentions)
    ctx.crf_metrics = ctx.crf_result.metrics


def run_linking_stage(ctx: PipelineContext) -> None:
    """实体链接阶段：消歧与链接到知识库。"""
    ctx.linked_mentions = link_mentions(ctx.merged_mentions, ctx.sentences, ctx.schema)
    save_records(LINKING_DIR / "linked_mentions.jsonl", ctx.linked_mentions)


def run_relation_stage(ctx: PipelineContext) -> None:
    """关系抽取阶段：基于规则的三元组抽取。"""
    relation_ext = RelationExtractor(ctx.schema)
    ctx.asserted_triples = relation_ext.extract(ctx.linked_mentions, ctx.sentences)
    save_records(RELATION_DIR / "triples.jsonl", ctx.asserted_triples)


def run_reasoning_stage(ctx: PipelineContext) -> None:
    """推理阶段：产生式规则推理。"""
    reasoner = RuleReasoner(ctx.schema)
    ctx.inferred_triples, ctx.reasoning_summary = reasoner.apply(ctx.asserted_triples)
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


def run_pipeline() -> dict:
    """运行完整流水线：所有阶段顺序执行。"""
    ensure_runtime_dirs()
    jieba.initialize()
    ctx = PipelineContext(schema=load_domain_schema())
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
