<script setup lang="ts">
// Station picker (Arc 2 minimal — polished in Arc 4). Lists the KDS instances and
// links to each station board. Read-only over the canonical index endpoint.
import type { KDSIndexResponse } from "~/types/kds";

const { data, pending } = useFetch<KDSIndexResponse>("/api/v1/backstage/kds/", { key: "kds-index" });
const instances = computed(() => data.value?.instances ?? []);
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col gap-5 p-6">
    <header>
      <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Kitchen Display</p>
      <h1 class="text-2xl font-semibold">Escolha uma estação</h1>
    </header>

    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <p v-else-if="!instances.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      Nenhuma estação configurada.
    </p>

    <ul v-else class="grid gap-2">
      <li v-for="inst in instances" :key="inst.ref">
        <NuxtLink
          :to="`/estacao/${inst.ref}`"
          class="flex items-center justify-between gap-3 rounded-md border bg-card p-4 transition hover:border-primary/50 hover:bg-accent"
        >
          <span class="min-w-0">
            <span class="block text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ inst.type_display }}</span>
            <span class="block truncate text-lg font-semibold">{{ inst.name }}</span>
          </span>
          <span
            v-if="inst.pending_count"
            class="shrink-0 rounded-full bg-cyan-500/10 px-2 py-0.5 text-xs font-semibold text-cyan-700 dark:text-cyan-400"
          >
            {{ inst.pending_count }} pendentes
          </span>
        </NuxtLink>
      </li>
    </ul>
  </main>
</template>
