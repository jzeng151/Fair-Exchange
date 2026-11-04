<script setup lang="ts">
// One Vue app, two sides (routes):
//   #/        Producer: the FEX chat (issue #30)
//   #/review  Fair Trade USA: records to review (issue #31)
//   #/admin   Fair Trade USA admins: aggregate dashboard (issue #33)
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AdminDashboard from './components/AdminDashboard.vue'
import ChatView from './components/ChatView.vue'
import FexMark from './components/FexMark.vue'
import ReviewerView from './components/ReviewerView.vue'

type Side = 'producer' | 'review' | 'admin'
const ROUTES: Record<Side, string> = { producer: '#/', review: '#/review', admin: '#/admin' }
const sideFromHash = (): Side => (location.hash.startsWith('#/review') ? 'review' : location.hash.startsWith('#/admin') ? 'admin' : 'producer')
const side = ref<Side>(sideFromHash())
const reviewer = ref<InstanceType<typeof ReviewerView> | null>(null)
const admin = ref<InstanceType<typeof AdminDashboard> | null>(null)
const subtitles = ref(true) // English under every Spanish line (for presenters who don't read Spanish)

function go(next: Side) { location.hash = ROUTES[next] }
function onHash() {
  side.value = sideFromHash()
  if (side.value === 'review') reviewer.value?.refresh() // show records the chat just saved
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
    <template v-else-if="side === 'review'">Fair Trade USA side · demo · records saved in this browser until the review API (#27) is connected</template>
    <template v-else>Admin · demo · computed in this browser until the analytics API (#29) and admin sign-in (#11) are connected</template>
  </div>
  <main class="container">
    <!-- v-show keeps the producer's conversation in place while switching sides -->
    <ChatView v-show="side === 'producer'" :producer-view="true" :subtitles="subtitles" />
    <ReviewerView v-if="side === 'review'" ref="reviewer" />
    <AdminDashboard v-if="side === 'admin'" ref="admin" />
  </main>
</template>
