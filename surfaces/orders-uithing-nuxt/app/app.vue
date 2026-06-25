<script setup lang="ts">
// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds only the page outlet + global chrome.
useHead({ title: "Gestor de Pedidos" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <UiSonner />
  </div>
</template>
