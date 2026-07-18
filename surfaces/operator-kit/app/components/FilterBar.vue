<script setup lang="ts">
// Barra de filtros compacta (padrão Linear/Notion): uma linha só, com os recortes
// ativos como chips e um "+ Filtro" que abre a lista de dimensões e, ao escolher
// uma, o painel de opções no MESMO dropdown (dois passos, com voltar) — o operador
// não perde o contexto e o popover nunca sai da tela.
//
// Genérica de propósito: não conhece o domínio. O app hospedeiro passa as dimensões
// e recebe de volta os filtros ativos; interpretar o valor é dele.
import {
  activeDimensions,
  chipLabel,
  clearDimension,
  isSelected,
  optionsFor,
  toggleOption,
} from "../presentation/filterBar";
import type { ActiveFilters, FilterDimension } from "../types/filters";

const props = withDefaults(
  defineProps<{
    dimensions: FilterDimension[];
    modelValue: ActiveFilters;
    /** Rótulo do gatilho quando não há nenhum filtro ativo. */
    label?: string;
  }>(),
  { label: "Filtro" },
);

const emit = defineEmits<{ "update:modelValue": [ActiveFilters] }>();

const open = ref(false);
// Dimensão aberta no 2º passo do dropdown (null = lista de dimensões).
const step = ref<FilterDimension | null>(null);
const root = ref<HTMLElement | null>(null);

const chips = computed(() => activeDimensions(props.dimensions, props.modelValue));
const hasFilters = computed(() => chips.value.length > 0);

function openMenu() {
  step.value = null;
  open.value = !open.value;
}

function close() {
  open.value = false;
  step.value = null;
}

function pickDimension(dimension: FilterDimension) {
  step.value = dimension;
}

function pick(dimension: FilterDimension, value: string) {
  emit("update:modelValue", toggleOption(props.modelValue, dimension, value));
  // Multi-select fica aberto (marcar vários é um gesto só); os demais fecham.
  if (dimension.type !== "multi-select") close();
}

function remove(dimension: FilterDimension) {
  emit("update:modelValue", clearDimension(props.modelValue, dimension.id));
}

function clearAll() {
  emit("update:modelValue", {});
  close();
}

// Fechar ao clicar fora / Esc — o dropdown é leve demais para merecer um portal.
function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return;
  if (root.value && !root.value.contains(event.target as Node)) close();
}

onMounted(() => document.addEventListener("pointerdown", onDocumentPointerDown));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onDocumentPointerDown));
</script>

<template>
  <div ref="root" class="relative flex flex-wrap items-center gap-1.5" @keydown.esc="close">
    <!-- chips do recorte ativo: "dimensão: valor" + X -->
    <span
      v-for="dimension in chips"
      :key="dimension.id"
      class="inline-flex h-7 items-center gap-1 rounded-full border border-border bg-accent/60 pl-2.5 pr-1 text-xs font-medium text-foreground"
    >
      <span class="max-w-[18rem] truncate">{{ chipLabel(dimension, modelValue) }}</span>
      <button
        type="button"
        class="grid size-5 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground"
        :aria-label="`Remover filtro ${dimension.label}`"
        @click="remove(dimension)"
      >
        <Icon name="lucide:x" class="size-3" />
      </button>
    </span>

    <!-- gatilho + dropdown de dois passos -->
    <button
      type="button"
      class="inline-flex h-7 items-center gap-1 rounded-full border border-dashed border-border px-2.5 text-xs font-medium text-muted-foreground transition hover:border-solid hover:bg-accent hover:text-foreground"
      :class="open ? 'border-solid bg-accent text-foreground' : ''"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="openMenu"
    >
      <Icon name="lucide:list-filter" class="size-3.5" />
      {{ label }}
    </button>

    <button
      v-if="hasFilters"
      type="button"
      class="inline-flex h-7 items-center rounded-full px-2 text-xs font-medium text-muted-foreground transition hover:text-foreground"
      @click="clearAll"
    >
      Limpar filtros
    </button>

    <div
      v-if="open"
      role="menu"
      class="absolute left-0 top-8 z-40 w-60 rounded-lg border border-border bg-card p-1 shadow-lg"
    >
      <!-- passo 1: dimensões -->
      <template v-if="!step">
        <button
          v-for="dimension in dimensions"
          :key="dimension.id"
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-sm transition hover:bg-accent"
          @click="pickDimension(dimension)"
        >
          <span class="truncate">{{ dimension.label }}</span>
          <Icon name="lucide:chevron-right" class="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </template>

      <!-- passo 2: opções da dimensão -->
      <template v-else>
        <button
          type="button"
          class="mb-0.5 flex w-full items-center gap-1 rounded px-2 py-1.5 text-left text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          @click="step = null"
        >
          <Icon name="lucide:chevron-left" class="size-3.5" /> {{ step.label }}
        </button>
        <div class="max-h-64 overflow-auto">
          <button
            v-for="option in optionsFor(step)"
            :key="option.value"
            type="button"
            role="menuitemcheckbox"
            :aria-checked="isSelected(modelValue, step, option.value)"
            class="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-sm transition hover:bg-accent"
            @click="pick(step, option.value)"
          >
            <span
              class="grid size-4 shrink-0 place-items-center rounded border transition"
              :class="isSelected(modelValue, step, option.value)
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border'"
            >
              <Icon v-if="isSelected(modelValue, step, option.value)" name="lucide:check" class="size-3" />
            </span>
            <span class="truncate">{{ option.label }}</span>
            <span v-if="option.count !== undefined" class="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
              {{ option.count }}
            </span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
