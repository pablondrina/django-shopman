// KDS board read-side (Arc 2). Single source for a station's board:
//   - useFetch the canonical projection (GET /api/v1/backstage/kds/<ref>/);
//   - poll every 15s as a robust fallback (mirrors the HTMX `every 15s`);
//   - SSE realtime: EventSource on the Django events channel → refresh on push,
//     and a beep when the active-ticket count rises (new order arrived).
// SSE/poll/beep are client-only (EventSource + Web Audio are browser APIs).
import type { KDSBoardProjection, KDSBoardResponse } from "~/types/kds";
import { boardView, type KDSBoardView } from "~/presentation/board";

export function useKdsBoard(stationRef: string) {
  const config = useRuntimeConfig();
  const path = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/`;

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<KDSBoardResponse>(path, {
    key: `kds-board-${stationRef}`,
    server: true,
  });

  const board = computed<KDSBoardProjection | null>(() => data.value?.board ?? null);
  const view = computed<KDSBoardView | null>(() => (board.value ? boardView(board.value) : null));

  // Realtime + polling + audio cue (client only).
  const soundOn = ref(true);
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;
  let lastTotal = -1;

  function beep() {
    if (!soundOn.value) return;
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  }

  // Beep when the active total rises (a new ticket arrived on this station).
  watch(() => view.value?.total ?? 0, (total) => {
    if (lastTotal >= 0 && total > lastTotal) beep();
    lastTotal = total;
  });

  function connectSse() {
    if (source) return;
    const base = String(config.public.djangoPublicBaseUrl || "").replace(/\/$/, "");
    // SSE (EventSource) needs same-origin (or CORS on the eventstream). In prod the
    // KDS is served same-origin under /kds/, so it connects; in dev it's a different
    // origin (:3003 vs Django :8000) → skip and let the 15s poll carry realtime.
    if (base && new URL(base).origin !== window.location.origin) return;
    const url = `${base}/gestor/events/kds/${encodeURIComponent(stationRef)}/`;
    try {
      source = new EventSource(url, { withCredentials: true });
      // django-eventstream pushes named events; any of them means "refetch".
      const onPush = () => { refresh(); };
      ["message", "backstage-kds-update", "backstage-kds-created", "backstage-kds-status-changed", "backstage-kds-station-changed"]
        .forEach((name) => source!.addEventListener(name, onPush));
      source.onerror = () => { /* EventSource auto-reconnects; poll covers gaps. */ };
    } catch {
      source = null; // SSE unavailable → polling carries it.
    }
  }

  function toggleSound() {
    soundOn.value = !soundOn.value;
    if (import.meta.client) localStorage.setItem(`kds_sound_${stationRef}`, soundOn.value ? "on" : "off");
    if (soundOn.value) beep();
  }

  onMounted(() => {
    soundOn.value = localStorage.getItem(`kds_sound_${stationRef}`) !== "off";
    lastTotal = view.value?.total ?? -1;
    pollTimer = setInterval(() => refresh(), 15_000);
    connectSse();
  });

  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
  });

  return { board, view, pending, error, refresh, soundOn, toggleSound };
}
