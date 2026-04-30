"""HMM 命名实体识别：手写版 + hmmlearn 版，可与 Gazetteer/CRF 横向对比。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace

import numpy as np
from hmmlearn import hmm

from .records import MentionRecord, SentenceRecord, TokenRecord
from .ner import CrfResult, labels_from_mentions, mentions_by_sentence, tags_to_mentions


@dataclass
class _TagSet:
    """BIO 标签集索引映射。"""

    labels: list[str]
    label_to_idx: dict[str, int]

    @classmethod
    def from_labels(cls, labels: list[str]) -> "_TagSet":
        """从标签集合构建索引（含 O 和 B-/I- 前缀）。"""
        seen: dict[str, int] = {}
        # 确保 O 在索引 0
        seen["O"] = len(seen)
        for tag in sorted(set(labels)):
            for prefix in ("B", "I"):
                key = f"{prefix}-{tag}"
                if key not in seen:
                    seen[key] = len(seen)
        return cls(labels=list(seen.keys()), label_to_idx=seen)

    @property
    def size(self) -> int:
        return len(self.labels)

    @property
    def o_idx(self) -> int:
        return self.label_to_idx["O"]


def _sentences_to_examples(
    sentences: list[SentenceRecord],
    gazetteer_by_sentence: dict[str, list[MentionRecord]],
) -> list[tuple[SentenceRecord, list[str]]]:
    """将句子转换为 (句子, BIO标签列表) 训练示例。"""
    examples: list[tuple[SentenceRecord, list[str]]] = []
    for s in sentences:
        mentions = gazetteer_by_sentence.get(s.sentence_id, [])
        if not s.tokens:
            continue
        labels = labels_from_mentions(s.tokens, mentions)
        examples.append((s, labels))
    return examples


# ============================================================================
# 手写 HMM（纯 Python）
# ============================================================================


class _HandwrittenHMM:
    """手写隐马尔可夫模型：π/A/B 估计 + 维特比解码 + 拉普拉斯平滑。"""

    def __init__(self, tagset: _TagSet, alpha: float = 0.01):
        self.tagset = tagset
        self.n_states = tagset.size
        self.alpha = alpha  # 拉普拉斯平滑系数

        # 计数（训练时填充）
        self._init_counts: Counter[int] = Counter()
        self._trans_counts: dict[int, Counter[int]] = defaultdict(Counter)
        self._emit_counts: dict[int, Counter[str]] = defaultdict(Counter)

        # 概率矩阵
        self.pi: np.ndarray | None = None
        self.A: np.ndarray | None = None   # transfer matrix
        self.B: dict[int, dict[str, float]] = {}  # emit prob per state

    def fit(self, examples: list[tuple[SentenceRecord, list[str]]]) -> None:
        """从标注数据估计 π/A/B。"""
        for s, labels in examples:
            idxs = [self.tagset.label_to_idx[t] for t in labels]
            tokens = [tok.text for tok in s.tokens]

            # 初始状态计数
            self._init_counts[idxs[0]] += 1

            for i in range(len(idxs)):
                state = idxs[i]
                word = tokens[i]
                # 转移计数
                if i + 1 < len(idxs):
                    self._trans_counts[state][idxs[i + 1]] += 1
                # 发射计数
                self._emit_counts[state][word] += 1

        # 归一化为概率（带拉普拉斯平滑）
        total_init = sum(self._init_counts.values()) + self.alpha * self.n_states
        self.pi = np.array(
            [(self._init_counts.get(i, 0) + self.alpha) / total_init for i in range(self.n_states)]
        )

        self.A = np.zeros((self.n_states, self.n_states))
        for s in range(self.n_states):
            total = sum(self._trans_counts[s].values()) + self.alpha * self.n_states
            for t in range(self.n_states):
                self.A[s, t] = (self._trans_counts[s].get(t, 0) + self.alpha) / total

        self.B = {}
        for s in range(self.n_states):
            total = sum(self._emit_counts[s].values()) + self.alpha
            probs: dict[str, float] = {}
            for word, count in self._emit_counts[s].items():
                probs[word] = (count + self.alpha) / total
            probs["__UNK__"] = self.alpha / total
            self.B[s] = probs

    def predict(self, tokens: list[TokenRecord]) -> list[str]:
        """维特比算法解码最优标签序列。"""
        n = len(tokens)
        words = [tok.text for tok in tokens]

        if self.pi is None or self.A is None:
            return ["O"] * n

        # 发射概率：对未登录词用平滑值
        emit_prob = np.zeros((n, self.n_states))
        for i, word in enumerate(words):
            for s in range(self.n_states):
                probs = self.B.get(s, {})
                emit_prob[i, s] = probs.get(word, probs.get("__UNK__", self.alpha))

        # 避免 log(0)
        eps = 1e-12
        pi_log = np.log(self.pi + eps)
        A_log = np.log(self.A + eps)
        emit_log = np.log(emit_prob + eps)

        # 维特比
        delta = np.zeros((n, self.n_states))
        psi = np.zeros((n, self.n_states), dtype=int)

        delta[0] = pi_log + emit_log[0]

        for t in range(1, n):
            for j in range(self.n_states):
                scores = delta[t - 1] + A_log[:, j]
                psi[t, j] = int(np.argmax(scores))
                delta[t, j] = scores[psi[t, j]] + emit_log[t, j]

        # 回溯
        path = [int(np.argmax(delta[-1]))]
        for t in range(n - 1, 0, -1):
            path.append(psi[t, path[-1]])
        path.reverse()

        return [self.tagset.labels[idx] for idx in path]


class HMMExtractor:
    """手写 HMM 实体识别器。

    参数 alpha 控制拉普拉斯平滑强度，默认 0.01。
    训练数据来自词典弱监督标签（与 CRF 一致）。
    """

    def __init__(self, alpha: float = 0.01):
        self.alpha = alpha
        self._hmm: _HandwrittenHMM | None = None
        self._tagset: _TagSet | None = None

    def extract(
        self,
        sentences: list[SentenceRecord],
        gazetteer_mentions: list[MentionRecord],
    ) -> CrfResult:
        gb = mentions_by_sentence(gazetteer_mentions)
        examples = _sentences_to_examples(sentences, gb)

        if not examples:
            return CrfResult(mentions=[], metrics={"status": "skipped", "reason": "no_examples"})

        # 构建标签集
        all_labels: set[str] = set()
        for _, labels in examples:
            all_labels.update(labels)
        all_labels.discard("O")
        # 移除 B-/I- 前缀获取实体类型
        entity_types = {l.split("-", 1)[1] for l in all_labels if "-" in l}
        self._tagset = _TagSet.from_labels(entity_types)
        self._hmm = _HandwrittenHMM(self._tagset, alpha=self.alpha)
        self._hmm.fit(examples)

        mentions: list[MentionRecord] = []
        for s in sentences:
            if not s.tokens:
                continue
            tags = self._hmm.predict(s.tokens)
            mentions.extend(tags_to_mentions(s, tags, source="hmm"))

        return CrfResult(
            mentions=mentions,
            metrics={
                "status": "trained",
                "example_count": len(examples),
                "tag_count": self._tagset.size,
                "alpha": self.alpha,
            },
        )


# ============================================================================
# hmmlearn 版 HMM
# ============================================================================


def _word_feature_id(token_text: str) -> int:
    """将词映射到受限的特征桶（~60 个），避免 hmmlearn 观测空间过大。"""
    t = token_text.strip()
    if not t:
        return 0
    # 长度桶
    length_bucket = min(len(t), 10)
    # 字符类型
    has_han = any("一" <= c <= "鿿" for c in t)
    has_digit = any(c.isdigit() for c in t)
    has_ascii = any(c.isascii() and c.isalpha() for c in t)
    has_punct = all(not c.isalnum() for c in t)

    if has_punct:
        return 1
    if has_digit and not has_han:
        return 2 + length_bucket
    if has_ascii and not has_han:
        return 13 + length_bucket
    if has_han and has_ascii:
        return 24 + length_bucket
    # 纯中文：按首字 Unicode 分桶
    first_ord = ord(t[0]) if t else 0
    bucket = (first_ord // 500) % 10
    return 35 + bucket


class _HMMLearnModel:
    """hmmlearn CategoricalHMM 包装器，使用特征桶化观测。"""

    def __init__(self, tagset: _TagSet, random_state: int = 42):
        self.tagset = tagset
        self.n_states = tagset.size
        self._model: hmm.CategoricalHMM | None = None
        self._vocab: dict[str, int] = {}
        self._rng = random_state

    def fit(self, examples: list[tuple[SentenceRecord, list[str]]]) -> None:
        # 特征桶化观测空间
        feature_set: set[int] = set()
        for s, _ in examples:
            for tok in s.tokens:
                feature_set.add(_word_feature_id(tok.text))
        feature_list = sorted(feature_set)
        self._vocab = {w: feature_list.index(_word_feature_id(w)) for w in
                       {tok.text for s, _ in examples for tok in s.tokens}}
        n_obs = len(feature_list)

        lengths: list[int] = []
        obs_flat: list[int] = []
        for s, labels in examples:
            idxs = [self.tagset.label_to_idx[t] for t in labels]
            feat_ids = [_word_feature_id(tok.text) for tok in s.tokens]
            # 映射到连续索引
            obs_ids = [feature_list.index(f) if f in feature_list else 0 for f in feat_ids]
            if len(idxs) != len(obs_ids):
                continue
            lengths.append(len(idxs))
            obs_flat.extend(obs_ids)

        n = self.n_states
        init_counts = np.ones(n) * 0.01
        trans_counts = np.ones((n, n)) * 0.01
        emit_counts = np.ones((n, n_obs)) * 0.01

        for (s, labels), length in zip(examples, lengths):
            idxs = [self.tagset.label_to_idx[t] for t in labels]
            feat_ids = [_word_feature_id(tok.text) for tok in s.tokens]
            obs_ids = [feature_list.index(f) if f in feature_list else 0 for f in feat_ids]
            init_counts[idxs[0]] += 1
            for i in range(len(idxs)):
                state = idxs[i]
                emit_counts[state, obs_ids[i]] += 1
                if i + 1 < len(idxs):
                    trans_counts[state, idxs[i + 1]] += 1

        init_counts /= init_counts.sum()
        trans_counts /= trans_counts.sum(axis=1, keepdims=True)
        emit_counts /= emit_counts.sum(axis=1, keepdims=True)

        self._model = hmm.CategoricalHMM(
            n_components=n,
            init_params="",
            params="ste",
            random_state=self._rng,
        )
        self._model.startprob_ = init_counts
        self._model.transmat_ = trans_counts
        self._model.emissionprob_ = emit_counts

        if len(obs_flat) > 0:
            try:
                obs_array = np.array(obs_flat).reshape(-1, 1)
                self._model.fit(obs_array, lengths)
            except Exception:
                pass

    def predict(self, tokens: list[TokenRecord]) -> list[str]:
        if self._model is None:
            return ["O"] * len(tokens)

        obs = np.array([_word_feature_id(t.text) % 45 for t in tokens]).reshape(-1, 1)
        try:
            state_seq = self._model.predict(obs)
            return [self.tagset.labels[s] for s in state_seq]
        except Exception:
            return ["O"] * len(tokens)


class HMMLearnExtractor:
    """hmmlearn 库版 HMM 实体识别器。

    使用 MultinomialHMM + Baum-Welch EM 训练。
    训练数据来自词典弱监督标签（与 CRF 一致）。
    """

    def __init__(self, random_state: int = 42):
        self._random_state = random_state
        self._hmm: _HMMLearnModel | None = None
        self._tagset: _TagSet | None = None

    def extract(
        self,
        sentences: list[SentenceRecord],
        gazetteer_mentions: list[MentionRecord],
    ) -> CrfResult:
        gb = mentions_by_sentence(gazetteer_mentions)
        examples = _sentences_to_examples(sentences, gb)

        if not examples:
            return CrfResult(mentions=[], metrics={"status": "skipped", "reason": "no_examples"})

        all_labels: set[str] = set()
        for _, labels in examples:
            all_labels.update(labels)
        all_labels.discard("O")
        entity_types = {l.split("-", 1)[1] for l in all_labels if "-" in l}
        self._tagset = _TagSet.from_labels(entity_types)
        self._hmm = _HMMLearnModel(self._tagset, random_state=self._random_state)
        self._hmm.fit(examples)

        mentions: list[MentionRecord] = []
        for s in sentences:
            if not s.tokens:
                continue
            tags = self._hmm.predict(s.tokens)
            mentions.extend(tags_to_mentions(s, tags, source="hmmlearn"))

        return CrfResult(
            mentions=mentions,
            metrics={
                "status": "trained",
                "example_count": len(examples),
                "tag_count": self._tagset.size,
            },
        )
