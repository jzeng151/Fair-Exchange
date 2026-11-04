"""AgentCore Runtime entry point for FEX (#5). Packaged at the root of the agent code zip by infra/deploy.sh.

The runtime starts it as `opentelemetry-instrument main.py` (ADR 0002: plain `main.py` emits no traces).
Everything else is in the agent package: fex.conversation.runtime.create_app wires the engine from the
environment the stack sets (models, Guardrail, Knowledge Base, memory, records table).
"""
from fex.conversation.runtime import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
