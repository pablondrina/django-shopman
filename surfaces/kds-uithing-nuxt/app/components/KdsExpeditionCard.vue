<script setup lang="ts">
// An expedition (dispatch) board card. Delivery vs counter is a functional accent
// (info vs success); the action is dispatch or complete. Emits the gesture; the
// POST is wired in Arc 3.
import type { KDSExpeditionCardProjection } from "~/types/kds";

const props = defineProps<{ card: KDSExpeditionCardProjection; busy?: boolean }>();
defineEmits<{ action: [action: "dispatch" | "complete"] }>();

const accent = computed(() => (props.card.is_delivery ? "border-l-cyan-500" : "border-l-green-500"));
</script>

<template>
  <article class="flex flex-col overflow-hidden rounded-md border border-l-4 bg-card" :class="accent">
    <div class="flex items-start justify-between gap-3 border-b p-4">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon v-if="card.channel_icon" :name="`lucide:${card.channel_icon}`" class="size-3.5" />
          <span>{{ card.fulfillment_label }}</span>
        </div>
        <h3 class="truncate text-2xl font-bold tabular-nums leading-tight">{{ card.ref }}</h3>
        <p v-if="card.customer_name" class="mt-0.5 truncate text-sm font-medium text-muted-foreground">{{ card.customer_name }}</p>
      </div>
      <span
        class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold"
        :class="card.is_delivery ? 'border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-400' : 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-500'"
      >
        <Icon :name="`lucide:${card.fulfillment_icon}`" class="size-3.5" />
        {{ card.is_delivery ? "Despacho" : "Balcão" }}
      </span>
    </div>

    <div class="grid gap-3 p-4">
      <div class="grid grid-cols-3 gap-2 text-sm">
        <div>
          <div class="text-xs text-muted-foreground">Cliente</div>
          <div class="truncate font-semibold">{{ card.customer_name || "—" }}</div>
        </div>
        <div>
          <div class="text-xs text-muted-foreground">Unidades</div>
          <div class="font-semibold tabular-nums">{{ card.units_count }}</div>
        </div>
        <div>
          <div class="text-xs text-muted-foreground">Linhas</div>
          <div class="font-semibold tabular-nums">{{ card.line_count }}</div>
        </div>
      </div>
      <UiButton class="w-full justify-center" :disabled="busy" @click="$emit('action', card.is_delivery ? 'dispatch' : 'complete')">
        <Icon :name="`lucide:${card.fulfillment_icon}`" class="size-4" />
        {{ card.is_delivery ? "Despachar pedido" : "Entregar pedido" }}
      </UiButton>
    </div>
  </article>
</template>
