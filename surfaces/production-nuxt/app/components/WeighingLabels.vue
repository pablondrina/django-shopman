<script setup lang="ts">
// Etiquetas de pesagem — SÓ IMPRESSÃO (papel físico, medium ≠ tela). Dois papéis:
//   · CEGAS: código do dia + ingrediente + peso + data, SEM o nome da receita (o
//     colaborador pesa sem correlacionar; o mapa código↔preparo é visão de gestor);
//   · EXPLÍCITAS: a massa pronta se identifica (nome, validade, rendimento, objetivo).
// Os tamanhos aqui são fixos para a etiquetadora, não os papéis tipográficos de tela —
// por isso este componente é allowlistado no guardrail de tipografia (como o PosReceipt).
import type { WeighingTicketProjection } from "~/types/production";

export interface BlindLabel {
  code: string;
  ingredient: string;
  weight: string;
  date: string;
  key: string;
}

defineProps<{
  printMode: "pesagem" | "preparo";
  labels: BlindLabel[];
  tickets: WeighingTicketProjection[];
}>();
</script>

<template>
  <!-- Etiquetas CEGAS de pesagem: uma por (preparo × ingrediente). -->
  <section
    v-if="printMode === 'pesagem'"
    class="hidden print:block"
    aria-hidden="true"
  >
    <div class="grid grid-cols-2 gap-2">
      <div
        v-for="label in labels"
        :key="label.key"
        class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
      >
        <div class="flex items-baseline justify-between gap-2">
          <span class="font-mono text-2xl font-bold tracking-widest">{{
            label.code
          }}</span>
          <span class="text-[0.65rem]">{{ label.date }}</span>
        </div>
        <span class="text-sm">{{ label.ingredient }}</span>
        <span class="text-lg font-bold tabular-nums">{{ label.weight }}</span>
      </div>
    </div>
  </section>

  <!-- Etiquetas EXPLÍCITAS do preparo pronto: uma por preparo. -->
  <section v-else class="hidden print:block" aria-hidden="true">
    <div class="grid grid-cols-2 gap-2">
      <div
        v-for="ticket in tickets"
        :key="ticket.recipe_ref"
        class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
      >
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-lg font-bold uppercase leading-tight">{{
            ticket.name
          }}</span>
          <span class="text-xs font-semibold tabular-nums"
            >F {{ ticket.made_display }} · V {{ ticket.expiry_display }}</span
          >
        </div>
        <span class="text-base font-bold tabular-nums">
          {{ ticket.output_quantity_display
          }}<template v-if="ticket.dough_weight_display">
            · {{ ticket.dough_weight_display }}</template
          >
        </span>
        <span v-if="ticket.sources_display" class="text-xs"
          >Objetivo: {{ ticket.sources_display }}</span
        >
        <span class="font-mono text-[0.65rem]">{{ ticket.blind_code }}</span>
      </div>
    </div>
  </section>
</template>
