"""Made-up producer/consumer/supplier personas, so the chat can address the visitor by a
fictitious name (SDD.md). Deterministic per session seed, so a page reload keeps the same person.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict

PROFILES = ("producer", "consumer", "supplier")

# First and last names chosen to reflect Fair Trade's focus regions, with the record kept fictitious.
_FIRST = [
    "Mariana", "Kwame", "Aduke", "Santiago", "Priya", "Diego", "Amara", "Luz",
    "Tendai", "Rosa", "Kofi", "Yara", "Ananya", "Mateo", "Fatou", "Camila",
]
_LAST = [
    "Okafor", "Mendoza", "Osei", "Ramírez", "Sharma", "Fofana", "Herrera",
    "Nguyen", "Castillo", "Mwangi", "Silva", "Konan", "Reyes", "Diallo",
]

_REGIONS = {
    "producer": [
        ("Cauca", "Colombia", "Coffee"),
        ("Sud-Comoé", "Côte d'Ivoire", "Cocoa"),
        ("Chiapas", "Mexico", "Coffee"),
        ("San Martín", "Peru", "Cocoa"),
        ("Kericho", "Kenya", "Tea"),
    ],
    "consumer": [
        ("Portland", "United States", "Coffee drinker"),
        ("Berlin", "Germany", "Chocolate lover"),
        ("Toronto", "Canada", "Tea drinker"),
    ],
    "supplier": [
        ("Hamburg", "Germany", "Green coffee importer"),
        ("Antwerp", "Belgium", "Cocoa trader"),
        ("San Francisco", "United States", "Specialty roaster"),
    ],
}

# The entity each profile belongs to, used in the greeting.
_ROLE_LABEL = {
    "producer": "a producer cooperative member",
    "consumer": "a Fair Trade shopper",
    "supplier": "a supply-chain partner",
}


@dataclass
class Persona:
    name: str
    profile: str
    role_label: str
    region: str
    country: str
    focus: str
    org: str

    def as_dict(self) -> dict:
        return asdict(self)


def make_persona(seed: int, profile: str) -> Persona:
    profile = profile if profile in PROFILES else "producer"
    rng = random.Random(f"{seed}-{profile}")
    first, last = rng.choice(_FIRST), rng.choice(_LAST)
    region, country, focus = rng.choice(_REGIONS[profile])
    org = {
        "producer": f"{region} {focus} Cooperative",
        "consumer": f"{region} community",
        "supplier": f"{focus.split()[0]} Partners, {country}",
    }[profile]
    return Persona(
        name=f"{first} {last}",
        profile=profile,
        role_label=_ROLE_LABEL[profile],
        region=region,
        country=country,
        focus=focus,
        org=org,
    )
