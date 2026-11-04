"""Peer Premium projects and producer profiles, built from the FTUSA sample data (issue #16).

    PYTHONPATH=src uv run python -m fx_data.peers   # offline: writes peer_projects.json, producer_profiles.json

Peer catalog (#16 spec; interim build until the #7 generator replaces it):
  - one row per environmental Premium project (`pprojects-full-environmental-with-acct-detail.csv`),
    with its start year from `Premium Projects Environmental.csv`
  - only the publishable fields: fictional organization name, country, crop, entity type, category,
    sub-category, start year and the description (organization and person names replaced), plus an
    opaque `catalog_id` and the challenge tags
  - one private column, `owner_key` (a salted hash of the owning account), used only to leave a
    producer's own projects out; never returned
  - placeholder rows (lorem ipsum) are dropped
  - not yet done (owned by #7): Comprehend PII check of each description, and the reviewed
    vocabulary and sub-category mapping tables

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
    # Added after code review (#54) found producer names the first list missed. Found by listing
    # every capitalized word that never appears in lowercase, then reading each in context.
    # Public bodies and standards (ICA, FLO, FLOCERT, CLAC, WWF, JAS, the World Bank) and places
    # are left alone.
    ("Seville cacaficulturers' cooperative - CAFISEVILLA", "the cacaficulturers' cooperative"),
    ("KSU Rahmat Kinara", "a member farmers' group"),
    ("Joan Fernie Charitable Trust (JFCT)", "a charitable trust"),
    ("Joan Fernie Charitable Trust", "a charitable trust"),
    ("JFCT", "the trust"),
    ("FA Tunas Beringin", "a member farmers' association"),
    ("Tunas Beringin", "a member farmers' association"),
    ("Yaholu Village", "a village"),
    ("Yaholu", "the village"),
    ("Chemase Estate", "an estate"),
    ("Marinyn Estate", "an estate"),
    ("Kaproret Estate", "an estate"),
    ("Kitumbe Factory", "a factory"),
    ("Finteaflo office", "an office"),
    ("Chepkembe head office", "the head office"),
    ("Chemase", "the estate"),
    ("Marinyn", "the estate"),
    ("Kaproret", "the estate"),
    ("Kitumbe", "the factory"),
    ("Finteaflo", "the office"),
    ("Chepkembe", "the head office"),
    ("MUSASA Coffee School", "the coffee school"),
    ("Musasa Coffee school", "the coffee school"),
    ("MUSASA", "the school"),
    ("FABICOOP Ltda.", "the cooperative"),
    ("FABICOOP Ltda", "the cooperative"),
    ("FABICOOP", "the cooperative"),
    ("CAFESCOR", "the cooperative"),
    ("Coopervitae", "the cooperative"),
    ("MELCOOP", "the cooperative"),
    ("FFSM", "the association"),
    ("Asoprokia", "the association"),
    ("Coratioquia", "the committee"),
    ("CAFICAICEDONIA", "the cooperative"),
    ("CAFISEVILLA", "the cooperative"),
    ("COMIXCAEL", "the cooperative"),
    ("COOCAFISA", "the cooperative"),
    ("CORCI", "the cooperative"),
    ("Cenfrocafe", "the cooperative"),
    ("CECJ", "a partner group"),
    ("GSC Community Service Group", "a community service group"),
    ("GSC", "the group"),
    ("Edulag and Pentágono Agrícola", "two farms"),
    ("Edulag", "a farm"),
    ("Pentágono Agrícola", "a farm"),
    ("Montesol Group corporation", "a banana company"),
    ("Montesol Group", "a banana company"),
    ("Montesol", "the company"),
    ("Campo Limpio corporation", "a collection corporation"),
    ("Campo Limpio", "a collection corporation"),
    ("RGC COFFEE", "a coffee importer"),
    ("RGC", "the importer"),
    ("Casa Común's", "the organization's"),
    ("Casa Común", "the organization"),
    ("PT. BMB", "a company"),
    ("BMB", "a company"),
    ("Nobland VN", "a company"),
    ("Nobland", "a company"),
    ("Popoyan", "a partner organization"),
    ("Perpetani", "the village"),
    ("SMTA", "the group's"),
    # Villages where an individual certified producer's garden is, finer than the region.
    ("La Zarzamora", "a village"),
    ("Atapan", "a village"),
], key=lambda pair: -len(pair[0]))

_PLACEHOLDER = re.compile(r"\b(lorem|phasellus|suspendisse|curabitur)\b", re.IGNORECASE)


def owner_key(producer_id: str) -> str:
    return hashlib.sha256(f"{_OWNER_SALT}:{producer_id}".encode()).hexdigest()[:16]


def _ref(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha1('|'.join(parts).encode()).hexdigest()[:8].upper()}"


_NAME_PATTERNS = [(re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)", re.IGNORECASE), r) for n, r in NAME_REPLACEMENTS]


def fictionalize(text: str) -> str:
    for pattern, replacement in _NAME_PATTERNS:
        text = pattern.sub(replacement, text)
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


def _outcome(rows: list[dict]) -> set[tuple]:
    return {(r["project_status_name"], r["project_start_date"], r["project_end_date"]) for r in rows}


def build_status_index() -> dict[tuple[str, str], list[dict]]:
    """Status rows grouped by (account, description). Several projects can share a description."""
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in _read(STATUS_CSV):
        index[(r["account_sk"], r["project_description_txt"].strip())].append(r)
    return index


def resolve_status(index: dict, row: dict) -> dict:
    """The status row for one project, or {} when it cannot be told apart.

    Same account and description can belong to several projects with different statuses and dates.
    Narrow by region and subcategory, then by project name. If the candidates still disagree, return
    {} so the project shows no status rather than another project's status.
    """
    candidates = index.get((row["account_sk"], row["translated_project_description_txt"].strip()), [])
    steps = (lambda r: r["country_region_name"] == row["region"]
             and r["sub_category_taxonomy_term_txt"] == row["subcategory"],
             lambda r: normalize(r["project_name"]) == normalize(row["translated_project_name"]))
    for keep in (None, *steps):
        if keep:
            narrowed = [r for r in candidates if keep(r)]
            candidates = narrowed or candidates
        if len(_outcome(candidates)) == 1:
            return candidates[0]
    return {}


def unique_project_ref(seen: Counter, account: str, name: str, description: str) -> str:
    """A ref that names exactly one project. The sample repeats some projects (same account, name and
    description), so repeats get an occurrence number. Refs of projects that appear once are unchanged."""
    key = (account, name, description)
    n = seen[key]
    seen[key] += 1
    return _ref("PROJ", *key) if n == 0 else _ref("PROJ", *key, str(n))


# Fictional organization names (#16: "peers shown only by fictionalized organization name").
_NAME_WORDS = ("Ceiba", "Guayacán", "Nogal", "Cedro", "Laurel", "Roble", "Sauce", "Olivo", "Almendro",
               "Ébano", "Caoba", "Pino", "Arrayán", "Encino", "Jacaranda", "Aliso", "Fresno", "Tilo",
               "Acacia", "Bambú", "Mangle", "Palma", "Higuera", "Naranjo", "Limonero", "Cacao", "Vainilla",
               "Canela", "Romero", "Salvia")
_NAME_KINDS = ("Producers' Group", "Growers' Association", "Farmers' Cooperative", "Producer Union",
               "Growers' Collective")
FICTIONAL_NAMES = tuple(f"{w} {k}" for k in _NAME_KINDS for w in _NAME_WORDS)  # 150 names


def fictional_names(org_keys: list[str]) -> dict[str, str]:
    """A stable fictional name per organization: sorted keys take names in order."""
    keys = sorted(set(org_keys))
    if len(keys) > len(FICTIONAL_NAMES):
        raise ValueError(f"{len(keys)} organizations but only {len(FICTIONAL_NAMES)} fictional names")
    return dict(zip(keys, FICTIONAL_NAMES))


def build_peers() -> dict:
    status_index = build_status_index()
    seen_refs: Counter = Counter()
    projects, dropped = [], 0
    for row in _read(PROJECTS_CSV):
        texts = [row[f] for f in ("translated_project_name", "translated_project_description_txt",
                                  "translated_project_reason_txt", "translated_primary_goal_txt")]
        if any(_PLACEHOLDER.search(t or "") for t in texts):
            dropped += 1
            continue
        name, description, reason, goal = (fictionalize(t or "") for t in texts)
        status = resolve_status(status_index, row)
        project_ref = unique_project_ref(seen_refs, row["account_sk"], row["translated_project_name"],
                                         row["translated_project_description_txt"])
        start = status.get("project_start_date") or ""
        if start.startswith("1970-01-01"):  # Unix-epoch placeholder in the sample, not a real date
            start = ""
        projects.append({
            "catalog_id": project_ref,
            "_org": _ref("ORG", row["account_sk"]),
            "owner_key": owner_key(row["account_sk"]),
            "tags": [tag_for(row["subcategory"], *texts)],
            "country": row["country"] or None,
            "crop": row["product_category_name"] or None,
            "entity_type": row["structure"] or None,
            "category": row["category"] or None,
            "sub_category": row["subcategory"] or None,
            "start_year": int(start[:4]) if start[:4].isdigit() else None,
            "description": _short(description or name),
        })
    names = fictional_names([p["_org"] for p in projects])
    for p in projects:
        p["organization"] = names[p.pop("_org")]
    return {"description": "Peer catalog: publishable fields only (#16), plus the private owner_key, a "
                           "salted hash used only to exclude a producer's own projects. Organizations are "
                           "fictional.",
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

    def ids(self) -> list[str]:
        """Every producer ID in the table, sorted."""
        return sorted(self._profiles)


def crop_set(crop: str | None) -> set[str]:
    return {normalize(p) for p in (crop or "").split(";") if p.strip()}


PUBLISHABLE = ("organization", "country", "crop", "entity_type", "category", "sub_category", "start_year",
               "description")
MAX_EXAMPLES = 3
_STRENGTH_RANK = {"exact": 0, "nearest": 1, "limited": 2}


class PeerProjects:
    def __init__(self, table: dict):
        self._projects = table["projects"]

    @classmethod
    def load(cls, path: Path = PEERS_PATH) -> "PeerProjects":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def strength(project: dict, crops: set[str], entity_type: str | None) -> str:
        """#16: tag + a crop + entity type is exact; tag + one of them is nearest; tag only is limited."""
        crop = bool(crop_set(project["crop"]) & crops)
        entity = bool(entity_type) and normalize(project["entity_type"]) == normalize(entity_type)
        return "exact" if crop and entity else "nearest" if crop or entity else "limited"

    def find(self, producer_id: str, tags: set[str], crops: set[str], entity_type: str | None,
             limit: int = MAX_EXAMPLES) -> list[dict]:
        """Projects OTHER producers funded that share a confirmed tag, strongest first, then most recent.

        At most one project per organization, so one group cannot fill every slot.
        """
        own = owner_key(producer_id)
        candidates = [p for p in self._projects if set(p["tags"]) & tags and p["owner_key"] != own]
        ranked = sorted(candidates, key=lambda p: (_STRENGTH_RANK[self.strength(p, crops, entity_type)],
                                                   -(p["start_year"] or 0), p["catalog_id"]))
        items, seen = [], set()
        for p in ranked:
            if p["organization"] in seen:
                continue
            seen.add(p["organization"])
            data = {k: p[k] for k in PUBLISHABLE}
            where = ", ".join(x for x in (p["entity_type"], p["crop"], p["country"]) if x)
            year = f" starting in {p['start_year']}" if p["start_year"] else ""
            items.append({"source": f"Premium project, {p['organization']} [{p['catalog_id']}]", "kind": "peer",
                          "text": f"{p['organization']} ({where}) funded a Premium project{year}: {p['description']}",
                          "period": str(p["start_year"]) if p["start_year"] else None,
                          "strength": self.strength(p, crops, entity_type), "data": data})
            if len(items) >= limit:
                break
        return items


def main() -> None:
    peers = build_peers()
    PEERS_PATH.write_text(json.dumps(peers, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    profiles = build_profiles()
    PROFILES_PATH.write_text(json.dumps(profiles, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tags = Counter(t for p in peers["projects"] for t in p["tags"])
    print(f"wrote {PEERS_PATH}: {len(peers['projects'])} projects "
          f"({peers['dropped_placeholder_rows']} placeholder rows dropped); {dict(tags)}", file=sys.stderr)
    print(f"wrote {PROFILES_PATH}: {len(profiles['profiles'])} profiles", file=sys.stderr)


if __name__ == "__main__":
    main()
