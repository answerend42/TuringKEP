"""实体识别模块：词典匹配 + CRF 弱监督。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any

from sklearn.model_selection import train_test_split
from sklearn_crfsuite import CRF
from sklearn_crfsuite import metrics as crf_metrics

from .records import MentionRecord, SentenceRecord, TokenRecord
from .schema import DomainSchema


@dataclass(frozen=True)
class CrfResult:
    mentions: list[MentionRecord]
    metrics: dict[str, Any]


def build_alias_index(schema: DomainSchema) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for entity in schema.entities:
        for alias in entity.all_names:
            records.append(
                {
                    "entity_id": entity.id,
                    "entity_type": entity.entity_type,
                    "alias": alias,
                }
            )
    return sorted(records, key=lambda item: (-len(item["alias"]), item["alias"]))


def find_gazetteer_mentions(
    sentence_record: SentenceRecord, alias_index: list[dict[str, str]]
) -> list[MentionRecord]:
    text = sentence_record.text
    lowered = text.lower()
    candidates: list[MentionRecord] = []
    for entry in alias_index:
        alias = entry["alias"]
        search_space = lowered if alias.isascii() else text
        target = alias.lower() if alias.isascii() else alias
        start = 0
        while True:
            found = search_space.find(target, start)
            if found == -1:
                break
            end = found + len(target)
            candidates.append(
                MentionRecord(
                    mention_id="",
                    sentence_id=sentence_record.sentence_id,
                    document_id=sentence_record.document_id,
                    text=text[found:end],
                    start=found,
                    end=end,
                    entity_type=entry["entity_type"],
                    source="gazetteer",
                )
            )
            start = found + 1

    selected: list[MentionRecord] = []
    occupied: list[tuple[int, int]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item.start, -(item.end - item.start)),
    ):
        span = (candidate.start, candidate.end)
        if any(not (span[1] <= left or span[0] >= right) for left, right in occupied):
            continue
        occupied.append(span)
        selected.append(candidate)

    return [
        replace(mention, mention_id=f"{sentence_record.sentence_id}-g{index:03d}")
        for index, mention in enumerate(selected, start=1)
    ]


def mentions_by_sentence(
    mentions: list[MentionRecord],
) -> dict[str, list[MentionRecord]]:
    grouped: dict[str, list[MentionRecord]] = defaultdict(list)
    for mention in mentions:
        grouped[mention.sentence_id].append(mention)
    return grouped


def labels_from_mentions(tokens: list[TokenRecord], mentions: list[MentionRecord]) -> list[str]:
    labels = ["O"] * len(tokens)
    for mention in sorted(mentions, key=lambda item: (item.start, item.end)):
        covered_indices = [
            index
            for index, token in enumerate(tokens)
            if token.end > mention.start and token.start < mention.end
        ]
        if not covered_indices:
            continue
        labels[covered_indices[0]] = f"B-{mention.entity_type}"
        for index in covered_indices[1:]:
            labels[index] = f"I-{mention.entity_type}"
    return labels


def token_features(tokens: list[TokenRecord], index: int) -> dict[str, Any]:
    token = tokens[index].text
    features: dict[str, Any] = {
        "bias": 1.0,
        "token": token,
        "token.lower": token.lower(),
        "token[:1]": token[:1],
        "token[:2]": token[:2],
        "token[-1:]": token[-1:],
        "token[-2:]": token[-2:],
        "token.isdigit": token.isdigit(),
        "token.isascii": token.isascii(),
        "token.len": len(token),
        "token.has_han": any("\u4e00" <= char <= "\u9fff" for char in token),
    }
    if index == 0:
        features["BOS"] = True
    else:
        prev_token = tokens[index - 1].text
        features["-1:token"] = prev_token
        features["-1:isdigit"] = prev_token.isdigit()
    if index == len(tokens) - 1:
        features["EOS"] = True
    else:
        next_token = tokens[index + 1].text
        features["+1:token"] = next_token
        features["+1:isdigit"] = next_token.isdigit()
    return features


def prepare_crf_examples(
    sentence_records: list[SentenceRecord],
    gazetteer_by_sentence: dict[str, list[MentionRecord]],
    max_examples: int = 1500,
) -> list[dict[str, Any]]:
    positives: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []

    for sentence in sentence_records:
        if not sentence.tokens:
            continue
        mentions = gazetteer_by_sentence.get(sentence.sentence_id, [])
        example = {
            "sentence_id": sentence.sentence_id,
            "text": sentence.text,
            "tokens": sentence.tokens,
            "labels": labels_from_mentions(sentence.tokens, mentions),
        }
        if mentions:
            positives.append(example)
        else:
            negatives.append(example)

    negative_budget = min(len(negatives), max(len(positives), 200))
    dataset = positives + negatives[:negative_budget]
    return dataset[:max_examples]


def tags_to_mentions(
    sentence_record: SentenceRecord, tags: list[str], source: str
) -> list[MentionRecord]:
    mentions: list[MentionRecord] = []
    current_type: str | None = None
    current_start: int | None = None
    current_end: int | None = None

    for token, tag in zip(sentence_record.tokens, tags):
        if tag == "O":
            if current_type is not None and current_start is not None and current_end is not None:
                mentions.append(
                    MentionRecord(
                        mention_id="",
                        sentence_id=sentence_record.sentence_id,
                        document_id=sentence_record.document_id,
                        text=sentence_record.text[current_start:current_end],
                        start=current_start,
                        end=current_end,
                        entity_type=current_type,
                        source=source,
                    )
                )
            current_type = None
            current_start = None
            current_end = None
            continue

        prefix, entity_type = tag.split("-", 1)
        if prefix == "B" or current_type != entity_type:
            if current_type is not None and current_start is not None and current_end is not None:
                mentions.append(
                    MentionRecord(
                        mention_id="",
                        sentence_id=sentence_record.sentence_id,
                        document_id=sentence_record.document_id,
                        text=sentence_record.text[current_start:current_end],
                        start=current_start,
                        end=current_end,
                        entity_type=current_type,
                        source=source,
                    )
                )
            current_type = entity_type
            current_start = token.start
            current_end = token.end
        else:
            current_end = token.end

    if current_type is not None and current_start is not None and current_end is not None:
        mentions.append(
            MentionRecord(
                mention_id="",
                sentence_id=sentence_record.sentence_id,
                document_id=sentence_record.document_id,
                text=sentence_record.text[current_start:current_end],
                start=current_start,
                end=current_end,
                entity_type=current_type,
                source=source,
            )
        )

    return [
        replace(mention, mention_id=f"{sentence_record.sentence_id}-c{index:03d}")
        for index, mention in enumerate(mentions, start=1)
    ]


def train_and_predict_crf(
    sentence_records: list[SentenceRecord],
    gazetteer_mentions: list[MentionRecord],
) -> CrfResult:
    gazetteer_by_sentence = mentions_by_sentence(gazetteer_mentions)
    examples = prepare_crf_examples(sentence_records, gazetteer_by_sentence)
    if len(examples) < 20:
        return CrfResult(
            mentions=[],
            metrics={"status": "skipped", "reason": "too_few_examples"},
        )

    train_examples, test_examples = train_test_split(
        examples, test_size=0.2, random_state=42
    )

    x_train = [
        [token_features(example["tokens"], index) for index in range(len(example["tokens"]))]
        for example in train_examples
    ]
    y_train = [example["labels"] for example in train_examples]
    x_test = [
        [token_features(example["tokens"], index) for index in range(len(example["tokens"]))]
        for example in test_examples
    ]
    y_test = [example["labels"] for example in test_examples]

    model = CRF(
        algorithm="lbfgs",
        c1=0.1,
        c2=0.1,
        max_iterations=75,
        all_possible_transitions=True,
    )
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)

    report = crf_metrics.flat_classification_report(
        y_test,
        y_pred,
        digits=3,
        output_dict=True,
        zero_division=0,
    )

    predicted_mentions: list[MentionRecord] = []
    for sentence in sentence_records:
        features = [token_features(sentence.tokens, index) for index in range(len(sentence.tokens))]
        tags = model.predict_single(features)
        predicted_mentions.extend(tags_to_mentions(sentence, tags, source="crf"))

    return CrfResult(
        mentions=predicted_mentions,
        metrics={
            "status": "trained",
            "example_count": len(examples),
            "train_count": len(train_examples),
            "test_count": len(test_examples),
            "token_report": report,
        },
    )


class GazetteerExtractor:
    """词典匹配抽取器：基于候选词表进行最大匹配。"""

    def __init__(self, schema: DomainSchema) -> None:
        self.alias_index = build_alias_index(schema)

    def extract(self, sentences: list[SentenceRecord]) -> list[MentionRecord]:
        mentions: list[MentionRecord] = []
        for sentence in sentences:
            mentions.extend(find_gazetteer_mentions(sentence, self.alias_index))
        return mentions


class CRFExtractor:
    """CRF 序列标注抽取器：使用词典标注作为弱监督训练 CRF 模型。"""

    def extract(
        self,
        sentences: list[SentenceRecord],
        gazetteer_mentions: list[MentionRecord],
    ) -> CrfResult:
        return train_and_predict_crf(sentences, gazetteer_mentions)


def merge_mentions(
    gazetteer_mentions: list[MentionRecord],
    *crf_mentions: list[MentionRecord],
) -> list[MentionRecord]:
    combined = list(gazetteer_mentions)
    for mentions in crf_mentions:
        combined.extend(mentions)
    grouped: dict[str, list[MentionRecord]] = defaultdict(list)
    for mention in combined:
        grouped[mention.sentence_id].append(mention)

    merged: list[MentionRecord] = []
    for sentence_id, mentions in grouped.items():
        selected: list[MentionRecord] = []
        ordered = sorted(
            mentions,
            key=lambda item: (
                item.source != "gazetteer",
                -(item.end - item.start),
                item.start,
            ),
        )
        for mention in ordered:
            span = (mention.start, mention.end)
            if any(
                not (span[1] <= existing.start or span[0] >= existing.end)
                for existing in selected
            ):
                continue
            selected.append(mention)
        selected.sort(key=lambda item: item.start)
        merged.extend(
            replace(mention, mention_id=f"{sentence_id}-m{index:03d}")
            for index, mention in enumerate(selected, start=1)
        )
    return merged
