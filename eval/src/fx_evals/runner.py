"""The scenario runner (#35): drives one run's turns and checks each one, for offline runs and for the
AgentCore Evaluations dataset runner (#36).

Each turn's response stream is read through `done`. The runner checks that the expected step arrived and
that the next action is allowed, answers extra intake questions from `intake_replies`, and fails a run
whose expected step doesn't arrive within 60 seconds. A run stops at its first problem: later turns
would only repeat it.
"""
import queue
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from fx_evals.runs import LAST_REPLY, Run

STEP_TIMEOUT_S = 60.0
MAX_EXTRA_REPLIES = 6  # extra intake answers before the runner gives up waiting for a later step
_END = object()


class Transport(Protocol):
    def send(self, producer_id: str, conversation_id: str, body: dict) -> Iterable[dict]: ...


class InProcessTransport:
    """The agent entrypoint in this process, streamed the way the runtime streams it."""

    def __init__(self, engine: Any):
        self.engine = engine

    def send(self, producer_id: str, conversation_id: str, body: dict) -> Iterable[dict]:
        from fex.conversation.runtime import stream

        return stream({"producerId": producer_id, "conversationId": conversation_id, **body}, self.engine)


@dataclass
class RunState:
    """What the runner carries between one run's turns."""

    allowed: list[str] = field(default_factory=list)
    replies_used: int = 0
    events: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    run: Run
    conversation_id: str
    events: list[dict]
    problems: list[str]

    @property
    def answer_evidence(self) -> str | None:
        """`full` or `limited` from the last answer the producer saw, or None if no answer finished."""
        return next((e["evidence"] for e in reversed(self.events) if e.get("type") == "answer"), None)


def _steps(events: list[dict]) -> list[str]:
    return [e["step"] for e in events if e.get("type") == "step"]


class ScenarioRunner:
    def __init__(self, transport: Transport, clock: Callable[[], float] = time.monotonic,
                 step_timeout: float = STEP_TIMEOUT_S, max_extra_replies: int = MAX_EXTRA_REPLIES):
        self.transport = transport
        self.clock = clock
        self.step_timeout = step_timeout
        self.max_extra_replies = max_extra_replies

    def _exchange(self, run: Run, conversation_id: str, body: dict, st: RunState, deadline: float) -> list[dict]:
        """Send one request and read its stream through `done`, never past the deadline. The stream is read
        in a background thread, so a stalled model call or a stream that never ends can't block the run."""
        within = f"within {self.step_timeout:g} s"
        if self.clock() >= deadline:
            st.problems.append(f"{body['kind']}: the expected step did not arrive {within}")
            return []
        items: queue.Queue = queue.Queue()

        def pump() -> None:
            try:
                for event in self.transport.send(run.producer_id, conversation_id, body):
                    items.put(event)
                    if event.get("type") == "done":
                        break
            except Exception as exc:  # noqa: BLE001 - reported as a problem with the run
                items.put(exc)
            finally:
                items.put(_END)

        threading.Thread(target=pump, daemon=True).start()
        events: list[dict] = []
        failure = None
        while True:
            try:
                item = items.get(timeout=max(0.0, deadline - self.clock()))
            except queue.Empty:
                failure = f"{body['kind']}: no complete response {within}"
                break
            if item is _END:
                break
            if isinstance(item, Exception):
                failure = f"{body['kind']}: the request failed: {type(item).__name__}: {item}"
                break
            events.append(item)
            if item.get("type") == "done":
                break
        st.events += events
        if failure:
            st.problems.append(failure)
        else:
            st.problems += [f"error event {e.get('code')}: {e.get('message')}" for e in events if e.get("type") == "error"]
            if not events or events[-1].get("type") != "done":
                st.problems.append(f"{body['kind']}: the stream ended before done")
        if actions := [e for e in events if e.get("type") == "actions"]:
            st.allowed = actions[-1]["allowed"]
        return events

    def start(self, run: Run, conversation_id: str, st: RunState) -> None:
        self._exchange(run, conversation_id, {"kind": "start"}, st, self.clock() + self.step_timeout)

    def play_turn(self, run: Run, conversation_id: str, number: int, st: RunState) -> None:
        """Turn `number` (1-based) of the run, with any extra intake answers it needs, all within one deadline."""
        turn = run.turns[number - 1]
        expect = turn["expect_step"]
        if "action" in turn and turn["action"]["name"] not in st.allowed:
            st.problems.append(f"turn {number}: {turn['action']['name']} is not allowed now {st.allowed}")
            return
        body = ({"kind": "message", "text": turn["message"]} if "message" in turn
                else {"kind": "action", "action": turn["action"]})
        before = len(st.problems)
        deadline = self.clock() + self.step_timeout
        steps = _steps(self._exchange(run, conversation_id, body, st, deadline))
        extra = 0
        while len(st.problems) == before and expect != "intake" and steps[-1:] == ["intake"]:
            if extra == self.max_extra_replies:
                st.problems.append(f"still in intake after {extra} extra intake answers")
                break
            text = run.intake_replies[st.replies_used] if st.replies_used < len(run.intake_replies) else LAST_REPLY
            st.replies_used += 1
            extra += 1
            steps = _steps(self._exchange(run, conversation_id, {"kind": "message", "text": text}, st, deadline))
        if len(st.problems) == before and expect not in steps:
            st.problems.append(f"expected step {expect}, got {steps}")
        st.problems[before:] = [f"turn {number}: {p}" for p in st.problems[before:]]

    def run(self, run: Run, conversation_id: str) -> RunResult:
        st = RunState()
        self.start(run, conversation_id, st)
        for number in range(1, len(run.turns) + 1):
            if st.problems:
                break
            self.play_turn(run, conversation_id, number, st)
        return RunResult(run, conversation_id, st.events, st.problems)


# ------------------------------------------------------------------ AgentCore Evaluations

def agentcore_dataset(runs: list[Run]) -> list:
    """One predefined AgentCore scenario per run. Turn 0 starts the conversation; turn n plays run turn n."""
    from bedrock_agentcore.evaluation.runner.dataset_types import PredefinedScenario, Turn

    return [PredefinedScenario(scenario_id=run.run_id,
                               turns=[Turn(input={"run_id": run.run_id, "turn": n}) for n in range(len(run.turns) + 1)],
                               metadata={"producer_id": run.producer_id, "kind": run.kind})
            for run in runs]


class AgentCoreInvoker:
    """The agent invoker the AgentCore dataset runner calls once per dataset turn. Its session ID is the
    runtime session ID and so the conversation ID (#36)."""

    def __init__(self, runner: ScenarioRunner, runs: list[Run]):
        self.runner = runner
        self.runs = {run.run_id: run for run in runs}
        self.states: dict[str, RunState] = {}

    def __call__(self, invoker_input: Any) -> Any:
        from bedrock_agentcore.evaluation.runner.invoker_types import AgentInvokerOutput

        run = self.runs[invoker_input.payload["run_id"]]
        number = invoker_input.payload["turn"]
        conversation_id = invoker_input.session_id
        st = self.states.setdefault(conversation_id, RunState())
        seen = len(st.events)
        if st.problems:
            pass  # an earlier turn failed: don't send more requests for this run
        elif number == 0:
            self.runner.start(run, conversation_id, st)
        else:
            self.runner.play_turn(run, conversation_id, number, st)
        new = st.events[seen:]
        return AgentInvokerOutput(agent_output={"steps": _steps(new), "problems": list(st.problems),
                                                "text": "".join(e.get("text", "") for e in new if e.get("type") == "text")})
