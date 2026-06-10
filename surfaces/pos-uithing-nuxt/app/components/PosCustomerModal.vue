<script setup lang="ts">
// Customer picker (spec — Odoo "Choose Customer" clone, redesign 2026-06-10).
// One SHARED modal for both the comanda header and the payment screen, replacing
// the two divergent inline dialogs. Picker-first (not form-first), full-screen
// overlay like Odoo:
//   1. associated customer (if any) pinned at top, highlighted, with "Remover
//      cliente" (= Odoo's UNSELECT — the disassociate affordance we were missing);
//   2. a prominent search → rich results list (shared PosCustomerSearch);
//   3. a create/edit form below.
// The payment context also passes showFiscal to surface the fiscal/comprovante
// block (it rides with the customer because the receipt needs the e-mail).
// Renders intent; the shell owns clearCustomer / resolveCustomer / search.
import type {
  POSCheckoutOptionProjection,
  POSCustomerLookupProjection,
  POSCustomerSearchResult,
} from "~/types/pos";

const props = withDefaults(defineProps<{
  open: boolean;
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  customerLookup: POSCustomerLookupProjection | null;
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
  lookupBusy: boolean;
  /** Payment context: also show the fiscal/comprovante block. */
  showFiscal?: boolean;
  issueFiscalDocument?: boolean;
  receiptMode?: string;
  receiptModes?: POSCheckoutOptionProjection[];
  receiptEmail?: string;
}>(), {
  showFiscal: false,
  issueFiscalDocument: false,
  receiptMode: "none",
  receiptModes: () => [],
  receiptEmail: "",
});

const emit = defineEmits<{
  "update:open": [boolean];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  "update:issueFiscalDocument": [boolean];
  "update:receiptMode": [string];
  "update:receiptEmail": [string];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  clear: [];
  resolveCustomer: [];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
}>();

// A customer is associated when there's a loaded lookup or a name in context.
const hasCustomer = computed(() => Boolean(props.customerName.trim() || props.customerLookup));
const memory = computed(() => props.customerLookup?.memory || null);
const identityChips = computed(() =>
  [props.customerPhone, props.customerTaxId, props.customerEmail].map((v) => v.trim()).filter(Boolean),
);

// Reset the shared search field whenever the modal reopens fresh.
watch(() => props.open, (open) => { if (!open) emit("search", ""); });

function onSelect(result: POSCustomerSearchResult) {
  emit("selectResult", result);
}
function onConclude() {
  emit("resolveCustomer");
  emit("update:open", false);
}
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <!-- Full-screen overlay (Odoo "Choose Customer"): a large panel; the register
         stays dimly visible behind. Neutral tokens, our omotenashi tone. -->
    <UiDialogContent class="flex h-[90vh] w-[min(60rem,94vw)] max-w-none flex-col gap-0 overflow-hidden rounded-md p-0 sm:max-w-none">
      <UiDialogHeader class="shrink-0 border-b px-6 py-4">
        <UiDialogTitle class="text-lg">Cliente</UiDialogTitle>
        <UiDialogDescription>
          Busque por nome, telefone, CPF ou e-mail — selecione um cadastro ou crie um novo.
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div class="mx-auto grid max-w-2xl gap-5">
          <!-- 1 · associated customer (Odoo's pinned-and-highlighted) + Remover -->
          <div v-if="hasCustomer" class="grid gap-3 rounded-md border border-primary bg-primary/5 p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="flex items-center gap-1.5 text-base font-semibold">
                  <Icon name="lucide:user-check" class="size-4 shrink-0 text-primary" />
                  <span class="truncate">{{ customerName || customerLookup?.name || "Cliente" }}</span>
                </p>
                <p v-if="identityChips.length" class="mt-0.5 truncate text-sm tabular-nums text-muted-foreground">
                  {{ identityChips.join(" · ") }}
                </p>
              </div>
              <UiButton type="button" variant="outline" size="sm" class="shrink-0 text-destructive" @click="$emit('clear')">
                <Icon name="lucide:user-x" class="size-4" />
                Remover cliente
              </UiButton>
            </div>
            <!-- Guestman memory (warmer than Odoo's raw "All Orders"): favourite +
                 last order, one tap to apply. -->
            <div v-if="memory && (memory.favorite_item?.sku || memory.last_order_items?.length || memory.total_orders)" class="flex flex-wrap items-center gap-2">
              <span v-if="memory.total_orders" class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {{ memory.total_orders }} {{ memory.total_orders === 1 ? "pedido" : "pedidos" }}
              </span>
              <UiButton v-if="memory.favorite_item?.sku" type="button" variant="outline" size="xs" @click="$emit('applyCustomerFavorite')">
                <Icon name="lucide:heart" class="size-3.5" /> Favorito
              </UiButton>
              <UiButton v-if="memory.last_order_items?.length" type="button" variant="outline" size="xs" @click="$emit('repeatCustomerLastOrder')">
                <Icon name="lucide:rotate-ccw" class="size-3.5" /> Último pedido
              </UiButton>
            </div>
          </div>

          <!-- 2 · the picker: prominent search + rich results list -->
          <PosCustomerSearch :results="searchResults" :busy="searchBusy" @search="$emit('search', $event)" @select="onSelect" />

          <!-- 3 · create / edit form -->
          <div class="grid gap-3">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {{ hasCustomer ? "Editar cadastro" : "Novo cadastro" }}
            </p>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">Nome</span>
                <UiInput :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">WhatsApp</span>
                <UiInput :model-value="customerPhone" inputmode="tel" placeholder="(43) 99999-0000" @update:model-value="$emit('update:customerPhone', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
                <UiInput :model-value="customerTaxId" inputmode="numeric" placeholder="Para fiscal" @update:model-value="$emit('update:customerTaxId', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">E-mail</span>
                <UiInput :model-value="customerEmail" type="email" placeholder="cliente@email.com" @update:model-value="$emit('update:customerEmail', String($event || ''))" />
              </label>
            </div>
          </div>

          <!-- payment context only: fiscal + comprovante (rides with the customer) -->
          <div v-if="showFiscal" class="grid gap-3 border-t pt-4">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Fiscal e comprovante</p>
            <UiButton
              type="button"
              variant="outline"
              class="justify-between"
              :class="issueFiscalDocument ? 'border-primary bg-primary/5' : ''"
              @click="$emit('update:issueFiscalDocument', !issueFiscalDocument)"
            >
              <span>Emitir nota fiscal</span>
              <Icon :name="issueFiscalDocument ? 'lucide:check' : 'lucide:minus'" class="size-4" />
            </UiButton>
            <div class="grid grid-cols-3 gap-2">
              <UiButton
                v-for="mode in receiptModes"
                :key="mode.ref"
                type="button"
                variant="outline"
                class="h-auto justify-center whitespace-normal px-2 py-2 text-xs"
                :class="receiptMode === mode.ref ? 'border-primary bg-primary/5' : ''"
                @click="$emit('update:receiptMode', mode.ref)"
              >
                {{ mode.label }}
              </UiButton>
            </div>
            <label v-if="receiptMode === 'email'" class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">E-mail do comprovante</span>
              <UiInput :model-value="receiptEmail" type="email" :placeholder="customerEmail || 'cliente@email.com'" @update:model-value="$emit('update:receiptEmail', String($event || ''))" />
              <span v-if="!receiptEmail.trim() && customerEmail.trim()" class="text-xs text-muted-foreground">
                Sem preencher, enviamos para o e-mail do cliente: <span class="font-medium text-foreground">{{ customerEmail }}</span>
              </span>
            </label>
          </div>
        </div>
      </div>

      <UiDialogFooter class="shrink-0 border-t px-6 py-4">
        <UiButton class="w-full" @click="onConclude">Concluir</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
