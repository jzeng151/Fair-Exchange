"""Regional fact table (#8): CHIRPS, Aqueduct and World Bank prices, pre-extracted."""
import json

import pytest
from fx_data.regional import (FACTS_PATH, REGIONS, SOURCES_PATH, RegionalFacts, _band, build,
                              normalize)

PRIORITY_COUNTRIES = {"peru", "cote d'ivoire", "colombia", "honduras", "mexico"}
PRIORITY_CROPS = ("coffee", "cocoa", "bananas")
NAMED_SOURCES = ("CHIRPS", "WRI Aqueduct", "World Bank Commodity Price Data")


@pytest.fixture(scope="module")
def table():
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def test_committed_facts_match_the_committed_sources(table):
    assert table == build(json.loads(SOURCES_PATH.read_text(encoding="utf-8")))


def test_every_region_in_the_list_was_fetched(table):
    assert {(r["country"], r["region"]) for r in table["regions"]} == set(REGIONS)


def test_covers_the_priority_countries_and_crops(table):
    countries = {normalize(r["country"]) for r in table["regions"] if r["facts"]}
    assert PRIORITY_COUNTRIES <= countries
    for crop in PRIORITY_CROPS:
        assert table["prices"][crop], crop


def test_every_region_has_rainfall_and_water_facts(table):
    for r in table["regions"]:
        metrics = {f["metric"] for f in r["facts"]}
        assert {"rainfall_change_pct", "baseline_water_stress", "projected_water_stress_2050"} <= metrics, \
            (r["country"], r["region"])


def test_every_fact_cites_a_named_dataset_and_period(table):
    facts = [f for r in table["regions"] for f in r["facts"]] + \
            [f for crop in table["prices"].values() for f in crop]
    for f in facts:
        assert f["source"].startswith(NAMED_SOURCES), f["source"]
        assert f["text"] and f["period"]
        assert f["strength"] in {"nearest", "limited"}


def test_prices_are_labelled_as_world_benchmarks(table):
    for crop in PRIORITY_CROPS:
        assert all(f["strength"] == "limited" for f in table["prices"][crop])
    assert "not a farm-gate price" in table["prices"]["coffee"][0]["text"]


def test_lookup_matches_names_despite_accents_case_and_apostrophes(table):
    facts = RegionalFacts(table)
    assert facts.lookup("Cote d'Ivoire", "Bas-Sassandra", "Cocoa").matched
    assert facts.lookup("CÔTE D’IVOIRE", "bas-sassandra", "Cocoa").match_level == "region"


def test_lookup_adds_prices_for_multi_crop_producers(table):
    facts = RegionalFacts(table)
    sources = {f["source"] for f in facts.lookup("Colombia", "Tolima", "Cocoa;Coffee").facts}
    assert any("Cocoa" in s for s in sources) and any("Arabica" in s for s in sources)


def test_lookup_never_substitutes_another_region(table):
    facts = RegionalFacts(table)
    unknown = facts.lookup("Colombia", "Narino", "Coffee")
    assert unknown.match_level == "country"
    assert all(f["metric"].startswith("benchmark_price") for f in unknown.facts)
    nothing = facts.lookup("Vietnam", "Khanh Hoa", "Seafood")
    assert not nothing.matched and nothing.facts == []


def test_band_tidies_aqueduct_labels():
    assert _band("Low - Medium (10-20%)") == "low to medium (10-20%)"
    assert _band("Low-medium (10-20%)") == "low to medium (10-20%)"
    assert _band("Medium-high (20-40%)") == "medium to high (20-40%)"
    assert _band(None) is None


def test_incomplete_rainfall_years_produce_no_rainfall_fact():
    record = {"country": "X", "region": "Y", "lat": 0, "lon": 0,
              "chirps": {"2024": {"total_mm": 900.0, "days": 200}}, "aqueduct": None}
    built = build({"fetched_at": "x", "regions": [record],
                   "prices": {"updated": "x", "series": json.loads(SOURCES_PATH.read_text())["prices"]["series"]}})
    assert built["regions"][0]["facts"] == []
