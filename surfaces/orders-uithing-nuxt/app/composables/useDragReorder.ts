// Drag-to-reorder genérico (HTML5 drag nativo — sem lib externa). O componente
// possui a lista de chaves (na ordem exibida); no drop calculamos a nova ordem e
// chamamos ``commit(newKeys)`` para o pai persistir (otimista + POST).
export function useDragReorder(commit: (orderedKeys: string[]) => void) {
  const dragKey = ref<string | null>(null);
  const overKey = ref<string | null>(null);

  function onDragStart(key: string, e: DragEvent) {
    dragKey.value = key;
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", key); // Firefox exige um payload
    }
  }
  function onDragOver(key: string, e: DragEvent) {
    if (dragKey.value === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    if (key !== overKey.value) overKey.value = key;
  }
  function onDrop(keys: string[]) {
    const from = dragKey.value;
    const to = overKey.value;
    reset();
    if (!from || !to || from === to) return;
    const next = [...keys];
    const fromIdx = next.indexOf(from);
    const toIdx = next.indexOf(to);
    if (fromIdx < 0 || toIdx < 0) return;
    next.splice(fromIdx, 1);
    next.splice(toIdx, 0, from);
    commit(next);
  }
  function reset() {
    dragKey.value = null;
    overKey.value = null;
  }

  return { dragKey, overKey, onDragStart, onDragOver, onDrop, reset };
}
