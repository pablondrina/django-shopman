// Pure logic ainda usada pelo PDV: o teclado de PIN (PosPinPad, reusado pelo diálogo
// de autorização de gerente) e o auto-lock de kiosk (usePosAutoLock). A identificação
// (PIN/crachá) em si mora no lock compartilhado do kit (useOperatorLock/OperatorLock).
// Framework-free para ser testável sem runtime Nuxt.

/** Whether the terminal should auto-lock given idle time. timeoutSec<=0 disables. */
export function isIdleBeyond(lastActivityMs: number, nowMs: number, timeoutSec: number): boolean {
  if (timeoutSec <= 0) return false;
  return nowMs - lastActivityMs >= timeoutSec * 1000;
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
