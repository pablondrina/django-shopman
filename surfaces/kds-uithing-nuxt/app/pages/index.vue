<script setup lang="ts">
// Station picker — choose which station this screen shows. KDS-refined grammar
// (dark, distance-reading), aligned with the station/expedition cards.
import type { KDSIndexResponse } from "~/types/kds";

const { data, pending } = useFetch<KDSIndexResponse>("/api/v1/backstage/kds/", { key: "kds-index" });
const instances = computed(() => data.value?.instances ?? []);

function typeIcon(type: string): string {
  if (type === "expedition") return "lucide:package-check";
  if (type === "separation") return "lucide:layers";
  return "lucide:cooking-pot";
}
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 md:p-10">
    <header>
      <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Kitchen Display</p>
      <h1 class="text-3xl font-bold">Escolha uma estação</h1>
    </header>

    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <p v-else-if="!instances.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      Nenhuma estação configurada.
    </p>

    <ul v-else class="grid gap-3">
      <li v-for="inst in instances" :key="inst.ref">
        <NuxtLink
          :to="`/estacao/${inst.ref}`"
          class="flex items-center gap-4 rounded-md border bg-card p-5 transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
        >
          <span class="grid size-12 shrink-0 place-items-center rounded-md bg-background text-muted-foreground">
            <Icon :name="typeIcon(inst.type)" class="size-6" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ inst.type_display }}</span>
            <span class="block truncate text-2xl font-bold leading-tight">{{ inst.name }}</span>
          </span>
          <span
            v-if="inst.pending_count"
            class="shrink-0 rounded-full border border-cyan-500/40 bg-cyan-500/15 px-3 py-1 text-sm font-bold tabular-nums text-cyan-300"
          >
            {{ inst.pending_count }}
          </span>
          <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground" />
        </NuxtLink>
      </li>
    </ul>
  </main>
</template>
