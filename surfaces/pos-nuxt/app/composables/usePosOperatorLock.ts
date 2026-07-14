import { onBeforeUnmount, onMounted, ref } from "vue";

import type { OperatorCard } from "~/utils/operatorLock";
import { isIdleBeyond, unlockBody } from "~/utils/operatorLock";

interface UnlockResponse {
  ok: boolean;
  operator?: OperatorCard;
  error?: { code?: string; message?: string };
}

/**
 * Operator lock state for the POS terminal.
 *
 * The auth source of truth is the SHARED operator lock (operator-kit's
 * `useOperatorLock`): the device session, the active operator, the forced-change
 * flag and the eligible-operator picker all come from `operator/session/` and
 * `operator/eligible/?perm=`, which are gated on the DEVICE session only — never
 * on an active operator. This is what the other four operator apps already do.
 *
 * The POS reads those endpoints INDEPENDENTLY of `/pos/` (the terminal
 * projection), which is gated on the active operator and therefore 403s while the
 * station is locked. Deriving the lock screen from `/pos/` was circular: the PIN
 * picker needed data that only exists once someone has already unlocked (C1-01).
 *
 * On top of the shared read, the POS keeps two surface-specific behaviours: an
 * auto-lock idle timer (kiosk at a shared counter) and inline PIN-error reporting
 * on its own lock screen (`PosLockScreen`), rather than the kit overlay's toast.
 */
export function usePosOperatorLock(opts: {
  autoLockSeconds?: () => number;
}) {
  const action = usePosAction();
  const {
    authenticated,
    locked,
    operator: activeOperator,
    mustChange,
    eligible,
    loadEligible,
    refresh: refreshSession,
  } = useOperatorLock("backstage.operate_pos");

  const busy = ref(false);
  const error = ref("");

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
        lastActivity = Date.now();
        await refreshSession();
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
      // Locking is local-first; a failed server call still drops the operator once
      // the session refresh lands (or on the next poll).
    }
    error.value = "";
    await refreshSession();
  }

  // Operator rotates their own PIN, proving the current one (the backend authorizes
  // on that). `operatorId` targets the picked/active operator; forced flow passes the
  // temp PIN as `currentPin`. The caller refreshes so the must-change flag clears.
  const changeError = ref("");
  async function changePin(operatorId: number, currentPin: string, newPin: string): Promise<boolean> {
    busy.value = true;
    changeError.value = "";
    try {
      await action.call("/api/v1/backstage/operator/pin/change/", {
        body: { operator_id: operatorId, current_pin: currentPin, new_pin: newPin },
      });
      return true;
    }
    catch (e: unknown) {
      const data = (e as { data?: { detail?: string } })?.data;
      changeError.value = data?.detail || "Não foi possível trocar o PIN.";
      return false;
    }
    finally {
      busy.value = false;
    }
  }

  function markActivity() {
    lastActivity = Date.now();
  }

  onMounted(() => {
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown"];
    events.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));
    const id = window.setInterval(() => {
      if (!locked.value && isIdleBeyond(lastActivity, Date.now(), opts.autoLockSeconds?.() ?? 60)) {
        lock();
      }
    }, 5000);
    cleanup = () => {
      events.forEach((e) => window.removeEventListener(e, markActivity));
      window.clearInterval(id);
    };
  });

  onBeforeUnmount(() => cleanup?.());

  return {
    activeOperator,
    locked,
    authenticated,
    mustChange,
    eligible,
    loadEligible,
    busy,
    error,
    unlock,
    lock,
    changePin,
    changeError,
    refreshSession,
  };
}
