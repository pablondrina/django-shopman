<script setup lang="ts">
// Customer pickup board — o display que o cliente assiste. Painel de chegadas
// (sempre DARK, leitura à distância): código GRANDE, "pronto" em verde (vá retirar)
// com chegada animada, "em preparo" neutro. Relógio ao vivo. Marca fica no storefront
// / futuro customer display do PDV — aqui é chrome neutro, copy acolhedor. Read público.
import { realtimeIndicator, splitRef } from "~/presentation/board";

const { status, realtime } = useKdsCustomerBoard();
const preparing = computed(() => status.value?.preparing ?? []);
const ready = computed(() => status.value?.ready ?? []);
// Cue de tempo-real HONESTO: "ao vivo" (verde, pulsando) só quando o SSE conectou;
// senão neutro "atualiza sozinho" (o poll de 10s carrega). Nunca mente pro cliente.
const liveCue = computed(() => realtimeIndicator(realtime.value));

// Relógio ao vivo (client-only — new Date() no SSR causaria mismatch).
const now = ref<Date | null>(null);
let clockTimer: ReturnType<typeof setInterval> | null = null;
const clockTime = computed(() =>
  now.value
    ? now.value.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "",
);
onMounted(() => {
  now.value = new Date();
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});
</script>

<template>
  <div
    class="dark grid min-h-screen grid-rows-[auto_1fr] bg-background text-foreground"
  >
    <!-- header -->
    <header
      class="flex items-center justify-between gap-4 border-b px-6 py-5 md:px-10"
    >
      <div class="min-w-0">
        <p
          class="text-sm font-medium uppercase tracking-wider text-muted-foreground"
        >
          Retirada no balcão
        </p>
        <h1 class="truncate text-3xl font-bold md:text-5xl">Seu pedido</h1>
      </div>
      <ClientOnly>
        <div v-if="now" class="flex flex-col items-end leading-none">
          <span class="text-xl font-bold tabular-nums md:text-4xl">{{
            clockTime
          }}</span>
          <span
            class="mt-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
            :title="liveCue.title"
          >
            <span
              class="inline-block size-2 rounded-full"
              :class="[liveCue.dotClass, liveCue.live ? 'animate-pulse' : '']"
            />
            {{ liveCue.label }}
          </span>
        </div>
      </ClientOnly>
    </header>

    <!-- duas colunas: pronto (verde = vá retirar) / em preparo (neutro) -->
    <div class="grid min-h-0 gap-px overflow-hidden bg-border md:grid-cols-2">
      <!-- ready -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2
          class="flex items-center gap-2.5 px-6 py-5 text-xl font-bold md:px-10 md:text-3xl"
        >
          <Icon
            name="lucide:circle-check-big"
            class="size-7 shrink-0 text-green-500"
          />
          Pronto para retirar
          <span
            v-if="ready.length"
            class="rounded-full bg-green-500/15 px-2.5 py-0.5 text-base font-bold tabular-nums text-green-500"
            >{{ ready.length }}</span
          >
        </h2>
        <TransitionGroup
          tag="div"
          name="kds-cust"
          class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10"
        >
          <article
            v-for="order in ready"
            :key="order.ref"
            class="rounded-lg border-2 border-green-500/50 bg-green-500/10 px-6 py-5 shadow-sm"
          >
            <p
              class="text-xs font-bold uppercase tracking-wider text-green-600 dark:text-green-500"
            >
              {{ splitRef(order.ref).prefix || "Pedido" }}
            </p>
            <p
              class="break-words text-5xl font-extrabold tabular-nums leading-none md:text-7xl"
            >
              {{ splitRef(order.ref).code }}
            </p>
          </article>
          <p
            v-if="!ready.length"
            :key="'empty-ready'"
            class="rounded-lg border border-dashed p-8 text-center text-base text-muted-foreground"
          >
            Seu número aparece aqui assim que o pedido ficar pronto. ✨
          </p>
        </TransitionGroup>
      </section>

      <!-- preparing -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2
          class="flex items-center gap-2.5 px-6 py-5 text-xl font-bold text-muted-foreground md:px-10 md:text-3xl"
        >
          <Icon name="lucide:flame" class="size-7 shrink-0" />
          Em preparo
          <span
            v-if="preparing.length"
            class="rounded-full bg-muted px-2.5 py-0.5 text-base font-bold tabular-nums text-muted-foreground"
            >{{ preparing.length }}</span
          >
        </h2>
        <TransitionGroup
          tag="div"
          name="kds-cust"
          class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10"
        >
          <article
            v-for="order in preparing"
            :key="order.ref"
            class="rounded-lg border bg-card px-6 py-4"
          >
            <p
              class="text-xs font-bold uppercase tracking-wider text-muted-foreground"
            >
              {{ splitRef(order.ref).prefix || "Pedido" }}
            </p>
            <p
              class="break-words text-4xl font-bold tabular-nums leading-none text-muted-foreground md:text-6xl"
            >
              {{ splitRef(order.ref).code }}
            </p>
          </article>
          <p
            v-if="!preparing.length"
            :key="'empty-prep'"
            class="rounded-lg border border-dashed p-8 text-center text-base text-muted-foreground"
          >
            Nenhum pedido em preparo agora.
          </p>
        </TransitionGroup>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* Chegada/movimento dos números no painel — suave, chama atenção sem agitar. */
.kds-cust-move {
  transition: transform 0.4s cubic-bezier(0.2, 0, 0, 1);
}
.kds-cust-enter-active {
  transition:
    opacity 0.4s ease,
    transform 0.4s cubic-bezier(0.2, 0, 0, 1);
}
.kds-cust-leave-active {
  transition: opacity 0.3s ease;
}
.kds-cust-enter-from {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}
.kds-cust-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .kds-cust-move,
  .kds-cust-enter-active,
  .kds-cust-leave-active {
    transition: none;
  }
}
</style>
