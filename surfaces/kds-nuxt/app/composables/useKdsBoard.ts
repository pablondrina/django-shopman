// KDS board read-side (Arc 2). Single source for a station's board:
//   - useFetch the canonical projection (GET /api/v1/backstage/kds/<ref>/);
//   - poll every 15s as a robust fallback (mirrors the HTMX `every 15s`);
//   - SSE realtime: EventSource on the Django events channel → refresh on push,
//     and a beep when the active-ticket count rises (new order arrived).
// SSE/poll/beep are client-only (EventSource + Web Audio are browser APIs).
import type { KDSBoardProjection, KDSBoardResponse, KDSTicketProjection } from "~/types/kds";
import { boardView, type KDSBoardView } from "~/presentation/board";

export function useKdsBoard(stationRef: string) {
  const config = useRuntimeConfig();
  const path = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/`;

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<KDSBoardResponse>(path, {
    key: `kds-board-${stationRef}`,
    server: true,
    // Sessão expirou no meio do turno → o poll passa a 401/403. Reabre o gate de
    // operador (re-fetch da sessão) em vez de deixar "reconectando…" para sempre.
    onResponseError: operatorSessionOnError,
  });

  const board = computed<KDSBoardProjection | null>(() => data.value?.board ?? null);
  const view = computed<KDSBoardView | null>(() => (board.value ? boardView(board.value) : null));

  // Realtime + polling + audio cue (client only).
  const soundOn = ref(true);
  // Som BLOQUEADO pela política de autoplay: o beep vem de um watch (não de um
  // gesto), então um AudioContext não-primado nasce suspenso e toca MUDO. A UI
  // mostra "toque para ativar o som" quando isto é true.
  const soundBlocked = ref(false);
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;
  let lastTotal = -1;

  // Um ÚNICO AudioContext compartilhado, resumido no primeiro gesto do operador
  // (destravar/tocar/qualquer toque) — recriar por beep garantia suspensão.
  let audioCtx: AudioContext | null = null;
  function ensureCtx(): AudioContext | null {
    if (!import.meta.client) return null;
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    return audioCtx;
  }
  function primeAudio() {
    const ctx = ensureCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    soundBlocked.value = soundOn.value && ctx.state !== "running";
  }

  function beep() {
    if (!soundOn.value) return;
    const ctx = ensureCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    if (ctx.state !== "running") {
      // Não conseguimos tocar sem um gesto — sinalize visualmente em vez de falhar mudo.
      soundBlocked.value = true;
      return;
    }
    soundBlocked.value = false;
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
    primeAudio(); // gesto do usuário — desbloqueia o áudio
    if (soundOn.value) beep();
  }

  let removeGestureListeners: (() => void) | null = null;

  onMounted(() => {
    soundOn.value = localStorage.getItem(`kds_sound_${stationRef}`) !== "off";
    lastTotal = view.value?.total ?? -1;
    pollTimer = setInterval(() => refresh(), 15_000);
    connectSse();
    // Primeiro gesto na tela destrava o áudio (a política de autoplay exige um).
    const onGesture = () => primeAudio();
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    // Tablet dormiu / voltou à aba: refetch imediato (setInterval é throttlado em
    // aba oculta), em vez de esperar até 15s por dados possivelmente muito velhos.
    const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    removeGestureListeners = () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
    // Reflete o estado inicial (provável bloqueado até o 1º gesto).
    primeAudio();
  });

  // ---- write-side: otimista + fila serial + reconciliação ----
  // Toque instantâneo: a UI muda na hora, o POST vai em segundo plano e a fila serial
  // preserva a ordem; uma reconciliação (refresh) ~500ms depois confere com a verdade
  // do servidor. Em falha, reverte o estado local + avisa. Sem `busy` bloqueando —
  // numa cozinha em ritmo, toques em sequência não podem ser descartados.
  let chain: Promise<unknown> = Promise.resolve();
  let reconcileTimer: ReturnType<typeof setTimeout> | null = null;

  // O `$fetch` tipado do Nitro estoura o typecheck (TS2321 excessive stack depth) ao casar
  // um path DINÂMICO contra o catch-all `/api/v1/**:path`. Estas escritas vão pro proxy BFF
  // (a resposta é JSON do Django, NÃO uma rota Nitro tipada), então aqui o $fetch é um cliente
  // HTTP simples — o cast declara isso com precisão (resposta `unknown`) e corta a recursão.
  const postProxy = $fetch as (
    path: string,
    opts: { method: string; body: Record<string, unknown> },
  ) => Promise<unknown>;

  function scheduleReconcile() {
    if (reconcileTimer) clearTimeout(reconcileTimer);
    reconcileTimer = setTimeout(() => refresh(), 500);
  }

  function enqueue(path: string, body?: Record<string, unknown>) {
    const run = chain.then(() => postProxy(path, { method: "POST", body: body ?? {} }));
    chain = run.then(() => undefined, () => undefined); // mantém a fila viva após erro
    return run;
  }

  function checkItem(pk: number, index: number, checked: boolean) {
    const t = data.value?.board?.tickets?.find((x) => x.pk === pk && "items" in x) as KDSTicketProjection | undefined;
    const item = t?.items?.[index];
    if (!t || !item) return;
    const prev = item.checked;
    item.checked = checked; // otimista
    t.all_checked = t.items.every((i) => i.checked);
    enqueue(`/api/v1/backstage/kds/tickets/${pk}/items/`, { index, checked })
      .then(() => scheduleReconcile())
      .catch((err) => {
        item.checked = prev; // reverte
        t.all_checked = t.items.every((i) => i.checked);
        useSonner.error(httpErrorMessage(err, "Falha ao marcar item."));
        refresh();
      });
  }

  // Remove um card de uma lista do board (tickets / cancelled / recent_done) na hora
  // e dispara o POST; recoloca + avisa em falha; reconcilia ~500ms depois.
  function removeFrom<T extends { pk: number }>(
    getList: () => T[] | undefined,
    pk: number,
    path: string,
    body?: Record<string, unknown>,
  ) {
    const list = getList();
    const idx = list?.findIndex((x) => x.pk === pk) ?? -1;
    if (!list || idx < 0) return;
    const [removed] = list.splice(idx, 1);
    enqueue(path, body)
      .then(() => scheduleReconcile())
      .catch((err) => {
        if (removed) getList()?.splice(idx, 0, removed);
        useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
        refresh();
      });
  }

  const finalize = (pk: number) =>
    removeFrom(() => data.value?.board?.tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/done/`);
  const expedite = (pk: number, action: "dispatch" | "complete") =>
    removeFrom(() => data.value?.board?.tickets, pk, `/api/v1/backstage/kds/expedition/${pk}/action/`, { action });
  // Recall: o concluído sai da lista de recentes; a reconciliação o traz de volta ao board ativo.
  const recall = (pk: number) =>
    removeFrom(() => data.value?.board?.recent_done, pk, `/api/v1/backstage/kds/tickets/${pk}/recall/`);
  // Reconhecer cancelado: some do board.
  const acknowledge = (pk: number) =>
    removeFrom(() => data.value?.board?.cancelled_tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/acknowledge/`);

  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (reconcileTimer) clearTimeout(reconcileTimer);
    if (source) { source.close(); source = null; }
    if (removeGestureListeners) removeGestureListeners();
  });

  return { board, view, pending, error, refresh, soundOn, soundBlocked, toggleSound, checkItem, finalize, expedite, recall, acknowledge };
}
