"""Configuration. Override with environment variables in each environment."""
import os

REGION = os.getenv("AWS_REGION", "us-west-2")

# Use `us.` inference profiles so processing stays in US regions (data sovereignty).
# Start with the smallest model that does each job well; upgrade only where eval/ shows it falls short.
MODEL_SMALL = os.getenv("FEX_MODEL_SMALL", "us.anthropic.claude-haiku-5-5")   # questions, playback, tagging
MODEL_LARGE = os.getenv("FEX_MODEL_LARGE", "us.anthropic.claude-sonnet-5-5")  # the grounded answer

GUARDRAIL_ID = os.getenv("FEX_GUARDRAIL_ID", "")          # TODO(#12): Guardrail in detect mode
GUARDRAIL_VERSION = os.getenv("FEX_GUARDRAIL_VERSION", "DRAFT")
