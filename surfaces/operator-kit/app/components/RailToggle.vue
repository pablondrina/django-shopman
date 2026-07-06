<script setup lang="ts">
// Controle do rail — vive no CABEÇALHO do app (não dentro do rail), para que a barra
// possa sumir por inteiro quando colapsada. Um toque cicla os 3 estados
// (colapsado → compacto → estendido → colapsado); ícone e rótulo anunciam o que o
// próximo toque faz. Estado compartilhado via `useRailState` (persistido por dispositivo).
import { computed } from "vue";

const { state, cycle } = useRailState();

// Ícone reflete o estado atual; o rótulo descreve a AÇÃO (o próximo estado).
const view = computed(() => {
  switch (state.value) {
    case "collapsed":
      return { icon: "lucide:panel-left-open", action: "Mostrar barra" };
    case "extended":
      return { icon: "lucide:panel-left-close", action: "Ocultar barra" };
    default:
      return { icon: "lucide:panel-left", action: "Expandir barra" };
  }
});
</script>

<template>
  <button
    type="button"
    class="grid size-9 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
    :aria-label="view.action"
    :title="view.action"
    @click="cycle"
  >
    <Icon :name="view.icon" class="size-5" />
  </button>
</template>
