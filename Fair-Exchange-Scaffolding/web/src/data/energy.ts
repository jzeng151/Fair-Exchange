// How much AI a conversation used, and a ROUGH energy estimate.
//
// In the prototype there is no real AI, so token counts are ESTIMATED from text length
// (about 4 characters per token). In the real system, Amazon Bedrock returns exact
// inputTokens/outputTokens for every call; use those instead.
//
// Energy per 1,000 tokens is an ILLUSTRATIVE ASSUMPTION for the demo, not a measured value.
// Replace with measured figures (e.g. from the AWS Customer Carbon Footprint Tool) before
// making any public claim.
export const WH_PER_1K_TOKENS = { small: 0.05, large: 0.4 }
export const MODEL_NAMES = { small: 'Claude Haiku (small, efficient)', large: 'Claude Sonnet (larger)' }

export const tokensFromText = (s: string | undefined) => Math.ceil((s || '').length / 4)

export interface Usage { small: { calls: number; tokens: number }; large: { calls: number; tokens: number } }

export function newUsage(): Usage {
  return { small: { calls: 0, tokens: 0 }, large: { calls: 0, tokens: 0 } }
}

// One model call: which size, plus estimated input and output tokens
export function addCall(usage: Usage, size: 'small' | 'large', inputTokens: number, outputTokens: number) {
  usage[size].calls += 1
  usage[size].tokens += Math.round(inputTokens + outputTokens)
}

export function estimateWh(usage: Usage) {
  return (usage.small.tokens / 1000) * WH_PER_1K_TOKENS.small + (usage.large.tokens / 1000) * WH_PER_1K_TOKENS.large
}

// Producer-facing level. Plain words only; no numbers shown to producers.
export function energyLevel(wh: number): 'veryLow' | 'low' | 'moderate' {
  if (wh < 3.5) return 'veryLow'
  if (wh < 7) return 'low'
  return 'moderate'
}

export function summarize(usage: Usage) {
  const wh = estimateWh(usage)
  const calls = usage.small.calls + usage.large.calls
  return {
    smallCalls: usage.small.calls, largeCalls: usage.large.calls,
    smallTokens: usage.small.tokens, largeTokens: usage.large.tokens,
    totalTokens: usage.small.tokens + usage.large.tokens,
    smallShare: calls ? usage.small.calls / calls : 0,
    estWh: Math.round(wh * 100) / 100,
    level: energyLevel(wh),
  }
}
