<script setup lang="ts">
// FEX monogram: the professional identity for Fair Exchange's assistant (no mascot).
// Indigo disc, white "FEX" lettering, thin Fair Trade green ring.
withDefaults(defineProps<{ size?: number }>(), { size: 36 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 48 48" role="img" aria-label="FEX" class="fex-mark">
    <circle cx="24" cy="24" r="22.5" fill="#313D7F" />
    <circle cx="24" cy="24" r="22.5" fill="none" stroke="#93D73B" stroke-width="3" />
    <text x="24" y="29" text-anchor="middle" fill="#FFFFFF"
          font-family="Rubik, Arial, sans-serif" font-weight="500" font-size="14" letter-spacing="0.5">FEX</text>
  </svg>
</template>

<style scoped>
.fex-mark { display: inline-block; flex: none; vertical-align: middle; }
</style>
