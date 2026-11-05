"""Seeded conversation records for the dashboard (issue #37). Spec: docs/specs/37-seeded-records.md.

A few demo conversations cannot clear the analytics rule that hides any group under 5, so this module
produces a fixed set of about 200 synthetic conversation records, from a fixed random seed:
  - every one of the 11 challenge tags, in `en` and `es`;
  - producers and their entity types from the producer table. The producer-record tool (#14) is not
    built yet, so this uses its stand-in, `ProducerProfiles` (the #7 producer table);
  - every consent scope, including declines; every feedback value; `full` and `limited` evidence;
    reviewed and pending records; and per-model token counts (`ai_usage`).

Records are plain JSON-ready dicts. They are validated against the record models and uploaded to the
`records-seeded/` S3 prefix by the agent package (`fex.seeded`): the record models live there, and the
agent package already depends on this one, so this module must not import `fex`.

All text and record IDs are visibly synthetic (`[Synthetic]`, `SEED-`). No personal information.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fx_data.peers import ProducerProfiles

SEED = 37
N_COMPLETED = 172
N_DECLINED = 28

# Mirrors the default model IDs of the agent runtime (agent/src/fex/conversation/runtime.py)
SMALL_MODEL = "us.anthropic.claude-haiku-5-5"
LARGE_MODEL = "us.anthropic.claude-sonnet-5-5"

BASE_TIME = datetime(2026, 9, 1, tzinfo=timezone.utc)
WINDOW_MINUTES = 60 * 24 * 60  # conversations spread over 60 days

# tag -> (related clause, English summary, Spanish summary)
TOPICS: dict[str, tuple[str, str, str]] = {
    "climate and weather": ("APS 1.3", "Rains came late this year and the harvest window moved.",
                            "Las lluvias llegaron tarde este año y la cosecha se movió."),
    "water": ("APS 4.1", "Wells run low in the dry months and irrigation is hard to plan.",
              "Los pozos bajan en los meses secos y es difícil planear el riego."),
    "soil and land": ("APS 4.3", "The soil on the slopes is tired and yields keep falling.",
                      "El suelo de las laderas está cansado y el rendimiento sigue bajando."),
    "market and price": ("APS 5.2", "The buyer price dropped and costs went up.",
                         "El precio del comprador bajó y los costos subieron."),
    "labor and migration": ("APS 3.5", "It is hard to find pickers at harvest time.",
                            "Es difícil encontrar recolectores en tiempo de cosecha."),
    "financial and access to capital": ("APS 1.2", "We cannot get credit to replace old plants.",
                                        "No conseguimos crédito para renovar las plantas viejas."),
    "education": ("APS 2.2", "Members want training on new farming practices.",
                  "Los socios quieren capacitación en nuevas prácticas agrícolas."),
    "health": ("APS 3.6", "Workers lack nearby access to a health post.",
               "Los trabajadores no tienen un puesto de salud cerca."),
    "infrastructure": ("APS 1.2", "The road to the collection center floods every season.",
                       "El camino al centro de acopio se inunda cada temporada."),
    "biodiversity and conservation": ("APS 4.2", "We want to protect the forest edge near the farms.",
                                      "Queremos proteger el borde del bosque cerca de las fincas."),
    "social and community": ("APS 1.1", "The community wants a say in how the Premium is used.",
                             "La comunidad quiere opinar sobre el uso de la Prima."),
}
CHALLENGE_TAGS = set(TOPICS)
_TAGS = list(TOPICS)
_FEEDBACK = ["yes", "somewhat", "no", None]
_REVIEWERS = ["SEED-REVIEWER-01", "SEED-REVIEWER-02"]


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _claim(rng: random.Random, tag: str, language: str, kind: str) -> dict:
    clause = TOPICS[tag][0]
    text = (f"[Sintético] Dato de demostración ({kind}) sobre {tag}." if language == "es"
            else f"[Synthetic] Demo {kind} about {tag}.")
    return {"text": text, "citation": {"source": "Synthetic seeded data (#37)", "standard_clause": clause,
                                       "period": "2025", "strength": rng.choice(["exact", "nearest", "limited"])}}


def _answer(rng: random.Random, tags: list[str], language: str, limited: bool) -> tuple[list, list]:
    insights = [_claim(rng, t, language, "insight") for t in tags]
    peers = [_claim(rng, tags[0], language, "peer example")]
    if limited:  # limited evidence: no insights or no peer examples
        if rng.random() < 0.5:
            insights = []
        else:
            peers = []
    return insights, peers


def _ai_usage(rng: random.Random, with_large: bool) -> list[dict]:
    usage = [{"model_id": SMALL_MODEL, "input_tokens": rng.randint(1500, 6000),
              "output_tokens": rng.randint(200, 900)}]
    if with_large:
        usage.append({"model_id": LARGE_MODEL, "input_tokens": rng.randint(4000, 20000),
                      "output_tokens": rng.randint(500, 2500)})
    return usage


def _history(rng: random.Random, final: str, at: datetime, earlier_choices: list[str]) -> list[dict]:
    """The distinct consent choices in order, ending with the final one at `at`."""
    history = []
    if rng.random() < 0.25:
        history.append({"scope": rng.choice(earlier_choices), "recorded_at": _ts(at - timedelta(minutes=2))})
    history.append({"scope": final, "recorded_at": _ts(at)})
    return history


def _completed(rng: random.Random, i: int, producer_id: str, entity_type: str | None) -> dict:
    tag = _TAGS[i % len(_TAGS)]
    tags = [tag] + ([rng.choice([t for t in _TAGS if t != tag])] if rng.random() < 0.35 else [])
    language = "es" if i % 2 else "en"
    scope = "internal_and_outward" if i % 3 == 0 else "internal"
    limited = i % 5 == 0
    feedback = _FEEDBACK[i % len(_FEEDBACK)]

    created = BASE_TIME + timedelta(minutes=rng.randrange(WINDOW_MINUTES))
    consented = created + timedelta(minutes=rng.randint(4, 15))
    history = _history(rng, scope, consented, [s for s in ("internal", "internal_and_outward", "declined")
                                               if s != scope])
    saves = [consented] * len(history)
    if feedback is not None:
        saves.append(consented + timedelta(minutes=1))
    closed = consented + timedelta(minutes=rng.randint(2, 30))
    reviewed = rng.random() < 0.6
    still_open = not reviewed and rng.random() < 0.15
    if not still_open:
        saves.append(closed)

    summary_en = f"[Synthetic] {TOPICS[tag][1]}"
    record = {
        "record_id": "", "producer_id": producer_id, "status": "completed",
        "created_at": _ts(created),
        "closed_at": None if still_open else _ts(closed),
        "consent": {"scope": scope, "recorded_at": _ts(consented)},
        "consent_history": history,
        "language": language,
        "entity_type": entity_type or "unknown",  # same fallback as write-back (#26)
        "summary_original": f"[Sintético] {TOPICS[tag][2]}" if language == "es" else summary_en,
        "summary_english": summary_en if language == "es" else None,
        "tags": tags,
        "feedback": feedback,
        "review_status": "pending",
        "earlier_answers": [],
    }
    if rng.random() < 0.1:  # the producer reopened the playback once
        ins, peers = _answer(rng, tags, language, limited=False)
        record["earlier_answers"].append({"given_at": _ts(consented - timedelta(minutes=3)), "reason": "reopened",
                                          "insights": ins, "peer_examples": peers, "evidence": "full"})
    record["insights"], record["peer_examples"] = _answer(rng, tags, language, limited)
    record["evidence"] = "limited" if limited else "full"
    if reviewed:
        reviewed_at = closed + timedelta(days=rng.randint(1, 5), minutes=rng.randrange(600))
        saves.append(reviewed_at)
        record.update(review_status="reviewed", reviewed_by=rng.choice(_REVIEWERS), reviewed_at=_ts(reviewed_at))
        if rng.random() < 0.25:  # the reviewer corrected the agent's tags
            record["reviewer_tags"] = [rng.choice([t for t in _TAGS if t not in tags])]
    record["version"] = len(saves)
    record["updated_at"] = _ts(max(saves))
    record["ai_usage"] = _ai_usage(rng, with_large=True)
    return record


def _declined(rng: random.Random, producer_id: str) -> dict:
    created = BASE_TIME + timedelta(minutes=rng.randrange(WINDOW_MINUTES))
    declined_at = created + timedelta(minutes=rng.randint(4, 15))
    history = _history(rng, "declined", declined_at, ["internal", "internal_and_outward"])
    closed = declined_at + timedelta(minutes=rng.randint(1, 10))
    return {
        "record_id": "", "producer_id": producer_id, "status": "declined",
        "created_at": _ts(created), "updated_at": _ts(closed), "version": len(history) + 1,
        "closed_at": _ts(closed),
        "consent": {"scope": "declined", "recorded_at": _ts(declined_at)},
        "consent_history": history,
        "ai_usage": _ai_usage(rng, with_large=rng.random() < 0.5),  # declined after the playback, or before
    }


def generate_seeded_records(seed: int = SEED, profiles: ProducerProfiles | None = None) -> list[dict]:
    """The seeded record set: the same seed always gives the same records, in the same order."""
    rng = random.Random(seed)
    profiles = profiles or ProducerProfiles.load()
    ids = profiles.ids()
    records = []
    for i in range(N_COMPLETED):
        producer = profiles.get(rng.choice(ids))
        records.append(_completed(rng, i, producer.producer_id, producer.entity_type))
    for _ in range(N_DECLINED):
        records.append(_declined(rng, rng.choice(ids)))
    rng.shuffle(records)
    for n, record in enumerate(records, start=1):
        record["record_id"] = f"SEED-{n:04d}"
    return records
