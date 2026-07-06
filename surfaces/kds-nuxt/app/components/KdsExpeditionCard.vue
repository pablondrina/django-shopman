<script setup lang="ts">
// An expedition (dispatch) board card — alinhado à gramática do card de preparo:
// código herói, superfície neutra (cor só onde tem significado; aqui não há SLA, e
// despacho/balcão é distinguido pelo ÍCONE, não por cor), meta enxuta e a ação
// principal em neutro INVERTIDO (despachar/entregar). Densidade-aware.
import type { KDSExpeditionCardProjection } from "~/types/kds";
import type { KDSDensity } from "~/components/KdsTicketCard.vue";
import { lucideIcon, splitRef } from "~/presentation/board";

const props = withDefaults(
  defineProps<{ card: KDSExpeditionCardProjection; density?: KDSDensity }>(),
  { density: "cozy" },
);
defineEmits<{ action: [action: "dispatch" | "complete"] }>();

const ref_ = computed(() => splitRef(props.card.order_ref));
// Conferência de itens na expedição: colapsado por padrão (board scannable),
// expande pra conferir o que entregar/despachar.
const showItems = ref(false);
const d = computed(
  () =>
    ({
      compact: {
        code: "text-xl",
        inset: "px-3",
        padT: "pt-3",
        padB: "pb-3",
        fin: "h-10",
      },
      cozy: {
        code: "text-3xl",
        inset: "px-4",
        padT: "pt-4",
        padB: "pb-4",
        fin: "h-11",
      },
      roomy: {
        code: "text-4xl",
        inset: "px-5",
        padT: "pt-5",
        padB: "pb-5",
        fin: "h-12",
      },
    })[props.density],
);
</script>

<template>
  <article
    class="flex flex-col gap-3 overflow-hidden rounded-md border bg-card shadow-sm"
    :class="[d.inset, d.padT, d.padB]"
  >
    <!-- identidade: código herói + badge neutro de despacho/balcão -->
    <div class="flex items-start justify-between gap-2.5">
      <div class="min-w-0">
        <div
          class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
        >
          <Icon
            v-if="card.channel_icon"
            :name="`lucide:${lucideIcon(card.channel_icon)}`"
            class="size-3.5 shrink-0"
          />
          <span class="truncate">{{ card.fulfillment_label }}</span>
        </div>
        <p
          class="whitespace-nowrap font-extrabold tracking-tight tabular-nums leading-none"
          :class="d.code"
        >
          {{ ref_.code }}
        </p>
        <p
          v-if="card.customer_name"
          class="mt-1.5 truncate text-sm font-medium text-foreground/80"
        >
          {{ card.customer_name }}
        </p>
      </div>
      <span
        class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold"
      >
        <Icon
          :name="`lucide:${lucideIcon(card.fulfillment_icon)}`"
          class="size-4 shrink-0"
        />
        {{ card.is_delivery ? "Despacho" : "Balcão" }}
      </span>
    </div>

    <!-- meta: VOLUMES em destaque (o que conferir/entregar) + linhas · total -->
    <div class="flex items-end justify-between gap-3">
      <div class="flex items-baseline gap-1.5">
        <span class="text-3xl font-extrabold tabular-nums leading-none">{{
          card.units_count
        }}</span>
        <span class="text-sm font-medium text-muted-foreground">{{
          card.units_count === "1" ? "volume" : "volumes"
        }}</span>
      </div>
      <div class="text-right text-sm leading-tight">
        <div class="text-muted-foreground">
          {{ card.line_count }} {{ card.line_count === 1 ? "linha" : "linhas" }}
        </div>
        <div class="font-bold tabular-nums">{{ card.total_display }}</div>
      </div>
    </div>

    <!-- conferência de itens (qty × nome): toggle pra manter o board enxuto -->
    <div v-if="card.items.length" class="border-t pt-2">
      <button
        type="button"
        class="flex w-full items-center justify-between gap-2 rounded-md px-1 py-1 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        :aria-expanded="showItems"
        @click="showItems = !showItems"
      >
        <span class="inline-flex items-center gap-1.5">
          <Icon name="lucide:list" class="size-4 shrink-0" />
          {{ showItems ? "Ocultar itens" : `Ver itens (${card.line_count})` }}
        </span>
        <Icon
          :name="showItems ? 'lucide:chevron-up' : 'lucide:chevron-down'"
          class="size-4 shrink-0"
        />
      </button>
      <ul v-if="showItems" class="mt-1 space-y-1">
        <li
          v-for="(item, idx) in card.items"
          :key="idx"
          class="flex items-baseline gap-2.5 text-sm"
        >
          <span class="min-w-[2.5ch] shrink-0 text-right font-bold tabular-nums"
            >{{ item.qty }}×</span
          >
          <span class="min-w-0 flex-1 truncate font-medium">{{
            item.name
          }}</span>
        </li>
      </ul>
    </div>

    <!-- ação principal: neutro invertido -->
    <button
      type="button"
      class="mt-auto flex w-full items-center justify-center gap-2 rounded-md bg-foreground font-semibold text-background transition hover:bg-foreground/90 active:scale-[0.99]"
      :class="d.fin"
      @click="$emit('action', card.is_delivery ? 'dispatch' : 'complete')"
    >
      <Icon
        :name="`lucide:${lucideIcon(card.fulfillment_icon)}`"
        class="size-4 shrink-0"
      />
      {{ card.is_delivery ? "Despachar pedido" : "Entregar pedido" }}
    </button>
  </article>
</template>
