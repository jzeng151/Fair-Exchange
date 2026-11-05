"""Sample chat history per profile, and a regional inquiry log (SDD.md).

All fictitious. The history shows what a prior exchange looked like for that profile; the log shows
recent concerns in the region so a visitor sees they are not alone.
"""
from __future__ import annotations

HISTORY = {
    "producer": [
        {"role": "assistant", "text": "Welcome back. Last time we looked at the dry spell affecting your coffee."},
        {"role": "user", "text": "Yes, the rains came late again and cherries dropped early."},
        {"role": "assistant",
         "text": "The rainfall data backed that up, and a nearby cooperative used the Premium for mulch "
                 "and catchment tanks. That's an option to weigh, not a step to take.",
         "citations": [{"label": "CHIRPS rainfall (open data)", "kind": "regional"},
                       {"label": "Fair Trade Premium project (sample) PROJ-1C85", "kind": "peer"}]},
    ],
    "consumer": [
        {"role": "assistant", "text": "Hi again. You were curious where your Fair Trade coffee comes from."},
        {"role": "user", "text": "Right, I'd love to know the impact of the Premium."},
        {"role": "assistant",
         "text": "For your roaster's cooperatives, the Premium has funded water retention and shared "
                 "processing. Here's a summary you can share.",
         "citations": [{"label": "Fair Trade impact summary (sample)", "kind": "peer"}]},
    ],
    "supplier": [
        {"role": "assistant", "text": "Welcome back. We were reviewing certification readiness for a new lot."},
        {"role": "user", "text": "Yes, which standard clauses matter most for traceability?"},
        {"role": "assistant",
         "text": "Traceability maps to the certification standard on chain-of-custody. I can point to the "
                 "clauses and what partner organizations usually document.",
         "citations": [{"label": "APS chain-of-custody clauses", "kind": "standard"}]},
    ],
}

# Recent concerns in the region, shown as a live-looking log. Fictitious, aggregated, no individuals.
REGIONAL_LOG = [
    {"region": "Cauca, Colombia", "tag": "Water", "note": "Late rains, early cherry drop", "count": 7},
    {"region": "Sud-Comoé, Côte d'Ivoire", "tag": "Price", "note": "Farm-gate price dip vs. 5-yr median", "count": 5},
    {"region": "Chiapas, Mexico", "tag": "Labor", "note": "Tight seasonal harvest crews", "count": 4},
    {"region": "San Martín, Peru", "tag": "Soil", "note": "Declining organic matter on low-cover plots", "count": 3},
    {"region": "Kericho, Kenya", "tag": "Water", "note": "High water-stress rating this season", "count": 3},
]


def history_for(profile: str) -> list[dict]:
    return [dict(m) for m in HISTORY.get(profile, HISTORY["producer"])]
