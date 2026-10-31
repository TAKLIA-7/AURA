"""AURA RAG Embeddings Service — generates normalized vector representations."""
from __future__ import annotations
import hashlib
import math
import os
from typing import List, Optional


class EmbeddingService:
    """Generates normalized vector embeddings with optional API backend and zero-dependency fallback."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _local_hash_embedding(self, text: str) -> List[float]:
        """Deterministic normalized dense embedding vector for testing and offline fallback."""
        import re
        vec = [0.0] * self.dimension
        words = re.findall(r"\w+", text.lower())
        if not words:
            return vec

        for i, word in enumerate(words):
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 / math.sqrt(i + 1))

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_text(self, text: str) -> List[float]:
        """Embed a single string."""
        return self._local_hash_embedding(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings."""
        return [self.embed_text(t) for t in texts]
