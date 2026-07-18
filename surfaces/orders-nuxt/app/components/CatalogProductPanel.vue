<script setup lang="ts">
// Painel de produto — edição completa dos campos escalares de UM produto, sem sair
// do Gestor (antes só existia no Admin). Presentacional: o pai é dono do fetch/save
// (useCatalogMatrix.fetchProductDetail / saveProductDetail) e do estado de ocupado;
// aqui mora só o rascunho do formulário, dividido em três abas (Geral · Preço e
// config · Ingredientes). Emitimos APENAS os campos alterados — o backend faz merge
// parcial, então não tocar num campo é diferente de gravá-lo igual.
// Fora do escopo (segue no Admin): tabela nutricional, bundles, coleções, listings.
import type { ProductDetailPatch, ProductDetailProjection } from "~/types/catalog";

const props = defineProps<{
  open: boolean;
  sku: string | null;
  detail: ProductDetailProjection | null;
  loading: boolean;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [patch: ProductDetailPatch];
}>();

const TABS = [
  { id: "geral", label: "Geral" },
  { id: "config", label: "Preço e config" },
  { id: "ingredientes", label: "Ingredientes" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const tab = ref<TabId>("geral");

const POLICIES = [
  { value: "stock_only", label: "Somente estoque" },
  { value: "planned_ok", label: "Aceita planejado" },
  { value: "demand_ok", label: "Aceita demanda" },
] as const;

// rascunho editável — reidratado toda vez que o painel abre (não vazar o produto
// anterior). keywords vivem como texto livre; viram lista ao salvar. O preço é
// editado em reais (vírgula) e volta a centavos no patch.
const draft = reactive({
  name: "",
  short_description: "",
  long_description: "",
  keywordsText: "",
  image_url: "",
  priceText: "",
  unit: "",
  unit_weight_g: "" as number | "",
  availability_policy: "planned_ok",
  shelf_life_days: "" as number | "",
  storage_tip: "",
  production_cycle_hours: "" as number | "",
  is_batch_produced: false,
  is_published: true,
  is_sellable: true,
  ingredients_text: "",
});

const centsToText = (q: number) => (q / 100).toFixed(2).replace(".", ",");
const numOrBlank = (v: number | null) => (v === null || v === undefined ? "" : v);

function hydrate(detail: ProductDetailProjection | null) {
  draft.name = detail?.name ?? "";
  draft.short_description = detail?.short_description ?? "";
  draft.long_description = detail?.long_description ?? "";
  draft.keywordsText = (detail?.keywords ?? []).join(", ");
  draft.image_url = detail?.image_url ?? "";
  draft.priceText = centsToText(detail?.base_price_q ?? 0);
  draft.unit = detail?.unit ?? "un";
  draft.unit_weight_g = numOrBlank(detail?.unit_weight_g ?? null);
  draft.availability_policy = detail?.availability_policy || "planned_ok";
  draft.shelf_life_days = numOrBlank(detail?.shelf_life_days ?? null);
  draft.storage_tip = detail?.storage_tip ?? "";
  draft.production_cycle_hours = numOrBlank(detail?.production_cycle_hours ?? null);
  draft.is_batch_produced = detail?.is_batch_produced ?? false;
  draft.is_published = detail?.is_published ?? true;
  draft.is_sellable = detail?.is_sellable ?? true;
  draft.ingredients_text = detail?.ingredients_text ?? "";
}

watch(
  () => [props.open, props.sku, props.detail],
  () => {
    if (props.open) hydrate(props.detail);
  },
  { immediate: true },
);
watch(
  () => props.open,
  (isOpen) => { if (isOpen) tab.value = "geral"; },
);

// "pão, artesanal caseiro" → ["pão", "artesanal caseiro"] (vírgula separa; espaço não).
function parseKeywords(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const kw = raw.trim();
    if (kw && !out.includes(kw)) out.push(kw);
  }
  return out;
}

function parseBrl(text: string): number | null {
  const cleaned = text.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}

const priceInvalid = computed(() => parseBrl(draft.priceText) === null);

const nullableInt = (v: number | "") => (v === "" ? null : Number(v));

// Só o que mudou entra no patch — merge parcial no backend.
function buildPatch(): ProductDetailPatch {
  const current = props.detail;
  const patch: ProductDetailPatch = {};
  if (!current) return patch;

  const put = <K extends keyof ProductDetailPatch>(key: K, next: ProductDetailPatch[K], prev: unknown) => {
    if (next !== prev) patch[key] = next;
  };

  put("name", draft.name.trim(), current.name);
  put("short_description", draft.short_description.trim(), current.short_description);
  put("long_description", draft.long_description.trim(), current.long_description);
  put("image_url", draft.image_url.trim(), current.image_url);
  put("unit", draft.unit.trim(), current.unit);
  put("storage_tip", draft.storage_tip.trim(), current.storage_tip);
  put("ingredients_text", draft.ingredients_text.trim(), current.ingredients_text);
  put("availability_policy", draft.availability_policy, current.availability_policy);
  put("unit_weight_g", nullableInt(draft.unit_weight_g), current.unit_weight_g);
  put("shelf_life_days", nullableInt(draft.shelf_life_days), current.shelf_life_days);
  put("production_cycle_hours", nullableInt(draft.production_cycle_hours), current.production_cycle_hours);
  put("is_batch_produced", draft.is_batch_produced, current.is_batch_produced);
  put("is_published", draft.is_published, current.is_published);
  put("is_sellable", draft.is_sellable, current.is_sellable);

  const price_q = parseBrl(draft.priceText);
  if (price_q !== null && price_q !== current.base_price_q) patch.base_price_q = price_q;

  const keywords = parseKeywords(draft.keywordsText);
  const sameKeywords =
    keywords.length === current.keywords.length && keywords.every((k) => current.keywords.includes(k));
  if (!sameKeywords) patch.keywords = keywords;

  return patch;
}

const patchSize = computed(() => Object.keys(buildPatch()).length);
const canSave = computed(() => !props.busy && !props.loading && !priceInvalid.value && patchSize.value > 0);

function onSave() {
  if (!canSave.value) return;
  emit("save", buildPatch());
}

const fieldClass =
  "h-9 w-full rounded-md border border-border bg-background px-2.5 text-sm outline-none focus:ring-1 focus:ring-ring";
const areaClass =
  "w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm outline-none focus:ring-1 focus:ring-ring";
const labelClass = "mb-1 block text-xs font-medium text-muted-foreground";
</script>

<template>
  <UiSheet :open="open" @update:open="(v) => emit('update:open', v)">
    <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg" :title="undefined">
      <div class="border-b border-border px-5 py-4">
        <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Editar produto</p>
        <h2 class="truncate text-lg font-semibold text-foreground">{{ detail?.name || "Produto" }}</h2>
        <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span class="font-mono">{{ sku }}</span>
          <template v-if="detail?.primary_collection_name">
            <span class="text-muted-foreground/40">·</span>
            <span class="rounded bg-muted px-1.5 py-0.5">{{ detail.primary_collection_name }}</span>
          </template>
        </p>
      </div>

      <!-- abas: o formulário é longo demais para uma coluna só -->
      <div class="flex gap-1 border-b border-border px-3 pt-2">
        <button
          v-for="t in TABS"
          :key="t.id"
          type="button"
          class="rounded-t-md px-3 py-2 text-sm font-medium transition"
          :class="tab === t.id
            ? 'border-b-2 border-primary text-foreground'
            : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground'"
          @click="tab = t.id"
        >{{ t.label }}</button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 py-4">
        <div v-if="loading" class="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-4" /> Carregando produto…
        </div>

        <div v-else-if="!detail" class="py-8 text-sm text-muted-foreground">
          Não foi possível carregar este produto.
        </div>

        <template v-else>
          <!-- Geral -->
          <div v-show="tab === 'geral'" class="space-y-4">
            <label class="block">
              <span :class="labelClass">Nome</span>
              <input v-model="draft.name" :class="fieldClass" type="text" placeholder="Ex.: Pão francês" />
            </label>

            <label class="block">
              <!-- a barra do rótulo abre espaço p/ o botão "sugerir" (assist de IA, Fase 2) -->
              <span class="mb-1 flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-muted-foreground">Descrição curta</span>
              </span>
              <input
                v-model="draft.short_description" :class="fieldClass" type="text" maxlength="255"
                placeholder="Uma linha para listagens e vitrine"
              />
              <span class="mt-1 block text-xs text-muted-foreground">{{ draft.short_description.length }}/255</span>
            </label>

            <label class="block">
              <span class="mb-1 flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-muted-foreground">Descrição longa</span>
              </span>
              <textarea v-model="draft.long_description" rows="5" :class="areaClass" placeholder="Texto completo da página do produto."></textarea>
            </label>

            <label class="block">
              <span :class="labelClass">Palavras-chave</span>
              <input v-model="draft.keywordsText" :class="fieldClass" type="text" placeholder="padaria, pão artesanal, fermentação natural" />
              <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula. Usadas em busca e SEO.</span>
            </label>

            <label class="block">
              <span :class="labelClass">URL da imagem</span>
              <input v-model="draft.image_url" :class="fieldClass" type="url" placeholder="https://…" />
            </label>
            <img
              v-if="draft.image_url"
              :src="draft.image_url" alt="Prévia da imagem do produto"
              class="h-32 w-32 rounded-lg border border-border object-cover"
            />
          </div>

          <!-- Preço e config -->
          <div v-show="tab === 'config'" class="space-y-4">
            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">Preço base (R$)</span>
                <input
                  v-model="draft.priceText" :class="fieldClass" type="text" inputmode="decimal" placeholder="0,00"
                  :aria-invalid="priceInvalid"
                />
                <span v-if="priceInvalid" class="mt-1 block text-xs text-destructive">Informe um valor válido.</span>
              </label>
              <label class="block">
                <span :class="labelClass">Unidade</span>
                <input v-model="draft.unit" :class="fieldClass" type="text" placeholder="un, kg, lt" />
              </label>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">Peso por unidade (g)</span>
                <input v-model="draft.unit_weight_g" :class="fieldClass" type="number" min="0" placeholder="Ex.: 150" />
              </label>
              <label class="block">
                <span :class="labelClass">Validade (dias)</span>
                <input v-model="draft.shelf_life_days" :class="fieldClass" type="number" min="0" placeholder="Vazio = não perece" />
              </label>
            </div>

            <label class="block">
              <span :class="labelClass">Política de disponibilidade</span>
              <select v-model="draft.availability_policy" :class="fieldClass">
                <option v-for="p in POLICIES" :key="p.value" :value="p.value">{{ p.label }}</option>
              </select>
            </label>

            <label class="block">
              <span :class="labelClass">Dica de conservação</span>
              <input v-model="draft.storage_tip" :class="fieldClass" type="text" maxlength="300" placeholder="Ex.: guarde em saco de pano por até 2 dias" />
            </label>

            <label class="block">
              <span :class="labelClass">Ciclo de produção (horas)</span>
              <input v-model="draft.production_cycle_hours" :class="fieldClass" type="number" min="0" placeholder="Ex.: 4" />
            </label>

            <label class="flex items-center gap-2 text-sm">
              <input v-model="draft.is_batch_produced" type="checkbox" class="size-4 rounded border-border" />
              Produzido em lote
            </label>

            <div class="space-y-2 rounded-lg border border-border p-3">
              <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Publicação</p>
              <label class="flex items-center gap-2 text-sm">
                <input v-model="draft.is_published" type="checkbox" class="size-4 rounded border-border" />
                Publicado no catálogo
              </label>
              <label class="flex items-center gap-2 text-sm">
                <input v-model="draft.is_sellable" type="checkbox" class="size-4 rounded border-border" />
                Disponível para venda
              </label>
            </div>
          </div>

          <!-- Ingredientes -->
          <div v-show="tab === 'ingredientes'" class="space-y-4">
            <label class="block">
              <span class="mb-1 flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-muted-foreground">Ingredientes</span>
              </span>
              <textarea
                v-model="draft.ingredients_text" rows="8" :class="areaClass"
                placeholder="Farinha de trigo, água, fermento natural, sal marinho."
              ></textarea>
              <span class="mt-1 block text-xs text-muted-foreground">
                Em ordem decrescente de peso, como manda a ANVISA.
              </span>
            </label>
            <p class="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              A tabela nutricional continua no Admin, que tem o formulário com as validações da ANVISA.
            </p>
          </div>
        </template>
      </div>

      <div class="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
        <span v-if="patchSize" class="mr-auto text-xs text-muted-foreground">{{ patchSize }} campo(s) alterado(s)</span>
        <button
          type="button"
          class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          @click="emit('update:open', false)"
        >Cancelar</button>
        <button
          type="button"
          :disabled="!canSave"
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
