<script setup lang="ts">
// An expedition (dispatch) board card — KDS-refined to match the ticket grammar
// (distance-reading ref, density-aware, functional color on dark). Delivery vs
// counter is the functional accent (cyan vs green); the action is dispatch/complete.
import type { KDSExpeditionCardProjection } from "~/types/kds";
import type { KDSDensity } from "~/components/KdsTicketCard.vue";
import { splitRef } from "~/presentation/board";

const props = withDefaults(
  defineProps<{ card: KDSExpeditionCardProjection; busy?: boolean; density?: KDSDensity }>(),
  { density: "cozy" },
);
defineEmits<{ action: [action: "dispatch" | "complete"] }>();

const ref_ = computed(() => splitRef(props.card.ref));

const accent = computed(() => (props.card.is_delivery ? "border-l-cyan-500" : "border-l-green-500"));
const badge = computed(() =>
  props.card.is_delivery
    ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
    : "border-green-500/40 bg-green-500/15 text-green-300",
);
const refSize = computed(() => ({ compact: "text-xl", cozy: "text-2xl", roomy: "text-3xl" }[props.density]));
const pad = computed(() => ({ compact: "p-3", cozy: "p-4", roomy: "p-5" }[props.density]));
</script>

<template>
  <article class="flex flex-col overflow-hidden rounded-md border border-l-4 bg-card" :class="accent">
    <div class="flex items-start justify-between gap-3 border-b" :class="pad">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon v-if="card.channel_icon" :name="`lucide:${card.channel_icon}`" class="size-3.5" />
          <span class="truncate">{{ ref_.prefix }}{{ card.fulfillment_label }}</span>
        </div>
        <h3 class="break-words font-bold tabular-nums leading-none" :class="refSize">{{ ref_.code }}</h3>
        <p v-if="card.customer_name" class="mt-1 truncate text-sm font-medium text-muted-foreground">{{ card.customer_name }}</p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-sm font-bold" :class="badge">
        <Icon :name="`lucide:${card.fulfillment_icon}`" class="size-4" />
        {{ card.is_delivery ? "Despacho" : "Balcão" }}
      </span>
    </div>

    <div class="grid gap-3" :class="pad">
      <div class="grid grid-cols-3 gap-2">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted-foreground">Cliente</div>
          <div class="truncate font-semibold">{{ card.customer_name || "—" }}</div>
        </div>
        <div>
          <div class="text-xs uppercase tracking-wide text-muted-foreground">Unidades</div>
          <div class="text-lg font-bold tabular-nums">{{ card.units_count }}</div>
        </div>
        <div>
          <div class="text-xs uppercase tracking-wide text-muted-foreground">Linhas</div>
          <div class="text-lg font-bold tabular-nums">{{ card.line_count }}</div>
        </div>
      </div>
      <UiButton class="w-full justify-center" :class="density === 'roomy' ? 'h-14 text-base' : ''" :disabled="busy" @click="$emit('action', card.is_delivery ? 'dispatch' : 'complete')">
        <Icon :name="`lucide:${card.fulfillment_icon}`" class="size-5" />
        {{ card.is_delivery ? "Despachar pedido" : "Entregar pedido" }}
      </UiButton>
    </div>
  </article>
</template>
