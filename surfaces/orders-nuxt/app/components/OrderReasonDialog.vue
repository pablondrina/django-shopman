<script setup lang="ts">
// Reject/cancel reason dialog. Two shapes, decided by the order's channel:
//   - Marketplace (iFood): a coded picker from the provider's live per-order list.
//     The provider REQUIRES one of its codes; the picked description is mirrored into
//     the customer-facing reason. (Mirrors what the board's Recusar dialog does.)
//   - Other channels: store-configured presets (one tap) + free text.
// Presentational: the parent owns the fetch (reasons/loading) and the write action;
// this component owns only the in-dialog input state and emits the chosen reason+code.
import type { CancellationReason } from "~/types/orders";

const props = defineProps<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  presets: string[];
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [payload: { reason: string; cancellationCode: string }];
}>();

const reason = ref("");
const code = ref("");

// Fresh state every time the dialog opens (a reused order ref must not leak its
// previous pick).
watch(
  () => props.open,
  (open) => { if (open) { reason.value = ""; code.value = ""; } },
);

const isMarketplace = computed(() => props.reasons.length > 0);

const canConfirm = computed(() => {
  if (isMarketplace.value) return code.value !== "";
  // Free text: a reject needs a reason (the customer is told why); a cancel may go
  // out with the generic fallback, so an empty reason is allowed.
  return props.mode === "cancel" || reason.value.trim() !== "";
});

function onCodeChange() {
  // Mirror the picked reason's text into the customer-facing reason.
  const picked = props.reasons.find((r) => r.code === code.value);
  if (picked) reason.value = picked.description;
}

function applyPreset(text: string) {
  reason.value = text;
}

function submit() {
  if (!canConfirm.value || props.busy) return;
  emit("confirm", { reason: reason.value.trim(), cancellationCode: code.value });
}

const title = computed(() => (props.mode === "reject" ? "Recusar pedido" : "Cancelar pedido"));
const description = computed(() =>
  isMarketplace.value
    ? "Escolha o motivo exigido pelo iFood — ele é enviado ao marketplace."
    : props.mode === "reject"
      ? "Informe o motivo — o cliente é avisado."
      : "O motivo é enviado ao cliente na notificação de cancelamento.",
);
</script>

<template>
  <UiDialog :open="open" @update:open="(v) => emit('update:open', v)">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>{{ title }}</UiDialogTitle>
        <UiDialogDescription>{{ description }}</UiDialogDescription>
      </UiDialogHeader>

      <p v-if="loading" class="text-sm text-muted-foreground">Carregando motivos do iFood…</p>

      <!-- Marketplace (iFood): coded reason picker from the provider's live list -->
      <select
        v-else-if="isMarketplace"
        v-model="code"
        class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
        aria-label="Motivo exigido pelo iFood"
        @change="onCodeChange"
      >
        <option value="" disabled>Selecione o motivo…</option>
        <option v-for="r in reasons" :key="r.code" :value="r.code">{{ r.description }}</option>
      </select>

      <!-- Other channels: one-tap presets (Admin/Unfold) + free text -->
      <template v-else>
        <div v-if="presets.length" class="flex flex-wrap gap-1.5">
          <button
            v-for="(preset, i) in presets"
            :key="i"
            type="button"
            :aria-pressed="reason === preset"
            class="rounded-full border px-3 py-1 text-xs font-medium transition hover:bg-accent"
            :class="reason === preset ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
            @click="applyPreset(preset)"
          >
            {{ preset }}
          </button>
        </div>
        <textarea
          v-model="reason"
          rows="3"
          :placeholder="mode === 'reject' ? 'Motivo da recusa…' : 'Motivo do cancelamento (opcional)…'"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo"
        />
      </template>

      <UiDialogFooter>
        <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="emit('update:open', false)">
          Voltar
        </button>
        <button
          type="button"
          :disabled="busy || !canConfirm"
          class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          @click="submit"
        >
          {{ mode === "reject" ? "Recusar pedido" : "Confirmar" }}
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
