// Adaptive, visibility-aware polling. One place for the app's refresh cadence:
//   - interval() is re-read every tick, so the caller can speed up under
//     pressure (live floor: 30s → 10s while something is late);
//   - a hidden tab skips the fetch (tablet parked on another app costs zero);
//   - coming back to the tab refreshes immediately (no stale first paint).
// Polling over SSE is deliberate for production: the floor clock moves in
// minutes, alerts are low-frequency, and the SSE channel infra is order-scoped
// today — revisit post-alpha if cadence ever tightens (decision: WP-PE4).
export function useAdaptivePoll(refresh: () => unknown, interval: () => number): void {
  let timer: ReturnType<typeof setTimeout> | null = null;

  function schedule() {
    timer = setTimeout(async () => {
      if (!document.hidden) {
        try {
          await refresh();
        } catch {
          // o próximo tick tenta de novo; erros de rede já aparecem na tela
        }
      }
      schedule();
    }, Math.max(interval(), 5_000));
  }

  function onVisible() {
    if (!document.hidden) refresh();
  }

  onMounted(() => {
    schedule();
    document.addEventListener("visibilitychange", onVisible);
  });
  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisible);
  });
}
