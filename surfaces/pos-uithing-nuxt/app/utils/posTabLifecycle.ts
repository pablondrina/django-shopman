export interface POSTabLifecycleProjection {
  create_action_ref?: string;
  open_action_ref?: string;
  save_action_ref?: string;
  clear_action_ref?: string;
  tab_code_max_digits?: number;
  requires_open_tab_for_cart?: boolean;
  requires_tab_before_save?: boolean;
  allows_operator_tab_creation?: boolean;
  draft_association_target_states?: string[];
  occupied_tab_selection?: string;
}

function tabLifecycle(capabilities: Record<string, unknown> | null | undefined): POSTabLifecycleProjection {
  const raw = capabilities?.tab_lifecycle;
  return raw && typeof raw === "object" ? raw as POSTabLifecycleProjection : {};
}

export function requiresOpenTabForCart(capabilities: Record<string, unknown> | null | undefined): boolean {
  return tabLifecycle(capabilities).requires_open_tab_for_cart !== false;
}

export function requiresTabBeforeSave(capabilities: Record<string, unknown> | null | undefined): boolean {
  return tabLifecycle(capabilities).requires_tab_before_save !== false;
}

export function tabCodeMaxDigits(capabilities: Record<string, unknown> | null | undefined): number {
  const value = tabLifecycle(capabilities).tab_code_max_digits;
  return Number.isInteger(value) && Number(value) > 0 ? Number(value) : 8;
}

export function draftAssociationTargetStates(capabilities: Record<string, unknown> | null | undefined): string[] {
  const states = tabLifecycle(capabilities).draft_association_target_states;
  return Array.isArray(states) && states.length ? states.map(String) : ["empty"];
}
