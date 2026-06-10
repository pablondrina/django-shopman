<script setup lang="ts">
// Tab Board (spec §2.3) — the map of open/free comandas. Odoo-style first
// screen: pick or open a comanda before ringing. It renders the tabs Projection
// through `presentation/tabBoard` (ordering, in-use/all filter, per-card shape)
// and emits intent; it owns no orchestration. `move_lines` is Arc 4 — here the
// board only lists, selects and opens.
import type { POSTabProjection } from "~/types/pos";
import { countOpenTabs, filterTabs, sanitizeTabRef, sortTabs, tabCardView, type TabCardView, type TabFilter } from "~/presentation/tabBoard";

const props = defineProps<{
  tabs: POSTabProjection[];
  /** ref of the comanda bound to the current sale (highlighted). */
  selectedTabRef: string;
  /** there is an un-associated draft cart: selecting a busy tab is blocked. */
  hasDraft: boolean;
  busy: boolean;
  modelValue: string;
  maxLength: number;
  placeholder: string;
  disallowedChars: string[];
}>();

const emit = defineEmits<{
  "update:modelValue": [string];
  open: [POSTabProjection | string];
  requestAssociation: [];
}>();

// View preferences are board-local presentation state (not data, not policy).
const tabFilter = ref<TabFilter>("all");
const tabView = ref<"grid" | "list">("grid");

const ordered = computed(() => sortTabs(props.tabs));
const openCount = computed(() => countOpenTabs(props.tabs));
const cards = computed(() =>
  filterTabs(ordered.value, tabFilter.value).map((tab) => ({ tab, view: tabCardView(tab, props.selectedTabRef) })),
);

// Board color = a traffic-light semantic (Pablo, 2026-06-10): cor só onde tem
// significado. Selecionada vence (a venda ativa); depois "não pago" (âmbar =
// atenção real, disparado e não quitado); depois "livre" (verde = disponível,
// pode receber); "em uso" recede em neutro (ocupada, em andamento, sem ação).
function cardTone(view: TabCardView): string {
  if (view.selected) return "border-primary bg-primary/5";
  if (view.isUnpaid) return "border-amber-500/40 bg-amber-500/10";
  if (view.isFree) return "border-green-500/45 bg-green-500/5";
  return "";
}

function updateInput(value: unknown) {
  emit("update:modelValue", sanitizeTabRef(String(value || ""), {
    maxLength: props.maxLength,
    disallowedChars: props.disallowedChars,
  }));
}

function submitInput() {
  if (!props.modelValue.trim()) return;
  emit("open", props.modelValue);
}

function activateTab(tab: POSTabProjection) {
  if (props.hasDraft) emit("requestAssociation");
  else emit("open", tab);
}

// F2 focuses the comanda input (the shell owns the shortcut, the board the field).
const inputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
defineExpose({ focus: () => inputRef.value?.inputRef?.focus() });
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <form class="flex shrink-0 gap-2" @submit.prevent="submitInput">
      <UiInput
        ref="inputRef"
        :model-value="modelValue"
        class="h-11 max-w-xs flex-1 text-base"
        :maxlength="maxLength"
        :placeholder="placeholder"
        @update:model-value="updateInput"
      />
      <UiButton type="submit" size="lg" class="h-11 shrink-0 gap-2" :disabled="busy || !modelValue.trim()">
        <Icon name="lucide:plus" class="size-5" />
        Abrir / nova
      </UiButton>
    </form>
    <div v-if="tabs.length" class="flex shrink-0 flex-wrap items-center gap-2">
      <div class="flex gap-1">
        <UiButton
          size="sm"
          variant="outline"
          :class="tabFilter === 'all' ? 'border-primary bg-primary/5' : ''"
          @click="tabFilter = 'all'"
        >
          Todas {{ tabs.length }}
        </UiButton>
        <UiButton
          size="sm"
          variant="outline"
          :class="tabFilter === 'in_use' ? 'border-primary bg-primary/5' : ''"
          @click="tabFilter = 'in_use'"
        >
          Em uso {{ openCount }}
        </UiButton>
      </div>
      <div class="ml-auto flex gap-1">
        <UiButton
          size="icon-sm"
          variant="outline"
          aria-label="Ver em grade"
          title="Grade"
          :class="tabView === 'grid' ? 'border-primary bg-primary/5' : ''"
          @click="tabView = 'grid'"
        >
          <Icon name="lucide:layout-grid" class="size-4" />
        </UiButton>
        <UiButton
          size="icon-sm"
          variant="outline"
          aria-label="Ver em lista"
          title="Lista"
          :class="tabView === 'list' ? 'border-primary bg-primary/5' : ''"
          @click="tabView = 'list'"
        >
          <Icon name="lucide:list" class="size-4" />
        </UiButton>
      </div>
    </div>

    <p v-if="!tabs.length" class="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      Nenhuma comanda ainda. Digite uma referência acima para abrir a primeira.
    </p>
    <p v-else-if="!cards.length" class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
      Nenhuma comanda em uso agora.
      <button type="button" class="font-medium underline underline-offset-4" @click="tabFilter = 'all'">Ver todas</button>
    </p>
    <div
      v-else
      class="max-h-[72vh] content-start overflow-y-auto pr-1 md:max-h-none md:min-h-0 md:flex-1"
      :class="tabView === 'grid' ? 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6' : 'grid gap-2'"
    >
      <button
        v-for="{ tab, view } in cards"
        :key="view.ref"
        type="button"
        class="flex h-[5.5rem] flex-col gap-0.5 overflow-hidden rounded-lg border px-3 py-2 text-left transition hover:border-primary/50 hover:bg-accent"
        :class="cardTone(view)"
        @click="activateTab(tab)"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate font-semibold tabular-nums">#{{ view.displayRef }}</span>
          <span
            v-if="view.isUnpaid"
            class="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400"
            title="Disparado para a cozinha e ainda não pago"
          >
            <Icon name="lucide:flame" class="size-3" />
            não pago
          </span>
          <span v-else class="shrink-0 text-xs text-muted-foreground">{{ view.statusLabel }}</span>
        </div>
        <span class="truncate text-xs font-medium">{{ view.identity }}</span>
        <span
          class="mt-auto truncate text-xs tabular-nums"
          :class="view.isFree ? 'text-muted-foreground' : 'font-semibold'"
        >
          {{ view.summary }}
        </span>
      </button>
    </div>
  </section>
</template>
