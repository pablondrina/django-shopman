<script setup lang="ts">
// Expositores — o lado DISPLAY do cardápio. Um Expositor mostra um recorte de
// coleções PARA FORA (📺 menuboard na TV, 🛰 feed Google/Meta) sem transacionar.
// Aqui o operador liga/pausa, escolhe quais coleções cada um exibe e abre/prevê a
// saída. A ORDEM das coleções é global (reordenável no Catálogo).
import type { CollectionOptionProjection, ShowcaseProjection } from "~/types/showcase";

const { board, pending, refresh, isBusy, setActive, setCollections } = useShowcaseBoard();
const showcases = computed<ShowcaseProjection[]>(() => board.value?.showcases ?? []);
const allCollections = computed<CollectionOptionProjection[]>(() => board.value?.all_collections ?? []);
const loading = computed(() => pending.value && !board.value);

// saída servida pelo Django (menuboard/feed), não pelo host do Gestor.
const djangoBase = useRuntimeConfig().public.djangoPublicBaseUrl as string;
const outputHref = (sc: ShowcaseProjection) => `${djangoBase}${sc.output_path}`;

function toggleActive(sc: ShowcaseProjection) {
  setActive(sc.ref, !sc.is_active);
}

// editor de coleções (popover): rascunho local, aplica de uma vez.
const editRef = ref<string | null>(null);
const draft = ref<Set<string>>(new Set());
function openEdit(sc: ShowcaseProjection) {
  editRef.value = sc.ref;
  draft.value = new Set(sc.collections.map((c) => c.ref));
}
function toggleDraft(ref_: string) {
  const next = new Set(draft.value);
  if (next.has(ref_)) next.delete(ref_);
  else next.add(ref_);
  draft.value = next;
}
async function applyEdit(sc: ShowcaseProjection) {
  await setCollections(sc.ref, [...draft.value]);
  editRef.value = null;
}

useHead({ title: "Expositores · Gestor" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <UiToolbar>
      <div class="flex items-center gap-2">
        <Icon name="lucide:monitor-play" class="size-4 text-muted-foreground" />
        <h1 class="text-sm font-semibold">Expositores</h1>
        <span class="text-xs text-muted-foreground">exibem o cardápio para fora (TV, feeds)</span>
      </div>
      <template #end>
        <p class="hidden text-xs text-muted-foreground sm:block">
          <span class="tabular-nums">{{ showcases.length }}</span> expositor{{ showcases.length === 1 ? "" : "es" }}
        </p>
        <!-- criar/configurar a fundo (novo expositor, opções) é no Admin -->
        <a
          :href="`${djangoBase}/admin/shop/showcase/`" target="_blank" rel="noopener"
          class="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          title="Criar / configurar expositores no Admin"
        >
          <Icon name="lucide:settings" class="size-4" />
          <span class="hidden sm:inline">Admin</span>
          <Icon name="lucide:external-link" class="size-3.5 opacity-60" />
        </a>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <!-- skeleton -->
      <div v-if="loading" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div v-for="i in 3" :key="i" class="h-40 animate-pulse rounded-xl border border-border bg-muted/40"></div>
      </div>

      <div v-else-if="showcases.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="sc in showcases" :key="sc.ref"
          class="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 transition"
          :class="sc.is_active ? '' : 'opacity-70'"
        >
          <!-- header: tipo + nome + switch ativo -->
          <div class="flex items-start gap-3">
            <span class="grid size-9 shrink-0 place-items-center rounded-md border bg-muted/40 text-foreground">
              <Icon :name="`lucide:${sc.kind_icon}`" class="size-4" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium text-foreground">{{ sc.name }}</p>
              <p class="text-xs text-muted-foreground">{{ sc.kind_label }}</p>
            </div>
            <button
              type="button" role="switch" :aria-checked="sc.is_active"
              class="relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-40"
              :class="sc.is_active ? 'bg-emerald-500' : 'bg-muted-foreground/30'"
              :disabled="isBusy(sc.ref)"
              :aria-label="sc.is_active ? 'Pausar expositor' : 'Ativar expositor'"
              :title="sc.is_active ? 'Ativo — clique para pausar' : 'Pausado — clique para ativar'"
              @click="toggleActive(sc)"
            >
              <span class="inline-block size-4 rounded-full bg-white shadow-sm transition-transform" :class="sc.is_active ? 'translate-x-4' : 'translate-x-0.5'"></span>
            </button>
          </div>

          <!-- coleções exibidas -->
          <div class="flex min-h-8 flex-wrap items-center gap-1.5">
            <span
              v-for="c in sc.collections" :key="c.ref"
              class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
              :class="c.exists ? 'border-border text-muted-foreground' : 'border-destructive/40 text-destructive'"
            >
              <Icon v-if="!c.exists" name="lucide:triangle-alert" class="size-3" />
              {{ c.name }}
            </span>
            <span v-if="!sc.collections.length" class="text-xs text-muted-foreground/70">Nenhuma coleção — nada a exibir.</span>
          </div>

          <!-- ações -->
          <div class="mt-auto flex items-center gap-1.5 border-t border-border pt-3">
            <UiPopover :open="editRef === sc.ref" @update:open="(v) => { if (!v) editRef = null; else openEdit(sc); }">
              <UiPopoverTrigger as-child>
                <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent">
                  <Icon name="lucide:layers" class="size-3.5" /> Coleções
                </button>
              </UiPopoverTrigger>
              <UiPopoverContent align="start" :side-offset="6" class="w-60 p-2">
                <p class="mb-1 px-1 text-xs font-medium text-muted-foreground">Coleções exibidas</p>
                <div class="max-h-60 overflow-auto">
                  <label
                    v-for="opt in allCollections" :key="opt.ref"
                    class="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1.5 text-sm transition hover:bg-accent"
                  >
                    <input type="checkbox" :checked="draft.has(opt.ref)" class="size-4 rounded border-border accent-foreground" @change="toggleDraft(opt.ref)" />
                    <span class="flex-1 truncate">{{ opt.name }}</span>
                    <span class="text-xs tabular-nums text-muted-foreground/60">{{ opt.product_count }}</span>
                  </label>
                </div>
                <div class="mt-2 flex justify-end gap-1.5 border-t border-border pt-2">
                  <button type="button" class="rounded-md border px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="editRef = null">Cancelar</button>
                  <button type="button" :disabled="isBusy(sc.ref)" class="rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="applyEdit(sc)">Aplicar</button>
                </div>
              </UiPopoverContent>
            </UiPopover>

            <a
              :href="outputHref(sc)" target="_blank" rel="noopener"
              class="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
              :title="sc.output_path"
            >
              <Icon :name="sc.capability === 'display' ? 'lucide:external-link' : 'lucide:code-xml'" class="size-3.5" />
              {{ sc.capability === "display" ? "Abrir TV" : "Ver feed" }}
            </a>
          </div>
        </article>
      </div>

      <div v-else class="grid place-items-center rounded-xl border border-dashed border-border py-16 text-center">
        <Icon name="lucide:monitor-off" class="mb-2 size-8 text-muted-foreground/40" />
        <p class="text-sm text-muted-foreground">Nenhum expositor. Crie um no Admin (menuboard ou feed).</p>
      </div>
    </section>
  </main>
</template>
