// Drag-to-reorder por POINTER events + POINTER CAPTURE (não HTML5 DnD, que é instável).
// A captura prende o ponteiro ao elemento: todos os move/up chegam nele mesmo se o
// cursor sair — sem isso, um drag de mouse real dispara seleção/drag nativo que engole
// os eventos. Limiar de 5px deixa o clique puro passar (seleção). O alvo é o item sob o
// ponteiro (elementFromPoint → `[data-dragkey]`).
//
// `getKeys()` = ordem exibida atual; `commit(novaOrdem)` persiste (otimista + POST no pai).
const DRAG_ATTR = "data-dragkey";
const THRESHOLD = 5;

export function useDragReorder(getKeys: () => string[], commit: (orderedKeys: string[]) => void) {
  const dragKey = ref<string | null>(null);
  const overKey = ref<string | null>(null);

  let pendingKey: string | null = null;
  let startX = 0;
  let startY = 0;
  let captureEl: HTMLElement | null = null;
  let pointerId = -1;

  function keyAt(x: number, y: number): string | null {
    const el = document.elementFromPoint(x, y);
    const item = el && "closest" in el ? (el as Element).closest(`[${DRAG_ATTR}]`) : null;
    return item?.getAttribute(DRAG_ATTR) ?? null;
  }

  function onMove(e: PointerEvent) {
    if (dragKey.value === null) {
      if (pendingKey === null) return;
      if (Math.hypot(e.clientX - startX, e.clientY - startY) < THRESHOLD) return;
      dragKey.value = pendingKey; // limiar cruzado → começa o arraste
      overKey.value = pendingKey;
      document.body.style.userSelect = "none";
    }
    e.preventDefault(); // agora que é arraste, bloqueia seleção/scroll nativo
    const k = keyAt(e.clientX, e.clientY);
    if (k && k !== overKey.value) overKey.value = k;
  }

  function onUp(e: PointerEvent) {
    const from = dragKey.value;
    const to = overKey.value ?? keyAt(e.clientX, e.clientY);
    detach();
    reset();
    if (from === null || !to || from === to) return; // clique puro ou sem alvo → nada
    const keys = [...getKeys()];
    const fromIdx = keys.indexOf(from);
    const toIdx = keys.indexOf(to);
    if (fromIdx < 0 || toIdx < 0) return;
    keys.splice(fromIdx, 1);
    keys.splice(toIdx, 0, from);
    commit(keys);
  }

  function onCancel() {
    detach();
    reset();
  }

  function detach() {
    if (captureEl) {
      captureEl.removeEventListener("pointermove", onMove);
      captureEl.removeEventListener("pointerup", onUp);
      captureEl.removeEventListener("pointercancel", onCancel);
      try {
        captureEl.releasePointerCapture(pointerId);
      } catch {
        /* já solto */
      }
    }
    document.body.style.userSelect = "";
    captureEl = null;
    pendingKey = null;
  }

  function onPointerDown(key: string, e: PointerEvent) {
    if (e.pointerType === "mouse" && e.button !== 0) return; // só botão esquerdo do mouse
    pendingKey = key;
    startX = e.clientX;
    startY = e.clientY;
    // Captura no ELEMENTO do item (o que tem data-dragkey) — grande e confiável —,
    // não no handle minúsculo (span/svg), onde setPointerCapture falhava e o drag de
    // mouse real perdia os eventos ao sair do handle.
    const trigger = e.currentTarget as HTMLElement;
    captureEl = (trigger.closest(`[${DRAG_ATTR}]`) as HTMLElement) ?? trigger;
    pointerId = e.pointerId;
    try {
      captureEl.setPointerCapture(pointerId);
    } catch {
      /* navegadores antigos: cai no fluxo sem captura */
    }
    captureEl.addEventListener("pointermove", onMove);
    captureEl.addEventListener("pointerup", onUp);
    captureEl.addEventListener("pointercancel", onCancel);
  }

  function reset() {
    dragKey.value = null;
    overKey.value = null;
  }

  return { dragKey, overKey, onPointerDown, reset };
}
