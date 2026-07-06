// Operator lock read/write (Opção C, Camada 2). Reads the terminal lock state,
// lists who may unlock this surface, and unlocks by PIN or badge / locks. All I/O
// goes through the django proxy (CSRF handled there). The surface's permission is
// passed so the picker + unlock are scoped to operators who can use THIS app.
import type {
  OperatorCard,
  OperatorEligibleResponse,
  OperatorSession,
} from "~/types/operator";
import {
  buildUnlockPayload,
  isLocked,
  type UnlockInput,
} from "~/presentation/operatorLock";

export function useOperatorLock(perm: string) {
  const { data, refresh } = useFetch<OperatorSession>(
    "/api/v1/backstage/operator/session/",
    {
      key: "operator-session",
      server: true,
    },
  );

  const session = computed<OperatorSession | null>(() => data.value ?? null);
  // The device session exists when operator/session returned a device_user; when
  // unauthenticated the endpoint 403s (data null) → not authenticated → login prompt.
  const authenticated = computed(() => Boolean(session.value?.device_user));
  const locked = computed(() => isLocked(session.value));
  const operator = computed<OperatorCard | null>(
    () => session.value?.operator ?? null,
  );
  const requireOperator = computed(() =>
    Boolean(session.value?.require_operator),
  );
  // O operador ativo foi resetado pelo gerente (PIN temporário) → força a troca.
  const mustChange = computed(() => Boolean(session.value?.pin_must_change));

  const eligible = ref<OperatorCard[]>([]);
  async function loadEligible(): Promise<void> {
    try {
      const res = await $fetch<OperatorEligibleResponse>(
        "/api/v1/backstage/operator/eligible/",
        {
          query: { perm },
        },
      );
      eligible.value = res.operators ?? [];
    } catch {
      eligible.value = [];
    }
  }

  const busy = ref(false);

  async function unlock(input: Omit<UnlockInput, "perm">): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await $fetch("/api/v1/backstage/operator/unlock/", {
        method: "POST",
        body: buildUnlockPayload({ ...input, perm }),
      });
      await refresh();
      // Os fetches que rodaram TRANCADOS falharam (403) e ficariam com o erro grudado na
      // tela até o próximo poll (≤15s) — destravou, recarrega tudo já (paridade POS/Fournil).
      await refreshNuxtData();
      return true;
    } catch (err: any) {
      useSonner.error(
        err?.data?.detail || "Identificação inválida. Tente de novo.",
      );
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function lock(): Promise<void> {
    try {
      await $fetch("/api/v1/backstage/operator/lock/", {
        method: "POST",
        body: {},
      });
      await refresh();
    } catch {
      // best-effort: a failed lock leaves the operator active; surfaced on next action.
    }
  }

  const changeError = ref("");
  // Trocar o próprio PIN provando o atual. `operatorId` identifica o alvo na lock
  // screen (fluxo forçado, onde o "atual" é o PIN temporário); ausente = operador ativo.
  async function changePin(input: {
    operatorId?: number;
    currentPin: string;
    newPin: string;
  }): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    changeError.value = "";
    try {
      await $fetch("/api/v1/backstage/operator/pin/change/", {
        method: "POST",
        body: {
          operator_id: input.operatorId,
          current_pin: input.currentPin,
          new_pin: input.newPin,
        },
      });
      await refresh();
      return true;
    } catch (err: any) {
      changeError.value = err?.data?.detail || "Não foi possível trocar o PIN.";
      return false;
    } finally {
      busy.value = false;
    }
  }

  return {
    session,
    authenticated,
    locked,
    operator,
    requireOperator,
    mustChange,
    eligible,
    loadEligible,
    unlock,
    lock,
    changePin,
    changeError,
    refresh,
    busy,
  };
}
