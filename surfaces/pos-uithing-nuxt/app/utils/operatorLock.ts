// Pure logic for the POS operator lock screen. Kept framework-free so it can be
// unit-tested without a Nuxt runtime (the composable is the thin glue around it).

export interface OperatorCard {
  id: number;
  username: string;
  name: string;
}

/** Whether the terminal should auto-lock given idle time. timeoutSec<=0 disables. */
export function isIdleBeyond(lastActivityMs: number, nowMs: number, timeoutSec: number): boolean {
  if (timeoutSec <= 0) return false;
  return nowMs - lastActivityMs >= timeoutSec * 1000;
}

/** Build the unlock request body. PIN is sent as-is (digits); server hashes/validates. */
export function unlockBody(operatorId: number | string, pin: string): Record<string, unknown> {
  return { operator_id: operatorId, pin };
}

/** Append a digit to a PIN buffer, capped at maxLength. Ignores non-digits. */
export function appendPinDigit(current: string, digit: string, maxLength: number): string {
  if (!/^[0-9]$/.test(digit)) return current;
  if (current.length >= maxLength) return current;
  return current + digit;
}

/** Remove the last digit from a PIN buffer. */
export function backspacePin(current: string): string {
  return current.slice(0, -1);
}
