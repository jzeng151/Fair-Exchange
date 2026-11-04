// Reviewer actions (issue #31): approve, or correct tags and summary, then mark reviewed.
// A corrected record must still satisfy the #6 schema rules; identity, source and consent never change.
import type { CompletedRecord, ConversationRecord } from '../../../../api/src/types/conversation-record'
import { CHALLENGE_TAGS } from '../data/scenarios'

export class ReviewError extends Error {}

export interface ReviewChanges {
  tags?: string[]
  summaryOriginal?: string
  summaryEnglish?: string
}

const ALLOWED_TAGS = new Set<string>(CHALLENGE_TAGS)

export function reviewRecord(record: ConversationRecord, changes: ReviewChanges, reviewer: string, now: Date): CompletedRecord {
  if (record.status !== 'completed') throw new ReviewError('A declined record has no content to review.')
  if (!reviewer.trim()) throw new ReviewError('A reviewer name is required.')

  const tags = changes.tags ?? record.tags
  if (tags.length === 0) throw new ReviewError('Keep at least one challenge tag.')
  const unknown = tags.filter((t) => !ALLOWED_TAGS.has(t))
  if (unknown.length) throw new ReviewError(`Not one of the 11 challenge tags: ${unknown.join(', ')}`)

  const summaryOriginal = changes.summaryOriginal ?? record.summary_original
  if (!summaryOriginal.trim()) throw new ReviewError('The summary in the producer’s words can’t be empty.')

  const summaryEnglish = changes.summaryEnglish ?? record.summary_english ?? null
  if (record.language !== 'en' && !summaryEnglish?.trim()) {
    throw new ReviewError('Non-English records need an English summary.')
  }

  return {
    ...record,
    tags: tags as CompletedRecord['tags'],
    summary_original: summaryOriginal,
    summary_english: record.language === 'en' ? null : summaryEnglish,
    review_status: 'reviewed',
    reviewed_by: reviewer.trim(),
    reviewed_at: now.toISOString(),
  }
}
