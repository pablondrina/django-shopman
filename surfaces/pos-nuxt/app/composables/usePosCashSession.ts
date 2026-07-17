import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { Action, POSCashManagementCapability, POSProjection } from "~/types/pos";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { actionHref } from "~/utils/posIntent";

interface CashSessionDeps {
  pos: ComputedRef<POSProjection | null>;
  actions: ComputedRef<Action[]>;
  refresh: () => Promise<void>;
  action: { call: (path: string, opts?: { body?: Record<string, unknown> }) => Promise<unknown> };
}

/**
 * Write-side da SESSÃO de caixa (antesala): abrir/fechar turno, fechar turno
 * bloqueante e movimentos (sangria/suprimento/ajuste). Vivia dentro do
 * usePosSale quando o caixa era um diálogo da tela de venda; com a antesala
 * (`/session`) a sessão tem tela própria e o write-side acompanha. Cada ação
 * devolve `true` no sucesso para a página decidir navegação (ex.: abrir caixa
 * → ir vender). Erros sobem como toast, mesmo dialeto do restante do PDV.
 */
export function usePosCashSession({ pos, actions, refresh, action }: CashSessionDeps) {
  const busy = ref(false);

  const cashManagement = computed<POSCashManagementCapability | null>(
    () => (pos.value?.checkout?.capabilities?.cash_management ?? null) as POSCashManagementCapability | null,
  );
  const movementKinds = computed<string[]>(
    () => cashManagement.value?.movement_kinds || ["sangria", "suprimento", "ajuste"],
  );
  // O bloqueio de venda sem turno é contrato da Projection (hoje sempre true);
  // o gate de redirect da antesala lê daqui em vez de assumir.
  const shiftRequiredForSale = computed(() => requiresOpenShiftForSale(cashManagement.value));

  async function run(path: string, body: Record<string, unknown>, failMessage: string): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await action.call(path, { body });
      await refresh();
      return true;
    } catch (error) {
      toast.error(httpErrorMessage(error, failMessage));
      return false;
    } finally {
      busy.value = false;
    }
  }

  function openCashShift(amount: string): Promise<boolean> {
    return run(
      actionHref(actions.value, "open_cash_shift", "/api/v1/backstage/pos/cash/open/"),
      { opening_amount: amount || "0", terminal_ref: pos.value?.terminal_ref || "" },
      "Falha ao abrir caixa.",
    );
  }

  function closeCashShift(payload: { amount: string; notes: string }): Promise<boolean> {
    return run(
      actionHref(actions.value, "close_cash_shift", "/api/v1/backstage/pos/cash/close/"),
      { closing_amount: payload.amount || "0", notes: payload.notes },
      "Falha ao fechar caixa.",
    );
  }

  // Fecha (contagem cega) o turno que bloqueia o terminal — gerente ou dono.
  // Destrava o terminal para o operador atual abrir o seu.
  function closeBlockingShift(payload: { shift_id: number; amount: string; notes: string }): Promise<boolean> {
    return run(
      "/api/v1/backstage/pos/cash/close-blocking/",
      { shift_id: payload.shift_id, closing_amount: payload.amount || "0", notes: payload.notes },
      "Falha ao fechar o turno.",
    );
  }

  function registerCashMovement(payload: { kind: string; amount: string; reason: string }): Promise<boolean> {
    return run(
      actionHref(actions.value, "cash_movement", "/api/v1/backstage/pos/cash/movement/"),
      { kind: payload.kind, amount: payload.amount || "0", reason: payload.reason },
      "Falha ao registrar movimento.",
    );
  }

  return {
    busy,
    movementKinds,
    shiftRequiredForSale,
    openCashShift,
    closeCashShift,
    closeBlockingShift,
    registerCashMovement,
  };
}
