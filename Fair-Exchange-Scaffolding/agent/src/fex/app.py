"""AgentCore Runtime entrypoint for FEX.

The API Lambda calls this with {"prompt": ..., "producerId": ...}. `producerId` comes from the
producer's login, set by OUR API, never from what the producer types. It is passed to tools
through invocation_state so the model can never change it.
"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from fex.agent import build_agent

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context):
    producer_id = payload.get("producerId")
    if not producer_id:
        yield {"error": "producerId is required (set by the API from the producer's login)"}
        return
    agent = build_agent()  # TODO(#13): reuse per session; pick small vs. large model per stage
    async for event in agent.stream_async(payload.get("prompt", ""), invocation_state={"producer_id": producer_id}):
        yield event


if __name__ == "__main__":
    app.run()
