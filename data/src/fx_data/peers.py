"""Peer catalog and producer profiles: the runtime lookups, plus the sample-text helpers the generator uses.

The catalog and producer tables are built by the generator (fx_data.generator, issue #7) and read from
`generated/` (fx_data.tables). Peer catalog rules (#7 and #16 specs):
  - only the publishable fields, plus an opaque `catalog_id` and the challenge tags
  - one private column, `owner_producer_id`, used only to leave a producer's own projects out; never returned
  - organizations are fictional, and organization and person names in the text are replaced (NAME_REPLACEMENTS)
"""
from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fx_data.tables import GENERATED_DIR, read_table
from fx_data.text import normalize

HERE = Path(__file__).parent
SAMPLE_DIR = HERE.parents[2] / "docs" / "olena_data"
PROJECTS_CSV = SAMPLE_DIR / "pprojects-full-environmental-with-acct-detail.csv"
LINKED_DIR = SAMPLE_DIR / "Producers with Linked Project & Survey Data"
STATUS_CSV = LINKED_DIR / "Premium Projects Environmental.csv"
ACCOUNTS_CSV = LINKED_DIR / "Producer Accounts.csv"

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


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _outcome(rows: list[dict]) -> set[tuple]:
    return {(r["project_status_name"], r["project_start_date"], r["project_end_date"]) for r in rows}


def build_status_index(path: Path = STATUS_CSV) -> dict[tuple[str, str], list[dict]]:
    """Status rows grouped by (account, description). Several projects can share a description."""
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in _read(path):
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
    def load(cls, root: Path = GENERATED_DIR) -> "ProducerProfiles":
        """From the producer table. Crops are joined with ";" (e.g. "cocoa;coffee"), as crop_set reads them."""
        return cls({"profiles": {p["producer_id"]: {"country": p["country"], "region": p["admin1"],
                                                    "crop": ";".join(p["crops"]) or None,
                                                    "entity_type": p["entity_type"]}
                                 for p in read_table("producers", root)}})

    def get(self, producer_id: str) -> ProducerProfile | None:
        row = self._profiles.get(producer_id)
        return ProducerProfile(producer_id, **row) if row else None

    def ids(self) -> list[str]:
        """Every producer ID in the table, sorted."""
        return sorted(self._profiles)


# "other" is never used for matching (#14 spec): two producers with an unknown crop or entity type are not alike.
OTHER = "other"


def crop_set(crop: str | None) -> set[str]:
    return {normalize(p) for p in (crop or "").split(";") if p.strip()} - {OTHER}


PUBLISHABLE = ("organization", "country", "crop", "entity_type", "category", "sub_category", "start_year",
               "description")
MAX_EXAMPLES = 3
_STRENGTH_RANK = {"exact": 0, "nearest": 1, "limited": 2}


class PeerProjects:
    def __init__(self, table: dict):
        self._projects = table["projects"]

    @classmethod
    def load(cls, root: Path = GENERATED_DIR) -> "PeerProjects":
        return cls({"projects": read_table("peer_catalog", root)})

    @staticmethod
    def strength(project: dict, crops: set[str], entity_type: str | None) -> str:
        """#16: tag + a crop + entity type is exact; tag + one of them is nearest; tag only is limited."""
        crop = bool(crop_set(project["crop"]) & crops)
        entity = normalize(entity_type) not in ("", OTHER) and normalize(project["entity_type"]) == normalize(entity_type)
        return "exact" if crop and entity else "nearest" if crop or entity else "limited"

    def find(self, producer_id: str, tags: set[str], crops: set[str], entity_type: str | None,
             limit: int = MAX_EXAMPLES) -> list[dict]:
        """Projects OTHER producers funded that share a confirmed tag, strongest first, then most recent.

        At most one project per organization, so one group cannot fill every slot.
        """
        candidates = [p for p in self._projects if set(p["tags"]) & tags and p["owner_producer_id"] != producer_id]
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
