<script setup lang="ts">
// One Vue app, several sides (routes):
//   #/        Producer: the FEX chat (issue #30)
//   #/me      Producer: "Your record" — what FTUSA stored (issue #32)
//   #/review  Fair Trade USA: records to review (issue #31)
//   #/admin   Fair Trade USA admins: aggregate dashboard (issue #33)
//   #/live    Producer: FEX against the real chat API (issue #116), only when VITE_FEX_API_URL is set
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AdminDashboard from './components/AdminDashboard.vue'
import ChatView from './components/ChatView.vue'
import FexMark from './components/FexMark.vue'
import LiveChatView from './components/LiveChatView.vue'
import ReviewerView from './components/ReviewerView.vue'
import YourRecordView from './components/YourRecordView.vue'
import LiveYourRecordView from './components/LiveYourRecordView.vue'
import LiveReviewerView from './components/LiveReviewerView.vue'
import { scenarios } from './data/scenarios'

type Side = 'producer' | 'live' | 'me' | 'review' | 'admin'
const ROUTES: Record<Side, string> = { producer: '#/', live: '#/live', me: '#/me', review: '#/review', admin: '#/admin' }
// Live mode exists only when a chat API address is configured at build time; the scripted demo stays the default.
const apiUrl = (import.meta.env.VITE_FEX_API_URL ?? '').trim()
const sideFromHash = (): Side =>
  apiUrl && location.hash.startsWith('#/live') ? 'live'
  : location.hash.startsWith('#/me') ? 'me'
    : location.hash.startsWith('#/review') ? 'review'
      : location.hash.startsWith('#/admin') ? 'admin'
        : 'producer'
const side = ref<Side>(sideFromHash())
const reviewer = ref<InstanceType<typeof ReviewerView> | null>(null)
const admin = ref<InstanceType<typeof AdminDashboard> | null>(null)
const yourRecord = ref<InstanceType<typeof YourRecordView> | null>(null)
const subtitles = ref(true) // English under every Spanish line (for presenters who don't read Spanish)

// Demo stand-in for the signed-in producer (#11): the first scenario, matching the chat's default.
// In production this is the identity from GET /me, never chosen in the view.
const demoProducerId = scenarios[0]?.id ?? 'P-001'

function go(next: Side) { location.hash = ROUTES[next] }
function onHash() {
  side.value = sideFromHash()
  if (side.value === 'me') yourRecord.value?.refresh() // show records the chat just saved
  if (side.value === 'review') reviewer.value?.refresh()
  if (side.value === 'admin') admin.value?.refresh()
}
onMounted(() => window.addEventListener('hashchange', onHash))
onBeforeUnmount(() => window.removeEventListener('hashchange', onHash))
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <FexMark :size="36" />
      <span class="brand-name">Fair Exchange</span>
      <span class="brand-product">by Fair Trade USA</span>
    </div>
    <div class="top-right">
      <nav class="side-switch" aria-label="Which side of Fair Exchange to show">
        <a href="#/" :aria-current="side === 'producer' ? 'page' : undefined" :class="{ active: side === 'producer' }" @click.prevent="go('producer')">🧑‍🌾 Producer</a>
        <a v-if="apiUrl" href="#/live" :aria-current="side === 'live' ? 'page' : undefined" :class="{ active: side === 'live' }" @click.prevent="go('live')">⚡ Live FEX</a>
        <a href="#/me" :aria-current="side === 'me' ? 'page' : undefined" :class="{ active: side === 'me' }" @click.prevent="go('me')">📄 Your record</a>
        <a href="#/review" :aria-current="side === 'review' ? 'page' : undefined" :class="{ active: side === 'review' }" @click.prevent="go('review')">🏢 Fair Trade USA</a>
        <a href="#/admin" :aria-current="side === 'admin' ? 'page' : undefined" :class="{ active: side === 'admin' }" @click.prevent="go('admin')">📊 Admin</a>
      </nav>
      <button v-if="side === 'producer'" class="view-toggle" role="switch" :aria-checked="subtitles" @click="subtitles = !subtitles">
        <span class="switch" :class="{ on: subtitles }" aria-hidden="true"></span>
        English subtitles
      </button>
    </div>
  </header>
  <div class="synthetic-banner" role="note">
    <template v-if="side === 'producer'">Demo · synthetic data · scripted replies until the chat API (#25) is connected</template>
    <template v-else-if="side === 'live'">Live · real chat API and agent · sample producer data</template>
    <template v-else-if="side === 'me'">{{ apiUrl ? 'Your record · live · sign in to see your saved conversations' : 'Your record · browser demo' }}</template>
    <template v-else-if="side === 'review'">{{ apiUrl ? 'Fair Trade USA · live reviewer access' : 'Fair Trade USA · browser demo' }}</template>
    <template v-else>{{ apiUrl ? 'Admin · live analytics available with the admin passcode' : 'Admin · browser demo' }}</template>
  </div>
  <main class="container">
    <!-- v-show keeps the producer's conversation in place while switching sides -->
    <ChatView v-show="side === 'producer'" :producer-view="true" :subtitles="subtitles" />
    <LiveChatView v-if="apiUrl" v-show="side === 'live'" :active="side === 'live'" :api-url="apiUrl" />
    <LiveYourRecordView v-if="side === 'me' && apiUrl" :api-url="apiUrl" />
    <YourRecordView v-else-if="side === 'me'" ref="yourRecord" :producer-id="demoProducerId" />
    <LiveReviewerView v-if="side === 'review' && apiUrl" :api-url="apiUrl" />
    <ReviewerView v-else-if="side === 'review'" ref="reviewer" />
    <AdminDashboard v-if="side === 'admin'" ref="admin" :api-url="apiUrl" />
  </main>
</template>
