<script setup lang="ts">
// Comanda header (Arc 5 · context bar) — the open comanda's command header,
// lifted out of the ticket panel into the top context bar so the cart keeps its
// vertical room for line items + numpad. Owns the renameable comanda number, the
// customer chip + sheet, and "liberar comanda" (with confirmation). It renders
// what the read-side hands it and emits intent; the shell resolves the commands.
import type { POSCustomerLookupProjection } from "~/types/pos";

const props = defineProps<{
  tabDisplay: string;
  hasOpenTab: boolean;
  canRename: boolean;
  customerName: string;
  customerPhone: string;
  customerLookup: POSCustomerLookupProjection | null;
  lookupBusy: boolean;
  loading: boolean;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  rename: [string];
  clear: [];
  lookupCustomer: [];
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

// Look the customer up at the moment they're informed — not via a manual button.
// Debounced once the phone looks complete; de-duped so the same number isn't
// re-fetched (the lookup also normalizes + writes the phone back). The commit
// still get-or-creates by phone/CPF, so this only surfaces the existing record.
let lookupTimer: ReturnType<typeof setTimeout> | null = null;
const lastLookupDigits = ref("");
watch(
  () => props.customerPhone,
  (phone) => {
    const digits = String(phone || "").replace(/\D/g, "");
    if (lookupTimer) clearTimeout(lookupTimer);
    if (digits.length < 10 || digits === lastLookupDigits.value) return;
    lookupTimer = setTimeout(() => {
      lastLookupDigits.value = digits;
      emit("lookupCustomer");
    }, 600);
  },
);
onBeforeUnmount(() => { if (lookupTimer) clearTimeout(lookupTimer); });

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

    <UiSheet v-model:open="customerSheetOpen">
      <UiSheetContent side="right" title="Cliente" description="Identifique o cliente desta comanda. Tudo opcional.">
        <template #content>
          <div class="grid gap-4 overflow-y-auto px-4 pb-6">
            <label class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">Nome</span>
              <UiInput
                :model-value="customerName"
                placeholder="Nome no balcão"
                @update:model-value="$emit('update:customerName', String($event || ''))"
              />
            </label>
            <label class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">WhatsApp</span>
              <div class="flex gap-2">
                <UiInput
                  :model-value="customerPhone"
                  inputmode="tel"
                  placeholder="(43) 99999-0000"
                  @update:model-value="$emit('update:customerPhone', String($event || ''))"
                  @keydown.enter.prevent="$emit('lookupCustomer')"
                />
                <UiButton
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="Buscar cliente"
                  title="Buscar cliente"
                  :disabled="lookupBusy || !customerPhone.trim()"
                  @click="$emit('lookupCustomer')"
                >
                  <Icon name="lucide:user-search" class="size-4" :class="lookupBusy ? 'animate-pulse' : ''" />
                </UiButton>
              </div>
            </label>

            <div
              v-if="customerLookup && (customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length)"
              class="grid gap-2 rounded-lg border bg-muted/30 p-3"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-semibold">{{ customerLookup.name }}</span>
                <span v-if="customerMemory?.total_orders" class="text-xs text-muted-foreground">
                  {{ customerMemory.total_orders }} pedidos
                </span>
              </div>
              <div class="flex flex-wrap gap-2">
                <UiButton
                  v-if="customerMemory?.favorite_item?.sku"
                  type="button"
                  variant="outline"
                  size="sm"
                  @click="$emit('applyCustomerFavorite')"
                >
                  <Icon name="lucide:heart" class="size-4" />
                  Favorito
                </UiButton>
                <UiButton
                  v-if="customerMemory?.last_order_items?.length"
                  type="button"
                  variant="outline"
                  size="sm"
                  @click="$emit('repeatCustomerLastOrder')"
                >
                  <Icon name="lucide:rotate-ccw" class="size-4" />
                  Último pedido
                </UiButton>
              </div>
            </div>

            <UiButton class="mt-2" @click="customerSheetOpen = false">Concluir</UiButton>
          </div>
        </template>
      </UiSheetContent>
    </UiSheet>

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
