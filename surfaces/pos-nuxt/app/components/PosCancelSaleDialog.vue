<script setup lang="ts">
// Cancelar uma venda fechada é EXCEÇÃO auditada (anti-fraude), não fluxo do
// operador: confirmação destrutiva + desafio de PIN gerencial num só diálogo —
// mesma tela focada do PosManagerAuthDialog, com motivo opcional de correção.
const props = defineProps<{
  open: boolean;
  orderRef: string;
  reason: string;
  maxAgeMinutes?: number;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:reason": [string];
  confirm: [string, string];
}>();

const username = ref("");
const pin = ref("");

// Fresh fields each time it opens; clear the PIN when the server rejects it.
watch(() => props.open, (open) => { if (open) { username.value = ""; pin.value = ""; } });
watch(() => props.error, (e) => { if (e) pin.value = ""; });

function confirm() {
  if (!username.value.trim() || pin.value.length === 0 || props.busy) return;
  emit("confirm", username.value.trim(), pin.value);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-destructive/40 bg-destructive/10 text-destructive">
          <Icon name="lucide:rotate-ccw" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Cancelar venda</UiDialogTitle>
        <UiDialogDescription>
          O pedido {{ orderRef }} será cancelado. Esta operação exige a autorização de um gerente.
          <template v-if="maxAgeMinutes">
            Disponível por até {{ maxAgeMinutes }} minutos após a venda; depois, cancele pelo gestor.
          </template>
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
        <UiInput
          :model-value="reason"
          placeholder="Motivo do cancelamento (opcional)"
          autocomplete="off"
          class="h-11 w-full max-w-60 text-center text-base"
          @update:model-value="(value) => emit('update:reason', String(value))"
        />
        <UiInput
          v-model="username"
          placeholder="Nome do gerente"
          autocomplete="off"
          class="h-11 w-full max-w-60 text-center text-base"
        />
        <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">{{ error }}</p>
        <PosPinPad v-model="pin" :disabled="busy" @submit="confirm" />
        <p class="text-center text-xs text-muted-foreground">Informe o gerente e o PIN, depois confirme.</p>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
