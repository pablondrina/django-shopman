<script setup lang="ts">
// Resumo do pedido em linhas ícone + valor (como/onde/pagamento/contato), sem
// rótulo — o valor já se explica. Diagramação única compartilhada pela revisão do
// checkout e pela aba "Resumo" do acompanhamento; cada tela monta suas linhas a
// partir da sua própria fonte de dados.
export interface OrderSummaryRow {
  icon: string
  // Linhas de texto do valor (ex.: endereço em várias linhas). A cauda opcional
  // `muted` (ex.: complemento) sai mais fraca.
  lines: string[]
  muted?: string
}

defineProps<{ rows: OrderSummaryRow[] }>()
</script>

<template>
  <dl class="divide-y text-sm">
    <div v-for="(row, i) in rows" :key="i" class="flex items-baseline gap-3 py-2 first:pt-0">
      <Icon :name="row.icon" class="size-4 shrink-0 translate-y-0.5 text-muted-foreground" />
      <dd class="min-w-0 flex-1">
        <span v-for="(line, j) in row.lines" :key="j" class="block">{{ line }}</span>
        <span v-if="row.muted" class="block text-muted-foreground">{{ row.muted }}</span>
      </dd>
    </div>
  </dl>
</template>
