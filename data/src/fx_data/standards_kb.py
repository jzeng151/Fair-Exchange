"""Standards Knowledge Base documents (issue #17). Spec: docs/specs/17-standards-grounding.md.

One document per APS or FPS clause, generated from clauses.json (the standards loader's clause table):
the clause's English text, with a Bedrock metadata sidecar holding `clause_id` and `standard`. The data
source uses no chunking, so each document is one vector and the top 5 results are 5 distinct clauses.

    cd data && uv run python -m fx_data.standards_kb OUT_DIR    # writes OUT_DIR/clauses/..., prints the hash

infra/deploy.sh uploads OUT_DIR to the artifacts bucket and passes the hash to CDK, so changed
clauses trigger re-ingestion on the next deploy.
"""
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from fx_data.standards import CLAUSES_JSON

PREFIX = "clauses/"  # the data source's inclusion prefix


@dataclass(frozen=True)
class Document:
    key: str  # S3 key of the document; the sidecar is key + ".metadata.json"
    body: str
    clause_id: str
    standard: str

    @property
    def metadata_key(self) -> str:
        return self.key + ".metadata.json"

    @property
    def metadata(self) -> str:
        # Bedrock Knowledge Base metadata sidecar format
        return json.dumps({"metadataAttributes": {"clause_id": self.clause_id, "standard": self.standard}},
                          sort_keys=True, ensure_ascii=False)


def _english_text(clause: dict) -> str:
    text = clause["text"]
    return text.get("en") or next((v for v in text.values() if v), "")


def documents(clauses: list[dict]) -> list[Document]:
    """One document per clause with English text, sorted by key."""
    docs = [Document(key=f"{PREFIX}{c['id'].replace(' ', '_')}.txt", body=_english_text(c) + "\n",
                     clause_id=c["id"], standard=c["standard"])
            for c in clauses if _english_text(c)]
    return sorted(docs, key=lambda d: d.key)


def content_hash(docs: list[Document]) -> str:
    """SHA-256 over every document and sidecar, so any change to a clause changes the hash."""
    digest = hashlib.sha256()
    for d in sorted(docs, key=lambda d: d.key):
        for part in (d.key, d.body, d.metadata):
            digest.update(part.encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def load_documents(path: Path = CLAUSES_JSON) -> list[Document]:
    return documents(json.loads(path.read_text(encoding="utf-8")))


def write(out_dir: Path, docs: list[Document]) -> None:
    for d in docs:
        for key, content in ((d.key, d.body), (d.metadata_key, d.metadata)):
            target = out_dir / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


def main(argv: list[str]) -> None:
    if len(argv) != 1:
        sys.exit("usage: python -m fx_data.standards_kb OUT_DIR")
    docs = load_documents()
    write(Path(argv[0]), docs)
    print(f"wrote {len(docs)} clause documents to {argv[0]}", file=sys.stderr)
    print(content_hash(docs))


if __name__ == "__main__":
    main(sys.argv[1:])
