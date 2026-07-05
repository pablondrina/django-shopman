import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

// Mocka só a fronteira de rede (@vueuse `useOnline`) para dirigir online→offline→online
// de forma determinística; a lógica de reconciliação (rodar handlers só ao VOLTAR a
// rede) é real. Env nuxt garante import.meta.client=true (senão o watch nem monta).
// O ref é criado DENTRO do factory (o vue já está pronto lá); o holder hoisted é só
// um objeto simples (não pode instanciar ref antes dos imports).
const net = vi.hoisted(() => ({ online: null as unknown as { value: boolean } }));
vi.mock("@vueuse/core", async () => {
  const { ref } = await import("vue");
  net.online = ref(true);
  return { useOnline: () => net.online };
});
// Lazy: o ref só existe depois que useConnectivity() importa @vueuse (roda o factory).
const online = () => net.online;

describe("useConnectivity — reconciliação ao reconectar", () => {
  afterEach(() => {
    if (net.online) net.online.value = true;
  });

  it("dispara os handlers ao VOLTAR a rede (offline→online)", async () => {
    const { onReconnect } = useConnectivity();
    const handler = vi.fn();
    onReconnect(handler);

    online().value = false; // caiu
    await nextTick();
    online().value = true; // voltou → reconcilia
    await nextTick();

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("NÃO dispara se nunca esteve offline (online estável)", async () => {
    const { onReconnect } = useConnectivity();
    const handler = vi.fn();
    onReconnect(handler);

    // Um "online" sem ter caído antes não é reconexão — não reconcilia à toa.
    online().value = true;
    await nextTick();

    expect(handler).not.toHaveBeenCalled();
  });

  it("o unregister devolvido para de receber reconexões", async () => {
    const { onReconnect } = useConnectivity();
    const handler = vi.fn();
    const stop = onReconnect(handler);
    stop();

    online().value = false;
    await nextTick();
    online().value = true;
    await nextTick();

    expect(handler).not.toHaveBeenCalled();
  });

  it("um handler que lança não derruba os demais (best-effort)", async () => {
    const { onReconnect } = useConnectivity();
    const boom = vi.fn(() => { throw new Error("boom"); });
    const ok = vi.fn();
    onReconnect(boom);
    onReconnect(ok);

    online().value = false;
    await nextTick();
    online().value = true;
    await nextTick();

    expect(boom).toHaveBeenCalledTimes(1);
    expect(ok).toHaveBeenCalledTimes(1);
  });
});
