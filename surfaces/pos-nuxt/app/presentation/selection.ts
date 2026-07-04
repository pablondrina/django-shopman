// Multi-select shaping (spec §2.2, Shopify v11) — pure functions that turn the
// screen-state line selection into the batch affordances the cart toolbar shows.
// The selection itself is screen state (a set of cart `sku`s); fire/unfire need
// the server `line_id`s, which the backend already accepts as `line_ids[]` (Arc
// 4). No policy here — only derivation from the cart items + the selected set.
import type { POSCartItem } from "~/types/pos";

/** Cart sku stable key per line. */
export function selectedItems(items: POSCartItem[], selected: ReadonlySet<string>): POSCartItem[] {
  return items.filter((item) => selected.has(item.sku));
}

/** All selected lines that carry a server line_id (fire/unfire payloads). */
export function selectedLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return selectedItems(items, selected)
    .map((item) => item.line_id || "")
    .filter((id): id is string => Boolean(id));
}

/** Selected lines not yet fired → can be sent to the kitchen. */
export function firableLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return selectedItems(items, selected)
    .filter((item) => item.line_id && !item.fired)
    .map((item) => item.line_id as string);
}

/** Selected lines already fired → can be unfired. */
export function unfirableLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return selectedItems(items, selected)
    .filter((item) => item.line_id && item.fired)
    .map((item) => item.line_id as string);
}

export interface SelectionView {
  count: number;
  skus: string[];
  firableLineIds: string[];
  unfirableLineIds: string[];
  canFire: boolean;
  canUnfire: boolean;
}

/** Shape the batch toolbar from the current selection (pure). */
export function selectionView(items: POSCartItem[], selected: ReadonlySet<string>): SelectionView {
  const chosen = selectedItems(items, selected);
  const fire = firableLineIds(items, selected);
  const unfire = unfirableLineIds(items, selected);
  return {
    count: chosen.length,
    skus: chosen.map((item) => item.sku),
    firableLineIds: fire,
    unfirableLineIds: unfire,
    canFire: fire.length > 0,
    canUnfire: unfire.length > 0,
  };
}

/** Toggle a sku in a selection set, returning a NEW set (reactive-friendly). */
export function toggleSelected(selected: ReadonlySet<string>, sku: string): Set<string> {
  const next = new Set(selected);
  if (next.has(sku)) next.delete(sku);
  else next.add(sku);
  return next;
}

/** Drop selected skus no longer present in the cart (keeps selection consistent). */
export function pruneSelection(selected: ReadonlySet<string>, items: POSCartItem[]): Set<string> {
  const present = new Set(items.map((item) => item.sku));
  const next = new Set<string>();
  selected.forEach((sku) => {
    if (present.has(sku)) next.add(sku);
  });
  return next;
}
