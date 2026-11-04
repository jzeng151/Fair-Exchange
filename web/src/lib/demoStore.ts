// Demo mode (issue #30): records are kept in this browser only, until the chat API (#25) and
// write-back (#26) exist. Records are built with the #6 schema types, so swapping this module
// for real API calls doesn't change their shape.
import type { CompletedRecord, ConversationRecord } from '../../../api/src/types/conversation-record'

const KEY = 'fair-exchange-demo-records'

function load(): ConversationRecord[] {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '[]') as ConversationRecord[] } catch { return [] }
}

function persist(records: ConversationRecord[]) {
  try { localStorage.setItem(KEY, JSON.stringify(records)) } catch { /* private mode etc. */ }
}

export function saveRecord(record: ConversationRecord) {
  persist([record, ...load()])
}

export function setFeedback(recordId: string, feedback: CompletedRecord['feedback']) {
  persist(load().map((r) => (r.record_id === recordId && r.status === 'completed' ? { ...r, feedback } : r)))
}
