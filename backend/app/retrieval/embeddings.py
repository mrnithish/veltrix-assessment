"""Embedding backends: fastembed (local ONNX on CPU) or a deterministic hashing embedder for tests."""

from __future__ import annotations

import hashlib
import math
import os
import re

import numpy as np

_WORD = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Bag-of-words hashing embedder. No downloads; good enough for offline tests."""

    dim = 384

    def _vec(self, text: str) -> list[float]:
        v = np.zeros(self.dim, dtype=np.float32)
        for word in _WORD.findall(text.lower()):
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 9) & 1 else -1.0
        n = float(np.linalg.norm(v)) or 1.0
        return (v / n).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FastEmbedder:
    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH") or None
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


def make_embedder(backend: str, model_name: str):
    if backend == "hash":
        return HashEmbedder()
    return FastEmbedder(model_name)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
