<script setup lang="ts">
// Aviso calmo e global de conexão para as superfícies de operador. Aparece só quando
// offline; feedback nunca no vácuo. Usa tokens do design system canônico (âmbar =
// aviso). Auto-importado pelo operator-kit — colocar uma vez no layout raiz de cada app.
import { computed } from "vue";

const { isOnline } = useConnectivity();
const show = computed(() => isOnline.value === false);
</script>

<template>
  <Transition name="operator-offline">
    <div
      v-if="show"
      role="status"
      aria-live="polite"
      class="pointer-events-none fixed inset-x-0 top-0 z-[100] flex justify-center px-3 pt-[env(safe-area-inset-top)]"
    >
      <div
        class="pointer-events-auto mt-2 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/12 px-3 py-1.5 text-sm font-medium text-amber-700 shadow-sm backdrop-blur-sm dark:text-amber-300"
      >
        <Icon name="lucide:wifi-off" class="size-4" aria-hidden="true" />
        <span>Sem conexão — tentando reconectar…</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.operator-offline-enter-active,
.operator-offline-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.operator-offline-enter-from,
.operator-offline-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}
</style>
