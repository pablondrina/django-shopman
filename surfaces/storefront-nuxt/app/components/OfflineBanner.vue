<script setup lang="ts">
// Banner global e calmo de conexão perdida. Persistente (não é toast) porque o
// estado dura enquanto o cliente estiver offline; some sozinho ao reconectar.
// Fica acima da bottom-nav no mobile para não cobrir a navegação.
const { isOnline } = useConnectivity()
</script>

<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="translate-y-2 opacity-0"
    leave-active-class="transition duration-150 ease-in"
    leave-to-class="translate-y-2 opacity-0"
  >
    <div
      v-if="!isOnline"
      role="status"
      aria-live="polite"
      data-testid="offline-banner"
      class="pointer-events-none fixed inset-x-0 bottom-16 z-50 px-4 md:bottom-4"
    >
      <div class="mx-auto flex max-w-md items-center justify-center gap-2 rounded-lg border bg-foreground px-4 py-2 text-background shadow-lg">
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span class="text-sm font-semibold">Sem conexão. Tentando reconectar…</span>
      </div>
    </div>
  </Transition>
</template>
