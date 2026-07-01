<script setup lang="ts">
// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C): when the gate is ON and nobody unlocked, a PIN/badge is
// required. Gated OFF → never shows.
const OPERATOR_PERM = "shop.manage_orders";
const { authenticated, locked } = useOperatorLock(OPERATOR_PERM);

useHead({ title: "Gestor de Pedidos" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Slim hub nav: switch between the two Gestor faces (pedidos + catálogo). -->
    <nav class="flex items-center gap-1 border-b border-border bg-card px-4 py-2">
      <span class="mr-3 text-sm font-semibold">Gestor</span>
      <NuxtLink
        to="/"
        class="h-9 rounded-md px-3 text-sm leading-9 transition-colors"
        active-class="bg-primary/5 text-foreground"
        exact-active-class="bg-primary/10 font-medium text-foreground"
      >
        Pedidos
      </NuxtLink>
      <NuxtLink
        to="/catalog"
        class="h-9 rounded-md px-3 text-sm leading-9 text-muted-foreground transition-colors hover:text-foreground"
        active-class="bg-primary/10 font-medium text-foreground"
      >
        Catálogo
      </NuxtLink>
    </nav>
    <NuxtPage />
    <OperatorLogin v-if="!authenticated" />
    <OperatorLock v-else-if="locked" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
