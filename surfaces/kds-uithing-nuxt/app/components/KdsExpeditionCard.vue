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

const ref_ = computed(() => splitRef(props.card.ref));
const d = computed(
  () =>
    ({
      compact: { code: "text-2xl", inset: "px-3", padT: "pt-3", padB: "pb-3", fin: "h-10" },
      cozy: { code: "text-3xl", inset: "px-4", padT: "pt-4", padB: "pb-4", fin: "h-11" },
      roomy: { code: "text-4xl", inset: "px-5", padT: "pt-5", padB: "pb-5", fin: "h-12" },
    })[props.density],
);
</script>

<template>
  <article class="flex flex-col gap-3 overflow-hidden rounded-md border bg-card shadow-sm" :class="[d.inset, d.padT, d.padB]">
    <!-- identidade: código herói + badge neutro de despacho/balcão -->
    <div class="flex items-start justify-between gap-2.5">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">
          <Icon v-if="card.channel_icon" :name="`lucide:${lucideIcon(card.channel_icon)}`" class="size-3.5 shrink-0" />
          <span class="truncate">{{ card.fulfillment_label }}</span>
        </div>
        <p class="whitespace-nowrap font-extrabold tracking-tight tabular-nums leading-none" :class="d.code">{{ ref_.code }}</p>
        <p v-if="card.customer_name" class="mt-1.5 truncate text-sm font-medium text-foreground/80">{{ card.customer_name }}</p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold">
        <Icon :name="`lucide:${lucideIcon(card.fulfillment_icon)}`" class="size-4 shrink-0" />
        {{ card.is_delivery ? "Despacho" : "Balcão" }}
      </span>
    </div>

    <!-- meta: unidades · linhas · total -->
    <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
      <span><strong class="tabular-nums">{{ card.units_count }}</strong> <span class="text-muted-foreground">{{ card.units_count === "1" ? "unidade" : "unidades" }}</span></span>
      <span><strong class="tabular-nums">{{ card.line_count }}</strong> <span class="text-muted-foreground">{{ card.line_count === 1 ? "linha" : "linhas" }}</span></span>
      <span class="ml-auto font-bold tabular-nums">{{ card.total_display }}</span>
    </div>

    <!-- ação principal: neutro invertido -->
    <button
      type="button"
      class="mt-auto flex w-full items-center justify-center gap-2 rounded-md bg-foreground font-semibold text-background transition hover:bg-foreground/90 active:scale-[0.99]"
      :class="d.fin"
      @click="$emit('action', card.is_delivery ? 'dispatch' : 'complete')"
    >
      <Icon :name="`lucide:${lucideIcon(card.fulfillment_icon)}`" class="size-4 shrink-0" />
      {{ card.is_delivery ? "Despachar pedido" : "Entregar pedido" }}
    </button>
  </article>
</template>
