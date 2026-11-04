// Demo mode (issues #30, #31): records are kept in this browser only, until the chat API (#25),
// write-back (#26) and review API (#27) exist. Records use the #6 schema types, so swapping this
// module for real API calls doesn't change their shape.
//
// Traces (the agent's step-by-step reasoning) are kept NEXT TO records, keyed by record ID: in
// production they come from AgentCore Observability, not from the record itself.
import type { CompletedRecord, ConversationRecord } from '../../../../api/src/types/conversation-record'

const RECORDS = 'fair-exchange-demo-records'
const TRACES = 'fair-exchange-demo-traces'

export interface TraceStep { time: string; tool: string; detail: string }

function read<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? fallback } catch { return fallback }
}
function write(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode etc. */ }
}

export function loadRecords(): ConversationRecord[] {
  return read<ConversationRecord[]>(RECORDS, [])
}

export function saveRecord(record: ConversationRecord) {
  write(RECORDS, [record, ...loadRecords().filter((r) => r.record_id !== record.record_id)])
}

export function updateRecord(record: ConversationRecord) {
  write(RECORDS, loadRecords().map((r) => (r.record_id === record.record_id ? record : r)))
}

export function setFeedback(recordId: string, feedback: CompletedRecord['feedback']) {
  write(RECORDS, loadRecords().map((r) => (r.record_id === recordId && r.status === 'completed' ? { ...r, feedback } : r)))
}

export function saveTrace(recordId: string, steps: TraceStep[]) {
  write(TRACES, { ...read<Record<string, TraceStep[]>>(TRACES, {}), [recordId]: steps })
}

export function loadTrace(recordId: string): TraceStep[] {
  return read<Record<string, TraceStep[]>>(TRACES, {})[recordId] ?? []
}

export function clearDemoData() {
  try { localStorage.removeItem(RECORDS); localStorage.removeItem(TRACES) } catch { /* ignore */ }
}
