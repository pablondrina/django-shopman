// Operator lock read/write (Opção C, Camada 2). Reads the terminal lock state,
// lists who may unlock this surface, and unlocks by PIN or badge / locks. All I/O
// goes through the django proxy (CSRF handled there). The surface's permission is
// passed so the picker + unlock are scoped to operators who can use THIS app.
import type { OperatorCard, OperatorEligibleResponse, OperatorSession } from "~/types/operator";
import { buildUnlockPayload, isLocked, type UnlockInput } from "~/presentation/operatorLock";

export function useOperatorLock(perm: string) {
  const { data, refresh } = useFetch<OperatorSession>("/api/v1/backstage/operator/session/", {
    key: "operator-session",
    server: true,
  });

  const session = computed<OperatorSession | null>(() => data.value ?? null);
  const locked = computed(() => isLocked(session.value));
  const operator = computed<OperatorCard | null>(() => session.value?.operator ?? null);
  const requireOperator = computed(() => Boolean(session.value?.require_operator));

  const eligible = ref<OperatorCard[]>([]);
  async function loadEligible(): Promise<void> {
    try {
      const res = await $fetch<OperatorEligibleResponse>("/api/v1/backstage/operator/eligible/", {
        query: { perm },
      });
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
      return true;
    } catch (err: any) {
      useSonner.error(err?.data?.detail || "Identificação inválida. Tente de novo.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function lock(): Promise<void> {
    try {
      await $fetch("/api/v1/backstage/operator/lock/", { method: "POST", body: {} });
      await refresh();
    } catch {
      // best-effort: a failed lock leaves the operator active; surfaced on next action.
    }
  }

  return { session, locked, operator, requireOperator, eligible, loadEligible, unlock, lock, refresh, busy };
}
