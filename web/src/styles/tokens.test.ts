// Brand palette (#169): design.fairtradecertified.org colours on a cream canvas, with WCAG AA contrast kept.
import { describe, expect, it } from 'vitest'

// Read the CSS files as text. Vitest hands CSS imports back empty, and web/ has no Node types, so fs is
// loaded at runtime with just the one signature this test needs.
const fsModule = 'node:fs'
const { readFileSync } = await import(/* @vite-ignore */ fsModule) as { readFileSync: (path: URL, encoding: 'utf8') => string }
const read = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8')
const appCss = read('./app.css')
const tokensCss = read('./tokens.css')

const tokens = Object.fromEntries([...tokensCss.matchAll(/(--ft-[a-z-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]!.trim()]))

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi! + 0.05) / (lo! + 0.05)
}

describe('brand tokens (#169)', () => {
  it('uses the design.fairtradecertified.org palette on a cream canvas', () => {
    expect(tokens['--ft-ui-canvas']).toBe('#F7F2E8')
    expect(tokens['--ft-ui-primary']).toBe('#313D7F')
    expect(tokens['--ft-ui-text']).toBe('#39373A')
    expect(tokens['--ft-brand-cyan']).toBe('#44AEC8')
    expect(tokens['--ft-brand-green']).toBe('#93D73B')
    expect(tokens['--ft-brand-amber']).toBe('#ECCA52')
  })

  it('keeps WCAG AA contrast for text, links and buttons', () => {
    const t = (k: string) => tokens[k]!
    expect(contrast(t('--ft-ui-text'), t('--ft-ui-canvas'))).toBeGreaterThanOrEqual(4.5)
    expect(contrast(t('--ft-ui-text'), t('--ft-ui-surface'))).toBeGreaterThanOrEqual(4.5)
    expect(contrast(t('--ft-ui-primary'), t('--ft-ui-canvas'))).toBeGreaterThanOrEqual(4.5) // links on the page
    expect(contrast('#FFFFFF', t('--ft-ui-primary'))).toBeGreaterThanOrEqual(4.5) // button labels
    expect(contrast('#FFFFFF', t('--ft-ui-primary-hover'))).toBeGreaterThanOrEqual(4.5)
  })

  it('is defined once: app.css does not override the tokens', () => {
    expect(appCss).not.toMatch(/--ft-ui-[a-z-]+\s*:/)
  })
})
