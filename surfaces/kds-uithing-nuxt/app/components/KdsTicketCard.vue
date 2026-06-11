<script setup lang="ts">
// A prep-station ticket card (KDS-refined). Best-practice driven (docs/research/
// kds-benchmarks): distance-reading typography that scales with the chosen density,
// modifications shown PROMINENTLY (anti prep-error), functional color used
// sparingly (the time semaphore — red reserved for late). Tuned for a dark,
// back-of-house screen.
import type { KDSTicketProjection } from "~/types/kds";
import { elapsedLabel, ticketTone, toneAccent } from "~/presentation/board";

export type KDSDensity = "compact" | "cozy" | "roomy";

const props = withDefaults(
  defineProps<{ ticket: KDSTicketProjection; busy?: boolean; density?: KDSDensity }>(),
  { density: "cozy" },
);
defineEmits<{ checkItem: [index: number, checked: boolean]; done: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const accent = computed(() => toneAccent(tone.value));
const timerClasses = computed(() => {
  if (tone.value === "late") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (tone.value === "warning") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-white/10 bg-white/5 text-muted-foreground";
});

// Density → distance-reading type scale (the adjustable-text-size best practice).
const refSize = computed(() => ({ compact: "text-2xl", cozy: "text-3xl", roomy: "text-4xl" }[props.density]));
const itemSize = computed(() => ({ compact: "text-base", cozy: "text-lg", roomy: "text-xl" }[props.density]));
const pad = computed(() => ({ compact: "p-3", cozy: "p-4", roomy: "p-5" }[props.density]));
</script>

<template>
  <article class="flex flex-col overflow-hidden rounded-md border border-l-4 bg-card" :class="accent">
    <!-- header: order ref + timer -->
    <div class="flex items-start justify-between gap-3 border-b" :class="pad">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon v-if="ticket.channel_icon" :name="`lucide:${ticket.channel_icon}`" class="size-3.5" />
          <Icon v-if="ticket.fulfillment_icon" :name="`lucide:${ticket.fulfillment_icon}`" class="size-3.5" />
          <span class="tabular-nums">{{ ticket.created_at_display }}</span>
        </div>
        <h3 class="truncate font-bold tabular-nums leading-none" :class="refSize">{{ ticket.order_ref }}</h3>
        <p v-if="ticket.customer_name" class="mt-1 truncate text-sm font-medium text-muted-foreground">
          {{ ticket.customer_name }}
        </p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-sm font-bold tabular-nums" :class="timerClasses">
        <Icon name="lucide:timer" class="size-4" />
        {{ elapsedLabel(ticket.elapsed_seconds) }}
      </span>
    </div>

    <!-- items: large + modifications PROMINENT -->
    <div class="grid gap-2" :class="pad">
      <button
        v-for="(item, idx) in ticket.items"
        :key="idx"
        type="button"
        class="flex items-start justify-between gap-3 rounded-md border bg-background/40 p-3 text-left transition hover:bg-accent disabled:opacity-60"
        :class="item.checked ? 'opacity-50' : ''"
        :disabled="busy"
        @click="$emit('checkItem', idx, !item.checked)"
      >
        <span class="min-w-0">
          <span class="block font-bold leading-tight" :class="[itemSize, item.checked ? 'line-through' : '']">
            {{ item.qty }}× {{ item.name }}
          </span>
          <!-- modifications: bold amber line (prevents prep errors) -->
          <span v-if="item.notes" class="mt-1 block text-sm font-semibold text-amber-300">
            ↳ {{ item.notes }}
          </span>
          <span v-if="item.stock_warning" class="mt-0.5 block text-sm font-bold text-red-400">
            ⚠ {{ item.stock_warning }}
          </span>
        </span>
        <Icon
          :name="item.checked ? 'lucide:check-circle-2' : 'lucide:circle'"
          class="size-6 shrink-0"
          :class="item.checked ? 'text-green-400' : 'text-muted-foreground'"
        />
      </button>

      <UiButton
        :variant="ticket.all_checked ? 'default' : 'outline'"
        class="w-full justify-center"
        :class="density === 'roomy' ? 'h-14 text-base' : ''"
        :disabled="busy"
        @click="$emit('done')"
      >
        <Icon name="lucide:check-check" class="size-5" />
        Finalizar pedido
      </UiButton>
    </div>
  </article>
</template>
