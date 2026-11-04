"""Serve the REAL FEX AgentCore entrypoint locally (#101), as AgentCore would run it.

    cd agent && FEX_DEMO_MODELS=1 FEX_LOCAL_RECORDS_DIR=/tmp/fex-records uv run python scripts/serve_local.py

POST http://localhost:8080/invocations with a conversation request (see fex/conversation/contract.py):
events stream back as Server-Sent Events, and `resume` returns plain JSON. Settings:
  FEX_DEMO_MODELS=1        deterministic demo model: no AWS, no cost (unset: real Claude via Bedrock)
  FEX_LOCAL_RECORDS_DIR    save records as JSON files there (unset: records aren't saved)
  FEX_AGENT_PORT           port (default 8080)
"""
import os

from fex.conversation.runtime import create_app

if __name__ == "__main__":
    create_app().run(port=int(os.environ.get("FEX_AGENT_PORT", "8080")))
