// Relógio compartilhado: um ÚNICO setInterval de 1s para todos os consumidores
// (ex.: o countdown de confirmação em cada OrderCard), em vez de um timer por
// componente. Refcount liga/desliga o interval conforme cards entram/saem —
// espelha o padrão de "relógio singleton por página" do resto da suíte.
const nowMs = ref<number>(Date.now());
let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;

export function useNowTick() {
  onMounted(() => {
    refs += 1;
    if (!timer) timer = setInterval(() => (nowMs.value = Date.now()), 1000);
  });
  onBeforeUnmount(() => {
    refs = Math.max(0, refs - 1);
    if (refs === 0 && timer) { clearInterval(timer); timer = null; }
  });
  return nowMs;
}
