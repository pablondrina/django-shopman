<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { OperatorCard } from "~/utils/operatorLock";

const props = withDefaults(
  defineProps<{
    operators: OperatorCard[];
    busy?: boolean;
    error?: string;
    // Forced change after a manager reset: the active operator must rotate the
    // temp PIN before operating. `forcedName` labels the change panel.
    forced?: boolean;
    forcedOperatorId?: number | null;
    forcedOperatorName?: string;
    changeError?: string;
    // Bumped by the parent after a successful change → the panel exits change mode.
    changeNonce?: number;
  }>(),
  { busy: false, error: "", forced: false, forcedOperatorId: null, forcedOperatorName: "", changeError: "", changeNonce: 0 },
);
const emit = defineEmits<{
  unlock: [operatorId: number, pin: string];
  changePin: [operatorId: number, currentPin: string, newPin: string];
}>();

const selectedId = ref<number | null>(null);
const pin = ref("");
const changing = ref(false); // voluntary "Trocar meu PIN" mode (an operator is selected)

const selectedName = computed(
  () => props.operators.find((o) => o.id === selectedId.value)?.name || "",
);

function submitVoluntaryChange(payload: { currentPin: string; newPin: string }) {
  if (selectedId.value === null) return;
  emit("changePin", selectedId.value, payload.currentPin, payload.newPin);
}

function submitForcedChange(payload: { currentPin: string; newPin: string }) {
  if (props.forcedOperatorId == null) return;
  emit("changePin", props.forcedOperatorId, payload.currentPin, payload.newPin);
}

// A successful change (parent bumps the nonce) leaves voluntary change mode so the
// operator returns to the PIN pad and unlocks with the new PIN.
watch(
  () => props.changeNonce,
  () => { changing.value = false; pin.value = ""; },
);

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
    <!-- Forced change: manager reset the operator's PIN; rotate before operating. -->
    <PosPinChange
      v-if="forced && forcedOperatorId != null"
      :operator-name="forcedOperatorName"
      forced
      :busy="busy"
      :error="changeError"
      @submit="submitForcedChange"
      @cancel="() => {}"
    />

    <!-- Voluntary change: the selected operator rotates their own PIN. -->
    <PosPinChange
      v-else-if="changing && selectedId !== null"
      :operator-name="selectedName"
      :busy="busy"
      :error="changeError"
      @submit="submitVoluntaryChange"
      @cancel="changing = false"
    />

    <div v-else class="w-full max-w-md px-6 py-8">
      <div class="mb-6 text-center">
        <div class="mx-auto mb-3 grid size-12 place-items-center rounded-md bg-primary text-primary-foreground shadow-sm">
          <Icon name="lucide:store" class="size-6" />
        </div>
        <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Ponto de venda</p>
        <h1 class="mt-1 text-3xl font-semibold">Quem está no caixa?</h1>
        <p class="mt-2 text-base text-muted-foreground">Selecione seu nome e digite seu PIN.</p>
      </div>

      <!-- operator picker -->
      <div v-if="operators.length > 1" class="mb-6 flex flex-wrap justify-center gap-2">
        <UiButton
          v-for="op in operators"
          :key="op.id"
          variant="outline"
          class="h-11"
          :class="selectedId === op.id ? 'border-primary bg-primary/5' : ''"
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
        <UiButton variant="ghost" size="sm" class="mt-1 gap-1.5 text-muted-foreground" :disabled="busy" @click="changing = true">
          <Icon name="lucide:key-round" class="size-4" /> Trocar meu PIN
        </UiButton>
      </div>
    </div>
  </div>
</template>
