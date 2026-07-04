<script setup lang="ts">
// Material/order shortage modal. Renders the structured shortage envelope the API
// returns (409) when a finish/plan would consume more than is available, or leave
// committed orders uncovered. For a material shortage the operator can override
// (force=1); an order shortage is informational (re-plan with a higher quantity).
import type { ProductionShortageError } from "~/types/production";

const props = defineProps<{ shortage: ProductionShortageError | null }>();
const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();

const isMaterial = computed(() => props.shortage?.code === "material_shortage");
</script>

<template>
  <UiDialog :open="shortage != null" @update:open="(v) => emit('update:open', v)">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle class="flex items-center gap-2">
          <Icon name="lucide:triangle-alert" class="size-5 text-amber-600" />
          {{ isMaterial ? "Insumos insuficientes" : "Quantidade não cobre pedidos" }}
        </UiDialogTitle>
        <UiDialogDescription>
          <template v-if="isMaterial">Faltam insumos para concluir {{ shortage?.work_order_ref }}. Você pode concluir mesmo assim — um alerta será registrado.</template>
          <template v-else>A nova quantidade de {{ shortage?.work_order_ref }} deixa pedidos descobertos.</template>
        </UiDialogDescription>
      </UiDialogHeader>

      <template v-if="shortage && shortage.code === 'material_shortage'">
        <ul class="divide-y rounded-md border text-sm">
          <li v-for="item in shortage.missing" :key="item.sku" class="flex items-center justify-between gap-2 px-3 py-2">
            <span class="font-medium">{{ item.sku }}</span>
            <span class="tabular-nums text-muted-foreground">
              precisa <b class="text-foreground">{{ item.needed }}</b> · tem {{ item.available }} ·
              <span class="text-red-600 dark:text-red-400">faltam {{ item.shortage }}</span>
            </span>
          </li>
        </ul>
      </template>
      <template v-else-if="shortage && shortage.code === 'order_shortage'">
        <div class="rounded-md border bg-muted/40 p-3 text-sm">
          <p>Comprometido: <b class="tabular-nums">{{ shortage.required }}</b> un. · solicitado: <b class="tabular-nums">{{ shortage.requested }}</b> un.</p>
          <p class="mt-1 text-muted-foreground">Pedidos: {{ shortage.order_refs.join(", ") }}</p>
        </div>
      </template>

      <UiDialogFooter>
        <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="emit('update:open', false)">
          {{ isMaterial ? "Cancelar" : "Entendi" }}
        </button>
        <button
          v-if="isMaterial"
          type="button"
          class="rounded-md border border-transparent bg-amber-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-amber-700"
          @click="emit('confirm')"
        >
          Concluir mesmo assim
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
