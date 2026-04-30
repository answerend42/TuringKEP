"""NER 方法对比评价：生成四方法的量化对比报告。"""

from __future__ import annotations

from collections import Counter

from .records import MentionRecord
from .utils import write_json


def compute_ner_comparison(
    gazetteer: list[MentionRecord],
    crf: list[MentionRecord],
    hmm: list[MentionRecord],
    hmmlearn: list[MentionRecord],
    merged: list[MentionRecord],
) -> dict:
    """生成 NER 四方法对比报告。"""

    methods = {
        "gazetteer": gazetteer,
        "crf": crf,
        "hmm_handwritten": hmm,
        "hmm_hmmlearn": hmmlearn,
    }

    report: dict = {"method_stats": {}, "aggregate": {}}

    for name, mentions in methods.items():
        type_dist = Counter(m.entity_type for m in mentions)
        source_dist = Counter(m.source for m in mentions)
        report["method_stats"][name] = {
            "mention_count": len(mentions),
            "unique_texts": len({m.text for m in mentions}),
            "entity_type_distribution": dict(type_dist),
            "source_distribution": dict(source_dist),
        }

    # 方法间的重叠度（基于文本位置）
    def _span_set(mentions: list[MentionRecord]) -> set[tuple[str, int, int]]:
        return {(m.sentence_id, m.start, m.end) for m in mentions}

    spans = {name: _span_set(mentions) for name, mentions in methods.items()}
    names = list(methods.keys())
    overlap_matrix: dict[str, dict[str, int]] = {}
    for a in names:
        overlap_matrix[a] = {}
        for b in names:
            if a == b:
                overlap_matrix[a][b] = len(spans[a])
            else:
                overlap_matrix[a][b] = len(spans[a] & spans[b])
    report["overlap_matrix"] = overlap_matrix

    # 汇总
    report["aggregate"] = {
        "merged_count": len(merged),
        "gazetteer_baseline": len(gazetteer),
        "method_contributions": {
            name: len(mentions) for name, mentions in methods.items()
        },
    }

    return report
