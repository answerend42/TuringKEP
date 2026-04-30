from __future__ import annotations

import argparse

from .legacy_wikidata import run_legacy_demo
from .paths import (
    EXTRACTED_DIR,
    GRAPH_DIR,
    LINKING_DIR,
    NER_DIR,
    PREPROCESSED_DIR,
    REASONING_DIR,
    RELATION_DIR,
    ensure_runtime_dirs,
)
from .pipeline import (
    PipelineContext,
    run_extract_stage,
    run_graph_stage,
    run_linking_stage,
    run_metrics_stage,
    run_ner_stage,
    run_pipeline,
    run_preprocess_stage,
    run_reasoning_stage,
    run_relation_stage,
    run_storage_stage,
)
from .records import (
    load_document_records,
    load_mention_records,
    load_sentence_records,
    load_triple_records,
)
from .schema import load_domain_schema
from .utils import read_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TuringKG minimal pipeline runner")
    parser.add_argument(
        "command",
        nargs="?",
        default="pipeline",
        choices=[
            "pipeline",
            "extract",
            "preprocess",
            "ner",
            "link",
            "relation",
            "reason",
            "store",
            "query",
            "graph",
            "metrics",
            "legacy-wikidata",
        ],
        help="Which workflow to run.",
    )
    parser.add_argument(
        "--method",
        choices=["all", "gazetteer", "crf", "hmm", "hmmlearn"],
        default="all",
        help="NER method selection (default: all).",
    )
    return parser


# ---------------------------------------------------------------------------
# Stage command handlers
# ---------------------------------------------------------------------------


def _cmd_pipeline(method: str = "all") -> None:
    summary = run_pipeline(ner_method=method)
    print("Pipeline finished.")
    print(f"Documents: {summary['document_count']}")
    print(f"Sentences: {summary['sentence_count']}")
    print(f"Linked mentions: {summary['linked_mention_count']}")
    print(f"Triples: {summary['triple_count']}")
    print(f"Asserted triples: {summary['asserted_triple_count']}")
    print(f"Inferred triples: {summary['inferred_triple_count']}")
    print(f"Graph HTML: {summary['graph_html']}")
    print(f"Store: {summary['store_path']}")
    print(f"Metrics: {summary['metrics_path']}")


def _cmd_extract(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    run_extract_stage(ctx)
    print(f"Extracted documents: {len(ctx.documents)}")


def _cmd_preprocess(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    run_preprocess_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")


def _cmd_ner(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.ner_method = method
    run_ner_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Entity mentions: {len(ctx.merged_mentions)}")


def _cmd_link(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.merged_mentions = load_mention_records(NER_DIR / "entity_mentions.jsonl")
    run_linking_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Linked mentions: {sum(1 for m in ctx.linked_mentions if not m.is_nil)}")


def _cmd_relation(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.linked_mentions = load_mention_records(LINKING_DIR / "linked_mentions.jsonl")
    run_relation_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Triples: {len(ctx.asserted_triples)}")


def _cmd_reason(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.linked_mentions = load_mention_records(LINKING_DIR / "linked_mentions.jsonl")
    ctx.asserted_triples = load_triple_records(RELATION_DIR / "triples.jsonl")
    run_reasoning_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Asserted triples: {len(ctx.asserted_triples)}")
    print(f"Inferred triples: {len(ctx.inferred_triples)}")
    print(f"All triples: {len(ctx.all_triples)}")
    print(f"Reasoning summary: {ctx.reasoning_summary['inferred_triple_count']} inferred facts")


def _cmd_store(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.linked_mentions = load_mention_records(LINKING_DIR / "linked_mentions.jsonl")
    ctx.asserted_triples = load_triple_records(RELATION_DIR / "triples.jsonl")
    ctx.inferred_triples = load_triple_records(REASONING_DIR / "inferred_triples.jsonl")
    ctx.all_triples = [*ctx.asserted_triples, *ctx.inferred_triples]
    run_storage_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Asserted triples: {len(ctx.asserted_triples)}")
    print(f"Inferred triples: {len(ctx.inferred_triples)}")
    print(f"Facts in store: {len(ctx.all_triples)}")
    print(f"Store summary: {ctx.store_summary['paths']['facts_jsonl']}")
    print(f"Query examples: {ctx.store_summary['paths']['query_examples']}")


def _cmd_graph(method: str = "all") -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.linked_mentions = load_mention_records(LINKING_DIR / "linked_mentions.jsonl")
    ctx.all_triples = load_triple_records(REASONING_DIR / "triples_all.jsonl")
    run_graph_stage(ctx)
    print(f"Documents: {len(ctx.documents)}")
    print(f"Sentences: {len(ctx.sentences)}")
    print(f"Triples: {len(ctx.all_triples)}")
    print(f"Focused graph nodes: {len(ctx.graph_payload['nodes'])}")
    print(f"Focused graph edges: {len(ctx.graph_payload['edges'])}")
    print("Full graph HTML: outputs/08_graph/turing_kg.html")
    print("Focused graph HTML: outputs/08_graph/turing_kg_focus.html")


def _cmd_metrics(method: str = "all") -> None:
    ensure_runtime_dirs()
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    ctx.linked_mentions = load_mention_records(LINKING_DIR / "linked_mentions.jsonl")
    ctx.all_triples = load_triple_records(REASONING_DIR / "triples_all.jsonl")
    ctx.graph_payload = read_json(GRAPH_DIR / "graph_focus.json")
    ctx.projection_stats = read_json(GRAPH_DIR / "projection.json")
    run_metrics_stage(ctx)
    summary = ctx.summary
    print("Pipeline finished.")
    print(f"Documents: {summary['document_count']}")
    print(f"Sentences: {summary['sentence_count']}")
    print(f"Linked mentions: {summary['linked_mention_count']}")
    print(f"Triples: {summary['triple_count']}")
    print(f"Asserted triples: {summary['asserted_triple_count']}")
    print(f"Inferred triples: {summary['inferred_triple_count']}")
    print(f"Graph HTML: {summary['graph_html']}")
    print(f"Store: {summary['store_path']}")
    print(f"Metrics: {summary['metrics_path']}")


def _cmd_legacy_wikidata(method: str = "all") -> None:
    output_path = run_legacy_demo()
    print(f"Legacy demo written to {output_path}")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

STAGE_HANDLERS = {
    "pipeline": _cmd_pipeline,
    "extract": _cmd_extract,
    "preprocess": _cmd_preprocess,
    "ner": _cmd_ner,
    "link": _cmd_link,
    "relation": _cmd_relation,
    "reason": _cmd_reason,
    "store": _cmd_store,
    "query": _cmd_store,
    "graph": _cmd_graph,
    "metrics": _cmd_metrics,
    "legacy-wikidata": _cmd_legacy_wikidata,
}


def main() -> int:
    args = build_parser().parse_args()
    handler = STAGE_HANDLERS.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}")
        return 1
    handler(method=args.method if hasattr(args, "method") else "all")
    return 0
