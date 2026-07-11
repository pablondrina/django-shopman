// Presentation — operator lock (Opção C). Pure transforms over the operator
// session projection. The barcode badge scanner behaves like a keyboard that
// types the token fast and ends with Enter; the PIN is typed on an on-screen pad.
// No network here — the composable owns I/O; this owns shape + the unlock payload.
import type { OperatorSession } from "../types/operator";

/** The overlay shows only when the gate is on AND nobody is operating. When the
 *  gate is off (SHOPMAN_REQUIRE_ACTIVE_OPERATOR=false) the surface is never locked. */
export function isLocked(session: OperatorSession | null): boolean {
  return Boolean(session?.require_operator && session?.locked);
}

export function operatorName(session: OperatorSession | null): string {
  return session?.operator?.name || session?.operator?.username || "";
}

/** Badge tokens are 24 hex chars (doorman ``issue_badge`` = token_hex(12)).
 *  Used to auto-route a scan to the badge unlock without an explicit mode toggle. */
export function isLikelyBadge(value: string): boolean {
  return /^[0-9a-f]{24}$/i.test(value.trim());
}

export interface UnlockInput {
  operatorId?: number | string | null;
  pin?: string;
  badge?: string;
  perm?: string;
}

/** The POST body for operator/unlock/. Badge wins when present; otherwise the
 *  picked operator + typed PIN. ``perm`` (the surface capability) restricts who
 *  may unlock here. */
export function buildUnlockPayload(input: UnlockInput): Record<string, unknown> {
  const badge = (input.badge ?? "").trim();
  const perm = input.perm ? { perm: input.perm } : {};
  if (badge) {
    return { badge, ...perm };
  }
  return { operator_id: input.operatorId ?? "", pin: (input.pin ?? "").trim(), ...perm };
}

/** Whether the PIN entry is ready to submit (an operator picked + a non-trivial PIN). */
export function canSubmitPin(operatorId: number | null, pin: string): boolean {
  return operatorId != null && pin.trim().length >= 4;
}

/** Append a digit to the PIN buffer, capped (keypads shouldn't grow unbounded). */
export function appendPinDigit(pin: string, digit: string, max = 8): string {
  if (!/^[0-9]$/.test(digit)) return pin;
  return pin.length >= max ? pin : pin + digit;
}
