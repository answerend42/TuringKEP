# Pipeline Development Guidelines

> Best practices for adding and modifying pipeline stages in this project.

---

## Overview

The TuringKEP pipeline is a linear sequence of 9 stages that transform raw documents into a knowledge graph. Data flows through a mutable `PipelineContext` — no cascading parameter passing, no expanding tuple returns.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Stage Design](./stage-design.md) | Stage function contracts, component patterns, CLI integration | Done |

---

## Pre-Development Checklist

Before writing code in the pipeline layer:

- [ ] New stage follows the `(ctx: PipelineContext) -> None` signature
- [ ] Stage reads from and writes to `PipelineContext` fields, not positional params
- [ ] Core logic is in a component class with a standalone interface (can be called without the pipeline)
- [ ] Stage saves its intermediate output to `outputs/0X_name/` via `save_records()` or `write_json()`
- [ ] CLI handler added to `STAGE_HANDLERS` dispatch table in `cli.py`
- [ ] CLI handler loads upstream data from intermediate files when running standalone

## Quality Check

- [ ] `python main.py pipeline` runs end-to-end without errors
- [ ] `python main.py <stage>` runs standalone by loading intermediate files
- [ ] All new types have `from __future__ import annotations` and proper type hints
- [ ] No cascading `if xxx is None` checks — stages trust `PipelineContext` has upstream data

---

**Language**: English and Chinese mixed — code identifiers in English, comments in Chinese.
