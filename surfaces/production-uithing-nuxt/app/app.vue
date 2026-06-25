<script setup lang="ts">
// Production surface shell (fournil.). Thin shell — the floor + planning are two
// boards, each at its own URL, so it uses pages/ routing (like the KDS/Gestor).
// The shell holds only the page outlet + global chrome.
useHead({ title: "Produção" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <UiSonner />
  </div>
</template>
