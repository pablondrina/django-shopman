// Canal PESSOAL do gestor (`user-<id>` no Django, `/sse/notifications` no BFF).
//
// É por aqui que o post recém-gerado aparece no painel sem ninguém apertar F5:
// a fornada termina, o engine cria o post, o backend empurra o aviso e a tela
// refaz o fetch canônico. O push só diz "chegou algo" (ADR-016) — quem manda é
// o refetch, então uma mensagem perdida custa no máximo um ciclo de poll.
export function useUserNotifications(onPush: () => void) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: EventSource | null = null;

  function connect() {
    if (source) return;
    const url = ssePath("/sse/notifications", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      // Qualquer aviso do canal pessoal justifica o refetch: o painel é barato
      // e distinguir categorias aqui só criaria um segundo lugar para errar.
      ["message", "user-notification"].forEach((name) =>
        source!.addEventListener(name, () => onPush()),
      );
      source.onopen = () => {
        realtime.value = "live";
      };
      source.onerror = () => {
        realtime.value = "polling";
      };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  // Voltar para a aba (ou para a rede) é motivo de reconciliar: enquanto
  // escondida, a tela pode ter perdido pushes.
  const onVisible = () => {
    if (document.visibilityState === "visible") onPush();
  };

  onMounted(() => {
    connect();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (source) {
      source.close();
      source = null;
    }
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
