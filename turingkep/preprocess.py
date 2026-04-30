"""分句与分词等轻量预处理逻辑。"""

from __future__ import annotations

import jieba

from .records import DocumentRecord, SentenceRecord, TokenRecord
from .utils import split_sentences


def tokenize_sentence(text: str) -> list[TokenRecord]:
    tokens = [
        TokenRecord(text=token, start=start, end=end)
        for token, start, end in jieba.tokenize(text)
        if token.strip()
    ]
    if tokens:
        return tokens
    return [TokenRecord(text=text, start=0, end=len(text))] if text else []


def build_sentence_records(documents: list[DocumentRecord]) -> list[SentenceRecord]:
    sentence_records: list[SentenceRecord] = []
    for document in documents:
        sentence_index = 0
        paragraphs = [segment.strip() for segment in document.text.split("\n\n") if segment.strip()]
        for paragraph_index, paragraph in enumerate(paragraphs):
            for sentence in split_sentences(paragraph):
                if len(sentence) < 6:
                    continue
                sentence_index += 1
                sentence_records.append(
                    SentenceRecord(
                        sentence_id=f"{document.document_id}-s{sentence_index:05d}",
                        document_id=document.document_id,
                        document_title=document.title,
                        paragraph_index=paragraph_index,
                        sentence_index=sentence_index,
                        text=sentence,
                        tokens=tokenize_sentence(sentence),
                    )
                )
    return sentence_records
