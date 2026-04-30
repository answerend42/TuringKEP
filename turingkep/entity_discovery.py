"""无监督实体发现：段落级 TF-IDF + spaCy NER + 实体共现增强。

停用词表来源：https://github.com/goto456/stopwords (cn + hit 合并)
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import jieba.analyse
from sklearn.feature_extraction.text import TfidfVectorizer

from .paths import DATA_DIR
from .records import DocumentRecord

# spaCy NER → 项目实体类型映射
SPACY_NER_TYPE_MAP = {
    "PERSON": "Person",
    "GPE": "Place",
    "LOC": "Place",
    "ORG": "Organization",
    "FAC": "Place",
    "EVENT": "Event",
    "PRODUCT": "Artifact",
    "WORK_OF_ART": "Concept",
}


def _load_stopwords() -> set[str]:
    """加载外部停用词表（cn_stopwords + hit_stopwords 合并去重）。"""
    stopwords: set[str] = set()
    for filename in ("cn_stopwords.txt", "hit_stopwords.txt"):
        path = DATA_DIR / filename
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                word = line.strip()
                if word and not word.startswith("#"):
                    stopwords.add(word)
    # 补充项目特定的非实体高频词
    stopwords.update({
        "一个", "这个", "一些", "这些", "那些", "一种", "各种",
        "许多", "很多", "非常", "十分", "特别", "更加",
    })
    return stopwords


STOPWORDS = _load_stopwords()


def _split_paragraphs(text: str, min_length: int = 40) -> list[str]:
    """将文本按段落切分，过滤过短段落。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text)]
    return [p for p in paragraphs if len(p) >= min_length]


def _segment_paragraph(text: str) -> str:
    """分词后用空格连接，作为 TF-IDF 输入。"""
    words = [
        w.strip()
        for w in jieba.lcut(text)
        if len(w.strip()) >= 2 and w.strip() not in STOPWORDS
    ]
    return " ".join(words)


def _paragraph_tfidf(
    segmented_paragraphs: list[str], topk: int = 300
) -> dict[str, float]:
    """段落级 TF-IDF：每段作为一个文档。"""
    if len(segmented_paragraphs) < 3:
        return {}
    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        lowercase=False,
        max_features=topk * 2,
        max_df=0.6,   # 忽略出现在 60%+ 段落的词
        min_df=2,     # 至少出现在 2 个段落
    )
    tfidf_matrix = vectorizer.fit_transform(segmented_paragraphs)
    feature_names = vectorizer.get_feature_names_out()

    # 取每个词在所有段落中的平均 TF-IDF
    import numpy as np
    mean_scores = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
    word_scores = {
        word: float(mean_scores[i])
        for i, word in enumerate(feature_names)
    }
    # 取 topk
    sorted_words = sorted(word_scores.items(), key=lambda x: -x[1])[:topk]
    return dict(sorted_words)


def _spacy_ner_candidates(texts: list[str]) -> dict[str, list[str]]:
    """用 spaCy 中文 NER 模型识别专名实体（批处理优化）。"""
    import spacy
    try:
        nlp = spacy.load("zh_core_web_sm")
    except Exception:
        return {}

    english_noise = {"the", "see", "for", "and", "was", "his", "had", "not",
                     "but", "are", "has", "can", "its", "new", "one", "two",
                     "of", "in", "to", "it", "is", "on", "at", "by", "or",
                     "be", "as", "we", "an", "if", "my", "so", "up", "no"}

    # 将文本切分为 5000 字符的块，用 nlp.pipe() 批处理
    chunks: list[str] = []
    for text in texts:
        chunk_size = 5000
        for start in range(0, len(text), chunk_size):
            chunks.append(text[start:start + chunk_size])

    candidates: dict[str, list[str]] = defaultdict(list)
    for doc in nlp.pipe(chunks, batch_size=4):
        for ent in doc.ents:
            name = ent.text.strip()
            if len(name) < 2:
                continue
            if name.lower() in english_noise:
                continue
            if ent.label_ in SPACY_NER_TYPE_MAP:
                etype = SPACY_NER_TYPE_MAP[ent.label_]
                if etype not in candidates[name]:
                    candidates[name].append(etype)

    return dict(candidates)


def _neighbour_boost(
    texts: list[str], known_names: set[str], window: int = 8
) -> dict[str, int]:
    """实体共现增强：出现在已知实体附近的名词获得权重。"""
    boosted: dict[str, int] = defaultdict(int)
    for text in texts:
        segments = jieba.lcut(text)
        known_positions = [
            i for i, w in enumerate(segments) if w.lower() in known_names
        ]
        for pos in known_positions:
            for offset in range(-window, window + 1):
                if offset == 0:
                    continue
                idx = pos + offset
                if 0 <= idx < len(segments):
                    neighbour = segments[idx].strip()
                    if (
                        len(neighbour) >= 2
                        and neighbour not in STOPWORDS
                        and neighbour.lower() not in known_names
                    ):
                        boost = window - abs(offset) + 1
                        boosted[neighbour] += boost
    return dict(boosted)


def discover_candidate_entities(
    documents: list[DocumentRecord],
    known_names: set[str],
    min_freq: int = 5,
) -> list[dict]:
    """无监督实体发现流水线。

    1. 文档切段 → 段落级 TF-IDF（sklearn TfidfVectorizer）
    2. jieba POS tagging — 识别人名/地名/机构名/专名
    3. 实体共现 boost — 已知实体附近的未识别词加权
    4. 词频统计 → 综合评分排序

    Returns:
        list of candidate dicts with: word, freq, tfidf, pos_types, boost, confidence, contexts
    """
    texts = [doc.text for doc in documents]

    # 1. 段落切分 + TF-IDF
    all_paragraphs: list[str] = []
    for text in texts:
        all_paragraphs.extend(_split_paragraphs(text))
    segmented_paras = [_segment_paragraph(p) for p in all_paragraphs]
    tfidf_weights = _paragraph_tfidf(segmented_paras, topk=300)
    # Remove single chars that slipped through
    tfidf_weights = {w: s for w, s in tfidf_weights.items() if len(w) >= 2}

    # 2. spaCy NER 实体识别
    pos_candidates = _spacy_ner_candidates(texts)

    # 3. 词频统计
    word_freq: Counter[str] = Counter()
    for text in texts:
        for word in jieba.lcut(text):
            word = word.strip()
            if (
                len(word) >= 2
                and word not in STOPWORDS
                and word.lower() not in known_names
            ):
                word_freq[word] += 1

    # 4. 实体共现 boost
    neighbour_boost = _neighbour_boost(texts, known_names)

    # 5. 合并评分
    pos_words = set(pos_candidates.keys())
    tfidf_words = set(tfidf_weights.keys())
    boost_words = set(neighbour_boost.keys())
    all_candidate_words = pos_words | tfidf_words | boost_words

    scored: list[dict] = []
    full_segments: list[str] = []
    for text in texts:
        full_segments.extend(jieba.lcut(text))

    for word in all_candidate_words:
        freq = word_freq.get(word, 0)
        if freq < min_freq:
            continue

        has_pos = word in pos_words
        pos_types = pos_candidates.get(word, [])
        tfidf = tfidf_weights.get(word, 0.0)
        boost = neighbour_boost.get(word, 0)

        # 综合置信度：POS (0.4) + TF-IDF (0.3) + 共现 (0.2) + 词频 (0.1)
        pos_score = 0.4 if has_pos else 0.0
        tfidf_score = 0.3 * min(tfidf * 8, 1.0)   # TF-IDF values are small, scale up
        boost_score = 0.2 * min(boost / 100, 1.0)
        freq_score = 0.1 * min(freq / 300, 1.0)
        confidence = round(pos_score + tfidf_score + boost_score + freq_score, 4)

        # 上下文窗口
        contexts: list[str] = []
        for i, w in enumerate(full_segments):
            if w == word and len(contexts) < 3:
                start = max(0, i - 3)
                end = min(len(full_segments), i + 4)
                ctx = "".join(full_segments[start:end])
                if ctx not in contexts:
                    contexts.append(ctx)

        scored.append({
            "word": word,
            "freq": freq,
            "tfidf_weight": round(tfidf, 6),
            "pos_types": pos_types,
            "neighbour_boost": boost,
            "confidence": confidence,
            "contexts": contexts,
        })

    scored.sort(key=lambda x: (-x["confidence"], -x["freq"]))
    return scored
