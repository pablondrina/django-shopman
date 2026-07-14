<script setup lang="ts">
// Ticket detail modal — opened from the minimal card. Holds the work: every item
// (with modifications prominent), tap to check, and finalize. Checked items dim
// (minimalist — no noisy strikethrough, per Pablo). Dark, distance-friendly.
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  itemProgress,
  lucideIcon,
  slaPercent,
  splitRef,
  targetLabel,
  ticketTone,
  toneBar,
  toneTimer,
} from "~/presentation/board";

const props = defineProps<{
  open: boolean;
  ticket: KDSTicketProjection | null;
}>();
defineEmits<{
  "update:open": [boolean];
  checkItem: [index: number, checked: boolean];
  done: [];
}>();

const ref_ = computed(() =>
  props.ticket ? splitRef(props.ticket.order_ref) : { prefix: "", code: "" },
);
const tone = computed(() =>
  props.ticket ? ticketTone(props.ticket.timer_class) : "ok",
);
const timerClasses = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const fill = computed(() =>
  props.ticket
    ? slaPercent(props.ticket.elapsed_seconds, props.ticket.target_seconds)
    : 0,
);
const progress = computed(() =>
  props.ticket ? itemProgress(props.ticket.items) : { done: 0, total: 0 },
);
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent
      v-if="ticket"
      class="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg"
    >
      <UiDialogTitle class="sr-only"
        >Pedido {{ ticket.order_ref }}</UiDialogTitle
      >
      <UiDialogDescription class="sr-only">
        {{ ticket.customer_name || "Sem cliente" }} — {{ progress.done }} de
        {{ progress.total }} itens prontos.
      </UiDialogDescription>
      <!-- header -->
      <div class="border-b">
        <div class="flex items-start justify-between gap-3 p-5">
          <div class="min-w-0">
            <p
              class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground"
            >
              <Icon
                v-if="ticket.channel_icon"
                :name="`lucide:${lucideIcon(ticket.channel_icon)}`"
                class="size-3.5"
              />
              <Icon
                v-if="ticket.fulfillment_icon"
                :name="`lucide:${lucideIcon(ticket.fulfillment_icon)}`"
                class="size-3.5"
              />
              <span class="tabular-nums"
                >{{ ref_.prefix }}{{ ticket.created_at_display }}</span
              >
            </p>
            <p
              class="break-words text-4xl font-extrabold tracking-tight tabular-nums leading-none"
            >
              {{ ref_.code }}
            </p>
            <p
              v-if="ticket.customer_name"
              class="mt-1.5 truncate text-sm font-medium text-foreground/80"
            >
              {{ ticket.customer_name }}
            </p>
          </div>
          <div
            class="flex shrink-0 flex-col items-end gap-0.5 rounded-md border px-3 py-2 text-right"
            :class="timerClasses"
          >
            <span
              class="flex items-center gap-1 text-3xl font-bold tabular-nums leading-none"
            >
              <Icon name="lucide:timer" class="size-5 opacity-70" />
              {{ elapsedLabel(ticket.elapsed_seconds) }}
            </span>
            <span
              v-if="ticket.target_seconds"
              class="text-xs font-medium uppercase tracking-wide opacity-60"
            >
              alvo {{ targetLabel(ticket.target_seconds) }}
            </span>
          </div>
        </div>
        <!-- time-to-SLA fill bar -->
        <div class="h-1.5 w-full bg-white/5" aria-hidden="true">
          <div
            class="h-full rounded-r-full transition-[width] duration-500"
            :class="barFill"
            :style="{ width: `${fill}%` }"
          />
        </div>
      </div>

      <!-- notas do pedido: diretiva de preparo do operador (cozinha) + nota do cliente
           (checkout). Aqui há espaço — mostra completo (sem clamp). -->
      <div
        v-if="ticket.kitchen_note || ticket.customer_note"
        class="flex flex-col gap-2 border-b p-4"
      >
        <p
          v-if="ticket.kitchen_note"
          class="flex items-start gap-2 rounded-md border border-foreground/20 bg-muted/60 px-3 py-2 text-sm font-medium leading-snug"
        >
          <Icon name="lucide:chef-hat" class="mt-0.5 size-4 shrink-0 opacity-70" />
          <span class="min-w-0 whitespace-pre-wrap">{{ ticket.kitchen_note }}</span>
        </p>
        <p
          v-if="ticket.customer_note"
          class="flex items-start gap-2 rounded-md border px-3 py-2 text-sm text-muted-foreground leading-snug"
        >
          <Icon name="lucide:user" class="mt-0.5 size-4 shrink-0" />
          <span class="min-w-0 whitespace-pre-wrap">{{ ticket.customer_note }}</span>
        </p>
      </div>

      <!-- items (tap to check; mods prominent; checked = dim, no strikethrough) -->
      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <div
          class="flex items-center justify-between px-1 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"
        >
          <span>Itens</span>
          <span class="tabular-nums"
            >{{ progress.done }}/{{ progress.total }}</span
          >
        </div>
        <ul class="flex flex-col">
          <li v-for="(item, idx) in ticket.items" :key="idx">
            <button
              type="button"
              class="flex w-full items-start justify-between gap-3 rounded-md p-3 text-left transition hover:bg-accent/50 active:scale-[0.99]"
              @click="$emit('checkItem', idx, !item.checked)"
            >
              <span class="min-w-0 flex-1">
                <span
                  class="relative flex items-center gap-2 text-lg leading-snug transition-colors duration-200"
                  :class="item.checked ? 'text-muted-foreground' : 'font-bold'"
                >
                  <span class="shrink-0 tabular-nums">{{ item.qty }}×</span>
                  <span class="min-w-0 flex-1 truncate">{{ item.name }}</span>
                  <span
                    v-if="item.checked"
                    aria-hidden="true"
                    class="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-muted-foreground/50"
                  />
                </span>
                <span
                  v-if="item.notes"
                  class="mt-1.5 flex"
                  :class="item.checked ? 'opacity-50' : ''"
                >
                  <span
                    class="inline-flex min-w-0 max-w-full items-center rounded border bg-muted px-2 py-0.5 text-sm font-medium text-muted-foreground"
                  >
                    <span class="truncate">{{ item.notes }}</span>
                  </span>
                </span>
                <span
                  v-if="item.stock_warning"
                  class="mt-1.5 flex"
                  :class="item.checked ? 'opacity-50' : ''"
                >
                  <span
                    class="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded border bg-muted px-2 py-0.5 text-sm font-semibold text-foreground"
                  >
                    <Icon
                      name="lucide:triangle-alert"
                      class="size-3.5 shrink-0"
                    />
                    <span class="truncate">{{ item.stock_warning }}</span>
                  </span>
                </span>
              </span>
              <Icon
                name="lucide:check"
                class="size-6 shrink-0 transition-colors duration-200"
                :class="
                  item.checked ? 'text-foreground' : 'text-muted-foreground/30'
                "
              />
            </button>
          </li>
        </ul>
      </div>

      <!-- finalize — neutro (preto no dark); tique verde é o acento ao ficar pronto -->
      <div class="shrink-0 border-t p-4">
        <button
          type="button"
          class="flex h-14 w-full items-center justify-center gap-2 rounded-md border text-base font-semibold transition active:scale-[0.99]"
          :class="
            ticket.all_checked
              ? 'border-border bg-background text-foreground hover:bg-accent'
              : 'border-border/60 text-muted-foreground hover:bg-accent hover:text-foreground'
          "
          @click="$emit('done')"
        >
          <Icon
            name="lucide:check-check"
            class="size-5"
            :class="ticket.all_checked ? 'text-success' : ''"
          />
          {{
            ticket.all_checked ? "Finalizar — tudo pronto" : "Finalizar pedido"
          }}
        </button>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
