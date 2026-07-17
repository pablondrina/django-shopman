<script setup lang="ts">
// Card de leitura de turno (X aberto, Z fechado) do relatório da antesala.
// BLIND: renderiza só o que a projection serve — abertura, movimentos, vendas
// por método e (no Z) o valor CONTADO. O esperado da gaveta não existe aqui.
import { movementFlow, readingTitle, shiftPeriodDisplay, signedMovementDisplay } from "~/presentation/cashReport";
import type { ShiftReading } from "~/types/cashReport";

const props = defineProps<{ reading: ShiftReading }>();

const period = computed(() => shiftPeriodDisplay(props.reading));
const isOpen = computed(() => props.reading.status === "open");
</script>

<template>
  <section class="grid gap-3 rounded-lg border bg-card p-4">
    <div class="flex flex-wrap items-center gap-2">
      <Icon :name="isOpen ? 'lucide:receipt-text' : 'lucide:archive'" class="size-4 text-muted-foreground" />
      <h2 class="text-base font-semibold">{{ readingTitle(reading) }}</h2>
      <span
        v-if="isOpen"
        class="inline-flex items-center rounded-md border border-success/40 bg-success/10 px-1.5 py-0.5 text-xs font-medium text-success"
      >
        Turno aberto · parcial
      </span>
      <span class="ml-auto truncate text-sm text-muted-foreground">
        {{ reading.operator }} · {{ reading.terminal_label }}<template v-if="period"> · {{ period }}</template>
      </span>
    </div>

    <div class="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:grid-cols-4">
      <div class="flex flex-col">
        <span class="text-xs text-muted-foreground">Abertura</span>
        <span class="font-medium tabular-nums">R$ {{ reading.opening_amount_display }}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-xs text-muted-foreground">Vendas</span>
        <span class="font-medium tabular-nums">{{ reading.sales_count }}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-xs text-muted-foreground">Total vendido</span>
        <span class="font-medium tabular-nums">R$ {{ reading.sales_total_display }}</span>
      </div>
      <div v-if="!isOpen" class="flex flex-col">
        <span class="text-xs text-muted-foreground">Contado no fechamento</span>
        <span class="font-medium tabular-nums">R$ {{ reading.counted_amount_display }}</span>
      </div>
    </div>

    <div class="grid gap-1">
      <h3 class="text-sm font-medium">Vendas por método</h3>
      <p v-if="!reading.sales_by_method.length" class="text-sm text-muted-foreground">
        Nenhum pagamento registrado no turno.
      </p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-xs text-muted-foreground">
              <th class="py-1.5 pr-3 font-medium">Método</th>
              <th class="py-1.5 pr-3 font-medium">Pagamentos</th>
              <th class="py-1.5 font-medium">Valor</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in reading.sales_by_method" :key="row.method" class="border-b border-border/60 last:border-0">
              <td class="py-1.5 pr-3 font-medium">{{ row.method_label }}</td>
              <td class="py-1.5 pr-3 tabular-nums">{{ row.orders_count }}</td>
              <td class="py-1.5 tabular-nums">R$ {{ row.amount_display }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="grid gap-1">
      <h3 class="text-sm font-medium">Movimentos de gaveta</h3>
      <p v-if="!reading.movements.length" class="text-sm text-muted-foreground">
        Nenhum movimento manual no turno.
      </p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-xs text-muted-foreground">
              <th class="py-1.5 pr-3 font-medium">Tipo</th>
              <th class="py-1.5 pr-3 font-medium">Motivo</th>
              <th class="py-1.5 font-medium">Valor</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="movement in reading.movements" :key="movement.created_at + movement.kind" class="border-b border-border/60 last:border-0">
              <td class="py-1.5 pr-3 font-medium">{{ movement.kind_label }}</td>
              <td class="py-1.5 pr-3 text-muted-foreground">{{ movement.reason || "Sem motivo informado" }}</td>
              <td
                class="py-1.5 tabular-nums"
                :class="movementFlow(movement) === 'out' ? 'text-destructive' : 'text-success'"
              >
                {{ signedMovementDisplay(movement) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-muted-foreground">
        Entradas: R$ {{ reading.movements_in_display }} · Saídas: R$ {{ reading.movements_out_display }}
      </p>
    </div>

    <p v-if="reading.notes" class="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
      Observações: {{ reading.notes }}
    </p>
  </section>
</template>
