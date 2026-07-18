<script setup lang="ts">
// PIM social — painel de edição dos atributos de catálogo social de UM produto
// (Product.metadata['social'], Arc A). Presentacional: o pai é dono do fetch/save
// (via useCatalogMatrix.saveSocial) e do estado de ocupado; aqui mora só o rascunho
// do formulário. Campos alimentam feeds comerciais (Google/Meta/TikTok): marca +
// categoria são o mínimo p/ publicar; GTIN/condição refinam; hashtags/legenda são
// conteúdo social. A validação forte (GTIN mod-10, categoria) é do backend — aqui só
// damos as dicas e desabilitamos o salvar sem mudanças.
import { pimSummary } from "~/presentation/catalog";
import type { CatalogRowProjection } from "~/types/catalog";

const props = defineProps<{
  open: boolean;
  row: CatalogRowProjection | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [patch: Record<string, unknown>];
}>();

const CONDITIONS = [
  { value: "new", label: "Novo" },
  { value: "refurbished", label: "Recondicionado" },
  { value: "used", label: "Usado" },
] as const;

// rascunho editável — reidratado toda vez que o painel abre (não vazar o produto
// anterior). hashtags vivem como texto livre; viram lista ao salvar.
const draft = reactive({
  brand: "",
  gtin: "",
  condition: "new",
  google_product_category: "",
  tiktok_category_id: "",
  hashtagsText: "",
  social_caption: "",
});

function hydrate(row: CatalogRowProjection | null) {
  const s = row?.social;
  draft.brand = s?.brand ?? "";
  draft.gtin = s?.gtin ?? "";
  draft.condition = s?.condition || "new";
  draft.google_product_category = s?.google_product_category ?? "";
  draft.tiktok_category_id = s?.tiktok_category_id ?? "";
  draft.hashtagsText = (s?.hashtags ?? []).join(" ");
  draft.social_caption = s?.social_caption ?? "";
}

watch(
  () => [props.open, props.row?.sku],
  () => { if (props.open) hydrate(props.row); },
  { immediate: true },
);

const summary = computed(() => (props.row ? pimSummary(props.row) : null));

// hashtags: texto "pão, #artesanal caseiro" → ["pão","artesanal","caseiro"].
function parseHashtags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.replace(/,/g, " ").split(/\s+/)) {
    const tag = raw.replace(/^#+/, "").trim();
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

function onSave() {
  emit("save", {
    brand: draft.brand.trim(),
    gtin: draft.gtin.trim(),
    condition: draft.condition,
    google_product_category: draft.google_product_category.trim(),
    tiktok_category_id: draft.tiktok_category_id.trim(),
    hashtags: parseHashtags(draft.hashtagsText),
    social_caption: draft.social_caption.trim(),
  });
}

const fieldClass =
  "h-9 w-full rounded-md border border-border bg-background px-2.5 text-sm outline-none focus:ring-1 focus:ring-ring";
</script>

<template>
  <UiSheet :open="open" @update:open="(v) => emit('update:open', v)">
    <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-md" :title="undefined">
      <div class="flex items-start justify-between border-b border-border px-5 py-4">
        <div class="min-w-0">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Dados para redes sociais</p>
          <h2 class="truncate text-lg font-semibold text-foreground">{{ row?.name ?? "Produto" }}</h2>
          <p v-if="row" class="font-mono text-xs text-muted-foreground">{{ row.sku }}</p>
        </div>
        <span
          v-if="summary"
          class="ml-3 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium"
          :class="summary.complete ? 'bg-success/15 text-emerald-600 dark:text-emerald-400' : 'bg-warning/15 text-amber-600 dark:text-amber-400'"
        >{{ summary.complete ? "Pronto p/ feed" : "Incompleto" }}</span>
      </div>

      <div class="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <p v-if="summary && summary.missing.length" class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          Para publicar em Google/Meta, preencha: {{ summary.missing.join(" e ") }}.
        </p>

        <label class="block">
          <span class="mb-1 block text-xs font-medium text-muted-foreground">Marca</span>
          <input v-model="draft.brand" :class="fieldClass" type="text" placeholder="Ex.: Nelson Boulangerie" />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-xs font-medium text-muted-foreground">GTIN / código de barras</span>
            <input v-model="draft.gtin" :class="fieldClass" type="text" inputmode="numeric" placeholder="8, 12, 13 ou 14 dígitos" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs font-medium text-muted-foreground">Condição</span>
            <select v-model="draft.condition" :class="fieldClass">
              <option v-for="c in CONDITIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </label>
        </div>

        <label class="block">
          <span class="mb-1 block text-xs font-medium text-muted-foreground">Categoria Google</span>
          <input v-model="draft.google_product_category" :class="fieldClass" type="text" placeholder="Ex.: Food, Beverages & Tobacco > Food Items > Bakery" />
        </label>

        <label class="block">
          <span class="mb-1 block text-xs font-medium text-muted-foreground">Categoria TikTok</span>
          <input v-model="draft.tiktok_category_id" :class="fieldClass" type="text" placeholder="ID da categoria (opcional)" />
        </label>

        <label class="block">
          <span class="mb-1 block text-xs font-medium text-muted-foreground">Hashtags</span>
          <input v-model="draft.hashtagsText" :class="fieldClass" type="text" placeholder="pão artesanal caseiro" />
          <span class="mt-1 block text-xs text-muted-foreground">Separe por espaço ou vírgula. O "#" é opcional.</span>
        </label>

        <label class="block">
          <span class="mb-1 block text-xs font-medium text-muted-foreground">Legenda social</span>
          <textarea
            v-model="draft.social_caption"
            rows="3"
            class="w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
            placeholder="Texto sugerido para posts e feeds."
          ></textarea>
        </label>
      </div>

      <div class="flex justify-end gap-2 border-t border-border px-5 py-4">
        <button
          type="button"
          class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          @click="emit('update:open', false)"
        >Cancelar</button>
        <button
          type="button"
          :disabled="busy"
          class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          @click="onSave"
        >
          <Icon v-if="busy" name="line-md:loading-loop" class="size-4" />
          Salvar
        </button>
      </div>
    </UiSheetContent>
  </UiSheet>
</template>
