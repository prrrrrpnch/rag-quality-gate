from pathlib import Path

import pytest

from rqg.rag.embeddings import HashingEmbedder, build_embedder
from rqg.rag.ingest import Document, chunk_document, load_corpus, parse_document
from rqg.rag.text import content_tokens, contextualize, is_follow_up, split_sentences

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "corpus"


def test_corpus_loads_with_metadata():
    docs = load_corpus(CORPUS)
    assert 12 <= len(docs) <= 16
    ids = {d.doc_id for d in docs}
    assert {"warranty_policy_2026", "warranty_faq_2023", "ap300_specs", "ap500_specs"} <= ids
    superseded = {d.doc_id for d in docs if d.status == "superseded"}
    assert superseded == {"warranty_faq_2023", "aeropure_quickstart_2024"}
    for d in docs:
        assert d.title and d.last_updated, d.doc_id


def test_duplicate_doc_ids_rejected(tmp_path):
    for name in ("a.md", "b.md"):
        (tmp_path / name).write_text("---\ndoc_id: same\n---\nbody")
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus(tmp_path)


def test_parse_document_without_front_matter(tmp_path):
    p = tmp_path / "plain.md"
    p.write_text("# Title\nhello")
    d = parse_document(p)
    assert d.doc_id == "plain" and d.status == "current"


def test_chunking_prefixes_title_and_windows_long_sections():
    long = "## Section\n" + ("word " * 400)
    doc = Document("d1", "Doc One", long)
    chunks = chunk_document(doc, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(c.text.startswith("Doc One\n") for c in chunks)
    assert [c.chunk_id for c in chunks] == [f"d1#{i}" for i in range(len(chunks))]


def test_hashing_embedder_is_normalised_and_deterministic():
    e = HashingEmbedder(dim=64)
    a, b = e.embed(["filter life eight months", "filter life eight months"])
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-5
    assert e.embed([""])[0] == [0.0] * 64


def test_unknown_backend():
    with pytest.raises(ValueError):
        build_embedder("nope")


@pytest.mark.parametrize(
    ("query", "expected_doc"),
    [
        ("What is the filter life of the AeroPure 500?", "ap500_specs"),
        ("robot vacuum error E12", "robosweep_s7_troubleshooting"),
        ("how do I descale the BrewMate kettle", "brewmate_k2_manual"),
        ("extended warranty price", "warranty_policy_2026"),
        ("refund for a damaged product", "returns_policy"),
    ],
)
def test_retrieval_hits_expected_doc(hashing_retriever, query, expected_doc):
    hits = hashing_retriever.retrieve(query, k=4)
    assert len(hits) == 4
    assert expected_doc in [h.doc_id for h in hits]
    assert hits == sorted(hits, key=lambda h: -h.score)


def test_empty_retriever():
    from rqg.rag.retriever import Retriever

    assert Retriever([], HashingEmbedder()).retrieve("x") == []


def test_text_helpers():
    assert "filter" in content_tokens("The filters are")
    assert split_sentences("- One thing. Two things.\n# heading\n") == ["One thing.", "Two things."]
    assert is_follow_up("And the AeroPure 500?")
    assert not is_follow_up("What is the noise level of the AeroPure 300 in Turbo mode?")
    assert contextualize(["weight of AP300"], "and the 500?") == "weight of AP300 and the 500?"
    assert contextualize([], "and the 500?") == "and the 500?"
