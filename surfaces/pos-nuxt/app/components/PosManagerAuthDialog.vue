<script setup lang="ts">
// Manager authorization (spec §1.4/§3): a focused PIN screen — like the operator
// lock, but flagged as an AUTHORIZATION — that appears when the review demands
// `requires_manager_approval`. The operator names the manager and keys the PIN on
// the same pad; the orchestrator verifies it (doorman `verify_manager_pin`).
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  open: boolean;
  thresholdQ: number;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  authorize: [string, string];
}>();

const username = ref("");
const pin = ref("");
const reason = computed(() =>
  props.thresholdQ > 0
    ? `Necessária para descontos acima de ${formatBRL(props.thresholdQ)}.`
    : "Esta venda precisa da autorização de um gerente para ser finalizada.",
);

// Fresh fields each time it opens; clear the PIN when the server rejects it.
watch(() => props.open, (open) => { if (open) { username.value = ""; pin.value = ""; } });
watch(() => props.error, (e) => { if (e) pin.value = ""; });

function confirm() {
  if (!username.value.trim() || pin.value.length === 0 || props.busy) return;
  emit("authorize", username.value.trim(), pin.value);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600">
          <Icon name="lucide:shield-check" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Autorização do gerente</UiDialogTitle>
        <UiDialogDescription>{{ reason }}</UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
        <UiInput
          v-model="username"
          placeholder="Nome do gerente"
          autocomplete="off"
          class="h-11 w-full max-w-60 text-center text-base"
          autofocus
        />
        <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">{{ error }}</p>
        <PosPinPad v-model="pin" :disabled="busy" @submit="confirm" />
        <p class="text-center text-xs text-muted-foreground">Informe o gerente e o PIN, depois confirme.</p>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
