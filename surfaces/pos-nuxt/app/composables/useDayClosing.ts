import { toast } from "vue-sonner";

import type { DayClosingResponse } from "~/types/closing";

interface DayClosingDeps {
  action: { call: (path: string, opts?: { body?: Record<string, unknown> }) => Promise<unknown> };
}

/**
 * Fechamento do DIA na antesala: leitura da projection (mesma
 * `build_day_closing` da retaguarda) e o comando de registrar a contagem
 * cega. Gate é da API (`backstage.perform_closing`): 401/403 viram
 * `accessDenied` e a página explica em vez de quebrar. O POST idempotente
 * responde 409 quando o dia já fechou — o refresh resolve a tela sozinho.
 */
export async function useDayClosing({ action }: DayClosingDeps) {
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

  const { data, pending, error, refresh } = await useFetch<DayClosingResponse>(
    "/api/v1/backstage/closing/",
    { key: "day-closing", credentials: "include", headers: requestHeaders },
  );

  const closing = computed(() => data.value?.closing ?? null);
  const accessDenied = computed(() => {
    const status = (error.value as { statusCode?: number } | null)?.statusCode;
    return status === 401 || status === 403;
  });

  const submitting = ref(false);

  async function submit(quantities: Record<string, string>): Promise<boolean> {
    if (submitting.value) return false;
    submitting.value = true;
    try {
      await action.call("/api/v1/backstage/closing/", { body: { quantities } });
      await refresh();
      toast.success("Fechamento do dia registrado.");
      return true;
    } catch (err) {
      toast.error(httpErrorMessage(err, "Falha no fechamento."));
      // 409 (dia já fechado) ou validação: a projection manda na tela.
      await refresh();
      return false;
    } finally {
      submitting.value = false;
    }
  }

  return { closing, pending, error, accessDenied, refresh, submitting, submit };
}
