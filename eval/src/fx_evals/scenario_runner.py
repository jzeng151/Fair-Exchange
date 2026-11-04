"""Scenario invoker: drives one conversation through the chat API (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36),
reusing the [#35](https://github.com/jzeng151/Fair-Exchange/issues/35) runner shape with the
[#25](https://github.com/jzeng151/Fair-Exchange/issues/25) chat contract).

The invoker is the callable the AgentCore on-demand dataset runner drives per scenario:
`agent_invoker(AgentInvokerInput(payload=Scenario.model_dump(), session_id=...)) ->
AgentInvokerOutput(agent_output=payload)`. The payload is the scenario dict; the invoked
session ID rides back for the runner to look up the record + evidence.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any, Protocol


class ChatTransport(Protocol):
    """The deployed chat API ([#25](https://github.com/jzeng151/Fair-Exchange/issues/25) endpoints)."""

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /conversations -> {conversation_id, ...}."""
        ...  # pragma: no cover - protocol

    def message(self, conversation_id: str, text: str) -> Iterator[dict[str, Any]]:
        """POST /conversations/{id}/messages with {text} -> NDJSON event stream to done."""
        ...  # pragma: no cover - protocol

    def actions(self, conversation_id: str, action: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """POST /conversations/{id}/actions with {"action", "args"} -> event stream."""
        ...  # pragma: no cover - protocol


class HttpChatTransport:
    """The deployed agent API. The base URL comes from the stack output (env `EVAL_API_BASE`)."""

    def __init__(self, base_url: str, timeout_s: int = 90):
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _post(self, path: str, payload: dict[str, Any] | None = None, stream: bool = False
              ) -> Any:
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=json.dumps(payload or {}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            if not stream:
                return json.loads(response.read())
            return response

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/conversations", payload)

    def message(self, conversation_id: str, text: str) -> Iterator[dict[str, Any]]:
        response = self._post(f"/conversations/{conversation_id}/messages",
                              {"text": text}, stream=True)
        for line in response:
            if line.strip():
                yield json.loads(line)

    def actions(self, conversation_id: str, action: dict[str, Any]) -> Iterator[dict[str, Any]]:
        response = self._post(f"/conversations/{conversation_id}/actions",
                              action, stream=True)
        for line in response:
            if line.strip():
                yield json.loads(line)


class StubChatTransport:
    """Replays canned transcript turns; the offline tests drive this."""

    def __init__(self, conversation_id: str, events: list[dict[str, Any]]):
        self._conversation_id = conversation_id
        self._events = events
        self.calls: list[tuple[str, Any]] = []

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create", payload))
        return {"conversation_id": self._conversation_id, "producer_id": payload.get("producer_id")}

    def message(self, conversation_id: str, text: str) -> Iterator[dict[str, Any]]:
        self.calls.append(("message", (conversation_id, text)))
        yield from self._events

    def actions(self, conversation_id: str, action: dict[str, Any]) -> Iterator[dict[str, Any]]:
        self.calls.append(("actions", (conversation_id, {"action": action.get("action"),
                                                         "args": action.get("args") or {}})))
        yield from self._events


def _producer_language(scenario: dict[str, Any]) -> str:
    return str(scenario.get("language") or "en")


def drive(
    scenario: dict[str, Any],
    chat: ChatTransport,
) -> str:
    """Drive one scenario's turns through the chat contract; returns the conversation ID.

    Scenario shape ([#35](https://github.com/jzeng151/Fair-Exchange/issues/35) fixtures):
    `{id, producer_id, language, turns: [{"kind": "start"} | {"kind": "message", "text": ...}
    | {"kind": "action", "action": {"name", "args"}}]}`. Turns never carry producer_id;
    the runner sends `producer_id` as the logged-in producer.
    """
    conversation_id = (chat.create({
        "producer_id": scenario["producer_id"],
        "language": _producer_language(scenario),
    }))["conversation_id"]
    for turn in scenario.get("turns", ()):
        kind = turn.get("kind")
        if kind == "start":
            continue
        if kind == "message":
            events = list(chat.message(conversation_id, str(turn["text"])))
            _check_steps(events, conversation_id)
        elif kind == "action":
            action = turn.get("action") or {}
            payload = {"action": str(action.get("name")),
                       "args": dict(action.get("args") or {})}
            events = list(chat.actions(conversation_id, payload))
            _check_steps(events, conversation_id)
        else:
            raise ValueError(f"scenario {conversation_id}: unknown turn kind {kind!r}")
    return conversation_id


def _step_names(events: Iterable[dict[str, Any]]) -> set[str]:
    return {step_kind(event) for event in events}


def step_kind(event: dict[str, Any]) -> str:
    step = event.get("step") or {}
    return str(step.get("kind", ""))


def _check_steps(events: Iterable[dict[str, Any]], conversation_id: str) -> None:
    kinds = _step_names(events)
    if "failed" in kinds:
        raise AssertionError(f"conversation {conversation_id} reported a failed step")