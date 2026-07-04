<script setup lang="ts">
// KDS surface shell (Arc 2). Thin shell — the KDS is a multi-display surface
// (station picker, per-station board, customer pickup board), each opened at its
// own URL on a physical kitchen screen, so it uses pages/ routing (unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C). The overlay covers the OPERATOR screens only — never the
// PUBLIC customer pickup board (/retirada), which has no auth. Gated OFF → never shows.
const OPERATOR_PERM = "backstage.operate_kds";
const { authenticated, locked, mustChange } = useOperatorLock(OPERATOR_PERM);

const route = useRoute();
const isCustomerBoard = computed(() => route.path.startsWith("/retirada"));

useHead({ title: "Shopman KDS" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <OperatorLogin v-if="!authenticated && !isCustomerBoard" />
    <OperatorLock v-else-if="(locked || mustChange) && !isCustomerBoard" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
