from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SCHEMA_DIR = ROOT_DIR / "schema"
OUTPUT_DIR = ROOT_DIR / "outputs"
EVALUATION_DIR = ROOT_DIR / "evaluation"

EXTRACTED_DIR = OUTPUT_DIR / "01_extracted"
PREPROCESSED_DIR = OUTPUT_DIR / "02_preprocessed"
NER_DIR = OUTPUT_DIR / "03_ner"
LINKING_DIR = OUTPUT_DIR / "04_linking"
RELATION_DIR = OUTPUT_DIR / "05_relations"
REASONING_DIR = OUTPUT_DIR / "06_reasoning"
STORAGE_DIR = OUTPUT_DIR / "07_storage"
GRAPH_DIR = OUTPUT_DIR / "08_graph"


def ensure_runtime_dirs() -> None:
    for path in (
        OUTPUT_DIR,
        EXTRACTED_DIR,
        PREPROCESSED_DIR,
        NER_DIR,
        LINKING_DIR,
        RELATION_DIR,
        GRAPH_DIR,
        STORAGE_DIR,
        REASONING_DIR,
        EVALUATION_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
