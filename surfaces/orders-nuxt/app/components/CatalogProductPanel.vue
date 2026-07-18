<script setup lang="ts">
// Painel de produto — edição COMPLETA de um produto sem sair do Gestor. Presentacional:
// o pai é dono do fetch/save (useCatalogMatrix.fetchProductDetail / saveProductDetail)
// e do estado de ocupado; aqui mora só o rascunho, dividido em cinco abas:
// Geral · Preço e config · Ingredientes e nutrição · Redes sociais · Fiscal.
//
// Emitimos APENAS o que mudou — o backend faz merge parcial, então não tocar num campo
// é diferente de gravá-lo igual. Os blocos aninhados (social, fiscal, nutricional)
// também vão parciais: mandar só `brand` não apaga a categoria.
//
// Fora do escopo (segue no Admin): componentes de bundle, coleções e listings.
import type {
  AssistableField,
  NutritionFacts,
  ProductDetailPatch,
  ProductDetailProjection,
} from "~/types/catalog";

const props = defineProps<{
  open: boolean;
  sku: string | null;
  detail: ProductDetailProjection | null;
  loading: boolean;
  busy: boolean;
  // assist de IA por campo — o pai injeta (useCatalogMatrix); o painel segue
  // presentacional e testável sem rede.
  assist: (field: AssistableField, currentValue: string) => Promise<string>;
  assistBusy: (field: AssistableField) => boolean;
  // aba em que o painel abre — o menu da linha tem um atalho direto para "Redes
  // sociais", que antes era um slide-over separado.
  initialTab?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [patch: ProductDetailPatch];
}>();

const TABS = [
  { id: "geral", label: "Geral" },
  { id: "config", label: "Preço e config" },
  { id: "rotulagem", label: "Ingredientes e nutrição" },
  { id: "social", label: "Redes sociais" },
  { id: "fiscal", label: "Fiscal" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const tab = ref<TabId>("geral");

const POLICIES = [
  { value: "stock_only", label: "Somente estoque" },
  { value: "planned_ok", label: "Aceita planejado" },
  { value: "demand_ok", label: "Aceita demanda" },
] as const;

const CONDITIONS = [
  { value: "new", label: "Novo" },
  { value: "refurbished", label: "Recondicionado" },
  { value: "used", label: "Usado" },
] as const;

// Tabela nutricional: os mesmos três grupos do rótulo ANVISA, na mesma ordem do
// formulário do Admin. Rótulos em pt-BR, chaves em inglês (contrato do backend).
const SERVING_FIELDS = [
  { key: "serving_size_g", label: "Porção (g)", step: "1" },
  { key: "servings_per_container", label: "Porções por embalagem", step: "1" },
] as const;
const MACRO_FIELDS = [
  { key: "energy_kcal", label: "Valor energético (kcal)", step: "0.01" },
  { key: "carbohydrates_g", label: "Carboidratos (g)", step: "0.01" },
  { key: "sugars_g", label: "Açúcares (g)", step: "0.01" },
  { key: "proteins_g", label: "Proteínas (g)", step: "0.01" },
  { key: "total_fat_g", label: "Gorduras totais (g)", step: "0.01" },
  { key: "saturated_fat_g", label: "Gorduras saturadas (g)", step: "0.01" },
  { key: "trans_fat_g", label: "Gorduras trans (g)", step: "0.01" },
] as const;
const MICRO_FIELDS = [
  { key: "fiber_g", label: "Fibras (g)", step: "0.01" },
  { key: "sodium_mg", label: "Sódio (mg)", step: "0.01" },
] as const;
type NutritionKey = keyof NutritionFacts;
const NUTRITION_KEYS: NutritionKey[] = [
  ...SERVING_FIELDS.map((f) => f.key),
  ...MACRO_FIELDS.map((f) => f.key),
  ...MICRO_FIELDS.map((f) => f.key),
];

// rascunho editável — reidratado toda vez que o painel abre (não vazar o produto
// anterior). Listas (keywords, alérgenos, hashtags) vivem como texto livre e viram
// lista ao salvar. O preço é editado em reais (vírgula) e volta a centavos no patch.
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
  allows_next_day_sale: false,
  ingredients_text: "",
  allergensText: "",
  dietaryText: "",
  serves: "",
  approx_dimensions: "",
  nutrition: {} as Record<string, number | "">,
  social: {
    brand: "",
    gtin: "",
    mpn: "",
    condition: "new",
    google_product_category: "",
    tiktok_category_id: "",
    hashtagsText: "",
    social_caption: "",
  },
  fiscal: { profile: "own_production", ncm: "", cest: "", unit: "UN" },
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
  draft.allows_next_day_sale = detail?.allows_next_day_sale ?? false;
  draft.ingredients_text = detail?.ingredients_text ?? "";
  draft.allergensText = (detail?.allergens ?? []).join(", ");
  draft.dietaryText = (detail?.dietary_info ?? []).join(", ");
  draft.serves = detail?.serves ?? "";
  draft.approx_dimensions = detail?.approx_dimensions ?? "";

  const facts = detail?.nutrition_facts;
  const nutrition: Record<string, number | ""> = {};
  for (const key of NUTRITION_KEYS) {
    const value = facts?.[key];
    // 0 é valor legítimo (gordura trans zero é uma afirmação do rótulo), então só
    // null/undefined viram campo vazio.
    nutrition[key] = value === null || value === undefined ? "" : value;
  }
  draft.nutrition = nutrition;

  const s = detail?.social;
  draft.social.brand = s?.brand ?? "";
  draft.social.gtin = s?.gtin ?? "";
  draft.social.mpn = s?.mpn ?? "";
  draft.social.condition = s?.condition || "new";
  draft.social.google_product_category = s?.google_product_category ?? "";
  draft.social.tiktok_category_id = s?.tiktok_category_id ?? "";
  draft.social.hashtagsText = (s?.hashtags ?? []).join(" ");
  draft.social.social_caption = s?.social_caption ?? "";

  const f = detail?.fiscal;
  draft.fiscal.profile = f?.profile || "own_production";
  draft.fiscal.ncm = f?.ncm ?? "";
  draft.fiscal.cest = f?.cest ?? "";
  draft.fiscal.unit = f?.unit || "UN";
}

watch(
  () => [props.open, props.sku, props.detail],
  () => {
    if (props.open) hydrate(props.detail);
  },
  { immediate: true },
);
const isTabId = (value: string | undefined): value is TabId =>
  TABS.some((t) => t.id === value);

watch(
  () => props.open,
  (isOpen) => { if (isOpen) tab.value = isTabId(props.initialTab) ? props.initialTab : "geral"; },
);

const fiscalProfiles = computed(() => props.detail?.fiscal_profiles ?? []);
const activeFiscalProfile = computed(
  () => fiscalProfiles.value.find((p) => p.key === draft.fiscal.profile) ?? null,
);

// "pão, artesanal caseiro" → ["pão", "artesanal caseiro"] (vírgula separa; espaço não).
function parseCommaList(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const item = raw.trim();
    if (item && !out.includes(item)) out.push(item);
  }
  return out;
}

// hashtags: "pão, #artesanal caseiro" → ["pão","artesanal","caseiro"].
function parseHashtags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.replace(/,/g, " ").split(/\s+/)) {
    const tag = raw.replace(/^#+/, "").trim();
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

function parseBrl(text: string): number | null {
  const cleaned = text.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}

const priceInvalid = computed(() => parseBrl(draft.priceText) === null);

// NCM/CEST são textuais (zero à esquerda conta) e de tamanho fixo. Validamos aqui
// só para avisar cedo; quem manda é o backend (fiscalman).
const ncmInvalid = computed(() => draft.fiscal.ncm !== "" && !/^\d{8}$/.test(draft.fiscal.ncm));
const cestInvalid = computed(() => draft.fiscal.cest !== "" && !/^\d{7}$/.test(draft.fiscal.cest));
const cestRequired = computed(
  () => !!activeFiscalProfile.value?.requires_cest && draft.fiscal.cest.trim() === "",
);

const nullableInt = (v: number | "") => (v === "" ? null : Number(v));
const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

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
  put("allows_next_day_sale", draft.allows_next_day_sale, current.allows_next_day_sale);
  put("serves", draft.serves.trim(), current.serves);
  put("approx_dimensions", draft.approx_dimensions.trim(), current.approx_dimensions);

  const price_q = parseBrl(draft.priceText);
  if (price_q !== null && price_q !== current.base_price_q) patch.base_price_q = price_q;

  const keywords = parseCommaList(draft.keywordsText);
  if (!sameList(keywords, current.keywords)) patch.keywords = keywords;

  const allergens = parseCommaList(draft.allergensText);
  if (!sameList(allergens, current.allergens)) patch.allergens = allergens;

  const dietary = parseCommaList(draft.dietaryText);
  if (!sameList(dietary, current.dietary_info)) patch.dietary_info = dietary;

  // nutricional — só as chaves alteradas
  const nutrition: Record<string, number> = {};
  for (const key of NUTRITION_KEYS) {
    const raw = draft.nutrition[key];
    const next = raw === "" ? null : Number(raw);
    const prev = current.nutrition_facts?.[key] ?? null;
    if (next !== prev && next !== null) nutrition[key] = next;
  }
  if (Object.keys(nutrition).length) patch.nutrition_facts = nutrition as ProductDetailPatch["nutrition_facts"];

  // social — só as chaves alteradas
  const social: Record<string, unknown> = {};
  const s = current.social;
  if (draft.social.brand.trim() !== s.brand) social.brand = draft.social.brand.trim();
  if (draft.social.gtin.trim() !== s.gtin) social.gtin = draft.social.gtin.trim();
  if (draft.social.mpn.trim() !== s.mpn) social.mpn = draft.social.mpn.trim();
  if (draft.social.condition !== s.condition) social.condition = draft.social.condition;
  if (draft.social.google_product_category.trim() !== s.google_product_category)
    social.google_product_category = draft.social.google_product_category.trim();
  if (draft.social.tiktok_category_id.trim() !== s.tiktok_category_id)
    social.tiktok_category_id = draft.social.tiktok_category_id.trim();
  if (draft.social.social_caption.trim() !== s.social_caption)
    social.social_caption = draft.social.social_caption.trim();
  const hashtags = parseHashtags(draft.social.hashtagsText);
  if (!sameList(hashtags, s.hashtags)) social.hashtags = hashtags;
  if (Object.keys(social).length) patch.social = social as ProductDetailPatch["social"];

  // fiscal — só as chaves alteradas
  const fiscal: Record<string, string> = {};
  const f = current.fiscal;
  if (draft.fiscal.profile !== f.profile) fiscal.profile = draft.fiscal.profile;
  if (draft.fiscal.ncm.trim() !== f.ncm) fiscal.ncm = draft.fiscal.ncm.trim();
  if (draft.fiscal.cest.trim() !== f.cest) fiscal.cest = draft.fiscal.cest.trim();
  if (draft.fiscal.unit.trim() !== f.unit) fiscal.unit = draft.fiscal.unit.trim();
  if (Object.keys(fiscal).length) patch.fiscal = fiscal as ProductDetailPatch["fiscal"];

  return patch;
}

const patchSize = computed(() => Object.keys(buildPatch()).length);
const formInvalid = computed(() => priceInvalid.value || ncmInvalid.value || cestInvalid.value);
const canSave = computed(() => !props.busy && !props.loading && !formInvalid.value && patchSize.value > 0);

function onSave() {
  if (!canSave.value) return;
  emit("save", buildPatch());
}

const fieldClass =
  "h-9 w-full rounded-md border border-border bg-background px-2.5 text-sm outline-none focus:ring-1 focus:ring-ring";
const areaClass =
  "w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm outline-none focus:ring-1 focus:ring-ring";
const labelClass = "mb-1 block text-xs font-medium text-muted-foreground";
const sectionClass = "text-xs font-medium uppercase tracking-wide text-muted-foreground";
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

      <!-- abas: o formulário é longo demais para uma coluna só. Rolam na horizontal
           porque cinco rótulos não cabem na largura do slide-over. -->
      <div class="flex gap-1 overflow-x-auto border-b border-border px-3 pt-2">
        <button
          v-for="t in TABS"
          :key="t.id"
          type="button"
          class="shrink-0 rounded-t-md px-3 py-2 text-sm font-medium transition"
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

            <CatalogAiSuggest
              field="short_description"
              label="Descrição curta"
              :current="draft.short_description"
              :busy="assistBusy('short_description')"
              :assist="assist"
              @accept="(text) => (draft.short_description = text)"
            >
              <input
                v-model="draft.short_description" :class="fieldClass" type="text" maxlength="255"
                placeholder="Uma linha para listagens e vitrine"
              />
              <span class="mt-1 block text-xs text-muted-foreground">{{ draft.short_description.length }}/255</span>
            </CatalogAiSuggest>

            <CatalogAiSuggest
              field="long_description"
              label="Descrição longa"
              :current="draft.long_description"
              :busy="assistBusy('long_description')"
              :assist="assist"
              @accept="(text) => (draft.long_description = text)"
            >
              <textarea v-model="draft.long_description" rows="5" :class="areaClass" placeholder="Texto completo da página do produto."></textarea>
            </CatalogAiSuggest>

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

            <label class="flex items-center gap-2 text-sm">
              <input v-model="draft.allows_next_day_sale" type="checkbox" class="size-4 rounded border-border" />
              Pode ser vendido no dia seguinte
            </label>

            <div class="space-y-2 rounded-lg border border-border p-3">
              <p :class="sectionClass">Publicação</p>
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

          <!-- Ingredientes e nutrição -->
          <div v-show="tab === 'rotulagem'" class="space-y-5">
            <CatalogAiSuggest
              field="ingredients_text"
              label="Ingredientes"
              :current="draft.ingredients_text"
              :busy="assistBusy('ingredients_text')"
              :assist="assist"
              hint="Em ordem decrescente de peso, como manda a ANVISA."
              @accept="(text) => (draft.ingredients_text = text)"
            >
              <textarea
                v-model="draft.ingredients_text" rows="6" :class="areaClass"
                placeholder="Farinha de trigo, água, fermento natural, sal marinho."
              ></textarea>
            </CatalogAiSuggest>

            <div class="space-y-3 rounded-lg border border-border p-3">
              <p :class="sectionClass">Rotulagem para compra remota</p>
              <p
                v-if="detail.dietary_auto_filled && (detail.allergens.length || detail.dietary_info.length)"
                class="rounded-md bg-muted/60 px-2.5 py-2 text-xs text-muted-foreground"
              >
                Alérgenos e restrições vieram da receita. Ao editar aqui, o produto passa a
                ignorar a receita e você fica responsável por manter estes campos.
              </p>

              <label class="block">
                <span :class="labelClass">Alérgenos</span>
                <input v-model="draft.allergensText" :class="fieldClass" type="text" placeholder="glúten, leite, gergelim" />
                <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula.</span>
              </label>

              <label class="block">
                <span :class="labelClass">Restrições atendidas</span>
                <input v-model="draft.dietaryText" :class="fieldClass" type="text" placeholder="100% vegetal, sem lactose" />
                <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula.</span>
              </label>

              <div class="grid grid-cols-2 gap-3">
                <label class="block">
                  <span :class="labelClass">Serve</span>
                  <input v-model="draft.serves" :class="fieldClass" type="text" placeholder="Ex.: 2 a 4 pessoas" />
                </label>
                <label class="block">
                  <span :class="labelClass">Medidas aproximadas</span>
                  <input v-model="draft.approx_dimensions" :class="fieldClass" type="text" placeholder="Ex.: aprox. 24 x 12 cm" />
                </label>
              </div>
            </div>

            <div class="space-y-3 rounded-lg border border-border p-3">
              <p :class="sectionClass">Tabela nutricional</p>
              <p v-if="detail.nutrition_auto_filled" class="rounded-md bg-muted/60 px-2.5 py-2 text-xs text-muted-foreground">
                Estes valores foram calculados a partir da receita. Ao editar, o cálculo
                automático para de valer para este produto.
              </p>

              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in SERVING_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="pt-1 text-xs font-medium text-muted-foreground">Macronutrientes</p>
              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in MACRO_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="pt-1 text-xs font-medium text-muted-foreground">Micronutrientes</p>
              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in MICRO_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="text-xs text-muted-foreground">
                Preencher qualquer nutriente exige informar a porção. Gorduras trans e saturadas
                não podem passar das totais, nem açúcares dos carboidratos.
              </p>
            </div>
          </div>

          <!-- Redes sociais (PIM) -->
          <div v-show="tab === 'social'" class="space-y-4">
            <p class="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Alimentam os feeds comerciais (Google, Meta, TikTok). Marca e categoria Google são
              o mínimo para publicar.
            </p>

            <label class="block">
              <span :class="labelClass">Marca</span>
              <input v-model="draft.social.brand" :class="fieldClass" type="text" placeholder="Ex.: Nelson Boulangerie" />
            </label>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">GTIN / código de barras</span>
                <input v-model="draft.social.gtin" :class="fieldClass" type="text" inputmode="numeric" placeholder="8, 12, 13 ou 14 dígitos" />
              </label>
              <label class="block">
                <span :class="labelClass">Condição</span>
                <select v-model="draft.social.condition" :class="fieldClass">
                  <option v-for="c in CONDITIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
                </select>
              </label>
            </div>

            <label class="block">
              <span :class="labelClass">MPN (código do fabricante)</span>
              <input v-model="draft.social.mpn" :class="fieldClass" type="text" placeholder="Opcional" />
            </label>

            <label class="block">
              <span :class="labelClass">Categoria Google</span>
              <input
                v-model="draft.social.google_product_category" :class="fieldClass" type="text"
                placeholder="Ex.: Food, Beverages & Tobacco > Food Items > Bakery"
              />
            </label>

            <label class="block">
              <span :class="labelClass">Categoria TikTok</span>
              <input v-model="draft.social.tiktok_category_id" :class="fieldClass" type="text" placeholder="ID da categoria (opcional)" />
            </label>

            <CatalogAiSuggest
              field="hashtags"
              label="Hashtags"
              :current="draft.social.hashtagsText"
              :busy="assistBusy('hashtags')"
              :assist="assist"
              hint="Separe por espaço ou vírgula. O &quot;#&quot; é opcional."
              @accept="(text) => (draft.social.hashtagsText = text)"
            >
              <input v-model="draft.social.hashtagsText" :class="fieldClass" type="text" placeholder="pão artesanal caseiro" />
            </CatalogAiSuggest>

            <CatalogAiSuggest
              field="social_caption"
              label="Legenda social"
              :current="draft.social.social_caption"
              :busy="assistBusy('social_caption')"
              :assist="assist"
              @accept="(text) => (draft.social.social_caption = text)"
            >
              <textarea
                v-model="draft.social.social_caption" rows="3" :class="areaClass"
                placeholder="Texto sugerido para posts e feeds."
              ></textarea>
            </CatalogAiSuggest>
          </div>

          <!-- Fiscal (NFC-e) -->
          <div v-show="tab === 'fiscal'" class="space-y-4">
            <p class="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Usado na emissão da NFC-e. CFOP, CSOSN, origem e PIS/COFINS vêm do perfil — aqui
              só o que muda de produto para produto.
            </p>

            <label class="block">
              <span :class="labelClass">Perfil fiscal</span>
              <select v-model="draft.fiscal.profile" :class="fieldClass">
                <option v-for="p in fiscalProfiles" :key="p.key" :value="p.key">{{ p.name }}</option>
              </select>
            </label>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">NCM</span>
                <input
                  v-model="draft.fiscal.ncm" :class="fieldClass" type="text" inputmode="numeric"
                  maxlength="8" placeholder="8 dígitos" :aria-invalid="ncmInvalid"
                />
                <span v-if="ncmInvalid" class="mt-1 block text-xs text-destructive">NCM deve ter 8 dígitos.</span>
              </label>
              <label class="block">
                <span :class="labelClass">Unidade comercial</span>
                <input v-model="draft.fiscal.unit" :class="fieldClass" type="text" maxlength="6" placeholder="UN" />
              </label>
            </div>

            <label v-if="activeFiscalProfile?.requires_cest" class="block">
              <span :class="labelClass">CEST</span>
              <input
                v-model="draft.fiscal.cest" :class="fieldClass" type="text" inputmode="numeric"
                maxlength="7" placeholder="7 dígitos" :aria-invalid="cestInvalid"
              />
              <span v-if="cestInvalid" class="mt-1 block text-xs text-destructive">CEST deve ter 7 dígitos.</span>
              <span v-else-if="cestRequired" class="mt-1 block text-xs text-amber-600 dark:text-amber-400">
                Obrigatório para itens de revenda com substituição tributária.
              </span>
            </label>
            <p v-else class="text-xs text-muted-foreground">
              CEST não se aplica a fabricação própria.
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
