// Presentation — kitchen handoff / fire-to-kitchen (spec §2.5, anti-fraud).
//
// Pure transforms for the progressive fire affordance: which lines are still
// firable vs already `fired`, the unfired count, the fire-button view (label
// from the `fire_tab` Action — never an invented CTA — plus the live delta
// count), and the per-line state that drives the badge + the unfire affordance.
//
// Fire is the named, auditable act (food to the kitchen before payment), so the
// state must be unambiguous: the operator always sees exactly what has gone to
// the kitchen and what is still pending. Firing dispatches only the unfired
// delta (the Core dedups by `fired_line_ids_for_session`, so nothing duplicates);
// unfire cancels a single still-cancellable line. Zero policy — capability and
// per-line `fired` come from the Projection; this module only shapes them.

import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";

/** Lines already sent to the kitchen. */
export function firedCount(items: POSCartItem[]): number {
  return items.filter((item) => item.fired).length;
}

/** Lines still to be sent (the delta a fire would dispatch). */
export function unfiredCount(items: POSCartItem[]): number {
  return items.filter((item) => !item.fired).length;
}

/** Every line is in the kitchen (and there is at least one line). */
export function allLinesFired(items: POSCartItem[]): boolean {
  return items.length > 0 && items.every((item) => item.fired);
}

export type KitchenLineState = "unfired" | "fired" | "fired_cancellable";

/**
 * Per-line kitchen state. A fired line is cancellable only when the channel
 * offers unfire AND the line carries a server `line_id` to target; otherwise it
 * shows as a non-interactive "in the kitchen" marker.
 */
export function kitchenLineState(item: POSCartItem, options: { canUnfire: boolean }): KitchenLineState {
  if (!item.fired) return "unfired";
  return options.canUnfire && Boolean(item.line_id) ? "fired_cancellable" : "fired";
}

const ALL_FIRED_LABEL = "Tudo na cozinha";

export interface FireBarView {
  /** The channel offers fire, the tab is open, and there are lines. */
  visible: boolean;
  /** `fire_tab` Action label + the live delta count, or the all-fired label. */
  label: string;
  unfired: number;
  fired: number;
  /** Nothing left to fire, or busy, or the Action is currently disabled. */
  disabled: boolean;
  allFired: boolean;
}

/**
 * The progressive fire button. Visible only when the `fire_tab` Action is
 * present, a tab is open, and the ticket has lines. The label is the Action's
 * own copy plus the unfired delta count; when nothing is left to fire it shows
 * the all-fired state and disables. Honors the Action's `enabled` verbatim.
 */
export function fireBarView(args: {
  items: POSCartItem[];
  affordance: ActionAffordance;
  hasOpenTab: boolean;
  busy: boolean;
}): FireBarView {
  const unfired = unfiredCount(args.items);
  const fired = firedCount(args.items);
  const visible = args.affordance.present && args.hasOpenTab && args.items.length > 0;
  return {
    visible,
    label: unfired ? `${args.affordance.label} (${unfired})` : ALL_FIRED_LABEL,
    unfired,
    fired,
    disabled: args.busy || !args.affordance.enabled || unfired === 0,
    allFired: allLinesFired(args.items),
  };
}
