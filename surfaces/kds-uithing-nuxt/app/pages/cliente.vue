<script setup lang="ts">
// Customer pickup board (Arc 4) — the customer-facing "your order" display. Always
// DARK (a distance-reading arrivals board), big refs, neutralized chrome (brand
// lives in the storefront / future POS customer display). Public read.
const { status } = useKdsCustomerBoard();
const preparing = computed(() => status.value?.preparing ?? []);
const ready = computed(() => status.value?.ready ?? []);
const updatedAt = computed(() => status.value?.updated_at_display ?? "");
</script>

<template>
  <div class="dark grid min-h-screen grid-rows-[auto_1fr] bg-background text-foreground">
    <!-- header -->
    <header class="flex items-center justify-between gap-4 border-b px-6 py-4 md:px-10">
      <div class="min-w-0">
        <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Retirada no balcão</p>
        <h1 class="truncate text-2xl font-bold md:text-4xl">Status dos pedidos</h1>
      </div>
      <span v-if="updatedAt" class="inline-flex shrink-0 items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
        <Icon name="lucide:clock" class="size-3.5" />
        Atualizado <span class="tabular-nums">{{ updatedAt }}</span>
      </span>
    </header>

    <!-- two columns: ready (green = vá retirar) / preparing (neutro) -->
    <div class="grid min-h-0 gap-px overflow-hidden bg-border md:grid-cols-2">
      <!-- ready -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2 class="flex items-center gap-2 px-6 py-4 text-xl font-bold md:px-10">
          Pronto para retirar
          <span v-if="ready.length" class="rounded-full bg-green-500/15 px-2 py-0.5 text-sm font-semibold text-green-500 tabular-nums">{{ ready.length }}</span>
        </h2>
        <div class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10">
          <article
            v-for="order in ready"
            :key="order.ref"
            class="rounded-md border border-green-500/40 bg-green-500/5 px-5 py-4"
          >
            <p class="text-xs font-medium uppercase tracking-wide text-green-600 dark:text-green-500">Pedido</p>
            <p class="truncate text-4xl font-extrabold tabular-nums leading-tight md:text-5xl">{{ order.ref }}</p>
          </article>
          <p v-if="!ready.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            Nenhum pedido pronto no momento.
          </p>
        </div>
      </section>

      <!-- preparing -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2 class="flex items-center gap-2 px-6 py-4 text-xl font-bold text-muted-foreground md:px-10">
          Em preparo
          <span v-if="preparing.length" class="rounded-full bg-amber-500/15 px-2 py-0.5 text-sm font-semibold text-amber-500 tabular-nums">{{ preparing.length }}</span>
        </h2>
        <div class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10">
          <article
            v-for="order in preparing"
            :key="order.ref"
            class="rounded-md border bg-card px-5 py-4"
          >
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pedido</p>
            <p class="truncate text-3xl font-bold tabular-nums leading-tight text-muted-foreground md:text-4xl">{{ order.ref }}</p>
          </article>
          <p v-if="!preparing.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            Nenhum pedido em preparo.
          </p>
        </div>
      </section>
    </div>
  </div>
</template>
