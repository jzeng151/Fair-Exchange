"""The FEX eval harness (#36): runs the eval dataset through the agent and scores each conversation.

Offline, the runner drives the agent entrypoint in this process; in the eval stack, AgentCore Evaluations
calls the same per-turn runner through its agent invoker. Evaluators read the saved record and the eval
evidence (#34) by conversation ID, never trace content.
"""
