import { parseAgentStream } from '../core/agent.js';
import type { AgentClient, AgentEvent, AgentRequest, ResumeResult } from '../core/types.js';

/**
 * Calls an agent served over plain HTTP the way AgentCore serves it (#101): POST <base>/invocations with the
 * request as JSON. Events come back as Server-Sent Events, `resume` as JSON. Used for local runs against
 * `agent/scripts/serve_local.py`; on AWS, `AgentCoreClient` calls InvokeAgentRuntime instead.
 */
export class HttpAgentClient implements AgentClient {
  constructor(private readonly baseUrl: string) {}

  private async post(request: AgentRequest, accept: string, signal?: AbortSignal): Promise<Response> {
    const res = await fetch(`${this.baseUrl}/invocations`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept },
      body: JSON.stringify(request),
      signal,
    });
    if (!res.ok) throw new Error(`Agent returned HTTP ${res.status}`);
    return res;
  }

  async *stream(request: AgentRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
    const res = await this.post(request, 'text/event-stream', signal);
    if (!res.body) throw new Error('Agent returned no response body');
    yield* parseAgentStream(res.body as unknown as AsyncIterable<Uint8Array>);
  }

  async resume(request: AgentRequest, signal?: AbortSignal): Promise<ResumeResult> {
    return (await (await this.post(request, 'application/json', signal)).json()) as ResumeResult;
  }
}
