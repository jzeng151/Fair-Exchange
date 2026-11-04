<script setup lang="ts">
// Schematic, offline map: plots the producer and peer organizations by latitude/longitude
// (equirectangular). No map tiles, so it works without internet.
import { computed } from 'vue'

import type { Copy, Lang } from '../data/i18n'
import type { Peer, Scenario } from '../data/scenarios'
const props = defineProps<{ home: Scenario; peers: Peer[]; lang: Lang; sub: boolean; en: Copy; t: Copy; selected: number | null }>()
const emit = defineEmits<{ select: [n: number] }>()

const W = 320, H = 150, PAD = 24

const proj = computed(() => {
  const pts = [props.home.coords, ...props.peers.map((p) => p.coords)]
  let minLat = Math.min(...pts.map((p) => p.lat)), maxLat = Math.max(...pts.map((p) => p.lat))
  let minLon = Math.min(...pts.map((p) => p.lon)), maxLon = Math.max(...pts.map((p) => p.lon))
  const latSpan = Math.max(maxLat - minLat, 4), lonSpan = Math.max(maxLon - minLon, 4)
  const scale = Math.min((W - 2 * PAD) / lonSpan, (H - 2 * PAD) / latSpan)
  const cLat = (minLat + maxLat) / 2, cLon = (minLon + maxLon) / 2
  return (c: { lat: number; lon: number }) => ({ x: W / 2 + (c.lon - cLon) * scale, y: H / 2 - (c.lat - cLat) * scale })
})
const homePt = computed(() => proj.value(props.home.coords))
// Peers very close to home get nudged apart, with a short leader line to their true spot
const peerPts = computed(() => props.peers.map((p, i) => {
  const t = proj.value(p.coords)
  let x = t.x, y = t.y
  const dx = t.x - homePt.value.x, dy = t.y - homePt.value.y
  const d = Math.hypot(dx, dy)
  if (d < 30) {
    const ux = d ? dx / d : 0.7, uy = d ? dy / d : 0.7
    x = homePt.value.x + ux * 34; y = homePt.value.y + Math.max(uy, 0.6) * 34
  }
  x = Math.min(Math.max(x, 14), W - 14); y = Math.min(Math.max(y, 14), H - 14)
  return { x, y, tx: t.x, ty: t.y, nudged: d < 30, n: i + 1, place: p.place }
}))
const textW = (s: string) => s.length * 5.9
type Pin = { x: number; y: number; place: string; nudged: boolean }
// Keep peer labels inside the frame: right of the pin if it fits, otherwise left
// Label to the right of the pin if it fits; otherwise centered below it (or above near the bottom).
// Nudged pins (very close to home) keep a side label so they don't collide with the home label.
const fitsRight = (p: Pin) => p.x + 14 + textW(p.place) <= W - 4
function centered(p: Pin) { return !fitsRight(p) && !p.nudged }
function labelX(p: Pin) {
  if (fitsRight(p)) return p.x + 14
  if (!centered(p)) return p.x - 14
  const w = textW(p.place) / 2
  return Math.min(Math.max(p.x, w + 4), W - w - 4)
}
function labelY(p: Pin) { return centered(p) ? (p.y + 26 < H - 4 ? p.y + 26 : p.y - 16) : p.y + 4 }
function anchor(p: Pin) { return fitsRight(p) ? 'start' : centered(p) ? 'middle' : 'end' }
const homeLabel = computed(() => `${props.t.you} · ${props.home.region}`)
// Home label centered above its pin, clamped inside the frame
const homeLabelX = computed(() => {
  const w = textW(homeLabel.value) / 2
  return Math.min(Math.max(homePt.value.x, w + 4), W - w - 4)
})
</script>

<template>
  <figure class="map">
    <figcaption class="map-title">
      {{ t.mapHeading }}
      <span v-if="sub && lang !== 'en'" class="sub">{{ en.mapHeading }}</span>
    </figcaption>
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="`${en.mapHeading}: ${home.region} and ${peers.map(p => p.place).join(', ')}`">
      <rect x="0" y="0" :width="W" :height="H" rx="8" class="sea" />
      <line v-for="p in peerPts" :key="'l'+p.n" :x1="homePt.x" :y1="homePt.y" :x2="p.x" :y2="p.y" class="link" />
      <circle v-for="p in peerPts.filter(q => q.nudged)" :key="'t'+p.n" :cx="p.tx" :cy="p.ty" r="3" class="true-spot" />
      <g v-for="p in peerPts" :key="p.n" class="pin" :class="{ active: selected === p.n }" tabindex="0" role="button"
         :aria-label="`${p.n}: ${p.place}`" @click="emit('select', p.n)" @keydown.enter="emit('select', p.n)">
        <circle :cx="p.x" :cy="p.y" r="16" fill="transparent" />
        <circle :cx="p.x" :cy="p.y" r="10" class="peer-dot" />
        <text :x="p.x" :y="p.y + 4" text-anchor="middle" class="peer-num">{{ p.n }}</text>
        <text :x="labelX(p)" :y="labelY(p)" :text-anchor="anchor(p)" class="place">{{ p.place }}</text>
      </g>
      <g class="home">
        <circle :cx="homePt.x" :cy="homePt.y" r="11" class="home-ring" />
        <circle :cx="homePt.x" :cy="homePt.y" r="6" class="home-dot" />
        <text :x="homeLabelX" :y="homePt.y - 16" text-anchor="middle" class="place strong">{{ homeLabel }}</text>
      </g>
    </svg>
    <p class="map-note">{{ t.mapNote }}<span v-if="sub && lang !== 'en'" class="sub-inline"> ({{ en.mapNote }})</span></p>
  </figure>
</template>

<style scoped>
.map { margin: 8px 0 12px; padding: 12px; border: 1px solid var(--ft-ui-border); border-radius: 8px; background: var(--ft-ui-surface); }
.map-title { font-weight: 500; font-size: 15px; margin-bottom: 6px; }
svg { width: 100%; height: auto; display: block; }
.sea { fill: var(--ft-ui-primary-tint); }
.link { stroke: var(--ft-ui-primary); stroke-width: 1.5; stroke-dasharray: 4 4; opacity: .6; }
.peer-dot { fill: var(--ft-ui-primary); stroke: #fff; stroke-width: 2; transition: r .15s; }
.pin { cursor: pointer; }
.pin:hover .peer-dot, .pin.active .peer-dot { r: 13; }
.pin:focus { outline: none; }
.pin:focus-visible .peer-dot { stroke: var(--ft-ui-text); }
.true-spot { fill: var(--ft-ui-primary); }
.peer-num { fill: #fff; font-size: 11px; font-weight: 500; pointer-events: none; }
.home-ring { fill: rgba(147, 215, 59, .35); animation: pulse 2s ease-in-out infinite; transform-origin: center; transform-box: fill-box; }
.home-dot { fill: #487410; stroke: #fff; stroke-width: 2; }
.place { font-size: 11px; fill: var(--ft-ui-text); paint-order: stroke; stroke: rgba(255,255,255,.85); stroke-width: 3px; }
.place.strong { font-weight: 500; }
.map-note { margin: 6px 0 0; font-size: 13px; color: var(--ft-ui-text-secondary); }
@keyframes pulse { 50% { transform: scale(1.35); opacity: .5; } }
@media (prefers-reduced-motion: reduce) { .home-ring { animation: none; } }
</style>
