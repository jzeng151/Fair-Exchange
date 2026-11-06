// The decline wording promises when the conversation itself is deleted; that must stay true (#169, #19).
import { describe, expect, it } from 'vitest'
import { liveCopy } from './liveCopy'

// web/ has no Node types; fs is loaded at runtime with just the signature this test needs.
const fsModule = 'node:fs'
const { readFileSync } = await import(/* @vite-ignore */ fsModule) as { readFileSync: (path: URL, encoding: 'utf8') => string }
const stack = readFileSync(new URL('../../../infra/lib/fair-exchange-stack.ts', import.meta.url), 'utf8')
const days = Number(/MEMORY_EVENT_EXPIRY_DAYS\s*=\s*(\d+)/.exec(stack)?.[1])

describe('decline wording (#169)', () => {
  it('names the same retention as the deployed conversation memory', () => {
    expect(days).toBeGreaterThan(0)
    const word = { en: 'days', es: 'días', fr: 'jours' } as const
    for (const lang of ['en', 'es', 'fr'] as const) {
      expect(liveCopy[lang].declinedSaved).toContain(`${days} ${word[lang]}`)
      expect(liveCopy[lang].consentExplain.declined).toContain(`${days} ${word[lang]}`)
    }
  })
})
