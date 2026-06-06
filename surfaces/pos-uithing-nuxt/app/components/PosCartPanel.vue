<script setup lang="ts">
import type {
  POSCartItem,
  POSCustomerLookupProjection,
} from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";
import { clampPercent, clampQty, popDigit, pushDigit } from "~/presentation/numpad";
import { fireBarView, kitchenLineState } from "~/presentation/kitchen";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  customerLookup: POSCustomerLookupProjection | null;
  requiresTab: boolean;
  hasOpenTab: boolean;
  customerName: string;
  customerPhone: string;
  loading: boolean;
  saving: boolean;
  lookupBusy: boolean;
  /** Kitchen handoff affordances (Projection `Action`s) — labels, not invented. */
  fireAction: ActionAffordance;
  unfireAction: ActionAffordance;
  firing: boolean;
  canRename: boolean;
  discountReasons?: Array<{ ref: string; label?: string } | string>;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  increment: [string];
  decrement: [string];
  remove: [string];
  setQty: [string, number];
  setDiscount: [string, number, string];
  save: [];
  prepare: [];
  move: [];
  fire: [];
  unfire: [string];
  rename: [string];
  clear: [];
  requestTab: [];
  lookupCustomer: [];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
}>();

// Kitchen handoff (spec §2.5): the fire bar and per-line state are shaped from
// the Projection's Actions + per-line `fired`, never decided here.
const fireBar = computed(() => fireBarView({
  items: props.items,
  affordance: props.fireAction,
  hasOpenTab: props.hasOpenTab,
  busy: props.loading || props.firing,
}));
function lineKitchenState(item: POSCartItem) {
  return kitchenLineState(item, { canUnfire: props.unfireAction.present });
}

const customerSheetOpen = ref(false);

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

// Interim local total — reflects per-line manual discount as an estimate so the
// operator sees the discount land. Backend review remains the authoritative total.
const totalDisplay = computed(() => formatBRL(props.items.reduce((sum, item) => {
  const gross = item.price_q * item.qty;
  const perUnit = item.discount?.value ? Math.min(item.price_q, Math.round(item.price_q * item.discount.value / 100)) : 0;
  return sum + Math.max(0, gross - perUnit * item.qty);
}, 0)));
const customerMemory = computed(() => props.customerLookup?.memory || null);

// Numpad targets the selected line: select a line, type a quantity (first
// digit replaces, the rest append). Stepper buttons stay for touch and re-arm
// the numpad on the line they touch. Price/discount-per-line modes are out of
// scope until the intent contract supports them.
const MAX_QTY = 999;
const selectedSku = ref("");
const numpadBuffer = ref("");
const numpadFresh = ref(true);
const numpadMode = ref<"qty" | "disc">("qty");

const defaultReasons = [
  { ref: "cortesia", label: "Cortesia" },
  { ref: "fidelidade", label: "Fidelidade" },
  { ref: "ajuste", label: "Ajuste" },
  { ref: "qualidade", label: "Qualidade" },
];
const reasonOptions = computed(() => {
  const raw = props.discountReasons;
  if (raw?.length) {
    return raw.map((r) => (typeof r === "string" ? { ref: r, label: r } : { ref: r.ref, label: r.label || r.ref }));
  }
  return defaultReasons;
});
const discountReason = ref("");

// The numpad always targets a line: the explicitly selected one, or — when none
// is selected — the last added/edited line. So a single-item ticket is editable
// without tapping it first.
const activeSku = computed(() => {
  if (selectedSku.value && props.items.some((item) => item.sku === selectedSku.value)) {
    return selectedSku.value;
  }
  return props.items[props.items.length - 1]?.sku ?? "";
});
const activeItem = computed(() => props.items.find((item) => item.sku === activeSku.value) || null);

function qtyOf(sku: string): number {
  return props.items.find((item) => item.sku === sku)?.qty || 0;
}

function syncBufferToMode() {
  numpadFresh.value = true;
  if (numpadMode.value === "qty") {
    numpadBuffer.value = String(qtyOf(activeSku.value));
  } else {
    const item = activeItem.value;
    numpadBuffer.value = item?.discount?.value ? String(item.discount.value) : "";
    discountReason.value = item?.discount?.reason || reasonOptions.value[0]?.ref || "cortesia";
  }
}

watch(activeSku, () => syncBufferToMode());
watch(numpadMode, () => syncBufferToMode());

function selectLine(sku: string) {
  selectedSku.value = sku;
  syncBufferToMode();
}

function setMode(mode: "qty" | "disc") {
  numpadMode.value = mode;
}

// Destructive actions require a confirmation modal naming the irreversible effect.
const confirmAction = ref<{ kind: "remove" | "clear"; sku?: string; name?: string } | null>(null);
function askRemove(sku: string) {
  const item = props.items.find((entry) => entry.sku === sku);
  confirmAction.value = { kind: "remove", sku, name: item?.name || "item" };
}
function askClear() {
  confirmAction.value = { kind: "clear" };
}
function cancelConfirm() {
  confirmAction.value = null;
}
function runConfirm() {
  const action = confirmAction.value;
  confirmAction.value = null;
  if (!action) return;
  if (action.kind === "remove" && action.sku) {
    if (selectedSku.value === action.sku) selectedSku.value = "";
    emit("remove", action.sku);
  } else if (action.kind === "clear") {
    emit("clear");
  }
}

function commitQty() {
  const sku = activeSku.value;
  if (!sku) return;
  const next = clampQty(numpadBuffer.value, MAX_QTY);
  if (next <= 0) {
    askRemove(sku);
    return;
  }
  emit("setQty", sku, next);
}

function commitDiscount() {
  const sku = activeSku.value;
  if (!sku) return;
  const value = clampPercent(numpadBuffer.value);
  emit("setDiscount", sku, value, discountReason.value || "cortesia");
}

function onDigit(digit: string) {
  if (!activeSku.value) return;
  numpadBuffer.value = pushDigit(numpadBuffer.value, digit, { fresh: numpadFresh.value, maxLength: 3 });
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

function onBackspace() {
  if (!activeSku.value) return;
  numpadBuffer.value = popDigit(numpadBuffer.value);
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

function onClear() {
  const sku = activeSku.value;
  if (!sku) return;
  if (numpadMode.value === "qty") {
    askRemove(sku);
  } else {
    numpadBuffer.value = "";
    numpadFresh.value = true;
    emit("setDiscount", sku, 0, discountReason.value || "cortesia");
  }
}

function pickReason(reason: string) {
  discountReason.value = reason;
  if (activeSku.value && numpadMode.value === "disc") commitDiscount();
}

function bump(sku: string, emitName: "increment" | "decrement") {
  selectedSku.value = sku;
  if (emitName === "decrement") {
    if (qtyOf(sku) <= 1) {
      askRemove(sku);
      return;
    }
    emit("decrement", sku);
    return;
  }
  emit("increment", sku);
}

// Physical keyboard feeds the active line (Odoo-style): select/add a product,
// then type a number to set its quantity. Ignored while typing in a field.
function onWindowKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  const editing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (editing || !props.items.length || !activeSku.value) return;
  if (event.key >= "0" && event.key <= "9") {
    event.preventDefault();
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    onBackspace();
  }
}
onMounted(() => window.addEventListener("keydown", onWindowKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown));
</script>

<template>
  <UiCard v-if="requiresTab && !hasOpenTab" class="gap-4 rounded-lg p-4 shadow-none md:h-full md:min-h-0">
    <div class="grid gap-3 text-center">
      <div class="mx-auto grid size-11 place-items-center rounded-lg border bg-muted">
        <Icon name="lucide:receipt-text" class="size-5 text-muted-foreground" />
      </div>
      <div class="grid gap-1">
        <p class="text-base font-semibold">Abra uma comanda</p>
        <p class="text-sm text-muted-foreground">
          O carrinho do POS fica recuperável somente depois de associado a uma comanda.
        </p>
      </div>
      <UiButton type="button" :disabled="loading" @click="$emit('requestTab')">
        Escolher comanda
      </UiButton>
    </div>
  </UiCard>

  <UiCard v-else class="gap-2.5 rounded-lg p-3 shadow-none md:flex md:h-full md:min-h-0 md:flex-col md:overflow-hidden">
    <div class="flex shrink-0 items-center justify-between gap-2">
      <div class="min-w-0">
        <p class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Comanda</p>
        <div v-if="renaming" class="mt-0.5 flex items-center gap-1">
          <UiInput
            v-model="renameValue"
            class="h-8 w-40 text-lg font-semibold"
            placeholder="Mesa, nome…"
            autofocus
            @keydown.enter.prevent="confirmRename"
            @keydown.esc.prevent="cancelRename"
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
          class="group mt-0.5 flex items-center gap-1.5"
          aria-label="Renomear comanda"
          @click="startRename"
        >
          <span class="text-xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</span>
          <Icon name="lucide:pencil" class="size-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
        <p v-else-if="hasOpenTab" class="text-xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</p>
        <p v-else class="text-lg font-semibold">Venda rápida</p>
      </div>
      <UiButton
        variant="ghost"
        size="icon-sm"
        aria-label="Liberar comanda"
        title="Liberar comanda"
        @click="askClear()"
      >
        <Icon name="lucide:x" class="size-4" />
      </UiButton>
    </div>

    <button
      type="button"
      class="flex shrink-0 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-sm transition hover:bg-accent"
      aria-haspopup="dialog"
      @click="customerSheetOpen = true"
    >
      <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
      <span v-if="customerName" class="min-w-0 flex-1 truncate font-medium">{{ customerName }}</span>
      <span v-else class="min-w-0 flex-1 truncate text-muted-foreground">Adicionar cliente</span>
      <span v-if="customerPhone" class="shrink-0 text-xs text-muted-foreground tabular-nums">{{ customerPhone }}</span>
      <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
    </button>

    <UiSeparator class="shrink-0" />

    <div class="min-h-24 max-h-[40vh] overflow-auto pr-1 md:max-h-none md:min-h-0 md:flex-1">
      <p v-if="!items.length" class="grid h-full min-h-24 place-items-center rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
        Carrinho vazio
      </p>
      <ul v-else class="grid gap-0.5">
        <li
          v-for="item in items"
          :key="item.sku"
          class="grid cursor-pointer grid-cols-[1fr_auto] items-center gap-2 rounded-lg px-2 py-1 transition"
          :class="activeSku === item.sku ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-accent/60'"
          :aria-current="activeSku === item.sku ? 'true' : undefined"
          @click="selectLine(item.sku)"
        >
          <div class="min-w-0">
            <p class="truncate text-sm font-medium leading-tight">{{ item.name }}</p>
            <p class="text-xs text-muted-foreground tabular-nums">
              {{ item.qty }}× {{ formatBRL(item.price_q) }} · {{ formatBRL(item.qty * item.price_q) }}
            </p>
            <span
              v-if="item.discount && item.discount.value > 0"
              class="mt-0.5 inline-flex w-fit items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
              :title="`Desconto: ${item.discount.reason}`"
            >
              <Icon name="lucide:tag" class="size-3" />
              −{{ item.discount.value }}% · {{ item.discount.reason }}
            </span>
            <button
              v-if="lineKitchenState(item) === 'fired_cancellable'"
              type="button"
              class="group mt-0.5 inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              :disabled="firing"
              :aria-label="`${unfireAction.label}: ${item.name}`"
              @click.stop="$emit('unfire', item.line_id || '')"
            >
              <Icon name="lucide:flame" class="size-3 group-hover:hidden" />
              <Icon name="lucide:x" class="hidden size-3 group-hover:inline" />
              Na cozinha
            </button>
            <span
              v-else-if="lineKitchenState(item) === 'fired'"
              class="mt-0.5 inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
            >
              <Icon name="lucide:flame" class="size-3" />
              Na cozinha
            </span>
          </div>
          <div class="flex items-center gap-1" @click.stop>
            <UiButton variant="ghost" size="icon-xs" aria-label="Diminuir" @click="bump(item.sku, 'decrement')">
              <Icon name="lucide:minus" class="size-3.5" />
            </UiButton>
            <span class="w-6 text-center text-sm font-semibold tabular-nums">{{ item.qty }}</span>
            <UiButton variant="ghost" size="icon-xs" aria-label="Aumentar" @click="bump(item.sku, 'increment')">
              <Icon name="lucide:plus" class="size-3.5" />
            </UiButton>
            <UiButton variant="ghost" size="icon-xs" aria-label="Remover" @click="askRemove(item.sku)">
              <Icon name="lucide:trash-2" class="size-3.5 text-destructive" />
            </UiButton>
          </div>
        </li>
      </ul>
    </div>

    <div v-if="items.length" class="grid shrink-0 gap-1.5">
      <div class="flex gap-1">
        <button
          type="button"
          class="flex-1 rounded-lg border py-0.5 text-sm font-medium transition"
          :class="numpadMode === 'qty' ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'"
          @click="setMode('qty')"
        >
          Qtd
        </button>
        <button
          type="button"
          class="flex-1 rounded-lg border py-0.5 text-sm font-medium transition"
          :class="numpadMode === 'disc' ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'"
          @click="setMode('disc')"
        >
          Desc %
        </button>
      </div>
      <div v-if="numpadMode === 'disc' && activeSku" class="flex flex-wrap gap-1">
        <button
          v-for="reason in reasonOptions"
          :key="reason.ref"
          type="button"
          class="rounded-full border px-2.5 py-0.5 text-xs transition"
          :class="discountReason === reason.ref ? 'border-primary bg-primary/10 font-medium' : 'hover:bg-accent'"
          @click="pickReason(reason.ref)"
        >
          {{ reason.label }}
        </button>
      </div>
      <PosNumpad
        compact
        :disabled="!items.length"
        @digit="onDigit"
        @backspace="onBackspace"
        @clear="onClear"
      />
    </div>

    <div class="grid shrink-0 gap-2 border-t pt-2.5">
      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground">Total parcial</span>
        <strong class="text-xl tabular-nums">{{ totalDisplay }}</strong>
      </div>
      <UiButton
        v-if="fireBar.visible"
        variant="outline"
        class="w-full justify-center gap-2"
        :disabled="fireBar.disabled"
        :loading="firing"
        @click="$emit('fire')"
      >
        <Icon name="lucide:flame" class="size-4" />
        {{ fireBar.label }}
      </UiButton>
      <UiButton
        size="lg"
        class="w-full"
        :disabled="!items.length || loading"
        :loading="loading"
        @click="$emit('prepare')"
      >
        Pagamento
      </UiButton>
      <UiButton
        v-if="hasOpenTab && items.length"
        variant="ghost"
        size="sm"
        class="w-full justify-center gap-1.5 text-muted-foreground"
        :disabled="loading"
        @click="$emit('move')"
      >
        <Icon name="lucide:split" class="size-4" />
        Mover itens
      </UiButton>
    </div>
  </UiCard>

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

  <UiDialog :open="!!confirmAction" @update:open="(value) => { if (!value) cancelConfirm(); }">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>
          {{ confirmAction?.kind === "clear" ? "Liberar comanda?" : "Remover item?" }}
        </UiDialogTitle>
        <UiDialogDescription>
          <template v-if="confirmAction?.kind === 'clear'">
            Isso descarta este atendimento e libera a comanda. A ação não pode ser desfeita.
          </template>
          <template v-else>
            Remover <strong>{{ confirmAction?.name }}</strong> do pedido? A ação não pode ser desfeita.
          </template>
        </UiDialogDescription>
      </UiDialogHeader>
      <UiDialogFooter class="gap-2">
        <UiButton variant="outline" @click="cancelConfirm">Cancelar</UiButton>
        <UiButton variant="destructive" @click="runConfirm">
          {{ confirmAction?.kind === "clear" ? "Liberar comanda" : "Remover item" }}
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
