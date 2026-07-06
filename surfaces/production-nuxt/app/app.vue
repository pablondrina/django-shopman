<script setup lang="ts">
// Production surface shell (fournil.). Thin shell com roteamento MISTO, três classes de
// tela (verificadas endpoint a endpoint):
//   · telas de OPERADOR (planejamento/preparação/produção/expedição) → rail canônico
//     (kit) + conteúdo, atrás do gate de operador;
//   · painel (Fornadas) → KIOSK de operador em tela cheia (a previsão exige
//     backstage.operate_production) — FORA do rail, mas DENTRO do gate;
//   · menuboard → cardápio Solari PÚBLICO da loja (GET /storefront/menu, sem auth) —
//     FORA do rail E FORA do gate (como o /retirada do KDS).
const OPERATOR_PERM = "backstage.operate_production";
const { authenticated, locked, mustChange, operator, lock } =
  useOperatorLock(OPERATOR_PERM);

const route = useRoute();
const isPublicBoard = computed(() => route.path.startsWith("/menuboard"));
const isKiosk = computed(
  () => isPublicBoard.value || route.path.startsWith("/painel"),
);

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Produção" });
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo e global de conexão (kit) — só aparece offline (paridade c/ POS/KDS/Gestor). -->
    <OfflineBanner />
    <!-- Kiosks (menuboard público, painel operador): tela cheia, sem rail. -->
    <NuxtPage v-if="isKiosk" />
    <!-- Telas de operador: rail canônico (kit) + conteúdo. -->
    <div v-else class="flex min-h-screen">
      <div
        v-if="authenticated"
        class="sticky top-0 flex h-screen shrink-0 print:hidden"
      >
        <OperatorRail
          app-icon="croissant"
          app-label="Fournil"
          :central-url="hubUrl"
          :operator-name="operator?.name"
          @lock="lock"
        />
      </div>
      <div class="flex min-w-0 flex-1 flex-col">
        <NuxtPage />
      </div>
    </div>
    <!-- Gate de login/lock: nunca no menuboard público (o painel de operador segue atrás dele). -->
    <OperatorLogin v-if="!authenticated && !isPublicBoard" />
    <OperatorLock
      v-else-if="(locked || mustChange) && !isPublicBoard"
      :perm="OPERATOR_PERM"
    />
    <UiSonner />
  </div>
</template>
