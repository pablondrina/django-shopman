<script setup lang="ts">
// Comanda header (Arc 5 · context bar) — the open comanda's command header,
// lifted out of the ticket panel into the top context bar so the cart keeps its
// vertical room for line items + numpad. Owns the renameable comanda number, the
// customer chip + sheet, and "liberar comanda" (with confirmation). It renders
// what the read-side hands it and emits intent; the shell resolves the commands.
import type { POSCustomerLookupProjection, POSCustomerSearchResult } from "~/types/pos";

const props = defineProps<{
  tabDisplay: string;
  hasOpenTab: boolean;
  canRename: boolean;
  customerName: string;
  customerPhone: string;
  customerLookup: POSCustomerLookupProjection | null;
  lookupBusy: boolean;
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
  loading: boolean;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  rename: [string];
  clear: [];
  lookupCustomer: [];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
}>();

const renaming = ref(false);
const renameValue = ref("");
function startRename() {
  renameValue.value = props.tabDisplay || "";
  renaming.value = true;
}
function confirmRename() {
  const next = renameValue.value.trim();
  renaming.value = false;
  if (next && next !== (props.tabDisplay || "")) emit("rename", next);
}
function cancelRename() {
  renaming.value = false;
}
function onRenameKeydown(event: KeyboardEvent) {
  if (event.key === "Enter") {
    event.preventDefault();
    confirmRename();
  } else if (event.key === "Escape") {
    event.preventDefault();
    cancelRename();
  }
}

const customerSheetOpen = ref(false);
const customerMemory = computed(() => props.customerLookup?.memory || null);

// Search the customer at the moment of entry (no manual button): one field
// matches any unique key (name/phone/CPF/email), debounced, returning a list to
// pick from. Picking fills the cart + runs the full lookup. The commit still
// get-or-creates by phone/CPF, so a fresh name+phone just creates on finalize.
const searchQuery = ref("");
let searchTimer: ReturnType<typeof setTimeout> | null = null;
watch(searchQuery, (q) => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => emit("search", q), 350);
});
function pickResult(result: POSCustomerSearchResult) {
  emit("selectResult", result);
  searchQuery.value = "";
}
// Reset the search when the modal closes so it opens fresh next time.
watch(customerSheetOpen, (open) => { if (!open) { searchQuery.value = ""; emit("search", ""); } });
onBeforeUnmount(() => { if (searchTimer) clearTimeout(searchTimer); });

const confirmClear = ref(false);
function runClear() {
  confirmClear.value = false;
  emit("clear");
}
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <!-- comanda number (renameable) -->
    <div v-if="renaming" class="flex items-center gap-1">
      <UiInput
        v-model="renameValue"
        class="h-8 w-40 text-lg font-semibold"
        placeholder="Mesa, nome…"
        autofocus
        @keydown="onRenameKeydown"
      />
      <UiButton variant="ghost" size="icon-sm" aria-label="Confirmar nome" @click="confirmRename">
        <Icon name="lucide:check" class="size-4" />
      </UiButton>
      <UiButton variant="ghost" size="icon-sm" aria-label="Cancelar" @click="cancelRename">
        <Icon name="lucide:x" class="size-4" />
      </UiButton>
    </div>
    <button
      v-else-if="hasOpenTab && canRename"
      type="button"
      class="group flex min-w-0 items-center gap-1.5"
      aria-label="Renomear comanda"
      @click="startRename"
    >
      <h1 class="truncate text-lg font-semibold leading-tight tabular-nums tracking-tight">#{{ tabDisplay || "..." }}</h1>
      <Icon name="lucide:pencil" class="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
    <h1 v-else-if="hasOpenTab" class="truncate text-lg font-semibold leading-tight tabular-nums tracking-tight">#{{ tabDisplay || "..." }}</h1>
    <h1 v-else class="truncate text-lg font-semibold leading-tight tracking-tight">Venda rápida</h1>

    <!-- customer chip -->
    <button
      type="button"
      class="flex min-w-0 shrink items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-sm transition hover:bg-accent"
      aria-haspopup="dialog"
      @click="customerSheetOpen = true"
    >
      <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
      <span v-if="customerName" class="min-w-0 max-w-40 truncate font-medium">{{ customerName }}</span>
      <span v-else class="shrink-0 text-muted-foreground">Adicionar cliente</span>
    </button>

    <!-- liberar comanda (pushed to the right of the context bar) -->
    <UiButton
      v-if="hasOpenTab"
      variant="ghost"
      size="icon-sm"
      class="ml-auto shrink-0 text-muted-foreground"
      aria-label="Liberar comanda"
      title="Liberar comanda"
      @click="confirmClear = true"
    >
      <Icon name="lucide:x" class="size-4" />
    </UiButton>

    <UiDialog v-model:open="customerSheetOpen">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Cliente</UiDialogTitle>
          <UiDialogDescription>Busque por nome, telefone, CPF ou e-mail — ou preencha para um novo.</UiDialogDescription>
        </UiDialogHeader>
        <div class="grid gap-4">
          <!-- multi-key search in evidence -->
          <div class="relative">
            <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <UiInput
              v-model="searchQuery"
              class="h-12 pl-10 text-base"
              placeholder="Nome, telefone, CPF ou e-mail"
              autofocus
            />
            <Icon v-if="searchBusy" name="lucide:loader-circle" class="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
          </div>

          <!-- results list -->
          <div v-if="searchResults.length" class="grid max-h-56 gap-0.5 overflow-auto rounded-xl border p-1">
            <button
              v-for="result in searchResults"
              :key="result.ref"
              type="button"
              class="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition hover:bg-accent"
              @click="pickResult(result)"
            >
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium">{{ result.name || "Sem nome" }}</span>
                <span class="block truncate text-xs text-muted-foreground tabular-nums">{{ [result.phone, result.document, result.email].filter(Boolean).join(" · ") }}</span>
              </span>
              <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
            </button>
          </div>
          <p v-else-if="searchQuery.trim().length >= 2 && !searchBusy" class="text-center text-xs text-muted-foreground">
            Nenhum cadastro encontrado — preencha abaixo para criar um novo.
          </p>

          <!-- selected customer surfaced for review -->
          <div v-if="customerLookup" class="grid gap-2 rounded-xl border border-primary/30 bg-primary/5 p-3">
            <div class="flex items-center justify-between gap-2">
              <span class="flex items-center gap-1.5 text-sm font-semibold">
                <Icon name="lucide:user-check" class="size-4 text-primary" />
                {{ customerLookup.name }}
              </span>
              <span v-if="customerMemory?.total_orders" class="text-xs text-muted-foreground">{{ customerMemory.total_orders }} pedidos</span>
            </div>
            <div v-if="customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length" class="flex flex-wrap gap-2">
              <UiButton v-if="customerMemory?.favorite_item?.sku" type="button" variant="outline" size="sm" @click="$emit('applyCustomerFavorite')">
                <Icon name="lucide:heart" class="size-4" /> Favorito
              </UiButton>
              <UiButton v-if="customerMemory?.last_order_items?.length" type="button" variant="outline" size="sm" @click="$emit('repeatCustomerLastOrder')">
                <Icon name="lucide:rotate-ccw" class="size-4" /> Último pedido
              </UiButton>
            </div>
          </div>

          <!-- editable fields (review / new) -->
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">Nome</span>
              <UiInput :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
            </label>
            <label class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">WhatsApp</span>
              <UiInput :model-value="customerPhone" inputmode="tel" placeholder="(43) 99999-0000" @update:model-value="$emit('update:customerPhone', String($event || ''))" />
            </label>
          </div>
        </div>
        <UiDialogFooter>
          <UiButton class="w-full" @click="customerSheetOpen = false">Concluir</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <UiDialog :open="confirmClear" @update:open="(value) => { if (!value) confirmClear = false; }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Liberar comanda?</UiDialogTitle>
          <UiDialogDescription>
            Isso descarta este atendimento e libera a comanda. A ação não pode ser desfeita.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter class="gap-2">
          <UiButton variant="outline" @click="confirmClear = false">Cancelar</UiButton>
          <UiButton variant="destructive" :disabled="loading" @click="runClear">Liberar comanda</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </div>
</template>
