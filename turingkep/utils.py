from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


MIDLINE_BREAK_RE = re.compile(
    r"(?<=[\u4e00-\u9fffA-Za-z0-9，,、；;：“”\"'（）()])\n(?=[\u4e00-\u9fffA-Za-z0-9])"
)
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [
            json.loads(line)
            for line in handle
            if line.strip()
        ]


def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = text.replace("\u3000", " ")
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = MIDLINE_BREAK_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"[ ]+\n", "\n", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    fragments = re.split(r"(?<=[。！？!?])\s*", text)
    sentences: list[str] = []
    for fragment in fragments:
        sentence = fragment.strip()
        if not sentence:
            continue
        if len(sentence) == 1 and sentence in {"。", "！", "？"}:
            continue
        sentences.append(sentence)
    return sentences


def slugify_name(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "document"
