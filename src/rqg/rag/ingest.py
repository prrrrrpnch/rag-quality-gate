"""Load the markdown corpus, parse front matter and chunk by section."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class Document:
    """One corpus document with its metadata."""

    doc_id: str
    title: str
    text: str
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.meta.get("status", "current")

    @property
    def last_updated(self) -> str:
        return self.meta.get("last_updated", "")


@dataclass
class Chunk:
    """A retrievable piece of a document."""

    chunk_id: str
    doc_id: str
    title: str
    text: str
    status: str
    last_updated: str


def parse_document(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    m = _FRONT.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = raw[m.end() :]
    doc_id = meta.get("doc_id", path.stem)
    return Document(doc_id=doc_id, title=meta.get("title", doc_id), text=body.strip(), meta=meta)


def load_corpus(corpus_dir: Path) -> list[Document]:
    """Load every ``*.md`` file in a directory (sorted, so ordering is deterministic)."""
    docs = [parse_document(p) for p in sorted(Path(corpus_dir).glob("*.md"))]
    ids = [d.doc_id for d in docs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate doc_ids in corpus: {sorted(dupes)}")
    return docs


def chunk_document(doc: Document, chunk_size: int = 700, overlap: int = 120) -> list[Chunk]:
    """Split on ``##`` sections; long sections are windowed with overlap.

    The document title is prepended to each chunk so a chunk is self-describing
    ("AeroPure 500 ... Filter life: 8 months") — this matters for near-duplicate docs.
    """
    sections = re.split(r"\n(?=## )", doc.text)
    pieces: list[str] = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= chunk_size:
            pieces.append(sec)
            continue
        start = 0
        while start < len(sec):
            end = min(len(sec), start + chunk_size)
            pieces.append(sec[start:end])
            if end == len(sec):
                break
            start = end - overlap
    return [
        Chunk(
            chunk_id=f"{doc.doc_id}#{i}",
            doc_id=doc.doc_id,
            title=doc.title,
            text=f"{doc.title}\n{p}",
            status=doc.status,
            last_updated=doc.last_updated,
        )
        for i, p in enumerate(pieces)
    ]


def chunk_corpus(docs: list[Document], chunk_size: int = 700, overlap: int = 120) -> list[Chunk]:
    return [c for d in docs for c in chunk_document(d, chunk_size, overlap)]
