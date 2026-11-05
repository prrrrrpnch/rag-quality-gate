"""Local embedding backends (no API key needed).

* ``onnx``    — all-MiniLM-L6-v2 exported to ONNX, shipped by Chroma (~80 MB, downloaded once
  to ``~/.cache/chroma``). Real semantic embeddings, used for evals.
* ``hashing`` — signed feature hashing of stemmed unigrams + bigrams. No download at all;
  used by unit tests and as an offline fallback. Lexical only.
"""

from __future__ import annotations

import hashlib
import itertools
from typing import Protocol

import numpy as np

from rqg.rag.text import content_tokens


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic feature-hashing embedder (L2-normalised)."""

    name = "hashing-512"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        toks = content_tokens(text)
        feats = toks + [f"{a}_{b}" for a, b in itertools.pairwise(toks)]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:4], "little")
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t).tolist() for t in texts]


class OnnxMiniLMEmbedder:
    """Chroma's bundled ONNX all-MiniLM-L6-v2 (runs on CPU via onnxruntime)."""

    name = "onnx-all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        self._fn = ONNXMiniLM_L6_V2()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._fn(texts)]


def build_embedder(backend: str) -> Embedder:
    if backend == "hashing":
        return HashingEmbedder()
    if backend == "onnx":
        return OnnxMiniLMEmbedder()
    raise ValueError(f"unknown embedding backend: {backend}")
