import { computed, watch } from "vue";

/**
 * Estado do rail de operador (`OperatorRail`) — a largura que o operador escolhe.
 *
 * Três estados, do mais enxuto ao mais explícito:
 *   - `collapsed` — some, sobra só um puxador fino (máxima área de trabalho).
 *   - `compact`   — só ícone (~w-14), o padrão histórico do POS.
 *   - `extended`  — ícone + rótulo (funções comuns nomeadas).
 *
 * Persistido por dispositivo via `useCookie` (host-only → por app/estação, e SSR-safe: o
 * servidor já renderiza a largura certa, sem flash de hidratação). O estado reativo mora
 * num `useState` compartilhado (uma verdade por app) com write-through pro cookie. É o
 * operador quem manda: [[feedback_transparent_timeouts]] não se aplica (preferência, não
 * TTL), mas a escolha nunca se perde entre turnos.
 */
export type RailState = "collapsed" | "compact" | "extended";

/** Do mais enxuto ao mais explícito — a ordem que `expand`/`collapse` percorrem. */
export const RAIL_STATES: readonly RailState[] = ["collapsed", "compact", "extended"] as const;

const DEFAULT_STATE: RailState = "compact";

function normalize(value: unknown): RailState {
  return RAIL_STATES.includes(value as RailState) ? (value as RailState) : DEFAULT_STATE;
}

export function useRailState() {
  // Default por app (só vale quando ainda não há cookie): a Central começa colapsada;
  // as demais, compactas. Vem do runtimeConfig (kit define; cada app pode sobrescrever).
  const appDefault = normalize(useRuntimeConfig().public.railDefaultState);

  // Fonte persistida (por dispositivo). Um ano; sameSite lax (navegação normal do operador).
  const cookie = useCookie<RailState>("operator-rail", {
    default: () => appDefault,
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 365,
    path: "/",
  });

  // Verdade reativa compartilhada no app (SSR-safe), semeada pelo cookie e higienizada
  // contra valor inválido/legado.
  const state = useState<RailState>("operator-rail-state", () => normalize(cookie.value));

  // Write-through: toda mudança persiste (no cliente; no servidor o cookie já é a origem).
  watch(state, (next) => {
    cookie.value = next;
  });

  const isCollapsed = computed(() => state.value === "collapsed");
  const isCompact = computed(() => state.value === "compact");
  const isExtended = computed(() => state.value === "extended");
  /** Rótulos só aparecem no estado estendido. */
  const showLabels = computed(() => state.value === "extended");

  /** Vai direto a um estado (ignora valor inválido). */
  function set(next: RailState) {
    if (RAIL_STATES.includes(next)) state.value = next;
  }

  /**
   * Próximo estado, em anel: collapsed → compact → extended → collapsed. É o gesto do
   * único controle no cabeçalho do app — um toque avança a largura; ao chegar no
   * estendido, o toque seguinte oculta a barra por inteiro.
   */
  function cycle() {
    const i = RAIL_STATES.indexOf(state.value);
    state.value = RAIL_STATES[(i + 1) % RAIL_STATES.length]!;
  }

  return { state, isCollapsed, isCompact, isExtended, showLabels, set, cycle };
}
