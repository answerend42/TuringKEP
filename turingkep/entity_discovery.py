"""半自动实体发现：从文本中提取候选实体供人工审核。"""

from __future__ import annotations

from collections import Counter

import jieba

from .records import DocumentRecord


STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "等", "这", "那",
    "他", "她", "它", "为", "对", "也", "就", "都", "但", "而",
    "且", "及", "从", "到", "不", "有", "个", "中", "上", "下",
    "着", "过", "得", "地", "被", "把", "要", "还", "可以", "可",
    "自己", "这样", "这个", "一种", "一个", "什么", "他们", "我们",
    "就是", "因为", "所以", "如果", "虽然", "这些", "那些", "已经",
    "没有", "只是", "这里", "那里", "其中", "之后", "之前", "其实",
    "也是", "只能", "便会", "这种", "一些", "乃至", "则是", "以此",
    "不仅", "而是", "但其", "对于", "通过", "作为", "当时", "成为",
    "由于", "此外", "例如", "之后", "之前", "以来", "及其", "之一",
    "非常", "所有", "任何", "各种", "某些", "许多", "很多", "怎么",
    "足以", "显得", "主要", "之间", "并非", "并未", "一位", "一位",
    "相当", "完全", "所谓", "极", "某", "另", "该", "此", "其",
    "之", "者", "所", "于", "以", "则", "即", "如", "虽", "惟",
}


def discover_candidate_entities(
    documents: list[DocumentRecord],
    known_names: set[str],
    min_freq: int = 5,
) -> list[tuple[str, int, list[str]]]:
    """从文档中发现候选实体。

    Returns:
        list of (word, frequency, sample_contexts) sorted by frequency desc
    """
    word_counter: Counter[str] = Counter()
    word_contexts: dict[str, list[str]] = {}

    for doc in documents:
        words = jieba.lcut(doc.text)
        # Collect word frequencies with context
        for i, w in enumerate(words):
            w = w.strip()
            if len(w) < 2:
                continue
            if w.isdigit():
                continue
            if w in STOPWORDS:
                continue
            if w in known_names:
                continue
            word_counter[w] += 1
            if w not in word_contexts:
                word_contexts[w] = []
            if len(word_contexts[w]) < 3:
                start = max(0, i - 2)
                end = min(len(words), i + 3)
                context = "".join(words[start:end])
                if context not in word_contexts[w]:
                    word_contexts[w].append(context)

    candidates = [
        (word, count, word_contexts.get(word, []))
        for word, count in word_counter.most_common(200)
        if count >= min_freq
    ]
    return candidates
