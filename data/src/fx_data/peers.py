"""Peer Premium projects and producer profiles, built from the FTUSA sample data (issue #16).

    PYTHONPATH=src uv run python -m fx_data.peers   # offline: writes peer_projects.json, producer_profiles.json

Peer projects:
  - one row per environmental Premium project (`pprojects-full-environmental-with-acct-detail.csv`),
    joined to its status and dates (`Premium Projects Environmental.csv`) on account + description
  - tagged with one challenge tag from the 11-tag set
  - fictionalized: each organization gets a stable `ORG-xxxxxxxx` reference, and organization and
    person names in the text are replaced with neutral words. The owning account is stored only as a
    salted hash, used to leave a producer's own projects out of their results
  - placeholder rows (lorem ipsum) are dropped

Producer profiles are a stand-in for the producer-record tool (#14) and the Athena tables (#28):
producer_id -> country, region, crop and entity type, so tools can resolve the session producer's
location without the model supplying it.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from fx_data.text import normalize

HERE = Path(__file__).parent
SAMPLE_DIR = HERE.parents[2] / "docs" / "olena_data"
PROJECTS_CSV = SAMPLE_DIR / "pprojects-full-environmental-with-acct-detail.csv"
LINKED_DIR = SAMPLE_DIR / "Producers with Linked Project & Survey Data"
STATUS_CSV = LINKED_DIR / "Premium Projects Environmental.csv"
ACCOUNTS_CSV = LINKED_DIR / "Producer Accounts.csv"
PEERS_PATH = HERE / "peer_projects.json"
PROFILES_PATH = HERE / "producer_profiles.json"

# Fixed salt: the hash only has to be stable and not reveal the account id in the shipped file.
_OWNER_SALT = "fair-exchange-peer-owner-v1"

SOURCE_PREFIX = "FTUSA Premium project (sample data, fictionalized)"

# Environmental subcategory -> challenge tag. Blank subcategories fall back to keywords.
SUBCATEGORY_TAGS = {
    "clean water": "water",
    "climate change mitigation/adaptation (clean energy, agroforestry etc.)": "climate and weather",
    "pest management": "soil and land",
    "crop diversification": "soil and land",
    "waste disposal / recycling": "biodiversity and conservation",
    "waste management (trash collection, recycling facilities etc.)": "biodiversity and conservation",
    "sustainability efforts": "biodiversity and conservation",
    "human resources and administration/ office services": "social and community",
}
KEYWORD_TAGS = [
    (("water", "irrigation", "wastewater", "rainwater"), "water"),
    (("climate", "solar", "clean energy", "carbon", "agroforestry", "reforest"), "climate and weather"),
    (("soil", "erosion", "pest", "fertiliz", "compost", "disease"), "soil and land"),
]
DEFAULT_TAG = "biodiversity and conservation"

# Organization and person names found in the sample text, replaced so peer examples cannot
# identify a producer. Longest first, so "SCPP Barra de Palmitas" goes before "SCPP".
NAME_REPLACEMENTS = sorted([
    ("Manuel Figueroa Bárcena", "a certified producer"),
    ("JOSÉ LUIS CASTRO VERDUZCO", "a member cooperative"),
    ("ABELARDO RUBIO CASTRO", "a member cooperative"),
    ("SCPP Barra de Palmitas", "the fishing cooperative"),
    ("SCPP Palmitas Bar", "the fishing cooperative"),
    ("SCPP FISHERMEN FROM LA PIONIA", "a member fishing cooperative"),
    ("SCPP ENSENADA VACAPORA", "a member fishing cooperative"),
    ("SCPP ISLETS OF THE RIVER", "a member fishing cooperative"),
    ("SCPP TONINA BAR", "a member fishing cooperative"),
    ("SCPP", "fishing cooperative"),
    ("Genesis Banana Corporation", "the producer organization"),
    ("Union and Progress Community Development Corporation", "a community development group"),
    ("Calavo de México, S.A. de C.V.", "a packing company"),
    ("Calavo de México", "a packing company"),
    ("Comercio Justo del Cupatitzio, A.C.", "a local fair trade association"),
    ("Comercio Justo del Cupatitzio", "a local fair trade association"),
    ("Association of Mexican Avocado Producers and Packers (APEAM)", "a national producers' association"),
    ("Association of Mexican Avocado Producers and Packers", "a national producers' association"),
    ("Association of Mexican Avocado Producers and Exporters", "a national producers' association"),
    ("APEAM", "the producers' association"),
    ("Asociación Fincas de El Oro", "The association"),
    ("Association of Beekeepers and Coffee Growers", "the producer association"),
    ("Beekeepers and Coffee Growers Association", "the producer association"),
    ("Maud Tea Estate and Sewpur Tea Estate", "the two tea estates"),
    ("Chesterhope Station", "the farm"),
    ("Chesterhope & Karamu", "Farm"),
    ("Finca Villa Emma", "a nearby farm"),
    ("El Salto Garden", "the producer's orchard"),
    ("“EL SALTO” Garden", "the producer's orchard"),
    ("CAC LA FLOR DEL CAFÉ", "the cooperative"),
    ("Tunas Muda FA", "a member farmers' association"),
    ("Sengkanaung FA", "a member farmers' association"),
    ("Tunas Muda", "a member farmers' association"),
    ("Sengkanaung", "a member farmers' association"),
    ("Tran Quoc Toan Secondary School", "a local secondary school"),
    ("Tran Quoc Toan secondary school", "a local secondary school"),
    ("Cupatitzio Fair Trade", "a local fair trade association"),
    ("Workers from Calavo", "workers from a packing company"),
    ("Huerta el Salto", "the producer's orchard"),
    ("GMCCFA", "the association"),
    ("NORTHEASTERN JUNGLE PRODUCERS ASSOCIATION", "THE PRODUCER ASSOCIATION"),
    ("CERRO FRESH", "THE COMPANY'S"),
    ("APROSELVANOR", "the association"),
    ("COOPCAFER", "the cooperative"),
    ("Coopcafer", "the cooperative"),
    ("AMCECAFÉ", "a partner group"),
    ("Expocafé", "an exporter"),
    ("ASOBRIS", "the association"),
    ("CORPCAES", "the association"),
    ("CADIBRINE", "the association"),
    ("COCAFELOL", "the cooperative"),
    ("CAFISUR", "the cooperative"),
    ("COAINLL", "the cooperative"),
    ("CNCFFTAI", "The association"),
    ("PSCPA", "The association"),
    ("GMC-CFA", "The association"),
    ("SAINSBURYS", "THE BUYER"),
    ("SAINSBURY", "THE BUYER"),
], key=lambda pair: -len(pair[0]))

_PLACEHOLDER = re.compile(r"\b(lorem|phasellus|suspendisse|curabitur)\b", re.IGNORECASE)


def owner_key(producer_id: str) -> str:
    return hashlib.sha256(f"{_OWNER_SALT}:{producer_id}".encode()).hexdigest()[:16]


def _ref(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha1('|'.join(parts).encode()).hexdigest()[:8].upper()}"


def fictionalize(text: str) -> str:
    for name, replacement in NAME_REPLACEMENTS:
        text = text.replace(name, replacement)
    return " ".join(text.split())


def _short(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def tag_for(subcategory: str, *texts: str) -> str:
    tag = SUBCATEGORY_TAGS.get(normalize(subcategory))
    if tag:
        return tag
    blob = " ".join(t.lower() for t in texts if t)
    for keywords, keyword_tag in KEYWORD_TAGS:
        if any(k in blob for k in keywords):
            return keyword_tag
    return DEFAULT_TAG


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build_peers() -> dict:
    status_by_key = {(r["account_sk"], r["project_description_txt"].strip()): r for r in _read(STATUS_CSV)}
    projects, dropped = [], 0
    for row in _read(PROJECTS_CSV):
        texts = [row[f] for f in ("translated_project_name", "translated_project_description_txt",
                                  "translated_project_reason_txt", "translated_primary_goal_txt")]
        if any(_PLACEHOLDER.search(t or "") for t in texts):
            dropped += 1
            continue
        name, description, reason, goal = (fictionalize(t or "") for t in texts)
        status = status_by_key.get((row["account_sk"], row["translated_project_description_txt"].strip()), {})
        project_ref = _ref("PROJ", row["account_sk"], row["translated_project_name"],
                           row["translated_project_description_txt"])
        projects.append({
            "project_ref": project_ref,
            "org_ref": _ref("ORG", row["account_sk"]),
            "owner_key": owner_key(row["account_sk"]),
            "source": f"{SOURCE_PREFIX} {project_ref}",
            "challenge_tag": tag_for(row["subcategory"], *texts),
            "crop": row["product_category_name"] or None,
            "entity_type": row["structure"] or None,
            "country": row["country"] or None,
            "region": row["region"] or None,
            "subcategory": row["subcategory"] or None,
            "name": _short(name, 160),
            "challenge": _short(reason),
            "action": _short(description or name),
            "intended_outcome": _short(goal),
            "status": status.get("project_status_name") or None,
            "start_date": status.get("project_start_date") or None,
            "end_date": status.get("project_end_date") or None,
        })
    return {"description": "Fictionalized, challenge-tagged peer Premium projects from the FTUSA sample. "
                           "owner_key is a salted hash used only to exclude a producer's own projects.",
            "dropped_placeholder_rows": dropped, "projects": projects}


def build_profiles() -> dict:
    regions: dict[str, Counter] = defaultdict(Counter)
    for row in _read(PROJECTS_CSV):
        if row["region"]:
            regions[row["account_sk"]][row["region"]] += 1
    profiles = {}
    for row in _read(ACCOUNTS_CSV):
        counts = regions.get(row["account_sk"])
        # Most projects decide the region; ties go to the alphabetically first, so builds are stable.
        region = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if counts else None
        profiles[row["account_sk"]] = {
            "country": row["country_name"] or None,
            "region": region,
            "crop": row["product_category_name"] or None,
            "entity_type": row["structure_txt"] or None,
        }
    return {"description": "Stand-in producer profiles from the FTUSA sample accounts, until the "
                           "producer-record tool (#14) and Athena tables (#28) exist.",
            "profiles": profiles}


# ---------------------------------------------------------------------------------------------
# Runtime lookups
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ProducerProfile:
    producer_id: str
    country: str | None
    region: str | None
    crop: str | None
    entity_type: str | None


class ProducerProfiles:
    def __init__(self, table: dict):
        self._profiles = table["profiles"]

    @classmethod
    def load(cls, path: Path = PROFILES_PATH) -> "ProducerProfiles":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def get(self, producer_id: str) -> ProducerProfile | None:
        row = self._profiles.get(producer_id)
        return ProducerProfile(producer_id, **row) if row else None


def _crops(crop: str | None) -> set[str]:
    return {normalize(p) for p in (crop or "").split(";") if p.strip()}


# Match weights. The tag is required; crop matters most, then entity type, then same country.
W_CROP, W_ENTITY, W_COUNTRY, W_COMPLETED = 0.4, 0.3, 0.2, 0.1


class PeerProjects:
    def __init__(self, table: dict):
        self._projects = table["projects"]

    @classmethod
    def load(cls, path: Path = PEERS_PATH) -> "PeerProjects":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def score(project: dict, profile: ProducerProfile) -> float:
        score = 0.0
        if _crops(project["crop"]) & _crops(profile.crop):
            score += W_CROP
        if profile.entity_type and normalize(project["entity_type"]) == normalize(profile.entity_type):
            score += W_ENTITY
        if profile.country and normalize(project["country"]) == normalize(profile.country):
            score += W_COUNTRY
        if project["status"] == "Completed":
            score += W_COMPLETED
        return round(score, 2)

    def find(self, challenge_tag: str, profile: ProducerProfile, limit: int = 3) -> list[dict]:
        """Projects OTHER producers funded for the same challenge, closest profile first.

        At most one project per organization, so one group cannot fill every slot.
        """
        own = owner_key(profile.producer_id)
        candidates = [p for p in self._projects
                      if p["challenge_tag"] == challenge_tag and p["owner_key"] != own]
        ranked = sorted(candidates, key=lambda p: (-self.score(p, profile), p["project_ref"]))
        results, seen_orgs = [], set()
        for p in ranked:
            if p["org_ref"] in seen_orgs:
                continue
            seen_orgs.add(p["org_ref"])
            item = {k: v for k, v in p.items() if k != "owner_key"}
            item["match_score"] = self.score(p, profile)
            results.append(item)
            if len(results) >= limit:
                break
        return results


def main() -> None:
    peers = build_peers()
    PEERS_PATH.write_text(json.dumps(peers, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    profiles = build_profiles()
    PROFILES_PATH.write_text(json.dumps(profiles, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tags = Counter(p["challenge_tag"] for p in peers["projects"])
    print(f"wrote {PEERS_PATH}: {len(peers['projects'])} projects "
          f"({peers['dropped_placeholder_rows']} placeholder rows dropped); {dict(tags)}", file=sys.stderr)
    print(f"wrote {PROFILES_PATH}: {len(profiles['profiles'])} profiles", file=sys.stderr)


if __name__ == "__main__":
    main()
