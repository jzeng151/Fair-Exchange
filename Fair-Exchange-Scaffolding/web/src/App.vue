<script setup lang="ts">
// Producer chat (#30). The Fair Trade USA reviewer view (#31) and dashboard (#33) come later.
import { ref } from 'vue'
import ChatView from './components/ChatView.vue'
import FexMark from './components/FexMark.vue'

const subtitles = ref(true) // English under every Spanish line (for presenters who don't read Spanish)
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <FexMark :size="36" />
      <span class="brand-name">Fair Exchange</span>
      <span class="brand-product">by Fair Trade USA</span>
    </div>
    <div class="top-right">
      <button class="view-toggle" role="switch" :aria-checked="subtitles" @click="subtitles = !subtitles">
        <span class="switch" :class="{ on: subtitles }" aria-hidden="true"></span>
        English subtitles
      </button>
    </div>
  </header>
  <div class="synthetic-banner" role="note">
    Demo · synthetic data · scripted replies until the chat API (#25) is connected
  </div>
  <main class="container">
    <ChatView :producer-view="true" :subtitles="subtitles" />
  </main>
</template>
