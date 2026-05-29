<script setup lang="ts">
import { ref, watch } from "vue";

import type { OperatorCard } from "~/utils/operatorLock";

const props = withDefaults(
  defineProps<{ operators: OperatorCard[]; busy?: boolean; error?: string }>(),
  { busy: false, error: "" },
);
const emit = defineEmits<{ unlock: [operatorId: number, pin: string] }>();

const selectedId = ref<number | null>(null);
const pin = ref("");

// Auto-select when there is a single operator (frictionless).
watch(
  () => props.operators,
  (ops) => {
    if (ops.length === 1 && ops[0]) selectedId.value = ops[0].id;
  },
  { immediate: true },
);

// Clear the PIN buffer whenever the server rejects it.
watch(
  () => props.error,
  (e) => {
    if (e) pin.value = "";
  },
);

function selectOperator(id: number) {
  selectedId.value = id;
  pin.value = "";
}

function submit() {
  if (selectedId.value === null || pin.value.length === 0 || props.busy) return;
  emit("unlock", selectedId.value, pin.value);
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="Identifique-se para operar o caixa"
  >
    <div class="w-full max-w-md px-6 py-8">
      <div class="mb-6 text-center">
        <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Shopman POS</p>
        <h1 class="mt-1 text-3xl font-semibold">Quem está no caixa?</h1>
        <p class="mt-2 text-base text-muted-foreground">Selecione seu nome e digite seu PIN.</p>
      </div>

      <!-- operator picker -->
      <div v-if="operators.length > 1" class="mb-6 flex flex-wrap justify-center gap-2">
        <UiButton
          v-for="op in operators"
          :key="op.id"
          :variant="selectedId === op.id ? 'default' : 'outline'"
          class="h-11"
          @click="selectOperator(op.id)"
        >
          {{ op.name }}
        </UiButton>
      </div>

      <p v-if="operators.length === 0" class="mb-6 text-center text-base text-muted-foreground">
        Nenhum operador com PIN configurado. Peça ao gerente para cadastrar o seu.
      </p>

      <div v-if="selectedId !== null" class="flex flex-col items-center gap-4">
        <p v-if="error" class="text-center text-base font-medium text-destructive" role="alert">
          {{ error }}
        </p>
        <PosPinPad v-model="pin" :disabled="busy" @submit="submit" />
      </div>
    </div>
  </div>
</template>
