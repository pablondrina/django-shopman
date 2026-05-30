<script setup lang="ts">
import type { POSCartItem, POSTabProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

type MoveMode = "split" | "transfer" | "merge";

const props = defineProps<{
  open: boolean;
  tabDisplay: string;
  items: POSCartItem[];
  suggestedSplitRef: string;
  otherTabs: POSTabProjection[];
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  submit: [{ mode: MoveMode; lineIds: string[]; toTabRef?: string; toSessionKey?: string; closeSource?: boolean }];
}>();

const mode = ref<MoveMode>("split");
const selected = ref<Set<string>>(new Set());
const splitRef = ref("");
const targetSessionKey = ref("");

const lineId = (item: POSCartItem) => item.line_id || item.sku;

watch(() => props.open, (isOpen) => {
  if (!isOpen) return;
  mode.value = "split";
  selected.value = new Set(props.items.map(lineId));
  splitRef.value = props.suggestedSplitRef;
  targetSessionKey.value = props.otherTabs[0]?.session_key || "";
});

function toggle(item: POSCartItem) {
  const id = lineId(item);
  const next = new Set(selected.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selected.value = next;
}

const selectedIds = computed(() => props.items.map(lineId).filter((id) => selected.value.has(id)));
const needsSelection = computed(() => mode.value !== "merge");
const canSubmit = computed(() => {
  if (props.busy) return false;
  if (mode.value === "split") return selectedIds.value.length > 0 && !!splitRef.value.trim();
  if (mode.value === "transfer") return selectedIds.value.length > 0 && !!targetSessionKey.value;
  return !!targetSessionKey.value && props.items.length > 0; // merge
});

function submit() {
  if (!canSubmit.value) return;
  if (mode.value === "split") {
    emit("submit", { mode: "split", lineIds: selectedIds.value, toTabRef: splitRef.value.trim() });
  } else if (mode.value === "transfer") {
    emit("submit", { mode: "transfer", lineIds: selectedIds.value, toSessionKey: targetSessionKey.value });
  } else {
    emit("submit", {
      mode: "merge",
      lineIds: props.items.map(lineId),
      toSessionKey: targetSessionKey.value,
      closeSource: true,
    });
  }
}

const MODES: Array<{ ref: MoveMode; label: string }> = [
  { ref: "split", label: "Dividir" },
  { ref: "transfer", label: "Transferir" },
  { ref: "merge", label: "Juntar" },
];
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Mover itens · #{{ tabDisplay || "comanda" }}</UiDialogTitle>
        <UiDialogDescription>
          O preço de cada item é mantido como foi cobrado nesta comanda.
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="grid grid-cols-3 gap-2">
        <UiButton
          v-for="option in MODES"
          :key="option.ref"
          variant="outline"
          size="sm"
          :class="mode === option.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
          @click="mode = option.ref"
        >
          {{ option.label }}
        </UiButton>
      </div>

      <p v-if="mode === 'merge'" class="rounded-lg border bg-muted/40 p-2 text-xs text-muted-foreground">
        Move todos os itens desta comanda para a comanda escolhida e libera esta.
      </p>

      <div v-if="needsSelection" class="grid max-h-56 gap-1 overflow-y-auto">
        <label
          v-for="item in items"
          :key="lineId(item)"
          class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5"
          :class="selected.has(lineId(item)) ? 'border-primary bg-primary/5' : ''"
        >
          <input
            type="checkbox"
            class="size-4 accent-primary"
            :checked="selected.has(lineId(item))"
            @change="toggle(item)"
          />
          <span class="min-w-0 flex-1 truncate text-sm">{{ item.qty }}x {{ item.name }}</span>
          <span class="text-xs tabular-nums text-muted-foreground">{{ formatBRL(item.price_q * item.qty) }}</span>
        </label>
      </div>

      <label v-if="mode === 'split'" class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">Nova comanda</span>
        <UiInput v-model="splitRef" placeholder="Ex: 1007/2" />
      </label>

      <label v-else class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">Comanda de destino</span>
        <select
          v-model="targetSessionKey"
          class="h-9 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <option v-if="!otherTabs.length" value="" disabled>Nenhuma outra comanda aberta</option>
          <option v-for="tab in otherTabs" :key="tab.session_key" :value="tab.session_key">
            #{{ tab.display_ref }}<template v-if="tab.customer_name"> · {{ tab.customer_name }}</template>
          </option>
        </select>
      </label>

      <UiDialogFooter>
        <UiButton variant="outline" :disabled="busy" @click="$emit('update:open', false)">Cancelar</UiButton>
        <UiButton :disabled="!canSubmit" :loading="busy" @click="submit">Mover</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
