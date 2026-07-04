<script setup lang="ts">
// Operator lock overlay (Opção C). Shown when the gate is on and nobody is
// operating. Two ways in: scan a badge (a barcode scanner types the token fast
// and ends with Enter, captured anywhere on the overlay), or pick yourself and
// type your PIN. The surface permission scopes who appears + who may unlock.
//
// Two PIN-change flows share this overlay: a FORCED change after a manager reset
// (must_change — the operator can't operate until they rotate the temp PIN), and
// a VOLUNTARY "Trocar PIN" from the pad. Both prove the current PIN (the backend
// authorizes on that), so no manager is needed for a routine change.
import { appendPinDigit, canSubmitPin, isLikelyBadge } from "~/presentation/operatorLock";
import type { OperatorCard } from "~/types/operator";

const props = defineProps<{ perm: string }>();

const { eligible, loadEligible, unlock, changePin, changeError, operator, mustChange, busy } = useOperatorLock(props.perm);

const picked = ref<OperatorCard | null>(null);
const pin = ref("");
const badgeBuffer = ref("");
const changing = ref(false); // voluntary "Trocar PIN" mode (an operator is picked)

onMounted(loadEligible);

function pick(op: OperatorCard) {
  picked.value = op;
  pin.value = "";
}

function press(digit: string) {
  pin.value = appendPinDigit(pin.value, digit);
}

function backspace() {
  pin.value = pin.value.slice(0, -1);
}

const canSubmit = computed(() => canSubmitPin(picked.value?.id ?? null, pin.value));

async function submitPin() {
  if (!canSubmit.value || !picked.value) return;
  const ok = await unlock({ operatorId: picked.value.id, pin: pin.value });
  if (!ok) pin.value = "";
}

// Badge scanner: a hidden, always-focused field collects the fast keystrokes; on
// Enter, if it looks like a badge token we unlock by badge. Keeps hands-free flow.
async function onBadgeEnter() {
  const value = badgeBuffer.value.trim();
  badgeBuffer.value = "";
  if (!isLikelyBadge(value)) return;
  await unlock({ badge: value });
}

// ── Voluntary change (an operator picked themselves and taps "Trocar PIN") ──
async function submitVoluntaryChange(payload: { currentPin: string; newPin: string }) {
  if (!picked.value) return;
  const ok = await changePin({ operatorId: picked.value.id, ...payload });
  if (ok) {
    changing.value = false;
    pin.value = "";
    useSonner.success("PIN atualizado. Entre com o novo PIN.");
  }
}

// ── Forced change (must_change after a manager reset) ──
async function submitForcedChange(payload: { currentPin: string; newPin: string }) {
  if (!operator.value) return;
  const ok = await changePin({ operatorId: operator.value.id, ...payload });
  if (ok) useSonner.success("PIN atualizado.");
  // success → session refresh clears must_change → the overlay closes on its own.
}
</script>

<template>
  <div class="fixed inset-0 z-[100] grid place-items-center bg-background/95 p-4 backdrop-blur-sm">
    <!-- hidden capture for the barcode scanner (types + Enter) -->
    <input
      v-if="!changing && !mustChange"
      v-model="badgeBuffer"
      class="sr-only"
      aria-hidden="true"
      autofocus
      @keyup.enter="onBadgeEnter"
    />

    <div class="w-full max-w-md rounded-xl border bg-card p-5 shadow-lg">
      <!-- Forced change: manager reset the operator's PIN; rotate before operating. -->
      <OperatorPinChange
        v-if="mustChange && operator"
        :operator-name="operator.name"
        forced
        :busy="busy"
        :error="changeError"
        @submit="submitForcedChange"
        @cancel="() => {}"
      />

      <!-- Voluntary change: the picked operator rotates their own PIN. -->
      <OperatorPinChange
        v-else-if="changing && picked"
        :operator-name="picked.name"
        :busy="busy"
        :error="changeError"
        @submit="submitVoluntaryChange"
        @cancel="changing = false"
      />

      <template v-else>
        <div class="mb-4 flex items-center gap-2">
          <Icon name="lucide:lock" class="size-5 text-muted-foreground" />
          <h2 class="text-lg font-bold">Identifique-se para operar</h2>
        </div>

        <p class="mb-3 text-sm text-muted-foreground">
          Passe o crachá no leitor, ou toque no seu nome e digite o PIN.
        </p>

        <!-- operator picker -->
        <template v-if="!picked">
          <div v-if="!eligible.length" class="grid place-items-center gap-1.5 rounded-lg border border-dashed py-8 text-center text-muted-foreground">
            <Icon name="lucide:user-x" class="size-6" />
            <p class="text-sm">Nenhum operador habilitado para esta tela.</p>
          </div>
          <div v-else class="grid grid-cols-2 gap-2">
            <button
              v-for="op in eligible"
              :key="op.id"
              type="button"
              class="rounded-lg border bg-background px-3 py-3 text-left text-sm font-medium transition hover:bg-accent"
              @click="pick(op)"
            >
              {{ op.name }}
            </button>
          </div>
        </template>

        <!-- PIN pad -->
        <template v-else>
          <button type="button" class="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" @click="picked = null">
            <Icon name="lucide:chevron-left" class="size-4" /> Trocar operador
          </button>
          <p class="mb-2 text-sm font-semibold">{{ picked.name }}</p>
          <div class="mb-3 flex h-10 items-center justify-center rounded-md border bg-background text-2xl tracking-[0.4em] tabular-nums">
            {{ "•".repeat(pin.length) || "—" }}
          </div>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="d in ['1','2','3','4','5','6','7','8','9']"
              :key="d"
              type="button"
              class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
              @click="press(d)"
            >
              {{ d }}
            </button>
            <button type="button" class="rounded-lg border bg-background py-3 text-sm transition hover:bg-accent" @click="backspace">
              <Icon name="lucide:delete" class="mx-auto size-5" />
            </button>
            <button type="button" class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent" @click="press('0')">0</button>
            <button
              type="button"
              :disabled="!canSubmit || busy"
              class="rounded-lg border border-transparent bg-primary py-3 text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
              @click="submitPin"
            >
              <Icon name="lucide:check" class="mx-auto size-5" />
            </button>
          </div>

          <button
            type="button"
            class="mt-3 inline-flex w-full items-center justify-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            @click="changing = true"
          >
            <Icon name="lucide:key-round" class="size-4" /> Trocar meu PIN
          </button>
        </template>
      </template>
    </div>
  </div>
</template>
