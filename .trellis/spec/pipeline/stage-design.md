# Stage Design

> How to design a pipeline stage: contracts, component patterns, and CLI integration.

---

## 1. PipelineContext — Unified Data Carrier

All stage data lives in a single mutable dataclass. Stages modify it in place — no return values, no cascading None-checks.

### Signature Contract

```python
# Every stage function must follow this signature
def run_xxx_stage(ctx: PipelineContext) -> None:
    ...
```

### PipelineContext Fields

```python
@dataclass
class PipelineContext:
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
```

### Adding a new field

When adding a new field to PipelineContext, use `field(default_factory=list)` or `field(default_factory=dict)` for mutable defaults. Use `None` with `| None` type for optional singleton fields.

---

## 2. Component Pattern — Dual Interface

Every stage's core logic lives in a **component class** that:
- Accepts dependencies in `__init__` (e.g., `schema`)
- Exposes an `extract()` / `apply()` / `export()` method for the pipeline
- Can also be called standalone with primitive data (not just PipelineContext)

### Concrete Signatures

```python
# NER components
class GazetteerExtractor:
    def __init__(self, schema: DomainSchema) -> None: ...
    def extract(self, sentences: list[SentenceRecord]) -> list[MentionRecord]: ...

class CRFExtractor:
    def extract(self, sentences: list[SentenceRecord], gazetteer_mentions: list[MentionRecord]) -> CrfResult: ...

# Relation component
class RelationExtractor:
    def __init__(self, schema: DomainSchema) -> None: ...
    def extract(self, linked_mentions: list[MentionRecord], sentences: list[SentenceRecord]) -> list[TripleRecord]: ...

# Reasoning component
class RuleReasoner:
    def __init__(self, schema: DomainSchema) -> None: ...
    def apply(self, asserted_triples: list[TripleRecord]) -> tuple[list[TripleRecord], dict[str, Any]]: ...

# Storage component
class GraphStore:
    def __init__(self, schema: DomainSchema, output_dir: Path) -> None: ...
    def export(self, linked_mentions: list[MentionRecord], asserted_triples: list[TripleRecord], inferred_triples: list[TripleRecord]) -> dict[str, Any]: ...
```

### Design Decision: Mutable PipelineContext

**Context**: PipelineContext needed a data-passing strategy.

**Options considered**:
1. Immutable (each stage returns `replace(ctx, field=...)`)
2. Mutable (each stage modifies `ctx.field = ...` in place)

**Decision**: Mutable (option 2). The context lives only for one pipeline run — no concurrency or rollback needs. Immutable `replace()` on a 16-field dataclass adds noise for zero benefit.

**Consequences**: Stage functions have no return value. `run_pipeline()` calls stages sequentially: `A(ctx); B(ctx); C(ctx); ...`.

---

## 3. Pipeline Orchestration

`run_pipeline()` is the single entry point for full end-to-end execution:

```python
def run_pipeline() -> dict:
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
```

Stage order is fixed — each stage depends on fields set by the previous stage. Do not reorder without verifying field dependencies.

---

## 4. CLI Dispatch

Commands are mapped via a dict, not if/elif chains:

```python
STAGE_HANDLERS = {
    "pipeline": _cmd_pipeline,
    "extract": _cmd_extract,
    "preprocess": _cmd_preprocess,
    "ner": _cmd_ner,
    "link": _cmd_link,
    "relation": _cmd_relation,
    "reason": _cmd_reason,
    "store": _cmd_store,
    "query": _cmd_store,        # alias
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
    handler()
    return 0
```

**When adding a new command**:
1. Add the command name to `argparse` choices in `build_parser()`
2. Write a `_cmd_xxx()` handler that loads upstream data from files, fills a PipelineContext, calls the stage, and prints results
3. Add the mapping to `STAGE_HANDLERS`

### Good vs Bad: Standalone handler

```python
# Good — loads intermediate files, can run without prior stages
def _cmd_ner() -> None:
    ctx = PipelineContext(schema=load_domain_schema())
    ctx.documents = load_document_records(EXTRACTED_DIR / "documents.jsonl")
    ctx.sentences = load_sentence_records(PREPROCESSED_DIR / "sentences.jsonl")
    run_ner_stage(ctx)
    print(f"Entity mentions: {len(ctx.merged_mentions)}")

# Bad — calls upstream stages internally, defeating standalone purpose
def _cmd_ner_bad() -> None:
    # Don't do this — standalone commands should load files, not cascade
    ctx = PipelineContext(schema=load_domain_schema())
    run_extract_stage(ctx)
    run_preprocess_stage(ctx)
    run_ner_stage(ctx)
```

---

## 5. Common Mistakes

### Mistake: Adding cascading None-check to stage functions

```python
# Don't — stage functions trust ctx has upstream data
def run_ner_stage(ctx, sentences=None, documents=None):
    if sentences is None or documents is None:
        documents, sentences = run_preprocess_stage(documents)
    ...
```

Pipeline stages do not guard against missing upstream data — `run_pipeline()` guarantees correct ordering. Standalone CLI handlers load data from files instead.

### Mistake: Bare `dict` type annotation

```python
# Wrong
metrics: dict = field(default_factory=dict)

# Correct
metrics: dict[str, Any] = field(default_factory=dict)
```

### Mistake: Returning data from stage functions

```python
# Wrong — data flows through ctx, not return values
def run_ner_stage(ctx):
    ...
    return documents, sentences, mentions

# Correct
def run_ner_stage(ctx: PipelineContext) -> None:
    ...
    ctx.merged_mentions = merge_mentions(...)
```

---

## 6. Tests Required

When adding a new stage:
- [ ] Unit test: component class works with mock data (no file I/O)
- [ ] Integration test: stage function modifies PipelineContext correctly
- [ ] CLI test: `python main.py <stage>` runs standalone and prints expected output
- [ ] End-to-end: `python main.py pipeline` completes without error
