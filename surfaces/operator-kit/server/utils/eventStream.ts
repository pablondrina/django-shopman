import {
  getRequestHeader,
  setResponseHeader,
  setResponseStatus,
  type H3Event,
} from "h3";

// Proxy SSE same-origin compartilhado das superfícies de operador (layer). O
// EventSource do app conecta em uma rota /sse/... do BFF e aqui repassamos o
// cookie de sessão e fazemos streaming do eventstream do Django, sem
// materializar o corpo.
//
// Same-origin de propósito: não há CORS no projeto e o cookie `.<zona>` viaja
// no proxy — em dev e em prod, o EventSource conecta no próprio host do app.
// Diferente do proxyDjangoApi (que bufferiza), SSE é corpo infinito — precisa
// de `fetch` nativo devolvendo o ReadableStream. Se o Django recusar (403/404
// p/ não-autorizado), propagamos o status para o EventSource falhar de vez
// (não reconecta) e a página seguir no fallback (poll).
//
// Mesmo transporte do storefront (server/utils/eventStream.ts de lá) — ver
// ADR-016 (SSE-first): push por SSE em cima de um fetch canônico que continua
// sendo a fonte da verdade.
export async function proxyEventStream(
  event: H3Event,
  upstreamPath: string,
): Promise<ReadableStream<Uint8Array> | string> {
  const config = useRuntimeConfig(event);

  const controller = new AbortController();
  // Cliente fechou o EventSource (troca de página/aba) → aborta o upstream para o
  // Django derrubar a inscrição em vez de deixar uma conexão pendurada.
  event.node.req.on("close", () => controller.abort());

  const target = `${config.djangoBaseUrl}${upstreamPath}`;
  const headers: Record<string, string> = { accept: "text/event-stream" };

  const cookie = getRequestHeader(event, "cookie");
  if (cookie) headers.cookie = cookie;

  // Resume após reconexão do EventSource, quando o canal é reliable.
  const lastEventId = getRequestHeader(event, "last-event-id");
  if (lastEventId) headers["last-event-id"] = lastEventId;

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: "GET", headers, signal: controller.signal });
  } catch {
    // Django fora do ar / rede caiu → 502; o fallback da página cobre a lacuna.
    setResponseStatus(event, 502);
    return "";
  }

  if (!upstream.ok || !upstream.body) {
    setResponseStatus(event, upstream.status || 502);
    return "";
  }

  setResponseHeader(event, "content-type", "text/event-stream");
  setResponseHeader(event, "cache-control", "no-cache, no-transform");
  setResponseHeader(event, "connection", "keep-alive");
  // Desliga o buffering de proxies (nginx) para o SSE fluir em tempo real.
  setResponseHeader(event, "x-accel-buffering", "no");
  return upstream.body as ReadableStream<Uint8Array>;
}
