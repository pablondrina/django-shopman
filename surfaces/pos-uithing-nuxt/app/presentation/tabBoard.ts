// Presentation — Tab Board shaping (spec §2.3).
//
// Pure transforms over the tabs Projection: ordering, the in-use/all filter,
// and the per-tab card view. Status labels and totals come pre-resolved from
// the serializer (Arc 1 E3/E4); this module only orders and composes them into
// the shape the board renders. No availability or price arithmetic.

import type { POSTabProjection } from "~/types/pos";

export type TabFilter = "all" | "in_use";

/** Open tabs first, then by display ref (numeric-aware, pt-BR). */
export function sortTabs(tabs: POSTabProjection[]): POSTabProjection[] {
  return [...tabs].sort((a, b) => {
    const aOpen = a.state === "in_use" ? 0 : 1;
    const bOpen = b.state === "in_use" ? 0 : 1;
    return aOpen - bOpen
      || a.display_ref.localeCompare(b.display_ref, "pt-BR", { numeric: true });
  });
}

export function filterTabs(tabs: POSTabProjection[], filter: TabFilter): POSTabProjection[] {
  return filter === "in_use" ? tabs.filter((tab) => tab.state === "in_use") : tabs;
}

export function countOpenTabs(tabs: POSTabProjection[]): number {
  return tabs.filter((tab) => tab.state === "in_use").length;
}

export interface TabCardView {
  ref: string;
  displayRef: string;
  isInUse: boolean;
  isFree: boolean;
  /** Fired to the kitchen and not yet paid — the loud state of the board. */
  isUnpaid: boolean;
  statusLabel: string;
  /** Customer name, falling back to an items preview, then an em dash. */
  identity: string;
  /** Line summary: item count + total, or the free-tab affordance. */
  summary: string;
  selected: boolean;
}

/**
 * Shape a free-text tab reference for input: strip control chars and the
 * channel's disallowed characters, collapse whitespace, and clamp to the
 * channel's max length. The allowed set comes from the tab-lifecycle capability
 * (Projection-driven) — this only enforces the shape, never the policy.
 */
export function sanitizeTabRef(
  value: string,
  options: { maxLength: number; disallowedChars: string[] },
): string {
  const disallowed = new Set(options.disallowedChars);
  return String(value || "")
    .replace(/[\r\n\t]/g, "")
    .split("")
    .filter((char) => !disallowed.has(char))
    .join("")
    .replace(/\s+/g, " ")
    .slice(0, options.maxLength);
}

export function tabCardView(tab: POSTabProjection, selectedRef = ""): TabCardView {
  const isInUse = tab.state === "in_use";
  const hasItems = tab.item_count > 0;
  return {
    ref: tab.ref,
    displayRef: tab.display_ref,
    isInUse,
    isFree: !hasItems,
    isUnpaid: Boolean(tab.fired),
    statusLabel: tab.status_label,
    identity: tab.customer_name || tab.items_preview || "—",
    summary: hasItems
      ? `${tab.item_count} ${tab.item_count === 1 ? "item" : "itens"} · ${tab.total_display}`
      : "Comanda livre",
    selected: Boolean(selectedRef) && tab.ref === selectedRef,
  };
}
