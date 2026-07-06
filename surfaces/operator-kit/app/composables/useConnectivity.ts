import { onScopeDispose, readonly, ref } from "vue";
import { useOnline } from "@vueuse/core";

type ReconnectHandler = () => void | Promise<void>;

/**
 * Sinal de conexão do operador (omotenashi de rede: uma padaria tem wi-fi instável).
 *
 * Expõe `isOnline` reativo e `onReconnect(handler)` para reconciliar dado stale ao
 * voltar a rede OU ao reganhar foco da aba (`visibilitychange`) — o tablet do balcão
 * que dormiu não deve esperar o próximo tick com dados velhos. O `<OfflineBanner>`
 * consome `isOnline` para um aviso calmo, nunca no vácuo ([[feedback_transparent_timeouts]]).
 */
export function useConnectivity() {
  const online = useOnline();
  const handlers = new Set<ReconnectHandler>();
  let wasOffline = ref(false);

  const runHandlers = () => {
    for (const handler of handlers) {
      try {
        void handler();
      } catch {
        // reconciliação best-effort; nunca propaga
      }
    }
  };

  if (import.meta.client) {
    watch(online, (value) => {
      if (!value) {
        wasOffline.value = true;
      } else if (wasOffline.value) {
        wasOffline.value = false;
        runHandlers();
      }
    });

    const onVisible = () => {
      if (document.visibilityState === "visible" && online.value) runHandlers();
    };
    document.addEventListener("visibilitychange", onVisible);
    onScopeDispose(() => document.removeEventListener("visibilitychange", onVisible));
  }

  /** Registra um reconciliador chamado ao reconectar / reganhar foco. Retorna o unregister. */
  const onReconnect = (handler: ReconnectHandler) => {
    handlers.add(handler);
    onScopeDispose(() => handlers.delete(handler));
    return () => handlers.delete(handler);
  };

  return { isOnline: readonly(online), onReconnect };
}
