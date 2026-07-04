// Política única do app: ao expirar a sessão do operador no meio do turno, o poll
// passa a 401/403. Reabre o gate re-buscando a sessão (refreshNuxtData) em vez de
// deixar "reconectando…" para sempre.
export function operatorSessionOnError(ctx: { response: { status: number } }): void {
  if (ctx.response.status === 401 || ctx.response.status === 403) {
    refreshNuxtData("operator-session");
  }
}
