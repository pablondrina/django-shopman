<script setup lang="ts">
// One order card in the board. Glanceable: ref + timer up top, customer + items in
// the middle, payment/total, then the pre-resolved affordances as buttons. Status
// color is functional; chrome neutral. Tapping the ref opens the detail page.
import type { OrderCardProjection } from "~/types/orders";
import {
  cardAffordances,
  confirmationRemainingLabel,
  lucideIcon,
  splitRef,
  statusTone,
  timerChip,
  timerTone,
  toneBadge,
  elapsedLabel,
  type AffordanceRef,
} from "~/presentation/board";

const props = defineProps<{ card: OrderCardProjection; busy?: boolean; error?: string; selected?: boolean }>();
const emit = defineEmits<{
  (e: "action", ref: AffordanceRef): void;
  (e: "dismiss-error" | "toggle-select" | "toggle-assign"): void;
}>();

const code = computed(() => splitRef(props.card.ref));
const affordances = computed(() => cardAffordances(props.card));
const tTone = computed(() => timerTone(props.card.timer_class));

// Countdown do prazo da confirmação otimista (só em cards com timer agendado).
// Usa o relógio compartilhado (um só interval no board, não um por card).
const nowMs = useNowTick();
const confirmationLeft = computed(() =>
  confirmationRemainingLabel(props.card.confirmation_deadline_iso, nowMs.value),
);

function buttonClass(priority: string): string {
  if (priority === "primary")
    return "bg-primary text-primary-foreground hover:bg-primary/90 border-transparent";
  if (priority === "danger")
    return "border-destructive/40 text-destructive hover:bg-destructive/10 dark:text-orange-300";
  return "border-border hover:bg-accent";
}
</script>

<template>
  <!-- foco: pedidos NOVOS (aguardando confirmar/recusar) ganham um filete âmbar à
       esquerda — a decisão pendente do operador salta à vista sem poluir o resto. -->
  <article
    class="flex flex-col gap-2.5 rounded-lg border bg-card p-3.5 transition hover:border-primary/40"
    :class="[
      selected ? 'border-primary ring-1 ring-primary' : '',
      card.can_confirm && !selected ? 'border-l-2 border-l-warning' : '',
    ]"
  >
    <!-- ref + timer -->
    <div class="flex items-start gap-2">
      <button
        type="button"
        class="mt-0.5 grid size-4 shrink-0 place-items-center rounded border transition"
        :class="selected ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'"
        :aria-label="selected ? 'Desmarcar pedido' : 'Selecionar pedido'"
        :aria-pressed="selected"
        @click="emit('toggle-select')"
      >
        <Icon v-if="selected" name="lucide:check" class="size-3" />
      </button>
      <NuxtLink :to="`/${card.ref}`" class="group min-w-0" :aria-label="`Abrir pedido ${card.ref}`">
        <span class="flex items-center gap-1.5">
          <Icon :name="`lucide:${lucideIcon(card.channel_icon)}`" class="size-3.5 shrink-0 text-muted-foreground" />
          <span class="truncate text-xs text-muted-foreground">{{ code.prefix }}</span>
        </span>
        <span class="block truncate text-lg font-bold leading-tight tabular-nums group-hover:underline">{{ code.code }}</span>
      </NuxtLink>
      <button
        type="button"
        class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium transition"
        :class="card.assigned_operator ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'"
        :aria-label="card.assigned_operator ? `Atendido por ${card.assigned_operator} — liberar` : 'Atender este pedido'"
        :title="card.assigned_operator ? `${card.assigned_operator} — liberar` : 'Atender'"
        @click="emit('toggle-assign')"
      >
        <Icon :name="card.assigned_operator ? 'lucide:user-check' : 'lucide:user-plus'" class="size-3.5" />
        <span v-if="card.assigned_operator" class="max-w-20 truncate">{{ card.assigned_operator }}</span>
      </button>
      <span
        class="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums"
        :class="timerChip(tTone)"
      >
        <Icon name="lucide:clock" class="size-3" />
        {{ elapsedLabel(card.elapsed_seconds) }}
      </span>
      <span
        v-if="confirmationLeft"
        class="inline-flex shrink-0 items-center gap-1 rounded-md border border-warning/50 bg-warning/10 px-2 py-0.5 text-xs font-semibold tabular-nums text-amber-700 dark:text-amber-400"
        :title="card.confirmation_action === 'cancel' ? 'Cancela automaticamente ao vencer' : 'Confirma automaticamente ao vencer'"
        role="timer"
        aria-live="off"
      >
        <Icon name="lucide:hourglass" class="size-3" />
        {{ confirmationLeft }}
      </span>
    </div>

    <!-- customer + fulfillment -->
    <div class="min-w-0">
      <p class="truncate text-sm font-medium">{{ card.customer_name || "Sem cliente" }}</p>
      <p class="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
        <Icon :name="`lucide:${lucideIcon(card.fulfillment_icon)}`" class="size-3.5 shrink-0" />
        {{ card.fulfillment_label }}
        <!-- corrida externa (Machine): estado do entregador direto no card -->
        <span v-if="card.courier_status_label" class="inline-flex items-center gap-1 truncate">
          · <Icon name="lucide:bike" class="size-3.5 shrink-0" /> {{ card.courier_status_label }}
        </span>
      </p>
    </div>

    <!-- items -->
    <p class="line-clamp-2 text-sm text-muted-foreground">{{ card.items_summary }}</p>

    <!-- status + payment + total -->
    <div class="flex flex-wrap items-center gap-1.5 text-xs">
      <span class="inline-flex items-center rounded-md border px-2 py-0.5 font-medium" :class="toneBadge(statusTone(card.status))">
        {{ card.status_label }}
      </span>
      <!-- agendado: pedido combinado para data futura -->
      <span
        v-if="card.is_preorder"
        class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-medium text-muted-foreground"
        data-preorder-badge
      >
        <Icon name="lucide:calendar-clock" class="size-3" />
        Agendado{{ card.commitment_date_display ? ` · ${card.commitment_date_display}` : "" }}
      </span>
      <span
        v-if="card.payment_method_label"
        class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-muted-foreground"
        :class="card.payment_pending ? 'border-warning/40 text-amber-700 dark:text-amber-300' : 'border-border'"
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

    <!-- action error: the backend's specific reason, inline and persistent -->
    <div
      v-if="error"
      class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive dark:text-orange-300"
      role="alert"
    >
      <Icon name="lucide:alert-triangle" class="mt-px size-3.5 shrink-0" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <button type="button" class="shrink-0 rounded p-0.5 transition hover:bg-destructive/20" aria-label="Dispensar aviso" @click="emit('dismiss-error')">
        <Icon name="lucide:x" class="size-3.5" />
      </button>
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
