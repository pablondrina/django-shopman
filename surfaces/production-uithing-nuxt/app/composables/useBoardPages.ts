// Paginação de painel de aeroporto: o quadro tem N linhas FIXAS (medidas na
// tela — kiosk não rola) e o conteúdo excedente vira páginas em ciclo. A
// virada re-monta as linhas → as palhetas cascateiam de novo: a "tempestade
// de clacs" que os painéis mecânicos fazem ao virar a página.
import type { Ref } from "vue";

const ROTATE_MS = 12_000;
const ROW_GAP_PX = 6; // gap-1.5 entre linhas

export function useBoardPages<T>(items: Ref<T[]>) {
  const listEl = ref<HTMLElement | null>(null);
  const pageSize = ref(8);
  const page = ref(0);
  let rotateTimer: ReturnType<typeof setInterval> | null = null;
  let observer: ResizeObserver | null = null;

  const pageCount = computed(() => Math.max(1, Math.ceil(items.value.length / Math.max(1, pageSize.value))));
  const visible = computed(() => {
    const size = Math.max(1, pageSize.value);
    const current = Math.min(page.value, pageCount.value - 1);
    return items.value.slice(current * size, (current + 1) * size);
  });

  function measure() {
    const list = listEl.value;
    const row = list?.querySelector<HTMLElement>("[data-board-row]");
    if (!list || !row || !row.offsetHeight) return;
    const fits = Math.floor((list.clientHeight + ROW_GAP_PX) / (row.offsetHeight + ROW_GAP_PX));
    pageSize.value = Math.max(3, fits);
  }

  function goTo(target: number) {
    page.value = ((target % pageCount.value) + pageCount.value) % pageCount.value;
  }

  onMounted(() => {
    void nextTick(measure);
    observer = new ResizeObserver(() => measure());
    if (listEl.value) observer.observe(listEl.value);
    rotateTimer = setInterval(() => {
      if (pageCount.value > 1) goTo(page.value + 1);
    }, ROTATE_MS);
  });

  onUnmounted(() => {
    if (rotateTimer) clearInterval(rotateTimer);
    observer?.disconnect();
  });

  watch(pageCount, (count) => {
    if (page.value >= count) page.value = 0;
  });
  watch(
    () => items.value.length,
    () => void nextTick(measure),
  );

  return { listEl, visible, page, pageCount, pageSize, goTo };
}
