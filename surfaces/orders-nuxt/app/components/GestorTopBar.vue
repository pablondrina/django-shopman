<script setup lang="ts">
// Cabeçalho de seção do Gestor — mora no topo do CONTEÚDO (não é o rail). Segura o
// controle do rail (kit) + a navegação de seção própria do Gestor (Pedidos/Catálogo/
// Feeds). As funções comuns (Central, operador, tema) vivem no OperatorRail à
// esquerda; a nav de seção fica aqui porque precisa de rótulo legível.
const route = useRoute();
const section = computed(() =>
  route.path.startsWith("/catalog") ? "catalog"
  : route.path.startsWith("/showcases") ? "showcases"
  : "orders",
);

const tabs = [
  { to: "/", key: "orders", label: "Pedidos", icon: "lucide:clipboard-list" },
  { to: "/catalog", key: "catalog", label: "Catálogo", icon: "lucide:book-open" },
  { to: "/showcases", key: "showcases", label: "Feeds", icon: "lucide:monitor-play" },
] as const;
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2.5 print:hidden">
    <RailToggle />
    <div class="h-6 w-px bg-border"></div>
    <!-- section switcher: um conjunto claro (segmented control); a aba ativa "sobe" -->
    <nav class="inline-flex items-center gap-0.5 rounded-md bg-muted p-1" aria-label="Seções do Gestor">
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
  </header>
</template>
