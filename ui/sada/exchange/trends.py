"""Demographics and trending concerns per persona region/product (E4), plus a simple report
builder (E3) and a shared-data points model (E7). All fictitious; shaped for later real data.
"""
from __future__ import annotations

from .catalog import Persona

# Trending concerns + light demographics, keyed by product. Aggregated, no individuals.
_TRENDS = {
    "coffee": {
        "demographics": [
            {"label": "Smallholders", "value": "72%"},
            {"label": "Women-led farms", "value": "34%"},
            {"label": "Avg. farm size", "value": "2.1 ha"},
        ],
        "trending": [
            {"tag": "Water", "note": "Late/short rains", "trend": "▲ 18%"},
            {"tag": "Price", "note": "Farm-gate dip vs. 5-yr median", "trend": "▲ 9%"},
            {"tag": "Soil", "note": "Organic matter on low-cover plots", "trend": "▲ 4%"},
        ],
    },
    "seafood": {
        "demographics": [
            {"label": "Artisanal fishers", "value": "81%"},
            {"label": "Cooperative members", "value": "61%"},
            {"label": "Avg. vessel size", "value": "< 12 m"},
        ],
        "trending": [
            {"tag": "Climate", "note": "Warmer sea surface, shifting catch", "trend": "▲ 22%"},
            {"tag": "Market", "note": "Export price swings", "trend": "▲ 7%"},
            {"tag": "Labor", "note": "Crew availability", "trend": "▲ 3%"},
        ],
    },
    "rice": {
        "demographics": [
            {"label": "Smallholders", "value": "68%"},
            {"label": "Irrigated plots", "value": "45%"},
            {"label": "Avg. farm size", "value": "1.6 ha"},
        ],
        "trending": [
            {"tag": "Soil", "note": "Fatigue on low-cover plots", "trend": "▲ 14%"},
            {"tag": "Water", "note": "Irrigation timing", "trend": "▲ 8%"},
            {"tag": "Climate", "note": "Heavier storms", "trend": "▲ 6%"},
        ],
    },
    "groceries": {
        "demographics": [
            {"label": "Repeat buyers", "value": "58%"},
            {"label": "Label-aware", "value": "76%"},
            {"label": "Premium interest", "value": "High"},
        ],
        "trending": [
            {"tag": "Transparency", "note": "Where products come from", "trend": "▲ 19%"},
            {"tag": "Impact", "note": "What the Premium funds", "trend": "▲ 12%"},
            {"tag": "Price", "note": "Fair pricing questions", "trend": "▲ 5%"},
        ],
    },
}
_DEFAULT = _TRENDS["coffee"]


def trends_for(persona: Persona) -> dict:
    return _TRENDS.get(persona.product, _DEFAULT)


# E7: points for contributing data. Light gamification; fictitious economy.
POINTS_PER_SHARED_TURN = 25
POINTS_PER_TAG = 10
POINTS_PER_RATING = 5   # rating a shared answer tells reviewers how useful it was


def points_summary(shared_turns: int, tags: list[str], ratings: list[int] | None = None) -> dict:
    unique_tags = sorted(set(tags))
    rated = [r for r in (ratings or []) if isinstance(r, int) and 1 <= r <= 5]
    breakdown = [
        {"label": "Exchanges shared", "count": shared_turns, "points": shared_turns * POINTS_PER_SHARED_TURN},
        {"label": "Topics covered", "count": len(unique_tags), "points": len(unique_tags) * POINTS_PER_TAG},
        {"label": "Answers rated", "count": len(rated), "points": len(rated) * POINTS_PER_RATING},
    ]
    points = sum(b["points"] for b in breakdown)
    tier = "Seed" if points < 100 else "Grower" if points < 250 else "Steward"
    return {
        "shared_turns": shared_turns,
        "unique_tags": unique_tags,
        "points": points,
        "breakdown": breakdown,
        "tier": tier,
        "next_tier_at": 100 if points < 100 else 250 if points < 250 else None,
        "avg_rating": round(sum(rated) / len(rated), 1) if rated else None,
        "rated_count": len(rated),
    }


def usage_summary(persona: Persona, shared_turns: int, tags: list[str]) -> dict:
    """How shared exchanges were used and rated by others (E7). Sample figures, deterministic per persona
    and amount shared, until real reviewer/peer usage data exists."""
    if shared_turns <= 0:
        return {"sample": True, "peer_views": 0, "cited_in_answers": 0, "in_reports": 0,
                "peer_rating": None, "peer_raters": 0, "top_percent": None, "region": persona.location.place}
    seed = sum(ord(c) for c in persona.id)
    topics = len(set(tags))
    raters = 2 * shared_turns + topics + seed % 3
    return {
        "sample": True,
        "peer_views": 6 * shared_turns + 4 * topics + seed % 7,
        "cited_in_answers": shared_turns + topics // 2,
        "in_reports": 1 if shared_turns >= 2 else 0,
        "peer_rating": round(min(4.9, 3.8 + 0.15 * shared_turns + 0.1 * topics + (seed % 4) / 10), 1),
        "peer_raters": raters,
        "top_percent": max(5, 60 - 10 * shared_turns - 5 * topics),
        "region": persona.location.place.split(",")[0],
    }
