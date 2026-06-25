<script setup lang="ts">
// One order card in the board. Glanceable: ref + timer up top, customer + items in
// the middle, payment/total, then the pre-resolved affordances as buttons. Status
// color is functional; chrome neutral. Tapping the ref opens the detail page.
import type { OrderCardProjection } from "~/types/orders";
import {
  cardAffordances,
  lucideIcon,
  splitRef,
  statusTone,
  timerChip,
  timerTone,
  toneBadge,
  elapsedLabel,
  type AffordanceRef,
} from "~/presentation/board";

const props = defineProps<{ card: OrderCardProjection; busy?: boolean }>();
const emit = defineEmits<{ (e: "action", ref: AffordanceRef): void }>();

const code = computed(() => splitRef(props.card.ref));
const affordances = computed(() => cardAffordances(props.card));
const tTone = computed(() => timerTone(props.card.timer_class));

function buttonClass(priority: string): string {
  if (priority === "primary")
    return "bg-primary text-primary-foreground hover:bg-primary/90 border-transparent";
  if (priority === "danger")
    return "border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-300";
  return "border-border hover:bg-accent";
}
</script>

<template>
  <article class="flex flex-col gap-2.5 rounded-lg border bg-card p-3.5 transition hover:border-primary/40">
    <!-- ref + timer -->
    <div class="flex items-start justify-between gap-2">
      <NuxtLink :to="`/${card.ref}`" class="group min-w-0" :aria-label="`Abrir pedido ${card.ref}`">
        <span class="flex items-center gap-1.5">
          <Icon :name="`lucide:${lucideIcon(card.channel_icon)}`" class="size-3.5 shrink-0 text-muted-foreground" />
          <span class="truncate text-xs text-muted-foreground">{{ code.prefix }}</span>
        </span>
        <span class="block truncate text-lg font-bold leading-tight tabular-nums group-hover:underline">{{ code.code }}</span>
      </NuxtLink>
      <span
        class="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums"
        :class="timerChip(tTone)"
      >
        <Icon name="lucide:clock" class="size-3" />
        {{ elapsedLabel(card.elapsed_seconds) }}
      </span>
    </div>

    <!-- customer + fulfillment -->
    <div class="min-w-0">
      <p class="truncate text-sm font-medium">{{ card.customer_name || "Sem cliente" }}</p>
      <p class="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
        <Icon :name="`lucide:${lucideIcon(card.fulfillment_icon)}`" class="size-3.5 shrink-0" />
        {{ card.fulfillment_label }}
      </p>
    </div>

    <!-- items -->
    <p class="line-clamp-2 text-sm text-muted-foreground">{{ card.items_summary }}</p>

    <!-- status + payment + total -->
    <div class="flex flex-wrap items-center gap-1.5 text-xs">
      <span class="inline-flex items-center rounded-md border px-2 py-0.5 font-medium" :class="toneBadge(statusTone(card.status))">
        {{ card.status_label }}
      </span>
      <span
        v-if="card.payment_method_label"
        class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-muted-foreground"
        :class="card.payment_pending ? 'border-amber-500/40 text-amber-700 dark:text-amber-300' : 'border-border'"
      >
        <Icon :name="card.payment_pending ? 'lucide:hourglass' : 'lucide:wallet'" class="size-3" />
        {{ card.payment_method_label }}
      </span>
      <span class="ml-auto text-sm font-bold tabular-nums">{{ card.total_display }}</span>
    </div>

    <!-- awaiting production -->
    <div v-if="card.awaiting_work_orders.length" class="flex flex-col gap-1">
      <div
        v-for="wo in card.awaiting_work_orders"
        :key="wo.ref"
        class="flex items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 text-xs text-muted-foreground"
      >
        <Icon name="lucide:factory" class="size-3 shrink-0" />
        <span class="truncate">{{ wo.output_sku }} · {{ wo.status_label }}</span>
        <span class="ml-auto tabular-nums">{{ wo.progress_pct }}%</span>
      </div>
    </div>

    <!-- actions -->
    <div v-if="affordances.length" class="flex flex-wrap gap-1.5 pt-0.5">
      <button
        v-for="aff in affordances"
        :key="aff.ref"
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-semibold transition active:scale-[0.98] disabled:opacity-50"
        :class="buttonClass(aff.priority)"
        @click="emit('action', aff.ref)"
      >
        <Icon :name="aff.icon" class="size-3.5" />
        {{ aff.label }}
      </button>
    </div>
  </article>
</template>
