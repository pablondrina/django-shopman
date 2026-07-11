// Rota SSE same-origin do board da estação: /sse/kds/<ref> → streaming do
// eventstream do Django (canal /gestor/events/kds/<ref>/). O transporte
// (repasse de cookie/last-event-id, streaming do corpo, propagação de status)
// vive na layer operator-kit (server/utils/eventStream.ts, auto-importado).
export default defineEventHandler((event) => {
  const ref = getRouterParam(event, "ref") || "";
  if (!ref) {
    setResponseStatus(event, 400);
    return "";
  }
  return proxyEventStream(event, `/gestor/events/kds/${encodeURIComponent(ref)}/`);
});
