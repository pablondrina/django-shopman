<script setup lang="ts">
// KDS surface shell (Arc 2). Thin shell — the KDS is a multi-display surface
// (station picker, per-station board, customer pickup board), each opened at its
// own URL on a physical kitchen screen, so it uses pages/ routing (unlike the POS
// kiosk single-shell). The shell holds only the page outlet + global chrome.
useHead({ title: "Shopman KDS" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <UiSonner />
  </div>
</template>
