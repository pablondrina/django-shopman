<script setup lang="ts">
// Hub top bar — the single identity + section-switch + global-tools layer for the
// whole Gestor. It owns what is shared across both boards: the wordmark, the
// Pedidos/Catálogo segmented nav, the live clock and the theme toggle. Per-page
// chrome (search, filters, board actions) lives in each page's UiToolbar below this,
// so there are two chrome layers, not three — no page repeats "Gestor".
const route = useRoute();
const section = computed(() =>
  route.path.startsWith("/catalog") ? "catalog"
  : route.path.startsWith("/expositores") ? "showcases"
  : "orders",
);

const tabs = [
  { to: "/", key: "orders", label: "Pedidos", icon: "lucide:clipboard-list" },
  { to: "/catalog", key: "catalog", label: "Catálogo", icon: "lucide:book-open" },
  { to: "/expositores", key: "showcases", label: "Expositores", icon: "lucide:monitor-play" },
] as const;

const colorMode = useColorMode();
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}

// live clock (client-only; new Date() on SSR would mismatch the hydration).
const now = ref<Date | null>(null);
let timer: ReturnType<typeof setInterval> | null = null;
const clock = computed(() =>
  now.value ? now.value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "",
);
onMounted(() => {
  now.value = new Date();
  timer = setInterval(() => (now.value = new Date()), 30_000);
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b bg-card px-4 py-2.5 print:hidden">
    <span class="grid size-9 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground">
      <Icon name="lucide:store" class="size-4" />
    </span>
    <span class="text-sm font-bold tracking-tight">Gestor</span>
    <div class="h-6 w-px bg-border"></div>

    <!-- section switcher: um conjunto claro (segmented control); a aba ativa "sobe" -->
    <nav class="inline-flex items-center gap-0.5 rounded-lg bg-muted p-1">
      <NuxtLink
        v-for="t in tabs"
        :key="t.key"
        :to="t.to"
        class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm transition-all"
        :class="section === t.key
          ? 'bg-card font-semibold text-foreground shadow-sm'
          : 'text-muted-foreground hover:bg-card/60 hover:text-foreground'"
      >
        <Icon :name="t.icon" class="size-4" :class="section === t.key ? 'text-foreground' : 'text-muted-foreground'" />
        <span>{{ t.label }}</span>
      </NuxtLink>
    </nav>

    <div class="ml-auto flex items-center gap-1.5">
      <ClientOnly>
        <span v-if="now" class="hidden text-sm font-bold tabular-nums text-muted-foreground sm:inline">{{ clock }}</span>
      </ClientOnly>
      <ClientOnly>
        <UiIconButton
          :icon="colorMode.value === 'dark' ? 'lucide:sun' : 'lucide:moon'"
          :label="colorMode.value === 'dark' ? 'Tema claro' : 'Tema escuro'"
          @click="toggleTheme"
        />
        <template #fallback>
          <span class="grid size-9 place-items-center rounded-md border text-muted-foreground"><Icon name="lucide:moon" class="size-4" /></span>
        </template>
      </ClientOnly>
    </div>
  </header>
</template>
