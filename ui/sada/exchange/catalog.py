"""Pickable personas for the PoC (one tile per persona on the picker), plus per-persona candidate questions,
location, and a made-up weather overlay. Later the weather block is replaced with a real feed.

Kept small on purpose: two roles, a few products each, at most three personas per product, drawn from
the vision document's focus regions (Peru, Honduras, Colombia, Côte d'Ivoire, Mexico, and seafood).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Location:
    place: str          # "Chiapas, Mexico"
    lat: float
    lon: float
    zoom: int = 6

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Weather:
    """Made-up now; shaped like a real feed so it can be swapped later."""
    summary: str
    temp_c: int
    rain_mm_7d: int
    rain_vs_normal: str   # e.g. "32% below normal"
    water_stress: str     # "High" | "Medium" | "Low"
    icon: str             # emoji stand-in

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Persona:
    id: str
    role: str            # "producer" | "consumer"
    product: str         # "coffee" | "seafood" | "rice" | "cocoa" | "groceries"
    name: str
    blurb: str
    org: str
    location: Location
    weather: Weather
    questions: list[str]
    avatar: str          # emoji
    language: str = "en"  # chat language the persona starts in (a key of engine.LANGUAGES)
    flag: str = ""        # emoji flag for the location
    # Real API mode: the scenario producer (eval/scenarios/*.json) this persona signs in as. Producers only;
    # the real agent serves producers, so consumers stay on mock data.
    fex_producer_id: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


# ------------------------------------------------------------------ catalog

PERSONAS: list[Persona] = [
    # ---- PRODUCERS ----
    Persona(
        id="prod-coffee-mx",
        role="producer", product="coffee",
        name="Mateo Herrera", avatar="☕",
        blurb="Smallholder coffee farmer; late rains hurt this season's cherries.",
        org="Chiapas Highlands Coffee Cooperative",
        language="es", flag="🇲🇽",
        fex_producer_id="95A4A8BC3F2E3F38F8D6A81B57BA5E4A",  # mexico-price-drop-en
        location=Location("Chiapas, Mexico", 16.75, -92.64, 6),
        weather=Weather("Dry and warm, late rains", 24, 11, "38% below normal", "High", "🌤️"),
        questions=[
            "The rains came late again — what does the data show for my area?",
            "How have nearby cooperatives used the Premium for water?",
        ],
    ),
    Persona(
        id="prod-coffee-co",
        role="producer", product="coffee",
        name="Luz Ramírez", avatar="☕",
        blurb="Cooperative member in Cauca; prices dipped below last year.",
        org="Cauca Coffee Growers Cooperative",
        language="es", flag="🇨🇴",
        fex_producer_id="CFC19603C1B7B29C017954FD1DB2D620",  # colombia-drought-es
        location=Location("Cauca, Colombia", 2.44, -76.61, 6),
        weather=Weather("Humid, scattered showers", 21, 48, "near normal", "Medium", "🌦️"),
        questions=[
            "Farm-gate prices dropped — what are peers doing about it?",
            "What do the standards say about Premium and pricing?",
        ],
    ),
    Persona(
        id="prod-seafood-pe",
        role="producer", product="seafood",
        name="Rosa Castillo", avatar="🐟",
        blurb="Artisanal fisher cooperative; catches are shifting with warmer water.",
        org="Pacífico Norte Fishers Association",
        language="es", flag="🇵🇪",
        fex_producer_id="CED2DEE8ED99922FA5C6244DEF177AF3",  # S4 honduras (es): the Peru scenario left eval/scenarios
        location=Location("Piura, Peru (coast)", -5.19, -81.11, 6),
        weather=Weather("Warm sea surface, calm", 26, 2, "dry season", "Low", "🌊"),
        questions=[
            "Our catch is changing — what does the data suggest?",
            "How have other fisher groups adapted with the Premium?",
        ],
    ),
    Persona(
        id="prod-rice-ci",
        role="producer", product="rice",
        name="Fatou Fofana", avatar="🌾",
        blurb="Rice grower; soil is tiring on low-cover plots.",
        org="Sud-Comoé Rice Collective",
        language="fr", flag="🇨🇮",
        fex_producer_id="9D79CF4ED3FBE4CFBD3640576B74642A",  # cote-divoire-cocoa-pii-fr
        location=Location("Sud-Comoé, Côte d'Ivoire", 5.52, -3.22, 6),
        weather=Weather("Hot, humid, storms building", 30, 64, "12% above normal", "Medium", "⛈️"),
        questions=[
            "My soil feels tired — what can the data tell me?",
            "What have similar farms tried for soil health?",
        ],
    ),

    # ---- CONSUMERS ----
    Persona(
        id="cons-coffee-us",
        role="consumer", product="coffee",
        name="Priya Sharma", avatar="🛍️",
        blurb="Buys Fair Trade coffee; curious where it comes from and the impact.",
        org="Portland, shopper",
        language="en", flag="🇺🇸",
        location=Location("Portland, United States", 45.52, -122.68, 7),
        weather=Weather("Cool and clear", 12, 20, "near normal", "Low", "🌥️"),
        questions=[
            "Where does my Fair Trade coffee come from?",
            "What has the Premium funded for those growers?",
        ],
    ),
    Persona(
        id="cons-groceries-de",
        role="consumer", product="groceries",
        name="Amara Okafor", avatar="🧺",
        blurb="Weekly Fair Trade groceries; wants to understand the label.",
        org="Berlin, shopper",
        language="en", flag="🇩🇪",
        location=Location("Berlin, Germany", 52.52, 13.40, 7),
        weather=Weather("Overcast, mild", 9, 14, "near normal", "Low", "☁️"),
        questions=[
            "What does the Fair Trade Certified label actually guarantee?",
            "How do producers decide how to use the Premium?",
        ],
    ),
    Persona(
        id="cons-seafood-ca",
        role="consumer", product="seafood",
        name="Diego Mendoza", avatar="🐟",
        blurb="Chooses Fair Trade seafood; cares about the fishers behind it.",
        org="Toronto, shopper",
        language="en", flag="🇨🇦",
        location=Location("Toronto, Canada", 43.65, -79.38, 7),
        weather=Weather("Crisp, light wind", 7, 9, "near normal", "Low", "🌬️"),
        questions=[
            "What does Fair Trade mean for the fishers who caught this?",
            "How is seafood traced back to its source?",
        ],
    ),
]

ROLES = ["producer", "consumer"]

# Personas shown on the picker, three per role. Others stay in PERSONAS so their chat links still work.
PICKER_IDS = [
    "prod-coffee-mx", "prod-seafood-pe", "prod-rice-ci",
    "cons-coffee-us", "cons-groceries-de", "cons-seafood-ca",
]


def products_for(role: str) -> list[str]:
    seen: list[str] = []
    for p in PERSONAS:
        if p.role == role and p.product not in seen:
            seen.append(p.product)
    return seen


def personas_for(role: str, product: str) -> list[Persona]:
    return [p for p in PERSONAS if p.role == role and p.product == product][:3]


def get_persona(persona_id: str) -> Persona | None:
    return next((p for p in PERSONAS if p.id == persona_id), None)


PRODUCT_LABEL = {
    "coffee": "Coffee", "seafood": "Seafood & fishers", "rice": "Rice",
    "cocoa": "Cocoa", "groceries": "Groceries",
}
ROLE_LABEL = {"producer": "Producer", "consumer": "Consumer"}
ROLE_ICON = {"producer": "🌱", "consumer": "🛍️"}
PRODUCT_ICON = {
    "coffee": "☕", "seafood": "🐟", "rice": "🌾", "cocoa": "🍫", "groceries": "🧺",
}
