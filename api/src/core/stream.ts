/** A minimal writable sink, matched by both the real Lambda response stream and tests. */
export interface Sink {
  write(chunk: string): void;
  end(): void;
}

export function writeEvent(sink: Sink, event: Record<string, unknown>): void {
  sink.write(`${JSON.stringify(event)}\n`);
}

export function writeErrorThenDone(sink: Sink, code: string, message: string): void {
  writeEvent(sink, { type: 'error', code, message });
  writeEvent(sink, { type: 'done' });
  sink.end();
}
