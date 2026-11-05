"""Vector retrieval over Chroma with a light lexical re-rank."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import chromadb

from rqg.rag.embeddings import Embedder, build_embedder
from rqg.rag.ingest import Chunk, chunk_corpus, load_corpus
from rqg.rag.text import content_tokens


@dataclass
class RetrievedChunk:
    """A chunk returned by retrieval, with its fused score."""

    chunk_id: str
    doc_id: str
    title: str
    text: str
    status: str
    last_updated: str
    score: float


class Retriever:
    """Dense retrieval (cosine) fused with token overlap: ``0.75*dense + 0.25*lexical``.

    The lexical term helps exact identifiers (error codes like "E12", part codes like
    "ZF-500") that small sentence-embedding models blur together.
    """

    def __init__(self, chunks: list[Chunk], embedder: Embedder, dense_weight: float = 0.75):
        self.embedder = embedder
        self.dense_weight = dense_weight
        self.chunks = {c.chunk_id: c for c in chunks}
        self.doc_ids = sorted({c.doc_id for c in chunks})
        client = chromadb.EphemeralClient()
        self.collection = client.create_collection(
            name=f"rqg-{uuid.uuid4().hex[:8]}", metadata={"hnsw:space": "cosine"}
        )
        if chunks:
            self.collection.add(
                ids=[c.chunk_id for c in chunks],
                embeddings=embedder.embed([c.text for c in chunks]),
                documents=[c.text for c in chunks],
                metadatas=[{"doc_id": c.doc_id} for c in chunks],
            )

    @classmethod
    def from_corpus(
        cls, corpus_dir: Path, backend: str = "onnx", chunk_size: int = 700, overlap: int = 120
    ) -> Retriever:
        chunks = chunk_corpus(load_corpus(corpus_dir), chunk_size, overlap)
        return cls(chunks, build_embedder(backend))

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedChunk]:
        """Return the top-k chunks for a query, best first."""
        if not self.chunks:
            return []
        n_cand = min(len(self.chunks), max(k * 4, 12))
        res = self.collection.query(query_embeddings=self.embedder.embed([query]), n_results=n_cand)
        q = set(content_tokens(query))
        scored: list[RetrievedChunk] = []
        for cid, dist in zip(res["ids"][0], res["distances"][0], strict=True):
            c = self.chunks[cid]
            dense = 1.0 - float(dist)
            lex = len(q & set(content_tokens(c.text))) / len(q) if q else 0.0
            score = self.dense_weight * dense + (1 - self.dense_weight) * lex
            scored.append(
                RetrievedChunk(
                    c.chunk_id, c.doc_id, c.title, c.text, c.status, c.last_updated, score
                )
            )
        scored.sort(key=lambda r: (-r.score, r.chunk_id))
        return scored[:k]
