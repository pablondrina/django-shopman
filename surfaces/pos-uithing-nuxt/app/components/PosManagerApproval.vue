<script setup lang="ts">
// Manager approval (spec §1.4/§3): a manager PIN challenge that appears ONLY
// when the review's Projection demands it (`requires_manager_approval`), never
// by a fixed list of client-side gates. The screen renders what the review
// requires; the orchestrator verifies the PIN (doorman `verify_manager_pin`).
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  managerUsername: string;
  managerPin: string;
  /** Discount threshold (cents) above which approval is required; 0 = N/A. */
  thresholdQ: number;
}>();

defineEmits<{
  "update:managerUsername": [string];
  "update:managerPin": [string];
}>();

const reason = computed(() =>
  props.thresholdQ > 0
    ? `Necessária para descontos acima de ${formatBRL(props.thresholdQ)}.`
    : "Necessária para esta operação sensível.",
);
</script>

<template>
  <div class="grid shrink-0 gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5">
    <div class="flex items-center gap-1.5">
      <Icon name="lucide:shield-check" class="size-4 text-amber-700" />
      <p class="text-xs font-semibold text-amber-800">Aprovação do gerente</p>
    </div>
    <p class="text-xs text-amber-700">{{ reason }}</p>
    <UiInput
      :model-value="managerUsername"
      placeholder="Gerente"
      autocomplete="off"
      class="h-9"
      @update:model-value="$emit('update:managerUsername', String($event || ''))"
    />
    <UiInput
      :model-value="managerPin"
      type="password"
      inputmode="numeric"
      placeholder="PIN"
      autocomplete="off"
      class="h-9"
      @update:model-value="$emit('update:managerPin', String($event || ''))"
    />
  </div>
</template>
