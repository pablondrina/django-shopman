// Presentation — move lines between tabs (spec §2.3, price frozen on move).
//
// Pure transforms for the "mover itens" dialog: which modes the channel offers
// (config-driven from `tab_manipulation`), the line identity used to address a
// move, the per-mode line-selection requirement, the submit gate, and the
// command payload shaped per mode (split/transfer/merge). Zero policy lives in
// the screen — the dialog renders these and emits the payload to `submitMove`,
// which calls the `move_tab_lines` Action. The Core freezes each line's price as
// charged on the source tab; this module only flags that invariant so the
// screen can state it, never re-prices.

import type { POSCartItem, POSTabProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

export type MoveMode = "split" | "transfer" | "merge";

export interface MoveModeOption {
  ref: MoveMode;
  label: string;
}

const MODE_LABELS: Record<MoveMode, string> = {
  split: "Dividir",
  transfer: "Transferir",
  merge: "Juntar",
};

const MODE_ORDER: MoveMode[] = ["split", "transfer", "merge"];

interface TabManipulationCapability {
  allows_split?: boolean;
  allows_transfer?: boolean;
  allows_merge?: boolean;
  freezes_price_on_move?: boolean;
}

function asCapability(capability: unknown): TabManipulationCapability | null {
  return capability && typeof capability === "object" ? (capability as TabManipulationCapability) : null;
}

/**
 * Move modes the channel offers, in canonical order. Driven by the
 * `tab_manipulation` capability (`allows_split/transfer/merge`); when the
 * capability is absent (defensive), all three are offered so the dialog stays
 * functional.
 */
export function availableMoveModes(capability: unknown): MoveModeOption[] {
  const cap = asCapability(capability);
  const allowed: Record<MoveMode, boolean> = cap
    ? { split: Boolean(cap.allows_split), transfer: Boolean(cap.allows_transfer), merge: Boolean(cap.allows_merge) }
    : { split: true, transfer: true, merge: true };
  return MODE_ORDER.filter((mode) => allowed[mode]).map((mode) => ({ ref: mode, label: MODE_LABELS[mode] }));
}

/**
 * Whether the move freezes each line's price (domain invariant of `move_lines`).
 * Driven by the capability; defaults to `true` because the Core always freezes
 * the as-charged price on a move.
 */
export function freezesPriceOnMove(capability: unknown): boolean {
  const cap = asCapability(capability);
  return cap ? cap.freezes_price_on_move !== false : true;
}

/**
 * Identity used to address a line in a move. Prefers the server `line_id` (the
 * move op needs it); falls back to the sku when a freshly added line has not
 * been persisted yet (the dialog reloads the tab first to populate `line_id`).
 */
export function moveLineId(item: POSCartItem): string {
  return item.line_id || item.sku;
}

/** Split and transfer act on selected lines; merge moves the whole tab. */
export function modeNeedsSelection(mode: MoveMode): boolean {
  return mode !== "merge";
}

export interface MoveLineView {
  id: string;
  label: string;
  amountDisplay: string;
}

export function moveLineView(item: POSCartItem): MoveLineView {
  return {
    id: moveLineId(item),
    label: `${item.qty}x ${item.name}`,
    amountDisplay: formatBRL(item.price_q * item.qty),
  };
}

/** Selected line ids in tab order (a stable, deterministic payload order). */
export function selectedLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return items.map(moveLineId).filter((id) => selected.has(id));
}

export interface MoveSubmitState {
  mode: MoveMode;
  selectedIds: string[];
  splitRef: string;
  targetSessionKey: string;
  itemCount: number;
  busy: boolean;
}

/** Whether the move is ready to submit, per mode. */
export function canSubmitMove(state: MoveSubmitState): boolean {
  if (state.busy) return false;
  if (state.mode === "split") return state.selectedIds.length > 0 && state.splitRef.trim().length > 0;
  if (state.mode === "transfer") return state.selectedIds.length > 0 && Boolean(state.targetSessionKey);
  return Boolean(state.targetSessionKey) && state.itemCount > 0; // merge
}

export interface MovePayload {
  mode: MoveMode;
  lineIds: string[];
  toTabRef?: string;
  toSessionKey?: string;
  closeSource?: boolean;
}

/**
 * Shape the `move_tab_lines` payload for the chosen mode, or `null` when the
 * mode's required input is missing (re-validates the submit gate). Merge moves
 * every line and closes the now-empty source tab.
 */
export function buildMovePayload(args: {
  mode: MoveMode;
  items: POSCartItem[];
  selectedIds: string[];
  splitRef: string;
  targetSessionKey: string;
}): MovePayload | null {
  if (args.mode === "split") {
    const toTabRef = args.splitRef.trim();
    if (!args.selectedIds.length || !toTabRef) return null;
    return { mode: "split", lineIds: args.selectedIds, toTabRef };
  }
  if (args.mode === "transfer") {
    if (!args.selectedIds.length || !args.targetSessionKey) return null;
    return { mode: "transfer", lineIds: args.selectedIds, toSessionKey: args.targetSessionKey };
  }
  if (!args.targetSessionKey || !args.items.length) return null;
  return {
    mode: "merge",
    lineIds: args.items.map(moveLineId),
    toSessionKey: args.targetSessionKey,
    closeSource: true,
  };
}

export interface MoveTargetOption {
  sessionKey: string;
  label: string;
}

/** Destination tabs for transfer/merge (those backed by an open session). */
export function moveTargetOptions(tabs: POSTabProjection[]): MoveTargetOption[] {
  return tabs
    .filter((tab) => tab.session_key)
    .map((tab) => ({
      sessionKey: tab.session_key,
      label: tab.customer_name ? `#${tab.display_ref} · ${tab.customer_name}` : `#${tab.display_ref}`,
    }));
}

/** First available destination session key (the dialog's default target). */
export function defaultMoveTarget(tabs: POSTabProjection[]): string {
  return moveTargetOptions(tabs)[0]?.sessionKey || "";
}
