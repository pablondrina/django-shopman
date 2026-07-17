<script setup lang="ts">
// ANTESALA do PDV (benchmark Odoo POS): a tela de SESSÃO antes da venda. O
// operador abre o caixa (fundo de troco), registra sangria/suprimento/ajuste e
// fecha o turno (contagem cega) aqui — não mais num diálogo espremido dentro da
// tela de venda. Sem turno aberto, a tela de venda redireciona para cá; com
// turno, o CTA "Continuar vendendo" leva de volta. BLIND: a antesala nunca
// mostra o valor esperado da gaveta — a conferência (esperado vs contado) fica
// no retaguarda. O fechamento do DIA (sobras/perdas) entra em `/session/closing`.
import { formatOpenedAt, movementLabel, sessionScreenState } from "~/presentation/cash";
import type { DayClosingResponse } from "~/types/closing";

useHead({ title: "Sessão de caixa · Shopman POS" });

const action = usePosAction();
const { pos, shift, actions, pending, refresh } = await usePosTerminal();

const OPERATOR_PERM = "backstage.operate_pos";
const { operator: activeOperator, lock } = useOperatorLock(OPERATOR_PERM);

const {
  busy,
  movementKinds,
  openCashShift,
  closeCashShift,
  closeBlockingShift,
  registerCashMovement,
} = usePosCashSession({ pos, actions, refresh, action });

// Entrada do FECHAMENTO DO DIA (contagem cega de sobras): o gate é da API
// (`backstage.perform_closing`) — sondagem leve; 401/403 = card não aparece.
const { data: dayClosingData } = useFetch<DayClosingResponse>(
  "/api/v1/backstage/closing/",
  { key: "day-closing-entry", credentials: "include", lazy: true, server: false },
);
const dayClosing = computed(() => dayClosingData.value?.closing ?? null);

const screen = computed(() => {
  if (!pos.value) return "closed";
  return sessionScreenState(pos.value.cash_runtime, pos.value.has_open_cash_session);
});
const cashRuntime = computed(() => pos.value?.cash_runtime ?? null);
const openedAtDisplay = computed(() => formatOpenedAt(cashRuntime.value?.opened_at));
const salesCount = computed(() => shift.value?.count ?? 0);

// Abrir caixa → direto para a venda (o motivo de estar na antesala acabou).
const openingAmount = ref("");
async function submitOpen() {
  const ok = await openCashShift(openingAmount.value);
  if (ok) await navigateTo("/");
}

// Movimentos de gaveta: sangria / suprimento / ajuste.
const movementKind = ref("");
const movementAmount = ref("");
const movementReason = ref("");
const canSubmitMovement = computed(
  () => Boolean(movementKind.value && movementAmount.value.trim() && movementReason.value.trim()),
);
async function submitMovement() {
  if (!canSubmitMovement.value) return;
  const ok = await registerCashMovement({
    kind: movementKind.value,
    amount: movementAmount.value,
    reason: movementReason.value,
  });
  if (ok) {
    movementAmount.value = "";
    movementReason.value = "";
  }
}

// Fechar caixa (contagem cega) — destrutivo, exige confirmação explícita.
const closingAmount = ref("");
const closingNotes = ref("");
const confirmingClose = ref(false);
async function confirmClose() {
  const ok = await closeCashShift({ amount: closingAmount.value, notes: closingNotes.value });
  confirmingClose.value = false;
  if (ok) {
    closingAmount.value = "";
    closingNotes.value = "";
  }
}

// Fechamento cego do turno BLOQUEANTE (gerente ou dono destrava o terminal).
const blockingAmount = ref("");
const blockingNotes = ref("");
const confirmingBlocking = ref(false);
async function confirmCloseBlocking() {
  const shiftId = cashRuntime.value?.blocking_shift_id;
  if (!shiftId) return;
  const ok = await closeBlockingShift({
    shift_id: shiftId,
    amount: blockingAmount.value,
    notes: blockingNotes.value,
  });
  confirmingBlocking.value = false;
  if (ok) {
    blockingAmount.value = "";
    blockingNotes.value = "";
  }
}
</script>

<template>
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      view="session"
      @board="navigateTo('/')"
      @cash="() => {}"
      @lock="lock()"
      @refresh="refresh()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <RailToggle />
        <h1 class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">Sessão de caixa</h1>
        <span v-if="pos" class="ml-auto truncate text-sm text-muted-foreground">
          {{ pos.terminal_label || "Terminal" }}
          <template v-if="screen === 'open'"> · {{ activeOperator?.name || cashRuntime?.operator_username }}</template>
        </span>
      </header>

      <div class="flex-1 md:min-h-0 md:overflow-y-auto">
        <div class="mx-auto grid w-full max-w-xl gap-4 p-4 md:py-8">
          <!-- Terminal ocupado: turno aberto por outro operador -->
          <section v-if="screen === 'occupied'" class="grid gap-2 rounded-lg border border-warning/40 bg-warning/10 p-4">
            <div class="flex items-center gap-2">
              <Icon name="lucide:lock" class="size-4 text-amber-700" />
              <p class="text-sm font-semibold text-amber-800">Terminal ocupado</p>
            </div>
            <p class="text-sm text-amber-800">
              Turno aberto por <strong>{{ cashRuntime?.blocking_operator_username }}</strong>
              <template v-if="cashRuntime?.blocking_shift_id"> (turno #{{ cashRuntime.blocking_shift_id }})</template>.
            </p>
            <p v-if="cashRuntime?.blocking_message" class="text-xs text-amber-700">{{ cashRuntime.blocking_message }}</p>

            <!-- Gerente ou dono do turno: fecha (contagem cega) e libera o terminal aqui mesmo. -->
            <template v-if="cashRuntime?.can_close_blocking">
              <div v-if="!confirmingBlocking" class="mt-1">
                <UiButton variant="outline" size="sm" class="w-full border-warning/50 text-amber-800 hover:bg-warning/10" :disabled="busy" @click="confirmingBlocking = true">
                  Fechar turno #{{ cashRuntime.blocking_shift_id }} (contagem cega)
                </UiButton>
              </div>
              <div v-else class="mt-1 grid gap-2 rounded-md border border-warning/40 bg-background p-3">
                <div class="flex items-start gap-2 text-xs text-muted-foreground">
                  <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
                  <span>Contagem cega: conte o dinheiro do caixa e informe o valor. A conferência fica no gestor.</span>
                </div>
                <label class="grid gap-1 text-sm">
                  <span class="font-medium text-muted-foreground">Valor contado</span>
                  <UiInput v-model="blockingAmount" inputmode="decimal" placeholder="0,00" />
                </label>
                <label class="grid gap-1 text-sm">
                  <span class="font-medium text-muted-foreground">Observações</span>
                  <UiTextarea v-model="blockingNotes" :rows="2" placeholder="Motivo (turno órfão, troca de operador…)" />
                </label>
                <div class="grid grid-cols-2 gap-2">
                  <UiButton variant="outline" :disabled="busy" @click="confirmingBlocking = false">Cancelar</UiButton>
                  <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmCloseBlocking">
                    Fechar e liberar
                  </UiButton>
                </div>
              </div>
            </template>
            <p v-else class="text-xs text-muted-foreground">
              Só o gerente ou o operador dono do turno pode fechá-lo. Chame o gerente ou feche no gestor.
            </p>
          </section>

          <!-- Caixa fechado: abrir turno -->
          <section v-else-if="screen === 'closed'" class="grid gap-3 rounded-lg border bg-card p-4">
            <div class="grid gap-1">
              <h2 class="text-base font-semibold">Abrir caixa</h2>
              <p class="text-sm text-muted-foreground">
                Abra o caixa antes de vender. Informe o valor de abertura (fundo de troco).
              </p>
            </div>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Valor de abertura</span>
              <UiInput v-model="openingAmount" inputmode="decimal" placeholder="0,00" @keydown.enter="submitOpen" />
            </label>
            <UiButton size="lg" :disabled="busy" :loading="busy" @click="submitOpen">
              <Icon name="lucide:wallet" class="size-5" />
              Abrir caixa e vender
            </UiButton>
          </section>

          <!-- Turno aberto: status (cego), continuar, movimentos, fechamento -->
          <template v-else>
            <section class="grid gap-3 rounded-lg border bg-card p-4">
              <div class="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 text-sm">
                <div class="flex flex-col">
                  <span class="text-xs text-muted-foreground">Aberto em</span>
                  <span class="font-medium tabular-nums">{{ openedAtDisplay }}</span>
                </div>
                <div class="flex flex-col">
                  <span class="text-xs text-muted-foreground">Vendas hoje</span>
                  <span class="font-medium tabular-nums">{{ salesCount }}</span>
                </div>
              </div>
              <UiButton size="lg" @click="navigateTo('/')">
                <Icon name="lucide:shopping-basket" class="size-5" />
                Continuar vendendo
              </UiButton>
            </section>

            <section class="grid gap-2 rounded-lg border bg-card p-4">
              <h2 class="text-base font-semibold">Movimento de caixa</h2>
              <div class="grid grid-cols-3 gap-2">
                <UiButton
                  v-for="kind in movementKinds"
                  :key="kind"
                  variant="outline"
                  size="sm"
                  :class="movementKind === kind ? 'border-primary bg-primary/5' : ''"
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
                :disabled="busy || !canSubmitMovement"
                @click="submitMovement"
              >
                Registrar movimento
              </UiButton>
            </section>

            <section class="grid gap-2 rounded-lg border bg-card p-4">
              <h2 class="text-base font-semibold">Fechar caixa</h2>
              <div class="flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
                <span>Contagem cega: conte o dinheiro do caixa e informe o valor. A conferência fica no gestor.</span>
              </div>
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
              <div v-else class="grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
                <p class="text-sm font-medium">Confirmar fechamento do caixa? Esta ação encerra o turno.</p>
                <div class="grid grid-cols-2 gap-2">
                  <UiButton variant="outline" :disabled="busy" @click="confirmingClose = false">Cancelar</UiButton>
                  <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmClose">
                    Confirmar
                  </UiButton>
                </div>
              </div>
            </section>
          </template>

          <!-- Fechamento do DIA (gerente): contagem cega de sobras/perdas. -->
          <section v-if="dayClosing" class="grid gap-2 rounded-lg border bg-card p-4">
            <div class="flex items-center gap-2">
              <Icon name="lucide:clipboard-check" class="size-4 text-muted-foreground" />
              <h2 class="text-base font-semibold">Fechamento do dia</h2>
            </div>
            <p class="text-sm text-muted-foreground">
              <template v-if="dayClosing.already_closed">{{ dayClosing.existing_closing_display }}</template>
              <template v-else>{{ dayClosing.today_display }} · contagem cega de sobras e perdas.</template>
            </p>
            <UiButton variant="outline" @click="navigateTo('/session/closing')">
              {{ dayClosing.already_closed ? "Ver fechamento" : "Fazer o fechamento" }}
            </UiButton>
          </section>
        </div>
      </div>
    </div>
  </main>
</template>
