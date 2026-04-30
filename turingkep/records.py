"""流水线阶段之间共享的数据记录类型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .utils import read_jsonl, write_jsonl


@dataclass(frozen=True)
class TokenRecord:
    text: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TokenRecord":
        return cls(
            text=payload["text"],
            start=payload["start"],
            end=payload["end"],
        )


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    source_path: str
    format: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentRecord":
        return cls(**payload)


@dataclass(frozen=True)
class SentenceRecord:
    sentence_id: str
    document_id: str
    document_title: str
    paragraph_index: int
    sentence_index: int
    text: str
    tokens: list[TokenRecord]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tokens"] = [token.to_dict() for token in self.tokens]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SentenceRecord":
        return cls(
            sentence_id=payload["sentence_id"],
            document_id=payload["document_id"],
            document_title=payload["document_title"],
            paragraph_index=payload["paragraph_index"],
            sentence_index=payload["sentence_index"],
            text=payload["text"],
            tokens=[TokenRecord.from_dict(token) for token in payload["tokens"]],
        )


@dataclass(frozen=True)
class MentionRecord:
    mention_id: str
    sentence_id: str
    document_id: str
    text: str
    start: int
    end: int
    entity_type: str
    source: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    linked_entity_id: str | None = None
    linked_entity_name: str | None = None
    link_score: float = 0.0
    is_nil: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MentionRecord":
        return cls(
            mention_id=payload["mention_id"],
            sentence_id=payload["sentence_id"],
            document_id=payload["document_id"],
            text=payload["text"],
            start=payload["start"],
            end=payload["end"],
            entity_type=payload["entity_type"],
            source=payload["source"],
            candidates=payload.get("candidates", []),
            linked_entity_id=payload.get("linked_entity_id"),
            linked_entity_name=payload.get("linked_entity_name"),
            link_score=payload.get("link_score", 0.0),
            is_nil=payload.get("is_nil", False),
        )


@dataclass(frozen=True)
class TripleRecord:
    triple_id: str
    sentence_id: str
    document_id: str
    relation_id: str
    relation_label: str
    subject_entity_id: str
    subject_name: str
    object_entity_id: str
    object_name: str
    evidence_sentence: str
    rule_pattern: str
    confidence: float
    source: str = "extracted"
    support_triple_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TripleRecord":
        return cls(
            triple_id=payload["triple_id"],
            sentence_id=payload["sentence_id"],
            document_id=payload["document_id"],
            relation_id=payload["relation_id"],
            relation_label=payload["relation_label"],
            subject_entity_id=payload["subject_entity_id"],
            subject_name=payload["subject_name"],
            object_entity_id=payload["object_entity_id"],
            object_name=payload["object_name"],
            evidence_sentence=payload["evidence_sentence"],
            rule_pattern=payload["rule_pattern"],
            confidence=payload["confidence"],
            source=payload.get("source", "extracted"),
            support_triple_ids=payload.get("support_triple_ids", []),
        )


def save_records(path: Path, records: Iterable[Any]) -> None:
    write_jsonl(path, [record.to_dict() for record in records])


def load_document_records(path: Path) -> list[DocumentRecord]:
    return [DocumentRecord.from_dict(item) for item in read_jsonl(path)]


def load_sentence_records(path: Path) -> list[SentenceRecord]:
    return [SentenceRecord.from_dict(item) for item in read_jsonl(path)]


def load_mention_records(path: Path) -> list[MentionRecord]:
    return [MentionRecord.from_dict(item) for item in read_jsonl(path)]


def load_triple_records(path: Path) -> list[TripleRecord]:
    return [TripleRecord.from_dict(item) for item in read_jsonl(path)]
