<script setup lang="ts">
// A started-WorkOrder card on the production live floor. Glanceable: recipe +
// quantity + the current manual/timed step with a progress bar tinted by urgency.
// Affordances (advance step / finish / void) come pre-resolved from the projection
// via kdsCardAffordances; the card only emits intent — the page owns the dialogs.
import type { FloorAffordanceRef } from "~/presentation/production";
import {
  elapsedLabel,
  kdsCardAffordances,
  splitRef,
  timerBar,
  timerChip,
  timerTone,
} from "~/presentation/production";
import type { ProductionKDSCardProjection } from "~/types/production";

const props = defineProps<{ card: ProductionKDSCardProjection; busy?: boolean }>();
const emit = defineEmits<{ action: [ref: FloorAffordanceRef] }>();

const tone = computed(() => timerTone(props.card.timer_class));
const code = computed(() => splitRef(props.card.ref).code);
const affordances = computed(() => kdsCardAffordances(props.card));

const stepLabel = computed(() => {
  const c = props.card;
  if (c.total_steps > 0 && c.current_step_index) {
    return `${c.current_step_index}/${c.total_steps} · ${c.current_step_name || c.current_step}`;
  }
  return c.current_step || "Produção";
});

function priorityClass(priority: "primary" | "secondary" | "danger"): string {
  if (priority === "primary") {
    return "border-transparent bg-primary text-primary-foreground hover:bg-primary/90";
  }
  if (priority === "danger") {
    return "border-border text-red-700 hover:bg-red-500/10 dark:text-red-300";
  }
  return "border-border hover:bg-accent";
}
</script>

<template>
  <article
    class="flex flex-col gap-3 rounded-lg border bg-card p-3 shadow-sm transition"
    :class="busy ? 'opacity-60' : ''"
  >
    <header class="flex items-start gap-2">
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline gap-1.5">
          <span class="text-base font-bold leading-tight">{{ card.output_sku }}</span>
          <span class="shrink-0 text-xs text-muted-foreground">#{{ code }}</span>
        </div>
        <p class="truncate text-xs text-muted-foreground">{{ card.recipe_name }}</p>
      </div>
      <span
        class="shrink-0 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums"
        :class="timerChip(tone)"
        :title="`Iniciado ${card.started_at_display}`"
      >
        {{ elapsedLabel(card.elapsed_seconds) }}
      </span>
    </header>

    <div class="flex items-center gap-3 text-sm">
      <span class="rounded-md bg-muted px-2 py-1 font-bold tabular-nums">{{ card.started_qty }} un.</span>
      <span v-if="card.position_ref" class="inline-flex items-center gap-1 text-muted-foreground">
        <Icon name="lucide:map-pin" class="size-3.5" />{{ card.position_ref }}
      </span>
      <span v-if="card.operator_ref" class="inline-flex items-center gap-1 truncate text-muted-foreground">
        <Icon name="lucide:user" class="size-3.5" />{{ card.operator_ref }}
      </span>
      <span
        v-if="card.order_refs.length"
        class="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-1.5 py-0.5 text-xs font-medium text-primary"
        :title="`Pedidos aguardando este lote: ${card.order_refs.join(', ')}`"
      >
        <Icon name="lucide:shopping-bag" class="size-3" />
        {{ card.order_refs.length }} pedido{{ card.order_refs.length > 1 ? "s" : "" }}
      </span>
    </div>

    <div class="flex flex-col gap-1">
      <div class="flex items-center justify-between text-xs">
        <span class="truncate font-medium">{{ stepLabel }}</span>
        <span v-if="card.next_step_name" class="shrink-0 text-muted-foreground">→ {{ card.next_step_name }}</span>
      </div>
      <div class="h-1.5 overflow-hidden rounded-full bg-muted">
        <div class="h-full rounded-full transition-all" :class="timerBar(tone)" :style="{ width: `${card.step_progress_pct}%` }" />
      </div>
    </div>

    <footer class="flex flex-wrap gap-1.5">
      <button
        v-for="aff in affordances"
        :key="aff.ref"
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition disabled:opacity-50"
        :class="priorityClass(aff.priority)"
        @click="emit('action', aff.ref)"
      >
        <Icon :name="aff.icon" class="size-4" />
        {{ aff.label }}
      </button>
    </footer>
  </article>
</template>
