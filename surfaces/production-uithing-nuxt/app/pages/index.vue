<script setup lang="ts">
// Production live floor — the started-WorkOrder board (the old HTML "KDS de
// produção", now Nuxt). Reads the production KDS projection + 30s poll via
// useProductionKds; renders WorkOrderKdsCards with advance-step / finish / void;
// gestures POST through the django proxy and reconcile. A material shortage on
// finish opens the shortage modal (override with force). Tablet/touch-first.
import type { FloorAffordanceRef } from "~/presentation/production";
import { matchesKdsQuery } from "~/presentation/production";
import type { ProductionKDSCardProjection, ProductionShortageError } from "~/types/production";

const { cards, totalCount, lateCount, pending, error, refresh, isBusy, advanceStep, finish, voidOrder } = useProductionKds();

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(() => route.query.q, (q) => { if (typeof q === "string") query.value = q; });
const filteredCards = computed<ProductionKDSCardProjection[]>(() =>
  cards.value.filter((c) => matchesKdsQuery(c, query.value)),
);

// finish dialog (default quantity = started_qty).
const finishCard = ref<ProductionKDSCardProjection | null>(null);
const finishQty = ref("");
function openFinish(card: ProductionKDSCardProjection) {
  finishCard.value = card;
  finishQty.value = card.started_qty;
}
async function confirmFinish(force = false) {
  const card = finishCard.value;
  if (!card || !finishQty.value.trim()) return;
  const res = await finish(card.pk, finishQty.value.trim(), force);
  if (res.ok) {
    finishCard.value = null;
    useSonner.success(`Produção concluída: ${card.output_sku}`);
  } else if (res.shortage) {
    finishCard.value = null;
    shortage.value = res.shortage;
  }
}

// void dialog (needs a reason).
const voidCard = ref<ProductionKDSCardProjection | null>(null);
const voidReason = ref("");
function openVoid(card: ProductionKDSCardProjection) {
  voidCard.value = card;
  voidReason.value = "";
}
async function confirmVoid() {
  const card = voidCard.value;
  if (!card) return;
  const res = await voidOrder(card.pk, voidReason.value.trim() || "Estornado pelo operador");
  if (res.ok) {
    voidCard.value = null;
    useSonner.success(`Ordem estornada: ${card.output_sku}`);
  }
}

// shortage modal (override a material shortage with force=1).
const shortage = ref<ProductionShortageError | null>(null);
async function overrideShortage() {
  const card = shortage.value && cards.value.find((c) => c.ref === shortage.value!.work_order_ref);
  shortage.value = null;
  if (card) {
    const res = await finish(card.pk, card.started_qty, true);
    if (res.ok) useSonner.success(`Produção concluída: ${card.output_sku}`);
  }
}

function onAction(card: ProductionKDSCardProjection, action: FloorAffordanceRef) {
  if (action === "advance_step") advanceStep(card.pk);
  else if (action === "finish") openFinish(card);
  else if (action === "void") openVoid(card);
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader v-model:query="query" title="Chão ao vivo" :count="totalCount" count-label="em produção" :pending="pending" @refresh="refresh()" />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !cards.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar a produção. Reconectando…
      </p>

      <div v-else-if="!cards.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:check-circle-2" class="size-8" />
        <p class="text-base font-medium">Nenhuma produção em andamento.</p>
        <NuxtLink to="/planejamento" class="text-sm text-primary underline-offset-2 hover:underline">Ir para o planejamento</NuxtLink>
      </div>

      <template v-else>
        <p v-if="lateCount" class="mb-3 inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-sm font-medium text-amber-700 dark:text-amber-300">
          <Icon name="lucide:clock-alert" class="size-4" /> {{ lateCount }} atrasada{{ lateCount > 1 ? "s" : "" }}
        </p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <WorkOrderKdsCard
            v-for="card in filteredCards"
            :key="card.pk"
            :card="card"
            :busy="isBusy(card.pk)"
            @action="(action) => onAction(card, action)"
          />
        </div>
        <p v-if="query && !filteredCards.length" class="mt-3 rounded-md border border-dashed p-3 text-center text-sm text-muted-foreground">
          Nenhum resultado para “{{ query.trim() }}”.
        </p>
      </template>
    </section>

    <!-- finish dialog -->
    <UiDialog :open="finishCard != null" @update:open="(v) => { if (!v) finishCard = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Concluir {{ finishCard?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Quantidade efetivamente produzida (#{{ finishCard?.ref }}).</UiDialogDescription>
        </UiDialogHeader>
        <input
          v-model="finishQty"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 100"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Quantidade concluída"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="finishCard = null">Cancelar</button>
          <button type="button" :disabled="!finishQty.trim()" class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="confirmFinish(false)">
            Concluir produção
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- void dialog -->
    <UiDialog :open="voidCard != null" @update:open="(v) => { if (!v) voidCard = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Estornar {{ voidCard?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>A ordem #{{ voidCard?.ref }} sai da produção. Informe o motivo (opcional).</UiDialogDescription>
        </UiDialogHeader>
        <p
          v-if="voidCard?.order_refs?.length"
          class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm text-amber-700 dark:text-amber-300"
        >
          <Icon name="lucide:shopping-bag" class="mt-0.5 size-4 shrink-0" />
          <span>
            {{ voidCard.order_refs.length }} pedido{{ voidCard.order_refs.length > 1 ? "s aguardam" : " aguarda" }} este lote
            ({{ voidCard.order_refs.join(", ") }}). O vínculo será desfeito ao estornar.
          </span>
        </p>
        <textarea
          v-model="voidReason"
          rows="3"
          placeholder="Motivo do estorno…"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo do estorno"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="voidCard = null">Cancelar</button>
          <button type="button" class="rounded-md border border-transparent bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700" @click="confirmVoid">
            Estornar ordem
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- shortage modal -->
    <ShortageDialog :shortage="shortage" @update:open="(v) => { if (!v) shortage = null }" @confirm="overrideShortage" />
  </main>
</template>
