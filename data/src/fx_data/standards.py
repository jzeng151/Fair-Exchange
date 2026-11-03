"""Look up APS/FPS clauses by ID or text (issue #9).

    from fx_data.standards import Standards
    standards = Standards.load()
    standards.get("APS 2.1.1")          # the clause, or None
    standards.exists("APS 2.1.1")       # for the citation verifier (#17)
    standards.search("forced labor")    # by text, in English, Spanish or French

Reads data/standards/clauses.json, built from the FTUSA workbooks by fx_data.standards_loader.
"""
import json
import re
import unicodedata
from pathlib import Path

CLAUSES_JSON = Path(__file__).resolve().parents[2] / "standards" / "clauses.json"
_LEVEL_RANK = {"objective": 0, "criterion": 1, "sub-module": 2}


def normalize_id(clause_id: str) -> str:
    """' aps  2.1.1 ' -> 'APS 2.1.1'. Case and spacing don't matter; the number must match exactly."""
    parts = (clause_id or "").split()
    return f"{parts[0].upper()} {parts[1]}" if len(parts) == 2 else ""


def _fold(text: str) -> str:
    """Lowercase and drop accents, so 'trabajo forzoso' matches regardless of accents."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _fold(text)) if len(w) > 2]


class Standards:
    def __init__(self, clauses: list[dict]):
        self._by_id = {c["id"]: c for c in clauses}
        self._order = {c["id"]: i for i, c in enumerate(clauses)}
        self._haystack = {c["id"]: _fold(" ".join(c["text"].values())) for c in clauses}
        self._words = {cid: set(_words(text)) for cid, text in self._haystack.items()}

    @classmethod
    def load(cls, path: Path = CLAUSES_JSON) -> "Standards":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def get(self, clause_id: str) -> dict | None:
        return self._by_id.get(normalize_id(clause_id))

    def exists(self, clause_id: str) -> bool:
        return normalize_id(clause_id) in self._by_id

    def search(self, text: str, standard: str | None = None, limit: int = 10) -> list[dict]:
        """Clauses whose text (any language) contains the query words, best matches first."""
        words = _words(text)
        phrase = _fold(text.strip())
        scored = []
        for cid, haystack in self._haystack.items():
            clause = self._by_id[cid]
            if standard and clause["standard"] != standard.upper():
                continue
            # whole words only (a word may carry a plural ending): "agua" matches "aguas", not "salvaguardas"
            hits = sum(1 for w in words if any(hw.startswith(w) for hw in self._words[cid]))
            if not hits:
                continue
            exact_phrase = phrase and re.search(rf"\b{re.escape(phrase)}", haystack)
            score = hits + (len(words) if exact_phrase else 0)
            scored.append((-score, _LEVEL_RANK.get(clause["level"], 3), self._order[cid], clause))
        return [item[-1] for item in sorted(scored, key=lambda s: s[:3])[:limit]]
