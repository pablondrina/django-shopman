import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import type { OperatorCard } from "~/utils/operatorLock";
import { isIdleBeyond, unlockBody } from "~/utils/operatorLock";

interface UnlockResponse {
  ok: boolean;
  operator?: OperatorCard;
  error?: { code?: string; message?: string };
}

/**
 * Operator lock state for the POS terminal. The terminal is authenticated as a
 * staff user; the active operator is a PIN-established identity layer for
 * attribution. Auto-locks after `autoLockSeconds` of inactivity — no
 * "stay logged in". Reusable across operator surfaces (POS/KDS/orders).
 */
export function useOperatorLock(opts: {
  initialOperator?: OperatorCard | null;
  autoLockSeconds?: number;
}) {
  const action = usePosAction();
  const activeOperator = ref<OperatorCard | null>(opts.initialOperator ?? null);
  const busy = ref(false);
  const error = ref("");
  const locked = computed(() => activeOperator.value === null);

  let lastActivity = Date.now();
  let cleanup: (() => void) | null = null;

  async function unlock(operatorId: number, pin: string): Promise<boolean> {
    busy.value = true;
    error.value = "";
    try {
      const res = await action.call<UnlockResponse>(
        "/api/v1/backstage/operator/unlock/",
        { body: unlockBody(operatorId, pin, "backstage.operate_pos") },
      );
      if (res.ok && res.operator) {
        activeOperator.value = res.operator;
        lastActivity = Date.now();
        return true;
      }
      error.value = res.error?.message || "PIN inválido.";
      return false;
    }
    catch (e: unknown) {
      const data = (e as { data?: { error?: { message?: string } } })?.data;
      error.value = data?.error?.message || "PIN inválido.";
      return false;
    }
    finally {
      busy.value = false;
    }
  }

  async function lock(): Promise<void> {
    try {
      await action.call("/api/v1/backstage/operator/lock/");
    }
    catch {
      // Locking is local-first; a failed server call still locks the screen.
    }
    activeOperator.value = null;
    error.value = "";
  }

  function markActivity() {
    lastActivity = Date.now();
  }

  onMounted(() => {
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown"];
    events.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));
    const id = window.setInterval(() => {
      if (!locked.value && isIdleBeyond(lastActivity, Date.now(), opts.autoLockSeconds ?? 60)) {
        lock();
      }
    }, 5000);
    cleanup = () => {
      events.forEach((e) => window.removeEventListener(e, markActivity));
      window.clearInterval(id);
    };
  });

  onBeforeUnmount(() => cleanup?.());

  return { activeOperator, locked, busy, error, unlock, lock };
}
