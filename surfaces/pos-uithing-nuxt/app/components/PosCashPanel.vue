<script setup lang="ts">
import type { POSCashRuntimeProjection, POSShiftSummaryProjection } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  cashRuntime: POSCashRuntimeProjection;
  shift: POSShiftSummaryProjection | null;
  hasOpenShift: boolean;
  movementKinds: string[];
  operatorName: string;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  openShift: [string];
  closeShift: [{ amount: string; notes: string }];
  movement: [{ kind: string; amount: string; reason: string }];
}>();

const openingAmount = ref("");
const closingAmount = ref("");
const closingNotes = ref("");
const movementKind = ref("");
const movementAmount = ref("");
const movementReason = ref("");
const confirmingClose = ref(false);

const occupied = computed(() =>
  props.cashRuntime.status === "terminal_occupied"
  || (!props.hasOpenShift && !!props.cashRuntime.blocking_operator_username),
);

const MOVEMENT_LABELS: Record<string, string> = {
  sangria: "Sangria",
  suprimento: "Suprimento",
  ajuste: "Ajuste",
};
function movementLabel(kind: string) {
  return MOVEMENT_LABELS[kind] || kind;
}

const openedAtDisplay = computed(() => {
  const raw = props.cashRuntime.opened_at;
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
});

watch(() => props.open, (isOpen) => {
  if (!isOpen) confirmingClose.value = false;
});

function submitMovement() {
  if (!movementKind.value || !movementAmount.value.trim() || !movementReason.value.trim()) return;
  emit("movement", {
    kind: movementKind.value,
    amount: movementAmount.value,
    reason: movementReason.value,
  });
  movementAmount.value = "";
  movementReason.value = "";
}

function confirmClose() {
  emit("closeShift", { amount: closingAmount.value, notes: closingNotes.value });
  confirmingClose.value = false;
}
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Caixa</UiDialogTitle>
        <UiDialogDescription>
          {{ cashRuntime.terminal_label || "Terminal" }}
          <template v-if="hasOpenShift"> · {{ operatorName || cashRuntime.operator_username }}</template>
        </UiDialogDescription>
      </UiDialogHeader>

      <!-- Occupied: terminal has an open shift under another operator -->
      <div v-if="occupied" class="grid gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-amber-700" />
          <p class="text-sm font-semibold text-amber-800">Terminal ocupado</p>
        </div>
        <p class="text-sm text-amber-800">
          Turno aberto por <strong>{{ cashRuntime.blocking_operator_username }}</strong>
          <template v-if="cashRuntime.blocking_shift_id"> (turno #{{ cashRuntime.blocking_shift_id }})</template>.
        </p>
        <p v-if="cashRuntime.blocking_message" class="text-xs text-amber-700">{{ cashRuntime.blocking_message }}</p>
        <p class="text-xs text-muted-foreground">
          Use o operador correto ou feche o turno atual no gestor antes de vender.
        </p>
      </div>

      <!-- Closed: open a shift -->
      <div v-else-if="!hasOpenShift" class="grid gap-3">
        <p class="text-sm text-muted-foreground">
          Abra o caixa antes de vender. Informe o valor de abertura (fundo de troco).
        </p>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Valor de abertura</span>
          <UiInput v-model="openingAmount" inputmode="decimal" placeholder="0,00" />
        </label>
        <UiButton :disabled="busy" :loading="busy" @click="$emit('openShift', openingAmount)">
          Abrir caixa
        </UiButton>
      </div>

      <!-- Open: summary, movements, close -->
      <div v-else class="grid gap-4">
        <div class="grid grid-cols-2 gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
          <div class="flex flex-col">
            <span class="text-xs text-muted-foreground">Aberto em</span>
            <span class="font-medium tabular-nums">{{ openedAtDisplay || "—" }}</span>
          </div>
          <div class="flex flex-col">
            <span class="text-xs text-muted-foreground">Vendas hoje</span>
            <span class="font-medium tabular-nums">{{ shift?.count ?? 0 }} · {{ shift?.total_display ?? "R$ 0,00" }}</span>
          </div>
          <div class="flex flex-col">
            <span class="text-xs text-muted-foreground">Dinheiro</span>
            <span class="font-medium tabular-nums">{{ shift?.cash_total_display ?? "R$ 0,00" }}</span>
          </div>
          <div class="flex flex-col">
            <span class="text-xs text-muted-foreground">Digital</span>
            <span class="font-medium tabular-nums">{{ shift?.digital_total_display ?? "R$ 0,00" }}</span>
          </div>
        </div>

        <div class="grid gap-2">
          <p class="text-sm font-medium text-muted-foreground">Movimento de caixa</p>
          <div class="grid grid-cols-3 gap-2">
            <UiButton
              v-for="kind in movementKinds"
              :key="kind"
              variant="outline"
              size="sm"
              :class="movementKind === kind ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="movementKind = kind"
            >
              {{ movementLabel(kind) }}
            </UiButton>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <UiInput v-model="movementAmount" inputmode="decimal" placeholder="Valor" />
            <UiInput v-model="movementReason" placeholder="Motivo" />
          </div>
          <UiButton
            variant="outline"
            size="sm"
            :disabled="busy || !movementKind || !movementAmount.trim() || !movementReason.trim()"
            @click="submitMovement"
          >
            Registrar movimento
          </UiButton>
        </div>

        <UiSeparator />

        <div class="grid gap-2">
          <p class="text-sm font-medium text-muted-foreground">Fechar caixa</p>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Valor contado</span>
            <UiInput v-model="closingAmount" inputmode="decimal" placeholder="0,00" />
          </label>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Observações</span>
            <UiTextarea v-model="closingNotes" :rows="2" placeholder="Conferência, divergências" />
          </label>
          <div v-if="!confirmingClose">
            <UiButton variant="destructive" class="w-full" :disabled="busy" @click="confirmingClose = true">
              Fechar caixa
            </UiButton>
          </div>
          <div v-else class="grid gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3">
            <p class="text-sm font-medium">Confirmar fechamento do caixa? Esta ação encerra o turno.</p>
            <div class="grid grid-cols-2 gap-2">
              <UiButton variant="outline" :disabled="busy" @click="confirmingClose = false">Cancelar</UiButton>
              <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmClose">
                Confirmar
              </UiButton>
            </div>
          </div>
        </div>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
