"""The eval dataset (#36): scenario runs, contrast runs, the labeled accounts and the adversarial scope set,
each as one run in the #35 scenario format."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "eval"
SCENARIOS = EVAL / "scenarios"
LABELED = EVAL / "labeled" / "challenge-tags.jsonl"
DEFINITIONS = ROOT / "data" / "generator_inputs" / "producer_definitions.json"
LAST_REPLY = "That's all I can add."  # sent when the intake replies run out (#35)

# The run that stands for each producer of #7's contrast pairs (eval/scenarios/README.md). S5 and S7 share a
# producer; S7 is the contrast run. A test checks these against #7's `contrast_pairs`.
PAIR_RUNS = {"C1": ("S1", "S7"), "C2": ("S2", "C2-SYN-007"), "C3": ("S3", "S6"), "C4": ("S1", "C4-SYN-008")}
# Same region and crop, so their regional facts overlap by design: judged on the reviewer mark alone (#36)
MARK_ONLY_PAIRS = frozenset({"C4"})

Kind = Literal["scenario", "contrast", "labeled", "scope"]


@dataclass(frozen=True)
class Run:
    run_id: str
    kind: Kind
    producer_id: str
    language: str
    turns: list[dict]
    intake_replies: list[str] = field(default_factory=list)
    expected: dict = field(default_factory=dict)  # a scenario's expected outcome; empty for labeled accounts
    reference_tags: list[str] = field(default_factory=list)  # labeled accounts: the settled human tags
    labeler_tags: tuple[list[str], list[str]] | None = None  # labeled accounts: labeler A's and B's tags
    private_markers: list[str] = field(default_factory=list)  # adversarial set: the other producer's data (#34)

    def scripted_text(self) -> str:
        """Everything the producer types in this run. An identifier here came from the producer, not a tool."""
        return " ".join([t.get("message", "") + json.dumps(t.get("action", {})) for t in self.turns]
                        + self.intake_replies)


def _from_file(path: Path, kind: Kind) -> Run:
    s = json.loads(path.read_text(encoding="utf-8"))
    return Run(run_id=s["scenario_id"], kind=kind, producer_id=s["producer_id"], language=s["language"],
               turns=s["turns"], intake_replies=s.get("intake_replies", []), expected=s.get("expected", {}),
               private_markers=s.get("private_markers", []))


def scenario_runs() -> list[Run]:
    return ([_from_file(p, "scenario") for p in sorted(SCENARIOS.glob("S*.json"))]
            + [_from_file(p, "contrast") for p in sorted((SCENARIOS / "contrast").glob("*.json"))])


def scope_runs() -> list[Run]:
    """The adversarial scope set (#34), once it exists in eval/scenarios/scope/."""
    return [_from_file(p, "scope") for p in sorted((SCENARIOS / "scope").glob("*.json"))]


def labeled_runs() -> list[Run]:
    """Each account runs as #35 says: the account as the intake message, then confirm, consent, end."""
    runs = []
    for line in LABELED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        runs.append(Run(
            run_id=item["id"], kind="labeled", producer_id=item["producer_id"], language=item["language"],
            turns=[{"message": item["text"], "expect_step": "playback"},
                   {"action": {"name": "confirm_playback", "args": {}}, "expect_step": "consent"},
                   {"action": {"name": "set_consent", "args": {"scope": "internal"}}, "expect_step": "feedback"},
                   {"action": {"name": "end", "args": {}}, "expect_step": "closed"}],
            reference_tags=item["reference"], labeler_tags=(item["labeler_a"], item["labeler_b"])))
    return runs


def all_runs() -> list[Run]:
    return scenario_runs() + labeled_runs() + scope_runs()


def contrast_pairs() -> list[dict]:
    return json.loads(DEFINITIONS.read_text(encoding="utf-8"))["contrast_pairs"]
