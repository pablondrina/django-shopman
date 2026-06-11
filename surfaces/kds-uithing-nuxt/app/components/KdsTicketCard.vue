<script setup lang="ts">
// A prep-station ticket card — MINIMAL/glanceable (Pablo's direction): the CODE
// the kitchen calls is the hero (channel/date prefix recedes), plus timer,
// customer and an item-progress hint. Tapping opens the detail modal (items +
// modifications + finalize). Functional color used sparingly (time semaphore).
import type { KDSTicketProjection } from "~/types/kds";
import { elapsedLabel, itemProgress, splitRef, ticketTone, toneAccent } from "~/presentation/board";

export type KDSDensity = "compact" | "cozy" | "roomy";

const props = withDefaults(
  defineProps<{ ticket: KDSTicketProjection; busy?: boolean; density?: KDSDensity }>(),
  { density: "cozy" },
);
defineEmits<{ open: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const accent = computed(() => toneAccent(tone.value));
const ref_ = computed(() => splitRef(props.ticket.order_ref));
const progress = computed(() => itemProgress(props.ticket.items));
const timerClasses = computed(() => {
  if (tone.value === "late") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (tone.value === "warning") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-white/10 bg-white/5 text-muted-foreground";
});
const codeSize = computed(() => ({ compact: "text-2xl", cozy: "text-3xl", roomy: "text-4xl" }[props.density]));
const pad = computed(() => ({ compact: "p-3", cozy: "p-4", roomy: "p-5" }[props.density]));
</script>

<template>
  <button
    type="button"
    class="flex w-full flex-col gap-3 overflow-hidden rounded-md border border-l-4 bg-card text-left transition hover:bg-accent active:translate-y-px"
    :class="[accent, pad]"
    @click="$emit('open')"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon v-if="ticket.channel_icon" :name="`lucide:${ticket.channel_icon}`" class="size-3.5" />
          <Icon v-if="ticket.fulfillment_icon" :name="`lucide:${ticket.fulfillment_icon}`" class="size-3.5" />
          <span class="truncate tabular-nums">{{ ref_.prefix }}{{ ticket.created_at_display }}</span>
        </div>
        <p class="break-words font-bold tabular-nums leading-none" :class="codeSize">{{ ref_.code }}</p>
        <p v-if="ticket.customer_name" class="mt-1 truncate text-sm font-medium text-muted-foreground">
          {{ ticket.customer_name }}
        </p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-sm font-bold tabular-nums" :class="timerClasses">
        <Icon name="lucide:timer" class="size-4" />
        {{ elapsedLabel(ticket.elapsed_seconds) }}
      </span>
    </div>

    <!-- progress hint (the items live in the modal; this keeps the card glanceable) -->
    <div class="flex items-center justify-between gap-2 text-sm text-muted-foreground">
      <span class="inline-flex items-center gap-1.5 tabular-nums">
        <Icon :name="ticket.all_checked ? 'lucide:check-circle-2' : 'lucide:utensils'" class="size-4" :class="ticket.all_checked ? 'text-green-400' : ''" />
        <span :class="ticket.all_checked ? 'text-green-400 font-semibold' : ''">
          {{ ticket.all_checked ? "Tudo pronto" : `${progress.done}/${progress.total} itens` }}
        </span>
      </span>
      <Icon name="lucide:maximize-2" class="size-4 opacity-50" />
    </div>
  </button>
</template>
