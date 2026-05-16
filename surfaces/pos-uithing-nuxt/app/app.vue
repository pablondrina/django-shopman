<script setup lang="ts">
import type {
  POSCartItem,
  POSCloseSaleResponse,
  POSProductProjection,
  POSResponse,
  POSTabPayload,
  POSTabProjection,
} from "~/types/pos";
import {
  actionHref,
  buildPosSaleIntent,
  cartTotalQ,
  concreteActionHref,
  formatBRL,
} from "~/utils/posIntent";

type FulfillmentType = "pickup" | "delivery";
type PaymentCollection = "terminal" | "on_delivery";

const apiPath = usePosApiPath();
const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { data, pending, error, refresh } = await useFetch<POSResponse>(
  () => apiPath("/api/v1/backstage/pos/"),
  { credentials: "include", headers: requestHeaders },
);

const search = ref("");
const activeCollection = ref("");
const tabInput = ref("");
const busy = ref(false);
const saving = ref(false);
const serverError = ref("");
const result = ref<{ orderRef: string; nextUrl: string } | null>(null);

const cart = reactive({
  tabCode: "",
  tabDisplay: "",
  tabSessionKey: "",
  items: [] as POSCartItem[],
  customerName: "",
  customerPhone: "",
  fulfillmentType: "pickup" as FulfillmentType,
  deliveryAddress: "",
  deliveryTimeSlot: "",
  paymentMethod: "",
  paymentCollection: "terminal" as PaymentCollection,
  clientRequestId: "",
});

const pos = computed(() => data.value?.pos || null);
const tabs = computed(() => data.value?.tabs || []);
const shift = computed(() => data.value?.shift || null);
const actions = computed(() => pos.value?.actions || []);
const totalDisplay = computed(() => formatBRL(cartTotalQ(cart.items)));
const itemCount = computed(() => cart.items.reduce((sum, item) => sum + item.qty, 0));
const hasOpenTab = computed(() => Boolean(cart.tabSessionKey));

const favoriteCollections = computed(() => new Set(pos.value?.favorite_collection_refs || []));
const orderedCollections = computed(() => {
  const collections = pos.value?.collections || [];
  return [...collections].sort((a, b) => {
    const aFavorite = favoriteCollections.value.has(a.ref) ? 0 : 1;
    const bFavorite = favoriteCollections.value.has(b.ref) ? 0 : 1;
    return aFavorite - bFavorite || a.name.localeCompare(b.name, "pt-BR");
  });
});

const filteredProducts = computed<POSProductProjection[]>(() => {
  const normalized = search.value.trim().toLowerCase();
  return (pos.value?.products || []).filter((product) => {
    if (activeCollection.value && product.collection_ref !== activeCollection.value) return false;
    if (!normalized) return true;
    return product.name.toLowerCase().includes(normalized) || product.sku.toLowerCase().includes(normalized);
  });
});

const sortedTabs = computed(() => [...tabs.value].sort((a, b) => {
  const aOpen = a.state === "in_use" ? 0 : 1;
  const bOpen = b.state === "in_use" ? 0 : 1;
  return aOpen - bOpen || a.display_code.localeCompare(b.display_code, "pt-BR", { numeric: true });
}));

const availablePaymentCollections = computed(() =>
  (pos.value?.payment_collections || []).filter((collection) =>
    collection.fulfillment_types.includes(cart.fulfillmentType)
    && collection.payment_method_refs.includes(cart.paymentMethod),
  ),
);

watch(pos, (projection) => {
  if (!projection) return;
  if (!cart.paymentMethod) cart.paymentMethod = projection.payment_methods[0]?.ref || "cash";
  const defaultFulfillment = projection.terminal_default_fulfillment_type === "delivery" ? "delivery" : "pickup";
  if (!cart.fulfillmentType) cart.fulfillmentType = defaultFulfillment;
  if (!projection.fulfillment_options.some((option) => option.ref === cart.fulfillmentType)) {
    cart.fulfillmentType = projection.fulfillment_options[0]?.ref || "pickup";
  }
}, { immediate: true });

watch(availablePaymentCollections, (collections) => {
  if (!collections.some((collection) => collection.ref === cart.paymentCollection)) {
    cart.paymentCollection = collections[0]?.ref || "terminal";
  }
}, { immediate: true });

function productQty(sku: string): number {
  return cart.items.find((item) => item.sku === sku)?.qty || 0;
}

function addProduct(product: POSProductProjection) {
  result.value = null;
  const existing = cart.items.find((item) => item.sku === product.sku);
  if (existing) {
    existing.qty += 1;
    return;
  }
  cart.items.push({
    sku: product.sku,
    name: product.name,
    price_q: product.price_q,
    qty: 1,
    notes: "",
    is_d1: product.is_d1,
  });
}

function setQty(sku: string, qty: number) {
  const existing = cart.items.find((item) => item.sku === sku);
  if (!existing) return;
  if (qty <= 0) {
    cart.items = cart.items.filter((item) => item.sku !== sku);
    return;
  }
  existing.qty = qty;
}

function resetCart() {
  cart.tabCode = "";
  cart.tabDisplay = "";
  cart.tabSessionKey = "";
  cart.items = [];
  cart.customerName = "";
  cart.customerPhone = "";
  cart.deliveryAddress = "";
  cart.deliveryTimeSlot = "";
  cart.paymentCollection = "terminal";
  cart.clientRequestId = "";
}

function setFromTabPayload(payload: POSTabPayload) {
  cart.tabCode = payload.tab_code;
  cart.tabDisplay = payload.tab_display;
  cart.tabSessionKey = payload.tab_session_key || payload.session_key;
  cart.items = (payload.items || []).map((item) => ({ ...item }));
  cart.customerName = payload.customer_name || "";
  cart.customerPhone = payload.customer_phone || "";
  cart.fulfillmentType = payload.fulfillment_type === "delivery" ? "delivery" : "pickup";
  cart.deliveryAddress = payload.delivery_address || "";
  cart.deliveryTimeSlot = payload.delivery_time_slot || "";
  cart.paymentMethod = payload.payment_method || cart.paymentMethod || pos.value?.payment_methods[0]?.ref || "cash";
  cart.paymentCollection = payload.payment_collection === "on_delivery" ? "on_delivery" : "terminal";
  cart.clientRequestId = "";
}

async function openTab(tab: POSTabProjection | string) {
  const tabCode = typeof tab === "string" ? tab.trim() : tab.code;
  if (!tabCode) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    const path = concreteActionHref(
      actions.value,
      "open_tab",
      "/api/v1/backstage/pos/tabs/{tab_code}/open/",
      { tab_code: tabCode },
    );
    const payload = await action.call<POSTabPayload>(path);
    setFromTabPayload(payload);
    tabInput.value = "";
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao abrir comanda.";
  } finally {
    busy.value = false;
  }
}

function currentIntentState() {
  return {
    tabCode: cart.tabCode,
    tabSessionKey: cart.tabSessionKey,
    items: cart.items,
    customerName: cart.customerName,
    customerPhone: cart.customerPhone,
    fulfillmentType: cart.fulfillmentType,
    deliveryAddress: cart.deliveryAddress,
    deliveryTimeSlot: cart.deliveryTimeSlot,
    paymentMethod: cart.paymentMethod,
    paymentCollection: cart.paymentCollection,
    clientRequestId: cart.clientRequestId || newClientRequestId(),
  };
}

async function saveTab() {
  if (!hasOpenTab.value) return;
  serverError.value = "";
  saving.value = true;
  try {
    const state = currentIntentState();
    cart.clientRequestId = state.clientRequestId;
    await action.call(actionHref(actions.value, "save_tab", "/api/v1/backstage/pos/tabs/save/"), {
      body: buildPosSaleIntent(state),
    });
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao salvar comanda.";
  } finally {
    saving.value = false;
  }
}

async function submitSale() {
  if (!hasOpenTab.value || !cart.items.length) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    const state = currentIntentState();
    cart.clientRequestId = state.clientRequestId;
    const response = await action.call<POSCloseSaleResponse>(
      actionHref(actions.value, "close_sale", "/api/v1/backstage/pos/sale/close/"),
      { body: buildPosSaleIntent(state) },
    );
    if (response.ok && response.order_ref) {
      const orderRef = response.order_ref;
      result.value = {
        orderRef,
        nextUrl: `${runtimeConfig.public.djangoPublicBaseUrl}/admin/operacao/pedidos/${encodeURIComponent(orderRef)}/`,
      };
      resetCart();
      await refresh();
    }
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao finalizar venda.";
  } finally {
    busy.value = false;
  }
}

async function clearCurrentTab() {
  if (!cart.tabSessionKey) {
    resetCart();
    return;
  }
  serverError.value = "";
  busy.value = true;
  try {
    const path = concreteActionHref(
      actions.value,
      "clear_tab",
      "/api/v1/backstage/pos/tabs/{session_key}/clear/",
      { session_key: cart.tabSessionKey },
    );
    await action.call(path, { method: "DELETE" });
    resetCart();
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao liberar comanda.";
  } finally {
    busy.value = false;
  }
}

function newClientRequestId(): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `pos-uithing:${random}`;
}
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <header class="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
      <div class="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <p class="text-xs font-medium uppercase text-muted-foreground">Shopman</p>
          <h1 class="text-xl font-semibold tracking-normal">POS</h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <UiBadge v-if="pos" :variant="pos.terminal_health_status === 'ready' ? 'success' : 'warning'">
            {{ pos.terminal_label }}
          </UiBadge>
          <UiBadge v-if="pos" variant="outline">
            Fiscal: {{ pos.fiscal_message || pos.fiscal_label }}
          </UiBadge>
          <UiBadge v-if="shift" variant="outline" class="tabular-nums">
            {{ shift.count }} hoje · {{ shift.total_display }}
          </UiBadge>
          <UiButton variant="outline" size="icon-sm" aria-label="Atualizar" title="Atualizar" :disabled="pending" @click="refresh()">
            <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
          </UiButton>
        </div>
      </div>
    </header>

    <div class="mx-auto grid max-w-screen-2xl gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <section class="grid gap-4">
        <UiAlert v-if="error" variant="destructive">
          <Icon name="lucide:triangle-alert" class="size-4" />
          <UiAlertTitle>POS indisponível</UiAlertTitle>
          <UiAlertDescription>Confira login e permissão de operação no gestor.</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="serverError" variant="destructive">
          <Icon name="lucide:circle-x" class="size-4" />
          <UiAlertTitle>Ação recusada</UiAlertTitle>
          <UiAlertDescription>{{ serverError }}</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="result" class="border-green-500/30 bg-green-500/10 text-green-800">
          <Icon name="lucide:circle-check" class="size-4" />
          <UiAlertTitle>Pedido criado: {{ result.orderRef }}</UiAlertTitle>
          <UiAlertDescription>
            <a class="font-semibold underline underline-offset-4" :href="result.nextUrl">Abrir no gestor</a>
          </UiAlertDescription>
        </UiAlert>

        <section class="grid gap-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h2 class="text-base font-semibold">Comandas</h2>
            <form class="flex min-w-0 flex-1 justify-end gap-2 sm:flex-none" @submit.prevent="openTab(tabInput)">
              <UiInput v-model="tabInput" class="max-w-40" inputmode="numeric" placeholder="Comanda" />
              <UiButton type="submit" :disabled="busy || !tabInput.trim()">Abrir</UiButton>
            </form>
          </div>
          <div class="flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="tab in sortedTabs"
              :key="tab.code"
              type="button"
              class="grid min-w-24 gap-1 rounded-lg border px-3 py-2 text-left transition hover:border-primary/50 hover:bg-accent"
              :class="[
                cart.tabCode === tab.code ? 'border-primary bg-primary/5' : '',
                tab.state === 'in_use' ? 'border-amber-500/40 bg-amber-500/10' : ''
              ]"
              @click="openTab(tab)"
            >
              <span class="font-semibold tabular-nums">#{{ tab.display_code }}</span>
              <span class="text-xs text-muted-foreground">{{ tab.status_label }}</span>
              <span v-if="tab.item_count" class="text-xs font-semibold tabular-nums">{{ tab.item_count }} · {{ tab.total_display }}</span>
            </button>
          </div>
        </section>

        <section class="grid gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <div class="relative min-w-64 flex-1">
              <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <UiInput v-model="search" class="pl-9" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
            </div>
            <UiButton
              variant="outline"
              :class="activeCollection === '' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="activeCollection = ''"
            >
              Tudo
            </UiButton>
            <UiButton
              v-for="collection in orderedCollections"
              :key="collection.ref"
              variant="outline"
              :class="activeCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="activeCollection = collection.ref"
            >
              {{ collection.name }}
            </UiButton>
          </div>

          <div v-if="pending" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <div v-for="idx in 10" :key="idx" class="h-32 animate-pulse rounded-lg border bg-muted" />
          </div>
          <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
            Nenhum produto encontrado.
          </div>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <PosProductTile
              v-for="product in filteredProducts"
              :key="product.sku"
              :product="product"
              :qty="productQty(product.sku)"
              @add="addProduct"
            />
          </div>
        </section>
      </section>

      <aside>
        <PosCartPanel
          :tab-display="cart.tabDisplay"
          :items="cart.items"
          :fulfillment-options="pos?.fulfillment_options || []"
          :payment-methods="pos?.payment_methods || []"
          :payment-collections="pos?.payment_collections || []"
          v-model:fulfillment-type="cart.fulfillmentType"
          v-model:payment-method="cart.paymentMethod"
          v-model:payment-collection="cart.paymentCollection"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:delivery-address="cart.deliveryAddress"
          v-model:delivery-time-slot="cart.deliveryTimeSlot"
          :loading="busy"
          :saving="saving"
          @increment="(sku) => setQty(sku, productQty(sku) + 1)"
          @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
          @remove="(sku) => setQty(sku, 0)"
          @save="saveTab"
          @submit="submitSale"
          @clear="clearCurrentTab"
        />
        <p class="mt-3 text-xs text-muted-foreground">
          {{ itemCount }} item(ns) · {{ totalDisplay }}. O backend confirma disponibilidade, total final, status e gravação do pedido.
        </p>
      </aside>
    </div>
  </main>
</template>
