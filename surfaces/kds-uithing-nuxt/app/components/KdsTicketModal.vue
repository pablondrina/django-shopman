<script setup lang="ts">
// Ticket detail modal — opened from the minimal card. Holds the work: every item
// (with modifications prominent), tap to check, and finalize. Checked items dim
// (minimalist — no noisy strikethrough, per Pablo). Dark, distance-friendly.
import type { KDSTicketProjection } from "~/types/kds";
import { elapsedLabel, splitRef, ticketTone } from "~/presentation/board";

const props = defineProps<{ open: boolean; ticket: KDSTicketProjection | null; busy?: boolean }>();
defineEmits<{ "update:open": [boolean]; checkItem: [index: number, checked: boolean]; done: [] }>();

const ref_ = computed(() => (props.ticket ? splitRef(props.ticket.order_ref) : { prefix: "", code: "" }));
const tone = computed(() => (props.ticket ? ticketTone(props.ticket.timer_class) : "ok"));
const timerClasses = computed(() => {
  if (tone.value === "late") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (tone.value === "warning") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-white/10 bg-white/5 text-muted-foreground";
});
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent v-if="ticket" class="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
      <!-- header -->
      <div class="flex items-start justify-between gap-3 border-b p-5">
        <div class="min-w-0">
          <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon v-if="ticket.channel_icon" :name="`lucide:${ticket.channel_icon}`" class="size-3.5" />
            <Icon v-if="ticket.fulfillment_icon" :name="`lucide:${ticket.fulfillment_icon}`" class="size-3.5" />
            <span class="tabular-nums">{{ ref_.prefix }}{{ ticket.created_at_display }}</span>
          </p>
          <p class="break-words text-3xl font-bold tabular-nums leading-none">{{ ref_.code }}</p>
          <p v-if="ticket.customer_name" class="mt-1 truncate text-sm font-medium text-muted-foreground">{{ ticket.customer_name }}</p>
        </div>
        <span class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-sm font-bold tabular-nums" :class="timerClasses">
          <Icon name="lucide:timer" class="size-4" />
          {{ elapsedLabel(ticket.elapsed_seconds) }}
        </span>
      </div>

      <!-- items (tap to check; mods prominent; checked = dim, no strikethrough) -->
      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <div class="grid gap-2">
          <button
            v-for="(item, idx) in ticket.items"
            :key="idx"
            type="button"
            class="flex items-start justify-between gap-3 rounded-md border bg-background/40 p-3 text-left transition hover:bg-accent disabled:opacity-60"
            :class="item.checked ? 'opacity-45' : ''"
            :disabled="busy"
            @click="$emit('checkItem', idx, !item.checked)"
          >
            <span class="min-w-0">
              <span class="block text-lg font-bold leading-tight">{{ item.qty }}× {{ item.name }}</span>
              <span v-if="item.notes" class="mt-1 block text-sm font-semibold text-amber-300">↳ {{ item.notes }}</span>
              <span v-if="item.stock_warning" class="mt-0.5 block text-sm font-bold text-red-400">⚠ {{ item.stock_warning }}</span>
            </span>
            <Icon
              :name="item.checked ? 'lucide:check-circle-2' : 'lucide:circle'"
              class="size-6 shrink-0"
              :class="item.checked ? 'text-green-400' : 'text-muted-foreground'"
            />
          </button>
        </div>
      </div>

      <!-- finalize -->
      <div class="shrink-0 border-t p-4">
        <UiButton
          :variant="ticket.all_checked ? 'default' : 'outline'"
          class="h-14 w-full justify-center text-base"
          :disabled="busy"
          @click="$emit('done')"
        >
          <Icon name="lucide:check-check" class="size-5" />
          Finalizar pedido
        </UiButton>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
