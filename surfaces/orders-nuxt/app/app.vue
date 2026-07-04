<script setup lang="ts">
// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C): when the gate is ON and nobody unlocked, a PIN/badge is
// required. Gated OFF → never shows.
const OPERATOR_PERM = "shop.manage_orders";
const { authenticated, locked, mustChange } = useOperatorLock(OPERATOR_PERM);

useHead({ title: "Gestor de Pedidos" });
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Hub chrome: one identity + section-switch + global-tools bar for both boards. -->
    <GestorTopBar />
    <NuxtPage />
    <OperatorLogin v-if="!authenticated" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
