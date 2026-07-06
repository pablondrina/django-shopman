<script setup lang="ts">
// KDS surface shell (Arc 2). Thin shell — the KDS is a multi-display surface
// (station picker, per-station board, customer pickup board), each opened at its
// own URL on a physical kitchen screen, so it uses pages/ routing (unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C). The overlay covers the OPERATOR screens only — never the
// PUBLIC customer pickup board (/retirada), which has no auth. Gated OFF → never shows.
const OPERATOR_PERM = "backstage.operate_kds";
const { authenticated, locked, mustChange, operator, lock } =
  useOperatorLock(OPERATOR_PERM);

const route = useRoute();
const isCustomerBoard = computed(() => route.path.startsWith("/retirada"));

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Shopman KDS" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo e global de conexão (kit) — só aparece offline (paridade POS/Gestor/Fournil). -->
    <OfflineBanner />
    <!-- Painel público de retirada: tela cheia, sem rail e sem auth. -->
    <NuxtPage v-if="isCustomerBoard" />
    <!-- Telas de operador: rail canônico (kit) + conteúdo. -->
    <div v-else class="flex min-h-screen">
      <div
        v-if="authenticated"
        class="sticky top-0 flex h-screen shrink-0 print:hidden"
      >
        <OperatorRail
          app-icon="chef-hat"
          app-label="Cozinha"
          :central-url="hubUrl"
          :operator-name="operator?.name"
          @lock="lock"
        >
          <template #nav>
            <!-- Nav própria do KDS: trocar de estação (voltar ao seletor). -->
            <RailItem
              icon="grid-2x2"
              label="Estações"
              :active="route.path === '/'"
              @activate="navigateTo('/')"
            />
          </template>
        </OperatorRail>
      </div>
      <div class="flex min-w-0 flex-1 flex-col">
        <NuxtPage />
      </div>
    </div>
    <OperatorLogin v-if="!authenticated && !isCustomerBoard" />
    <OperatorLock
      v-else-if="(locked || mustChange) && !isCustomerBoard"
      :perm="OPERATOR_PERM"
    />
    <UiSonner />
  </div>
</template>
