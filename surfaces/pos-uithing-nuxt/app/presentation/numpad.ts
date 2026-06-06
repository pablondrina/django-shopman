// Presentation — quantity/discount numpad buffer (spec §2.2: teclado→qtd).
//
// Pure string-buffer logic shared by the cart numpad and the physical keyboard.
// The PIN buffer is a separate concern in `utils/operatorLock.ts`; this one
// edits the active line's quantity or per-line discount percentage. No policy:
// the orchestrator validates and re-prices on save/review.

/**
 * Append a digit. After (re)selecting a line the buffer is "fresh": the first
 * keystroke replaces the seeded value; the rest append, capped at `maxLength`.
 */
export function pushDigit(
  buffer: string,
  digit: string,
  options: { fresh: boolean; maxLength: number },
): string {
  if (!/^[0-9]$/.test(digit)) return buffer;
  const next = options.fresh ? digit : `${buffer}${digit}`;
  return next.slice(0, options.maxLength);
}

export function popDigit(buffer: string): string {
  return buffer.slice(0, -1);
}

/** Parse the buffer as a quantity, clamped to [0, max]. */
export function clampQty(buffer: string, max: number): number {
  const parsed = Number.parseInt(buffer || "0", 10) || 0;
  return Math.min(max, Math.max(0, parsed));
}

/** Parse the buffer as a discount percentage, clamped to [0, 100]. */
export function clampPercent(buffer: string): number {
  const parsed = Number.parseInt(buffer || "0", 10) || 0;
  return Math.min(100, Math.max(0, parsed));
}
