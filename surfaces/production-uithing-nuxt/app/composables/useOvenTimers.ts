// Timer auxiliar do forno — lembrete armado por fornada (WO) para conferir/
// retirar. É a ferramenta ATIVA do forneiro; o relógio de idade do lote
// (started_at vs max_started_minutes) segue como guardrail de esquecimento
// via alertas (sino). Local ao aparelho: quem armou, ouve.
//
// Som: "dim-dom" quente em triangle wave, duas frases curtas, volume moderado
// — fácil de ouvir, fácil de conviver. Repete a cada 45s enquanto ninguém
// atende, com teto de 4 repetições (depois o chip pulsando continua avisando).
// Padrões configuráveis via Admin ficam para o ProductionConfig (follow-up).
import { countdownLabel } from "~/presentation/production";

interface OvenTimer {
  endsAt: number;
  minutes: number;
}

const STORAGE_KEY = "fournil.oven-timers";
const RECHIME_MS = 45_000;
const MAX_CHIMES = 4;

const timers = ref<Record<string, OvenTimer>>({});
const nowMs = ref(0);
const chimes = new Map<string, { count: number; lastAt: number }>();
let ticker: ReturnType<typeof setInterval> | null = null;
let audio: AudioContext | null = null;
let loaded = false;

function load() {
  if (loaded || !import.meta.client) return;
  loaded = true;
  nowMs.value = Date.now();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, OvenTimer>) : {};
    // Timers estourados há mais de 2h são lixo de um turno anterior.
    const cutoff = Date.now() - 2 * 60 * 60 * 1000;
    timers.value = Object.fromEntries(
      Object.entries(parsed).filter(([, t]) => t && typeof t.endsAt === "number" && t.endsAt > cutoff),
    );
  } catch {
    timers.value = {};
  }
  ensureTicker();
}

function persist() {
  if (!import.meta.client) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(timers.value));
  } catch {
    // storage indisponível: o timer ainda vive na sessão em memória
  }
}

function ensureTicker() {
  if (ticker || !import.meta.client) return;
  ticker = setInterval(() => {
    nowMs.value = Date.now();
    for (const key of Object.keys(timers.value)) {
      const t = timers.value[key];
      if (!t || t.endsAt > nowMs.value) continue;
      const state = chimes.get(key) ?? { count: 0, lastAt: 0 };
      if (state.count < MAX_CHIMES && nowMs.value - state.lastAt >= RECHIME_MS) {
        chime();
        chimes.set(key, { count: state.count + 1, lastAt: nowMs.value });
      }
    }
  }, 1000);
}

/** O gesto de armar é interação do usuário — aproveita para destravar o áudio. */
function unlockAudio() {
  if (!import.meta.client) return;
  try {
    audio = audio ?? new AudioContext();
    if (audio.state === "suspended") void audio.resume();
  } catch {
    audio = null;
  }
}

function chime() {
  if (!audio) return;
  try {
    const ctx = audio;
    const note = (freq: number, at: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(0.4, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.6);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.65);
    };
    const t = ctx.currentTime;
    note(880, t); // dim
    note(659.25, t + 0.28); // dom
    note(880, t + 1.05); // dim (eco)
    note(659.25, t + 1.33); // dom
  } catch {
    // sem áudio: o chip pulsando segue avisando
  }
}

export function useOvenTimers() {
  load();

  function arm(key: string, minutes: number) {
    const clamped = Math.max(1, Math.round(minutes));
    unlockAudio();
    chimes.delete(key);
    timers.value = { ...timers.value, [key]: { endsAt: Date.now() + clamped * 60_000, minutes: clamped } };
    persist();
    ensureTicker();
  }

  function clear(key: string) {
    const { [key]: _, ...rest } = timers.value;
    timers.value = rest;
    chimes.delete(key);
    persist();
  }

  function get(key: string): OvenTimer | null {
    return timers.value[key] ?? null;
  }

  function isRinging(key: string): boolean {
    const t = timers.value[key];
    return !!t && t.endsAt <= nowMs.value;
  }

  function remainingLabel(key: string): string {
    const t = timers.value[key];
    if (!t) return "";
    return countdownLabel((t.endsAt - nowMs.value) / 1000);
  }

  return { arm, clear, get, isRinging, remainingLabel };
}
