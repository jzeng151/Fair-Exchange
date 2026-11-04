"""Regional fact table (#8): CHIRPS, Aqueduct and World Bank prices, pre-extracted, as a validated CSV."""
import csv
import json

import pytest
from fx_data.regional import (COLUMNS, COUNTRY_CODES, FACTS_PATH, REGIONS, SOURCES_PATH, RegionalFacts,
                              _band, build, country_code, normalize_crops, source_label, validate_rows)

PRIORITY_COUNTRIES = {"PE", "CI", "CO", "HN", "MX"}
PRIORITY_CROPS = ("coffee", "banana", "cocoa")


@pytest.fixture(scope="module")
def rows():
    with open(FACTS_PATH, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _good(**overrides) -> dict:
    row = {"fact_id": "RF-TEST01", "scope": "region", "country": "CO", "admin1": "Cauca", "crop": "",
           "tags": "water", "indicator": "water_stress_score", "value": "1.0", "unit": "score 0-5",
           "comparison": "test", "period": "1979-2019", "source_name": "WRI Aqueduct 4.0",
           "source_url": "https://example.org", "extracted_at": "2026-11-04", "curated": "false"}
    return row | overrides


# ---- the committed table ----------------------------------------------------------------------

def test_committed_csv_matches_the_committed_sources(rows):
    built = build(json.loads(SOURCES_PATH.read_text(encoding="utf-8")))
    as_text = [{k: str(v) for k, v in r.items()} for r in built]
    assert rows == as_text


def test_columns_are_exactly_the_spec_columns():
    with open(FACTS_PATH, encoding="utf-8", newline="") as fh:
        assert tuple(next(csv.reader(fh))) == COLUMNS


def test_committed_rows_load_and_validate(rows):
    RegionalFacts(rows)  # raises on any invalid row


def test_every_region_in_the_list_has_rows(rows):
    have = {(r["country"], r["admin1"]) for r in rows if r["scope"] == "region"}
    assert have == {(COUNTRY_CODES[c], region) for c, region in REGIONS}


def test_every_priority_country_has_region_or_country_rows(rows):
    assert PRIORITY_COUNTRIES <= {r["country"] for r in rows if r["scope"] in ("region", "country")}


def test_every_priority_crop_has_a_price_row(rows):
    for crop in PRIORITY_CROPS:
        assert any(r["crop"] == crop and r["indicator"].startswith("price") for r in rows), crop


def test_source_labels_are_unique_and_end_in_the_fact_id(rows):
    labels = [source_label(r) for r in rows]
    assert len(labels) == len(set(labels))
    assert all(label.endswith(f"[{r['fact_id']}]") for label, r in zip(labels, rows))


def test_prices_are_global_rows_labelled_as_world_benchmarks(rows):
    prices = [r for r in rows if r["indicator"].startswith("price")]
    assert prices and all(r["scope"] == "global" and not r["country"] for r in prices)
    assert all("world benchmark" in r["comparison"] for r in prices)


# ---- the loader rejects bad rows --------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"tags": "drought"},                                    # unknown tag
    {"tags": ""},                                           # no tag
    {"source_name": ""},                                    # missing source
    {"source_url": " "},
    {"country": "XX"},                                      # bad country code
    {"country": "Colombia"},                                # a name, not ISO alpha-2
    {"crop": "bananas"},                                    # not the crop vocabulary
    {"scope": "district"},                                  # unknown scope
    {"scope": "country"},                                   # country row with an admin1
    {"admin1": ""},                                         # region row without an admin1
    {"scope": "global"},                                    # global row with a country
    {"curated": "yes"},
])
def test_invalid_rows_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_rows([_good(**bad)])


def test_duplicate_fact_ids_are_rejected():
    with pytest.raises(ValueError):
        validate_rows([_good(), _good()])


def test_a_valid_row_loads():
    validate_rows([_good(), _good(fact_id="RF-TEST02", scope="global", country="", admin1="", crop="coffee",
                                  tags="market and price")])


def test_curated_rows_say_so_in_their_source_label():
    assert source_label(_good(curated="true")).endswith(" (curated stand-in) [RF-TEST01]")


# ---- helpers ----------------------------------------------------------------------------------

def test_country_names_match_despite_accents_and_apostrophes():
    assert country_code("Cote d'Ivoire") == country_code("CÔTE D’IVOIRE") == "CI"
    assert country_code("Vietnam") is None


def test_crops_are_normalized_to_the_vocabulary():
    assert normalize_crops("Cocoa;Coffee") == {"cocoa", "coffee"}
    assert normalize_crops("Bananas") == {"banana"}
    assert normalize_crops("Apparel") == set()


def test_band_tidies_aqueduct_labels():
    assert _band("Low - Medium (10-20%)") == "low to medium (10-20%)"
    assert _band("Medium-high (20-40%)") == "medium to high (20-40%)"
    assert _band(None) is None


def test_incomplete_rainfall_years_produce_no_rainfall_row():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    record = {"country": "Colombia", "region": "Cauca", "lat": 0, "lon": 0,
              "chirps": {"2024": {"total_mm": 900.0, "days": 200}}, "aqueduct": None}
    built = build({"fetched_at": "x", "regions": [record], "prices": sources["prices"]})
    assert not [r for r in built if r["indicator"] == "rainfall_anomaly_pct"]
