"""Standards Knowledge Base documents (#17): one document per clause, with clause_id/standard metadata."""
import json
from dataclasses import replace

from fx_data.standards import CLAUSES_JSON
from fx_data.standards_kb import content_hash, documents, load_documents, main

CLAUSES = json.loads(CLAUSES_JSON.read_text(encoding="utf-8"))


def test_one_document_per_clause_with_unique_keys():
    docs = load_documents()
    assert len(docs) == len(CLAUSES)
    assert len({d.key for d in docs}) == len(docs)
    assert {d.clause_id for d in docs} == {c["id"] for c in CLAUSES}


def test_documents_hold_the_english_clause_text_and_metadata():
    docs = {d.clause_id: d for d in load_documents()}
    clause = next(c for c in CLAUSES if c["id"] == "APS 1.1")
    doc = docs["APS 1.1"]
    assert doc.key == "clauses/APS_1.1.txt" and doc.body.strip() == clause["text"]["en"]
    assert json.loads(doc.metadata) == {"metadataAttributes": {"clause_id": "APS 1.1", "standard": "APS"}}
    assert doc.metadata_key == "clauses/APS_1.1.txt.metadata.json"
    assert {d.standard for d in docs.values()} == {"APS", "FPS"}


def test_metadata_fits_the_bedrock_sidecar_limit():
    assert max(len(d.metadata.encode()) for d in load_documents()) < 10_000


def test_hash_is_stable_and_changes_when_a_clause_changes():
    docs = load_documents()
    assert content_hash(docs) == content_hash(list(reversed(docs)))
    changed = [replace(docs[0], body=docs[0].body + "x")] + docs[1:]
    assert content_hash(changed) != content_hash(docs)
    assert content_hash(documents(CLAUSES[:-1])) != content_hash(docs)


def test_cli_writes_documents_and_sidecars_and_prints_the_hash(tmp_path, capsys):
    main([str(tmp_path)])
    docs = load_documents()
    assert capsys.readouterr().out.strip() == content_hash(docs)
    assert (tmp_path / docs[0].key).read_text(encoding="utf-8") == docs[0].body
    assert json.loads((tmp_path / docs[0].metadata_key).read_text(encoding="utf-8"))["metadataAttributes"]
    assert len(list((tmp_path / "clauses").iterdir())) == 2 * len(docs)
