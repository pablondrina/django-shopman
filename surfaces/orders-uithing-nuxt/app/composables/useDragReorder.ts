// Drag-to-reorder por POINTER events (não HTML5 DnD — que é notoriamente instável).
// Funciona igual em todo browser: pointerdown no item → move além de um limiar inicia
// o arraste → o item sob o ponteiro vira o alvo → pointerup grava a nova ordem.
//
// `getKeys()` devolve a ordem exibida atual; `commit(novaOrdem)` persiste (o pai faz
// otimista + POST). Cada item arrastável precisa de `data-dragkey="<chave>"` no DOM.
const DRAG_ATTR = "data-dragkey";
const THRESHOLD = 5; // px antes de virar arraste (deixa o clique puro passar = seleção)

export function useDragReorder(getKeys: () => string[], commit: (orderedKeys: string[]) => void) {
  const dragKey = ref<string | null>(null);
  const overKey = ref<string | null>(null);

  let pendingKey: string | null = null;
  let startX = 0;
  let startY = 0;

  function keyAt(x: number, y: number): string | null {
    const el = document.elementFromPoint(x, y);
    const item = el && "closest" in el ? (el as Element).closest(`[${DRAG_ATTR}]`) : null;
    return item?.getAttribute(DRAG_ATTR) ?? null;
  }

  function onMove(e: PointerEvent) {
    if (dragKey.value === null) {
      if (pendingKey === null) return;
      if (Math.hypot(e.clientX - startX, e.clientY - startY) < THRESHOLD) return;
      // limiar cruzado → inicia o arraste
      dragKey.value = pendingKey;
      overKey.value = pendingKey;
      document.body.style.userSelect = "none";
    }
    const k = keyAt(e.clientX, e.clientY);
    if (k && k !== overKey.value) overKey.value = k;
  }

  function onUp(e: PointerEvent) {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    document.body.style.userSelect = "";
    const from = dragKey.value;
    const to = overKey.value ?? keyAt(e.clientX, e.clientY);
    pendingKey = null;
    reset();
    if (from === null || !to || from === to) return; // clique puro OU sem alvo → nada
    const keys = [...getKeys()];
    const fromIdx = keys.indexOf(from);
    const toIdx = keys.indexOf(to);
    if (fromIdx < 0 || toIdx < 0) return;
    keys.splice(fromIdx, 1);
    keys.splice(toIdx, 0, from);
    commit(keys);
  }

  function onPointerDown(key: string, e: PointerEvent) {
    if (e.button !== 0) return; // só botão esquerdo
    pendingKey = key;
    startX = e.clientX;
    startY = e.clientY;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function reset() {
    dragKey.value = null;
    overKey.value = null;
  }

  return { dragKey, overKey, onPointerDown, reset };
}
