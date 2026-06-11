<script setup lang="ts">
// A prep-station ticket card (Arc 2 render). Status color is FUNCTIONAL (timer
// urgency = left accent + timer chip); the chrome stays neutral. Emits the
// operator gestures; the write-side (POST) is wired in Arc 3.
import type { KDSTicketProjection } from "~/types/kds";
import { elapsedLabel, ticketTone, toneAccent } from "~/presentation/board";

const props = defineProps<{ ticket: KDSTicketProjection; busy?: boolean }>();
defineEmits<{ checkItem: [index: number, checked: boolean]; done: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const accent = computed(() => toneAccent(tone.value));
const timerClasses = computed(() => {
  if (tone.value === "late") return "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400";
  if (tone.value === "warning") return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400";
  return "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-500";
});
</script>

<template>
  <article class="flex flex-col overflow-hidden rounded-md border border-l-4 bg-card" :class="accent">
    <!-- header: order ref + timer -->
    <div class="flex items-start justify-between gap-3 border-b p-4">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon v-if="ticket.channel_icon" :name="`lucide:${ticket.channel_icon}`" class="size-3.5" />
          <Icon v-if="ticket.fulfillment_icon" :name="`lucide:${ticket.fulfillment_icon}`" class="size-3.5" />
          <span>{{ ticket.created_at_display }}</span>
        </div>
        <h3 class="truncate text-2xl font-bold tabular-nums leading-tight">{{ ticket.order_ref }}</h3>
        <p v-if="ticket.customer_name" class="mt-0.5 truncate text-sm font-medium text-muted-foreground">
          {{ ticket.customer_name }}
        </p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold tabular-nums" :class="timerClasses">
        <Icon name="lucide:timer" class="size-3.5" />
        {{ elapsedLabel(ticket.elapsed_seconds) }}
      </span>
    </div>

    <!-- items -->
    <div class="grid gap-2 p-3">
      <button
        v-for="(item, idx) in ticket.items"
        :key="idx"
        type="button"
        class="flex items-start justify-between gap-3 rounded-md border bg-background p-3 text-left transition hover:bg-accent disabled:opacity-60"
        :disabled="busy"
        @click="$emit('checkItem', idx, !item.checked)"
      >
        <span class="min-w-0">
          <span class="block text-base font-bold leading-snug">{{ item.qty }}× {{ item.name }}</span>
          <span class="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span v-if="item.notes">{{ item.notes }}</span>
            <span v-if="item.stock_warning" class="font-semibold text-red-600 dark:text-red-400">{{ item.stock_warning }}</span>
          </span>
        </span>
        <Icon
          :name="item.checked ? 'lucide:check-circle-2' : 'lucide:circle'"
          class="size-5 shrink-0"
          :class="item.checked ? 'text-green-600 dark:text-green-500' : 'text-muted-foreground'"
        />
      </button>

      <UiButton
        :variant="ticket.all_checked ? 'default' : 'outline'"
        class="w-full justify-center"
        :disabled="busy"
        @click="$emit('done')"
      >
        <Icon name="lucide:check-check" class="size-4" />
        Finalizar pedido
      </UiButton>
    </div>
  </article>
</template>
