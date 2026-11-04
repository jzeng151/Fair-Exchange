"""Regional-context tool (#15), called through Strands so the session context is injected for real."""
import pytest
from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts

from fex.tools import regional_context
from fex.tools.regional_context import get_regional_context
from tests.tool_harness import call_tool


def _row(fact_id, scope, country="", admin1="", crop="", tags="water", indicator="water_stress_score",
         value="2.5", unit="score 0-5", period="1979-2019", source="WRI Aqueduct 4.0") -> dict:
    return {"fact_id": fact_id, "scope": scope, "country": country, "admin1": admin1, "crop": crop, "tags": tags,
            "indicator": indicator, "value": value, "unit": unit, "comparison": "fixture", "period": period,
            "source_name": source, "source_url": "https://example.org", "extracted_at": "2026-11-04",
            "curated": "false"}


FIXTURE_ROWS = [
    _row("RF-REG001", "region", "CO", "Cauca"),
    _row("RF-REG002", "region", "CO", "Huila"),
    _row("RF-CTY001", "country", "CO"),
    _row("RF-CTY002", "country", "PE"),
    _row("RF-REG003", "region", "CO", "Cauca", tags="climate and weather;water",
         indicator="rainfall_anomaly_pct", value="-12.0", unit="%", period="2024-2025", source="CHIRPS v2.0"),
    _row("RF-GLB001", "global", crop="coffee", tags="market and price", indicator="price_usd_per_kg",
         value="5.1", unit="USD/kg", period="2025-09", source="World Bank Pink Sheet"),
    _row("RF-GLB002", "global", crop="cocoa", tags="market and price", indicator="price_usd_per_kg",
         value="8.0", unit="USD/kg", period="2025-09", source="World Bank Pink Sheet"),
]
FIXTURE_PROFILES = {
    "P-CAUCA": {"country": "Colombia", "region": "Cauca", "crop": "Coffee", "entity_type": "Cooperative"},
    "P-PERU": {"country": "Peru", "region": "Junin", "crop": "Coffee", "entity_type": "Cooperative"},
    "P-KENYA": {"country": "Kenya", "region": "Nyeri", "crop": "Tea", "entity_type": "Estate"},
}
ALL_TAGS = ["water", "climate and weather", "market and price"]


@pytest.fixture(autouse=True)
def fixture_tables(monkeypatch):
    tables = (RegionalFacts(FIXTURE_ROWS), ProducerProfiles({"profiles": FIXTURE_PROFILES}))
    monkeypatch.setattr(regional_context, "_tables", lambda: tables)


def _ids(items):
    return [i["data"]["fact_id"] for i in items]


def _call(pid, tags=ALL_TAGS, tool_input=None):
    status, items = call_tool(get_regional_context, tool_input or {}, {"producer_id": pid, "tags": tags})
    assert status == "success"
    return items


def test_model_cannot_set_any_parameter():
    assert get_regional_context.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_region_rows_are_exact_then_country_nearest_then_global_limited():
    items = _call("P-CAUCA")
    assert _ids(items) == ["RF-REG001", "RF-REG003", "RF-CTY001", "RF-GLB001"]
    assert [i["strength"] for i in items] == ["exact", "exact", "nearest", "limited"]
    assert all(i["kind"] == "regional" and i["text"] and i["source"].endswith(f"[{i['data']['fact_id']}]")
               for i in items)


def test_rows_for_another_crop_or_region_are_left_out():
    ids = _ids(_call("P-CAUCA"))
    assert "RF-GLB002" not in ids  # cocoa price, producer grows coffee
    assert "RF-REG002" not in ids and "RF-CTY002" not in ids  # Huila, Peru


def test_only_rows_for_the_confirmed_tags_are_returned():
    assert _ids(_call("P-CAUCA", tags=["market and price"])) == ["RF-GLB001"]
    assert _ids(_call("P-CAUCA", tags=["climate and weather"])) == ["RF-REG003"]
    assert _call("P-CAUCA", tags=[]) == []


def test_an_uncovered_country_returns_an_empty_list():
    assert _call("P-KENYA") == []


def test_unknown_producer_returns_an_empty_list():
    assert _call("NOT-A-PRODUCER") == []


def test_a_location_supplied_by_the_model_is_ignored():
    honest = _call("P-CAUCA")
    assert _call("P-CAUCA", tool_input={"country": "Peru", "admin1": "Junin", "tags": ["education"]}) == honest


def test_no_producer_in_session_is_refused():
    status, text = call_tool(get_regional_context, {}, {"tags": ALL_TAGS})
    assert status == "error" and "No producer in session" in text


def test_the_real_table_serves_a_real_sample_producer(monkeypatch):
    monkeypatch.undo()
    profiles = ProducerProfiles.load()
    pid = next(p for p in profiles.ids() if (profiles.get(p).country, profiles.get(p).region) == ("Colombia", "Cauca")
               and "coffee" in (profiles.get(p).crop or "").lower())
    items = _call(pid)
    assert {i["strength"] for i in items} == {"exact", "nearest", "limited"}
    assert any(i["source"].startswith("CHIRPS") for i in items)
    assert any(i["source"].startswith("World Bank") for i in items)
