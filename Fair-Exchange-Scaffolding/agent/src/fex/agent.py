"""Build the FEX Strands agent."""
from strands import Agent
from strands.models import BedrockModel

from fex import config
from fex.prompts import SYSTEM_PROMPT
from fex.tools import ALL_TOOLS


def build_agent(model_id: str = config.MODEL_LARGE) -> Agent:
    model = BedrockModel(model_id=model_id, region_name=config.REGION)
    # TODO(#12): attach the Bedrock Guardrail (detect mode) via guardrail_id / guardrail_version
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=ALL_TOOLS)
