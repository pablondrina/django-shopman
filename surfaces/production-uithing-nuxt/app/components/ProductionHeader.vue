<script setup lang="ts">
// Shared chrome for the production app: brand + the two-board nav (Chão ao vivo /
// Planejamento), live search, alerts bell, refresh, theme toggle. Touch-first
// (large targets) and light-first, like the Gestor.
defineProps<{ title: string; count?: number; countLabel?: string; pending?: boolean }>();
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });

const route = useRoute();
const colorMode = useColorMode();
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}

// O fluxo do dia em abas-etapa (refino Pablo 2026-07-03): decide → separa/
// pesa → produz → expede. As três grades são lentes do mesmo motor; a
// Preparação é a estação de pesagem/separação.
const tabs = [
  { to: "/planejamento", label: "Planejamento", icon: "lucide:layout-grid" },
  { to: "/preparacao", label: "Preparação", icon: "lucide:scale" },
  { to: "/", label: "Produção", icon: "lucide:flame" },
  { to: "/expedicao", label: "Expedição", icon: "lucide:package-check" },
  { to: "/painel", label: "Painel", icon: "lucide:tower-control" },
];
function isActive(to: string): boolean {
  return to === "/" ? route.path === "/" : route.path.startsWith(to);
}
</script>

<template>
  <header class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-2.5">
    <span class="grid size-9 shrink-0 place-items-center rounded-md border bg-card text-foreground">
      <Icon name="lucide:croissant" class="size-4" />
    </span>
    <div class="mr-2 min-w-0">
      <p class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">Fournil</p>
      <h1 class="truncate text-lg font-bold leading-tight">{{ title }}</h1>
    </div>

    <nav class="flex items-center gap-1 rounded-lg border bg-background p-0.5" aria-label="Telas de produção">
      <NuxtLink
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition"
        :class="isActive(tab.to) ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
      >
        <Icon :name="tab.icon" class="size-4" />
        <span class="hidden sm:inline">{{ tab.label }}</span>
      </NuxtLink>
    </nav>

    <div v-if="count != null" class="ml-auto hidden flex-col items-end leading-none sm:flex">
      <span class="text-lg font-bold tabular-nums">{{ count }}</span>
      <span class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">{{ countLabel || "ativos" }}</span>
    </div>

    <div class="flex items-center gap-1.5" :class="count != null ? '' : 'ml-auto'">
      <div class="relative">
        <Icon name="lucide:search" class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          v-model="query"
          type="search"
          inputmode="search"
          placeholder="Buscar…"
          class="h-9 w-32 rounded-md border bg-background pl-8 pr-7 text-sm outline-none transition focus:w-44 focus:ring-1 focus:ring-ring sm:w-40"
          aria-label="Buscar por código, SKU ou receita"
        />
        <button v-if="query" type="button" class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground" aria-label="Limpar busca" @click="query = ''">
          <Icon name="lucide:x" class="size-3.5" />
        </button>
      </div>
      <AlertsBell />
      <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" aria-label="Atualizar" title="Atualizar" @click="emit('refresh')">
        <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
      </button>
      <ClientOnly>
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" :aria-label="colorMode.value === 'dark' ? 'Tema claro' : 'Tema escuro'" title="Tema" @click="toggleTheme">
          <Icon :name="colorMode.value === 'dark' ? 'lucide:sun' : 'lucide:moon'" class="size-4" />
        </button>
        <template #fallback>
          <span class="grid size-9 place-items-center rounded-md border text-muted-foreground"><Icon name="lucide:moon" class="size-4" /></span>
        </template>
      </ClientOnly>
    </div>
  </header>
</template>
