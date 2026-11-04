import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore';
import type { AgentClient, AgentEvent, AgentRequest, ResumeResult } from './types.js';

/** Splits a byte stream into newline-delimited JSON events (application/x-ndjson). */
export async function* parseNdjson(chunks: AsyncIterable<Uint8Array>): AsyncGenerator<AgentEvent> {
  const decoder = new TextDecoder();
  let buffer = '';
  for await (const chunk of chunks) {
    buffer += decoder.decode(chunk, { stream: true });
    let newline: number;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) yield JSON.parse(line) as AgentEvent;
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) yield JSON.parse(buffer) as AgentEvent;
}

/**
 * Calls AgentCore InvokeAgentRuntime. The runtime session ID is the conversation ID
 * (a UUID v4 is long enough for a session ID), so one conversation is one agent session.
 */
export class AgentCoreClient implements AgentClient {
  constructor(
    private readonly runtimeArn: string,
    private readonly client: BedrockAgentCoreClient = new BedrockAgentCoreClient({}),
  ) {}

  private invoke(request: AgentRequest, accept: string, signal?: AbortSignal) {
    return this.client.send(
      new InvokeAgentRuntimeCommand({
        agentRuntimeArn: this.runtimeArn,
        runtimeSessionId: request.conversationId,
        contentType: 'application/json',
        accept,
        payload: new TextEncoder().encode(JSON.stringify(request)),
      }),
      { abortSignal: signal },
    );
  }

  async *stream(request: AgentRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
    const out = await this.invoke(request, 'application/x-ndjson', signal);
    if (!out.response) throw new Error('Agent returned no response body');
    yield* parseNdjson(out.response as unknown as AsyncIterable<Uint8Array>);
  }

  async resume(request: AgentRequest, signal?: AbortSignal): Promise<ResumeResult> {
    const out = await this.invoke(request, 'application/json', signal);
    if (!out.response) throw new Error('Agent returned no response body');
    return JSON.parse(await out.response.transformToString());
  }
}
