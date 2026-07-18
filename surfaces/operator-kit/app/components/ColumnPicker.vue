<script setup lang="ts">
// Seletor de colunas — botão discreto na toolbar que abre a lista de colunas
// opcionais com marcação. Mesmo desenho de dropdown da FilterBar (fecha ao clicar
// fora / Esc), para as duas ferramentas da toolbar se comportarem igual.
//
// Genérico de propósito: não conhece o domínio. O app passa as colunas que PODEM
// sumir — a coluna obrigatória fica de fora da lista e por isso é inocultável.
import { hideAll, isVisible, showAll, toggleColumn, visibleCount } from "../presentation/columnPicker";
import type { ColumnOption, HiddenColumns } from "../types/columns";

const props = withDefaults(
  defineProps<{
    columns: ColumnOption[];
    /** Colunas ocultas, por id (v-model). */
    modelValue: HiddenColumns;
    /** Rótulo do gatilho. */
    label?: string;
  }>(),
  { label: "Colunas" },
);

const emit = defineEmits<{ "update:modelValue": [HiddenColumns] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);

const shown = computed(() => visibleCount(props.columns, props.modelValue));
const total = computed(() => props.columns.length);
// O gatilho só vira "3 de 7" quando há recorte: sem coluna oculta ele fica quieto,
// como qualquer controle que não está fazendo nada.
const hasHidden = computed(() => shown.value < total.value);

function close() {
  open.value = false;
}

function toggle(id: string) {
  emit("update:modelValue", toggleColumn(props.modelValue, id));
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return;
  if (root.value && !root.value.contains(event.target as Node)) close();
}

// Esc no documento, não no root: depois de marcar uma coluna o foco pode estar em
// qualquer lugar, e Esc que só funciona "às vezes" é pior do que não ter.
function onDocumentKeydown(event: KeyboardEvent) {
  if (open.value && event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown);
  document.addEventListener("keydown", onDocumentKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  document.removeEventListener("keydown", onDocumentKeydown);
});
</script>

<template>
  <div ref="root" class="relative flex items-center">
    <button
      type="button"
      class="inline-flex h-7 items-center gap-1 rounded-full border border-dashed border-border px-2.5 text-xs font-medium text-muted-foreground transition hover:border-solid hover:bg-accent hover:text-foreground"
      :class="open || hasHidden ? 'border-solid bg-accent text-foreground' : ''"
      aria-haspopup="menu"
      :aria-expanded="open"
      :title="hasHidden ? `${shown} de ${total} colunas visíveis` : 'Escolher colunas'"
      @click="open = !open"
    >
      <Icon name="lucide:columns-3" class="size-3.5" />
      {{ label }}
      <span v-if="hasHidden" class="tabular-nums">{{ shown }}/{{ total }}</span>
    </button>

    <div
      v-if="open"
      role="menu"
      class="absolute left-0 top-8 z-40 w-56 rounded-lg border border-border bg-card p-1 shadow-lg"
    >
      <div class="flex items-center gap-1 px-1 pb-1">
        <button
          type="button"
          class="flex-1 rounded px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-40"
          :disabled="!hasHidden"
          @click="emit('update:modelValue', showAll())"
        >
          Mostrar todas
        </button>
        <button
          type="button"
          class="flex-1 rounded px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-40"
          :disabled="shown === 0"
          @click="emit('update:modelValue', hideAll(columns))"
        >
          Esconder todas
        </button>
      </div>
      <div class="mb-1 h-px bg-border"></div>

      <div class="max-h-64 overflow-auto">
        <button
          v-for="column in columns"
          :key="column.id"
          type="button"
          role="menuitemcheckbox"
          :aria-checked="isVisible(modelValue, column.id)"
          class="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-sm transition hover:bg-accent"
          @click="toggle(column.id)"
        >
          <span
            class="grid size-4 shrink-0 place-items-center rounded border transition"
            :class="isVisible(modelValue, column.id)
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border'"
          >
            <Icon v-if="isVisible(modelValue, column.id)" name="lucide:check" class="size-3" />
          </span>
          <span class="truncate" :class="isVisible(modelValue, column.id) ? '' : 'text-muted-foreground'">
            {{ column.label }}
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
