"""AgentCore Runtime entrypoint for the FEX conversation (issue #13).

The chat API (#25) invokes the runtime with one request per call ({kind, producerId, conversationId, ...}).
Model IDs are configuration (ADR 0001): a small model for intake, playback and tagging; a large model
for the grounded answer. Defaults are US inference profiles so processing stays in US regions.
Deploy pattern: docs/adr/0002-agentcore-runtime-spike.md.

State: in-memory per runtime session until AgentCore Memory (docs/specs/memory.md) replaces the store.
Records (#26): saved to the DynamoDB table named by FEX_RECORDS_TABLE; not saved when it is unset.
Guardrail (#12): attached to both models from FEX_GUARDRAIL_ID and FEX_GUARDRAIL_VERSION, in detect mode.
"""
import os
import queue
import threading
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from fex.conversation.contract import ResumeResponse
from fex.conversation.engine import ConversationEngine
from fex.conversation.state import InMemoryStateStore

DEFAULT_SMALL = "us.anthropic.claude-haiku-5-5"
DEFAULT_LARGE = "us.anthropic.claude-sonnet-5-5"


def model_ids() -> tuple[str, str]:
    return os.environ.get("FEX_SMALL_MODEL", DEFAULT_SMALL), os.environ.get("FEX_LARGE_MODEL", DEFAULT_LARGE)


def record_store():
    """The records table from configuration, or None when FEX_RECORDS_TABLE is unset (local runs)."""
    name = os.environ.get("FEX_RECORDS_TABLE")
    if not name:
        return None
    import boto3

    from fex.records import DynamoRecordStore

    return DynamoRecordStore(boto3.resource("dynamodb").Table(name))


@lru_cache(maxsize=1)
def default_engine() -> ConversationEngine:
    from fex.guardrail import OutputAssessor, guarded_bedrock_model

    small, large = model_ids()
    records = record_store()
    # The Comprehend seam (#20): scans run only when records are configured — they are part of saving one.
    pii_scanner = None
    if records is not None:
        from fex.pii import default_comprehend

        pii_scanner = default_comprehend()
    # Both models carry the detect-mode Guardrail (#12), and their structured output is assessed too.
    return ConversationEngine(store=InMemoryStateStore(), small_model=guarded_bedrock_model(small),
                              large_model=guarded_bedrock_model(large), records=records,
                              pii_scanner=pii_scanner, output_assessor=OutputAssessor())


def invoke(payload: dict[str, Any], engine: ConversationEngine | None = None) -> dict[str, Any]:
    """Run one request. Returns {"events": [...]}, {"resume": {...}} or {"error": {...}} as plain JSON."""
    try:
        result = (engine or default_engine()).handle(payload)
    except ValidationError as exc:
        return {"error": {"code": "invalid_request", "message": exc.errors(include_url=False)[0]["msg"]}}
    if isinstance(result, ResumeResponse):
        return {"resume": result.model_dump(mode="json")}
    return {"events": [e.model_dump(mode="json") for e in result]}


_DONE = object()


def stream(payload: dict[str, Any], engine: ConversationEngine | None = None) -> Iterator[dict[str, Any]]:
    """Run one request and yield each event as plain JSON the moment the engine produces it.

    The engine runs in a worker thread and hands events over a queue, so opening text and checked claims
    reach the chat API while later model calls (retrieval, rewrites) are still running. A resume or a
    malformed request yields a single item, as `invoke` returns it.
    """
    engine = engine or default_engine()
    events: queue.Queue = queue.Queue()
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = engine.handle(payload, on_event=lambda e: events.put(e.model_dump(mode="json")))
        except ValidationError as exc:
            outcome["error"] = {"code": "invalid_request", "message": exc.errors(include_url=False)[0]["msg"]}
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, never swallowed silently
            outcome["exception"] = exc
        finally:
            events.put(_DONE)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while (item := events.get()) is not _DONE:
        yield item
    worker.join()
    if "exception" in outcome:
        raise outcome["exception"]
    if "error" in outcome:
        yield {"error": outcome["error"]}
    elif isinstance(outcome.get("result"), ResumeResponse):
        yield {"resume": outcome["result"].model_dump(mode="json")}


def create_app():  # pragma: no cover - exercised when deployed
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def entry(payload: dict[str, Any], context: Any = None):
        # A generator: AgentCore streams each yielded event to the caller as it is produced
        yield from stream(payload)

    return app
