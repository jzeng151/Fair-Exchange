"""Interactive demo: run both tools for a producer and print the full response.

Lets you eyeball the real output for any inputs before committing. Uses the
generated tables in data/.

Examples:
    python -m tools.demo --country Colombia --region Cauca --crop Coffee --tag water
    python -m tools.demo --country Colombia --region Huila --crop Coffee --tag "climate and weather" --entity "1st Grade"
    python -m tools.demo --country Vietnam --region "Khanh Hoa" --crop Seafood --tag water
"""

from __future__ import annotations

import argparse
import sys

from peer_examples.tool import get_peer_examples
from regional_context.tool import get_regional_climate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo both agent tools for one producer")
    ap.add_argument("--country", required=True)
    ap.add_argument("--region", default=None)
    ap.add_argument("--crop", default=None)
    ap.add_argument("--tag", required=True, help="challenge tag, e.g. 'water'")
    ap.add_argument("--entity", default=None, help="entity type, e.g. '1st Grade'")
    ap.add_argument("--exclude", default=None, help="session producer account id to exclude")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args(argv)

    print("=" * 70)
    print(f"PRODUCER: {args.crop or '?'} | {args.region or '?'}, {args.country}")
    print(f"CHALLENGE TAG: {args.tag}" + (f" | ENTITY: {args.entity}" if args.entity else ""))
    print("=" * 70)

    print("\nWHAT THE DATA SHOWS (regional_context)")
    print("-" * 70)
    clim = get_regional_climate(args.country, args.region, args.crop)
    if clim.matched:
        if clim.note:
            print(f"  [note] {clim.note}")
        for c in clim.claims:
            val = f" ({c.value}{c.unit or ''})" if c.value is not None else ""
            print(f"  - {c.statement}{val}")
            print(f"      cite: {c.citation.source} | retrieved {c.citation.retrieved}")
    else:
        print(f"  (no regional data) {clim.note}")

    print("\nWHAT PEERS DID (peer_examples)")
    print("-" * 70)
    peers = get_peer_examples(
        challenge_tag=args.tag,
        crop=args.crop,
        entity_type=args.entity,
        exclude_account_sk=args.exclude,
        limit=args.limit,
    )
    if peers.matched:
        for i, e in enumerate(peers.examples, 1):
            print(f"  {i}. {e.crop or '?'} producer in {e.region or '?'}, {e.country or '?'} "
                  f"(match {e.match_score})")
            print(f"       challenge: {e.challenge}")
            print(f"       did:       {e.action}")
            print(f"       goal:      {e.intended_outcome}")
            print(f"       cite:      {e.citation.project_ref} / {e.citation.org_ref}")
    else:
        print(f"  (no peer examples) {peers.note}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
