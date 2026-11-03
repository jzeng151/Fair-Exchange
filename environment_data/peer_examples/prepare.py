"""Pre-extraction: build the static tagged peer-projects table.

Reads the synthetic Premium projects CSV once and produces a clean table the
runtime tool consumes. Per project it:
  - assigns a challenge tag from the 11-tag set (mapped from the project's
    environmental subcategory + keyword fallback on the free text),
  - fictionalizes the organization and project into stable reference ids (the
    spec allows fictionalized org names/IDs for peer projects),
  - keeps the challenge / action / intended-outcome text (translated fields).

Usage:
    python -m peer_examples.prepare \
        --csv ../docs/olena_data/pprojects-full-environmental-with-acct-detail.csv \
        --out data/peer_projects.json

In the sandbox this JSON goes to S3 alongside the climate table; here it is local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Map the CSV environmental subcategory -> one of the 11 challenge tags.
_SUBCATEGORY_TO_TAG = {
    "Clean Water": "water",
    "Climate Change Mitigation/Adaptation (Clean Energy, Agroforestry etc.)": "climate and weather",
    "Pest Management": "soil and land",
    "Crop Diversification": "soil and land",
    "Waste Disposal / Recycling": "biodiversity and conservation",
    "Waste management (Trash collection, recycling facilities etc.)": "biodiversity and conservation",
    "Waste Management (trash collection, recycling facilities etc.)": "biodiversity and conservation",
    "Sustainability efforts": "biodiversity and conservation",
    "Human resources and administration/ office services": "social and community",
}

# Keyword fallback for rows with a blank subcategory, applied to the free text.
_KEYWORD_TO_TAG = [
    (("water", "rainwater", "irrigation", "honey water", "wastewater"), "water"),
    (("solar", "clean energy", "carbon", "climate", "agroforestry", "reforest"), "climate and weather"),
    (("pest", "disease", "pesticide", "fungus", "soil", "erosion", "fertiliz", "compost"), "soil and land"),
    (("biodiversity", "conservation", "forest", "ecosystem", "wildlife", "recycl", "waste"), "biodiversity and conservation"),
]

_DEFAULT_TAG = "biodiversity and conservation"  # all rows are environmental


def _tag_for(subcategory: str, *texts: str) -> str:
    sub = (subcategory or "").strip()
    if sub in _SUBCATEGORY_TO_TAG:
        return _SUBCATEGORY_TO_TAG[sub]
    blob = " ".join(t.lower() for t in texts if t)
    for keywords, tag in _KEYWORD_TO_TAG:
        if any(k in blob for k in keywords):
            return tag
    return _DEFAULT_TAG


def _ref(prefix: str, *parts: str) -> str:
    """Stable, fictional reference id derived from the source identifiers.

    Deterministic (same input -> same ref) so the agent can cite a stable id,
    but it does not expose the real account_sk.
    """
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{h}"


def _truncate(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def build_table(csv_path: str) -> Dict:
    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    projects: List[Dict] = []
    for r in rows:
        account_sk = r.get("account_sk", "")
        name = r.get("translated_project_name", "")
        reason = r.get("translated_project_reason_txt", "")
        description = r.get("translated_project_description_txt", "")
        goal = r.get("translated_primary_goal_txt", "")
        crop = r.get("product_category_name", "") or None
        country = r.get("country", "") or None
        region = r.get("region", "") or None
        entity = r.get("structure", "") or None
        subcategory = r.get("subcategory", "")

        tag = _tag_for(subcategory, name, reason, description, goal)

        projects.append(
            {
                "project_ref": _ref("PROJ", account_sk, name),
                "org_ref": _ref("ORG", account_sk),
                # real account_sk kept ONLY for scope-exclusion at query time;
                # never surfaced to the producer.
                "_account_sk": account_sk,
                "challenge_tag": tag,
                "crop": crop,
                "country": country,
                "region": region,
                "entity_type": entity,
                "subcategory": subcategory or None,
                "name": _truncate(name, 160),
                "challenge": _truncate(reason),
                "action": _truncate(description or name),
                "intended_outcome": _truncate(goal),
            }
        )

    return {
        "schema_version": 1,
        "generated": datetime.utcnow().isoformat() + "Z",
        "description": (
            "Pre-extracted, challenge-tagged peer Premium projects (synthetic, "
            "fictionalized org/project refs) for the peer-example agent tool."
        ),
        "projects": projects,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pre-extract peer projects table")
    default_csv = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs",
        "olena_data",
        "pprojects-full-environmental-with-acct-detail.csv",
    )
    parser.add_argument("--csv", default=default_csv, help="path to the projects CSV")
    parser.add_argument("--out", default="data/peer_projects.json", help="output JSON path")
    args = parser.parse_args(argv)

    table = build_table(args.csv)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=2, ensure_ascii=False)

    from collections import Counter

    tags = Counter(p["challenge_tag"] for p in table["projects"])
    print(f"Wrote {args.out}: {len(table['projects'])} projects", file=sys.stderr)
    for tag, n in tags.most_common():
        print(f"  {n:4}  {tag}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
