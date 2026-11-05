"""Scenario invoker: drives one conversation through the chat API (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36),
reusing the [#35](https://github.com/jzeng151/Fair-Exchange/issues/35) runner shape with the
[#25](https://github.com/jzeng151/Fair-Exchange/issues/25) chat contract).

The invoker is the callable the AgentCore on-demand dataset runner drives per scenario:
`agent_invoker(AgentInvokerInput(payload=Scenario.model_dump(), session_id=...)) ->
AgentInvokerOutput(agent_output=payload)`. The payload is the scenario dict; the invoked
session ID rides back for the runner to look up the record + evidence.

Wire contract (api/src/core/routes.ts + api/src/core/validate.ts): `POST /conversations`
takes an EMPTY body and identifies the producer by the `x-demo-producer-id` header; the
message/action endpoints answer with the body `{text}` / `{"action", "args"}`. Every turn
returns an NDJSON stream: `{type: "conversation", conversationId}` on start, flat
`{type: "step", step: "closed", language: "en"}` progress events, `{type: "done"}` on success,
or `{type: "error", code, message}` on failure.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any, Protocol


class ChatTransport(Protocol):
    """The deployed chat API ([#25](https://github.com/jzeng151/Fair-Exchange/issues/25) endpoints)."""

    def create(self, producer_id: str, language: str) -> dict[str, Any]:
        """POST /conversations (empty body, `x-demo-producer-id` header) -> NDJSON stream.

        The stream opens with `{type: "conversation", conversationId}` before the first
        turn's step events.
        """
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

    def _post(self, path: str, payload: str | None = None,
              producer_id: str | None = None) -> Iterator[dict[str, Any]]:
        """Yield the NDJSON events of a turn; the response stays open while iterating.

        A generator only runs its `with` block as the caller iterates, so the response is
        not closed before the events are read ([#36] review: the streamed body must be
        consumed inside the context manager).
        """
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=payload.encode() if payload else b"",
            headers=(dict([("Content-Type", "application/json")]) if payload else {})
            | ({"x-demo-producer-id": producer_id} if producer_id else {}),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            for line in response:
                line = line.decode("utf-8").strip()
                if line:
                    yield json.loads(line)

    def create(self, producer_id: str, language: str) -> dict[str, Any]:
        """Consume the start stream (empty body, identity header) -> the conversation ID."""
        events = list(self._post("/conversations", producer_id=producer_id))
        try:
            conversation = next(e for e in events if e.get("type") == "conversation")
        except StopIteration as exc:
            raise AssertionError(
                "POST /conversations returned no {type: conversation} event") from exc
        _check_steps(events, str(conversation.get("conversationId", "[start]")))
        return {"conversation_id": str(conversation["conversationId"])}

    def message(self, conversation_id: str, text: str) -> Iterator[dict[str, Any]]:
        yield from self._post(f"/conversations/{conversation_id}/messages",
                              json.dumps({"text": text}))

    def actions(self, conversation_id: str, action: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield from self._post(f"/conversations/{conversation_id}/actions", json.dumps(action))


class StubChatTransport:
    """Replays canned transcript turns; the offline tests drive this."""

    def __init__(self, conversation_id: str, events: list[dict[str, Any]]):
        self._conversation_id = conversation_id
        self._events = events
        self.calls: list[tuple[str, Any]] = []

    def create(self, producer_id: str, language: str) -> dict[str, Any]:
        self.calls.append(("create", (producer_id, language)))
        return {"conversation_id": self._conversation_id}

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
    | {"kind": "action", "action": {"name", "args"}}]}`. Turns never carry producer fields;
    the producer identity rides the `x-demo-producer-id` header of `POST /conversations` and
    the conversation language comes from the producer profile.
    """
    conversation_id = chat.create(str(scenario["producer_id"]),
                                  _producer_language(scenario))["conversation_id"]
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


def _check_steps(events: Iterable[dict[str, Any]], conversation_id: str) -> None:
    """Flat wire events: any `{type: "error", code, message}` is a hard failure."""
    for event in events:
        if event.get("type") == "error":
            raise AssertionError(
                f"conversation {conversation_id} reported an error: "
                f"{event.get('code', '')}: {event.get('message', '')}")
