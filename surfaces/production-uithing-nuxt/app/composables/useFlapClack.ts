// O "clac" das palhetas do painel Solari — rajadas curtas de ruído filtrado,
// uma por giro de célula (com throttle: muitas células girando juntas viram
// um clatter natural, não uma metralhadora). Liga/desliga persistido; o
// browser exige gesto antes do áudio, então unlock() é chamado nos controles.
const STORAGE_KEY = "fournil.painel-som";

const enabled = ref(true);
let audio: AudioContext | null = null;
let noise: AudioBuffer | null = null;
let lastClack = 0;
let loaded = false;

function load() {
  if (loaded || !import.meta.client) return;
  loaded = true;
  try {
    enabled.value = window.localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    enabled.value = true;
  }
}

function persist() {
  if (!import.meta.client) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, enabled.value ? "on" : "off");
  } catch {
    // sem storage: a preferência vive só na sessão
  }
}

function unlock() {
  if (!import.meta.client) return;
  try {
    audio = audio ?? new AudioContext();
    if (audio.state === "suspended") void audio.resume();
    if (!noise) {
      // 30ms de ruído branco — a matéria-prima do clac.
      noise = audio.createBuffer(1, Math.floor(audio.sampleRate * 0.03), audio.sampleRate);
      const data = noise.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    }
  } catch {
    audio = null;
  }
}

function clack() {
  if (!enabled.value || !audio || !noise || audio.state !== "running") return;
  const now = performance.now();
  if (now - lastClack < 45) return;
  lastClack = now;
  try {
    const src = audio.createBufferSource();
    src.buffer = noise;
    const band = audio.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.value = 1800 + Math.random() * 900; // cada palheta soa um tico diferente
    band.Q.value = 1.2;
    const gain = audio.createGain();
    const t = audio.currentTime;
    gain.gain.setValueAtTime(0.12, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
    src.connect(band).connect(gain).connect(audio.destination);
    src.start(t);
    src.stop(t + 0.06);
  } catch {
    // áudio indisponível: o painel segue mudo
  }
}

export function useFlapClack() {
  load();

  function toggle() {
    enabled.value = !enabled.value;
    persist();
    if (enabled.value) unlock();
  }

  return { enabled, toggle, clack, unlock };
}
