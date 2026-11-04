import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore';
import type { AgentClient, AgentEvent, AgentRequest, ResumeResult } from './types.js';

/** One line of the agent's stream as an event, or undefined for lines that carry none. */
function lineToEvent(raw: string): AgentEvent | undefined {
  const line = raw.trim();
  if (!line || line.startsWith(':')) return undefined; // blank separator or SSE comment
  if (line.startsWith('data:')) return JSON.parse(line.slice(5).trim()) as AgentEvent;
  if (/^(event|id|retry):/.test(line)) return undefined; // other SSE fields
  return JSON.parse(line) as AgentEvent; // newline-delimited JSON
}

/**
 * Reads the agent runtime's event stream (#89). The AgentCore Python SDK streams a generator entrypoint as
 * Server-Sent Events (`data: <json>` then a blank line); newline-delimited JSON is accepted too.
 * Lines are decoded across chunk boundaries, including inside a multi-byte character.
 */
export async function* parseAgentStream(chunks: AsyncIterable<Uint8Array>): AsyncGenerator<AgentEvent> {
  const decoder = new TextDecoder();
  let buffer = '';
  for await (const chunk of chunks) {
    buffer += decoder.decode(chunk, { stream: true });
    let newline: number;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const event = lineToEvent(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      if (event) yield event;
    }
  }
  buffer += decoder.decode();
  const last = lineToEvent(buffer);
  if (last) yield last;
}

/** @deprecated kept for existing callers; use parseAgentStream. */
export const parseNdjson = parseAgentStream;

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
    const out = await this.invoke(request, 'text/event-stream', signal);
    if (!out.response) throw new Error('Agent returned no response body');
    yield* parseAgentStream(out.response as unknown as AsyncIterable<Uint8Array>);
  }

  async resume(request: AgentRequest, signal?: AbortSignal): Promise<ResumeResult> {
    const out = await this.invoke(request, 'application/json', signal);
    if (!out.response) throw new Error('Agent returned no response body');
    return JSON.parse(await out.response.transformToString());
  }
}
