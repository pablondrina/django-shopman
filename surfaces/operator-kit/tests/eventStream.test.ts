// Transporte SSE do BFF das superfícies de operador: proxyEventStream faz
// streaming same-origin do eventstream do Django. Exercita as decisões de
// transporte — repasse de cookie/last-event-id, alvo correto, streaming do
// corpo em 200 e propagação de status quando o Django recusa (403/404) ou cai
// (→ 502). Espelha a suíte do storefront (orderStream.test.ts).
import { IncomingMessage, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { createEvent, type H3Event } from "h3";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { proxyEventStream } from "../server/utils/eventStream";
import { ssePath } from "../app/utils/ssePath";

const DJANGO = "http://django.internal:8000";

function makeEvent(headers: Record<string, string> = {}): {
  event: H3Event;
  res: ServerResponse;
  req: IncomingMessage;
} {
  const req = new IncomingMessage(new Socket());
  req.method = "GET";
  req.url = "/sse/orders";
  req.headers = headers;
  const res = new ServerResponse(req);
  const event = createEvent(req, res);
  return { event, res, req };
}

function streamResponse(status: number, ok: boolean) {
  const body = ok
    ? new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(new Uint8Array([1]));
          c.close();
        },
      })
    : null;
  return { ok, status, body };
}

describe("proxyEventStream — BFF SSE das superfícies de operador", () => {
  let calls: Array<{ url: string; options: any }>;

  beforeEach(() => {
    calls = [];
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: DJANGO }));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options: any) => {
        calls.push({ url, options });
        return Promise.resolve(streamResponse(200, true));
      }),
    );
  });

  it("faz streaming do eventstream do Django com cookie e headers de SSE", async () => {
    const { event, res } = makeEvent({
      cookie: "sessionid=s1; csrftoken=t",
      "last-event-id": "evt-9",
    });

    const result = await proxyEventStream(event, "/gestor/events/orders/");

    // Alvo correto + método GET.
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(`${DJANGO}/gestor/events/orders/`);
    // Cookie de sessão e Last-Event-ID (resume) repassados; Accept de SSE.
    expect(calls[0]!.options.headers.cookie).toBe("sessionid=s1; csrftoken=t");
    expect(calls[0]!.options.headers["last-event-id"]).toBe("evt-9");
    expect(calls[0]!.options.headers.accept).toBe("text/event-stream");
    // Corpo é o ReadableStream do upstream (não bufferizado).
    expect(result).toBeInstanceOf(ReadableStream);
    // Headers de SSE na resposta.
    expect(res.getHeader("content-type")).toBe("text/event-stream");
    expect(res.getHeader("cache-control")).toBe("no-cache, no-transform");
    expect(res.getHeader("x-accel-buffering")).toBe("no");
  });

  it("não envia cookie nem last-event-id quando ausentes", async () => {
    const { event } = makeEvent();
    await proxyEventStream(event, "/gestor/events/orders/");
    expect(calls[0]!.options.headers.cookie).toBeUndefined();
    expect(calls[0]!.options.headers["last-event-id"]).toBeUndefined();
  });

  it("propaga o status quando o Django recusa (não-autorizado) — sem corpo", async () => {
    (fetch as any).mockImplementationOnce((url: string, options: any) => {
      calls.push({ url, options });
      return Promise.resolve(streamResponse(403, false));
    });
    const { event, res } = makeEvent();

    const result = await proxyEventStream(event, "/gestor/events/orders/");

    expect(result).toBe("");
    expect(res.statusCode).toBe(403);
    // Não vaza headers de SSE numa recusa.
    expect(res.getHeader("content-type")).not.toBe("text/event-stream");
  });

  it("responde 502 quando o upstream do Django falha", async () => {
    (fetch as any).mockImplementationOnce(() => Promise.reject(new Error("down")));
    const { event, res } = makeEvent();

    const result = await proxyEventStream(event, "/gestor/events/kds/bancada/");

    expect(result).toBe("");
    expect(res.statusCode).toBe(502);
  });

  it("aborta o upstream quando o cliente fecha a conexão", async () => {
    let signal: AbortSignal | undefined;
    (fetch as any).mockImplementationOnce((_url: string, options: any) => {
      signal = options.signal;
      return Promise.resolve(streamResponse(200, true));
    });
    const { event, req } = makeEvent();

    await proxyEventStream(event, "/gestor/events/orders/");
    expect(signal?.aborted).toBe(false);
    req.emit("close");
    expect(signal?.aborted).toBe(true);
  });
});

describe("ssePath — caminho same-origin das rotas SSE do BFF", () => {
  it("app na raiz (baseURL '/'): caminho sai limpo", () => {
    expect(ssePath("/sse/orders", "/")).toBe("/sse/orders");
  });

  it("app sob prefixo (ex.: KDS em /kds/): prefixa sem barra dupla", () => {
    expect(ssePath("/sse/kds/bancada", "/kds/")).toBe("/kds/sse/kds/bancada");
  });

  it("normaliza caminho sem barra inicial", () => {
    expect(ssePath("sse/orders", "/kds/")).toBe("/kds/sse/orders");
  });
});
