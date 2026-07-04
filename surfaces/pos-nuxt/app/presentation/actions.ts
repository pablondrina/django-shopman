// Presentation — Action → affordance.
//
// The Projection (data, owned by the orchestrator) carries `actions: Action[]`,
// each a sealed command contract (enabled/reason/href/method/confirmation). The
// screen never invents a CTA nor decides whether it may run — it renders the
// affordance the Projection offers. This module is the pure mapping from the
// raw `Action[]` to a render-ready affordance: it resolves the concrete href
// (substituting path params) and reflects enabled/reason verbatim. Zero policy.

import type { Action } from "~/types/pos";
import { actionHref, concreteActionHref } from "~/utils/posIntent";

export interface ActionAffordance {
  ref: string;
  /** The orchestrator offered this action in the Projection. */
  present: boolean;
  label: string;
  priority: string;
  /** present && the Projection marked it enabled. */
  enabled: boolean;
  /** Why it is unavailable (Projection copy); empty when enabled. */
  reason: string;
  /** Concrete href with path params substituted (or the fallback). */
  href: string;
  method: string;
  idempotency: string;
  confirmation: Record<string, unknown>;
}

export function findAction(actions: Action[] | undefined, ref: string): Action | undefined {
  return actions?.find((action) => action.ref === ref);
}

/** Whether the orchestrator offered this action at all. */
export function hasAction(actions: Action[] | undefined, ref: string): boolean {
  return Boolean(findAction(actions, ref));
}

/**
 * Resolve a single Action into a render-ready affordance. `params` are
 * substituted into a templated href (e.g. `{tab_ref}`); `fallbackHref` keeps a
 * screen functional if the Projection omits the action's href but the action
 * itself is present (the contract still carries enabled/reason).
 */
export function resolveAffordance(
  actions: Action[] | undefined,
  ref: string,
  options: { params?: Record<string, string>; fallbackHref?: string } = {},
): ActionAffordance {
  const action = findAction(actions, ref);
  const fallbackHref = options.fallbackHref ?? "";
  const href = options.params
    ? concreteActionHref(actions, ref, fallbackHref, options.params)
    : actionHref(actions, ref, fallbackHref);
  return {
    ref,
    present: Boolean(action),
    label: action?.label ?? "",
    priority: action?.priority ?? "secondary",
    enabled: Boolean(action?.enabled),
    reason: action?.reason ?? "",
    href,
    method: action?.method ?? "POST",
    idempotency: action?.idempotency ?? "none",
    confirmation: action?.confirmation ?? {},
  };
}
