<script setup lang="ts">
// Production surface shell (fournil.). Thin shell — the floor + planning are two
// boards, each at its own URL, so it uses pages/ routing (like the KDS/Gestor).
// The shell holds the page outlet, global chrome, and the operator lock overlay
// (Opção C): when the gate is ON and nobody has unlocked, the overlay covers the
// app until a PIN/badge identifies the operator. Gated OFF → never shows.
const OPERATOR_PERM = "backstage.operate_production";
const { locked } = useOperatorLock(OPERATOR_PERM);

useHead({ title: "Produção" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <OperatorLock v-if="locked" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
