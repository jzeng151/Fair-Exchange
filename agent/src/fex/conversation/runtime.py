"""AgentCore Runtime entrypoint for the FEX conversation (issue #13).

The chat API (#25) invokes the runtime with one request per call ({kind, producerId, conversationId, ...}).
Model IDs are configuration (ADR 0001): a small model for intake, playback and tagging; a large model
for the grounded answer. Defaults are US inference profiles so processing stays in US regions.
Deploy pattern: docs/adr/0002-agentcore-runtime-spike.md.

State: AgentCore Memory (docs/specs/memory.md) when FEX_MEMORY_ID is set, so a conversation survives a
recycled runtime and can be resumed; an in-process store otherwise, for local runs.
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
from fex.conversation.memory import AgentCoreMemoryStateStore, RetentionConfig
from fex.conversation.state import InMemoryStateStore, StateStore

DEFAULT_SMALL = "us.anthropic.claude-haiku-5-5"
DEFAULT_LARGE = "us.anthropic.claude-sonnet-5-5"


def model_ids() -> tuple[str, str]:
    return os.environ.get("FEX_SMALL_MODEL", DEFAULT_SMALL), os.environ.get("FEX_LARGE_MODEL", DEFAULT_LARGE)


def demo_models() -> bool:
    """FEX_DEMO_MODELS=1: the deterministic demo model instead of Bedrock (#101). No AWS, no cost."""
    return os.environ.get("FEX_DEMO_MODELS") == "1"


def state_store() -> StateStore:
    """AgentCore Memory (resume across a recycled runtime) when FEX_MEMORY_ID is set; otherwise an
    in-process store for local runs.

    When memory is configured, the retention rule is checked before the store is built: the agent
    refuses to start unless the short-term event expiry is longer than the maximum conversation
    lifetime (memory spec). Both are configuration values with no invented defaults.
    """
    memory_id = os.environ.get("FEX_MEMORY_ID")
    if not memory_id:
        return InMemoryStateStore()
    # Rejects at startup if event expiry is not longer than the maximum conversation lifetime, or is unset.
    if RetentionConfig.from_env() is None:
        raise RuntimeError(
            "FEX_MEMORY_ID is set but FEX_EVENT_EXPIRY_DAYS / FEX_MAX_LIFETIME_MINUTES are not; "
            "both are required so retention can be checked against the conversation lifetime")
    from bedrock_agentcore.memory import MemoryClient

    return AgentCoreMemoryStateStore(memory_id, MemoryClient(region_name=os.environ.get("AWS_REGION")))


def record_store():
    """Where records are saved: the DynamoDB table named by FEX_RECORDS_TABLE, local JSON files in
    FEX_LOCAL_RECORDS_DIR (local runs, #101), or None (not saved)."""
    name = os.environ.get("FEX_RECORDS_TABLE")
    if not name:
        local = os.environ.get("FEX_LOCAL_RECORDS_DIR")
        if local:
            from fex.records.local import FileRecordStore

            return FileRecordStore(local)
        return None
    import boto3

    from fex.records import DynamoRecordStore

    return DynamoRecordStore(boto3.resource("dynamodb").Table(name))


@lru_cache(maxsize=1)
def default_engine() -> ConversationEngine:
    from fex.guardrail import OutputAssessor, guarded_bedrock_model

    records = record_store()
    if demo_models():  # local runs (#101): no Bedrock, no Comprehend, no AWS at all
        from fex.conversation.demo_model import DemoModel

        from fex.tools.standards import LocalClauseRetriever

        demo = DemoModel()
        return ConversationEngine(store=InMemoryStateStore(), small_model=demo, large_model=demo, records=records,
                                  retriever=LocalClauseRetriever())
    small, large = model_ids()
    # The PII seam (#20, #24): scans run only when records are configured — they are part of saving one.
    # Comprehend handles en/es; the Guardrail handles fr, which Comprehend can't.
    pii_scanner = None
    if records is not None:
        from fex.pii import default_pii_scanner

        pii_scanner = default_pii_scanner()
    # State: AgentCore Memory when FEX_MEMORY_ID is set (resume across a recycled runtime), else in-process.
    # Both models carry the detect-mode Guardrail (#12), and their structured output is assessed too.
    from fex.translate import AmazonTranslator

    # Reviewer-facing English comes from Amazon Translate (#22); the model's English is the fallback.
    return ConversationEngine(store=state_store(), small_model=guarded_bedrock_model(small),
                              large_model=guarded_bedrock_model(large), records=records,
                              pii_scanner=pii_scanner, output_assessor=OutputAssessor(),
                              translator=AmazonTranslator())


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
        # Contract-shaped events, so the chat API passes them on like any other turn (#89)
        yield {"type": "error", "seq": 1, "code": "agent_failed",
               "message": f"Invalid request: {outcome['error']['message']}"}
        yield {"type": "done", "seq": 2}
    elif isinstance(outcome.get("result"), ResumeResponse):
        yield {"resume": outcome["result"].model_dump(mode="json")}


def respond(payload: dict[str, Any], engine: ConversationEngine | None = None):
    """What the AgentCore entrypoint returns (#89). The SDK sends a dict as `application/json` and streams a
    generator as Server-Sent Events (`data: <json>`), so:
      - `resume` returns the resume object itself (step, allowed, answer, history) as plain JSON;
      - every other request returns the event generator, streamed as SSE.
    """
    if payload.get("kind") == "resume":
        out = invoke(payload, engine=engine)
        return out["resume"] if "resume" in out else out
    return stream(payload, engine=engine)


def create_app():  # pragma: no cover - exercised when deployed
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def entry(payload: dict[str, Any], context: Any = None):
        # Not a generator itself: returns a dict (resume, sent as JSON) or a generator (events, streamed as SSE)
        return respond(payload)

    return app
