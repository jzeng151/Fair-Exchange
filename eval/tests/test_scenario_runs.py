"""Seam 1 (#35): every scenario run drives the agent entrypoint end to end with a scripted fake model.

The deterministic demo model (#101) stands in for Bedrock, the data tools and the citation verifier are
the real ones, and a fake PII scanner stands in for Comprehend. The runs go through the eval harness's
scenario runner (the one runner #34, #36 and #40 share), which reads each turn to `done`, checks the
expected step and allowed actions, and answers extra intake questions. Expected outcomes are checked except
tags, which need the real model, and out-of-scope handling, whose detector is not decided (#21).
"""
import re

import pytest
from fx_evals.offline import run_all
from fx_evals.report import outcome_checks
from fx_evals.runs import scenario_runs

RUNS = scenario_runs()

# The invented person in S5. Detecting names is Comprehend's job; this checks what the agent does with a hit.
KNOWN_NAMES = ["Kouame Konan"]
PHONE = re.compile(r"\+\d[\d ]{8,}\d")


def fake_pii_scanner(text: str, language: str) -> list[dict]:
    """Comprehend's response shape for the invented name and any international phone number."""
    spans = [(m, "NAME") for name in KNOWN_NAMES for m in re.finditer(re.escape(name), text)]
    spans += [(m, "PHONE") for m in PHONE.finditer(text)]
    return [{"Type": kind, "Score": 0.99, "BeginOffset": m.start(), "EndOffset": m.end()}
            for m, kind in sorted(spans, key=lambda s: s[0].start())]


@pytest.mark.parametrize("run", RUNS, ids=[r.run_id for r in RUNS])
def test_scenario_runs_end_to_end_with_its_expected_outcome(run, tmp_path):
    [session] = run_all([run], tmp_path, demo=True, pii_scanner=fake_pii_scanner)
    assert session.problems == []
    misses = [o for o in outcome_checks(session) if not o["pass"] and o["field"] != "tags"]
    assert misses == []
    assert session.evidence is not None and session.evidence.final_step == "closed"


def test_the_fake_scanner_finds_only_the_invented_person_and_phone():
    text = "The technician Kouame Konan came, call him at +225 07 00 00 00 00. Fair Trade helps."
    found = fake_pii_scanner(text, "en")
    assert [(e["Type"], text[e["BeginOffset"]:e["EndOffset"]]) for e in found] == [
        ("NAME", "Kouame Konan"), ("PHONE", "+225 07 00 00 00 00")]
