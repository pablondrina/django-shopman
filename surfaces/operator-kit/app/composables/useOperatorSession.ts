import { readonly } from "vue";

import { isUnauthenticatedError } from "../utils/httpError";

/**
 * Sessão do operador: re-gate global em 401 (omotenashi de resiliência).
 *
 * Uma sessão de dispositivo pode expirar no meio do turno (cookie `.<zona>` revogado,
 * timeout do lado do Django). Sem isto, cada gravação (save_tab, close_sale…) falharia
 * silenciosamente com um toast genérico e o operador seguiria batendo numa sessão morta.
 * O transporte de comandos chama `flagIfUnauthenticated(err)` no catch; a shell observa
 * `expired` e sobe a tela de login. Estado compartilhado via `useState` (SSR-safe, um por
 * app) — o interceptor herdado pelos 4 apps de operador ([[project_operator_apps_crosssubdomain_auth_gap]]).
 */
export function useOperatorSession() {
  const expired = useState("operator-session-expired", () => false);

  /**
   * Se o erro for autenticação perdida (401), marca a sessão como expirada e devolve
   * true (o chamador ainda pode re-lançar para o tratamento de erro existente). 403 e
   * demais status não disparam re-gate — devolve false.
   */
  function flagIfUnauthenticated(error: unknown): boolean {
    if (isUnauthenticatedError(error)) {
      expired.value = true;
      return true;
    }
    return false;
  }

  /** Limpa o sinal após re-autenticar (login/desbloqueio bem-sucedido). */
  function reset() {
    expired.value = false;
  }

  return { expired: readonly(expired), flagIfUnauthenticated, reset };
}
