<script setup lang="ts">
import type { POSCartItem, POSTabProjection } from "~/types/pos";
import {
  availableMoveModes,
  buildMovePayload,
  canSubmitMove,
  defaultMoveTarget,
  freezesPriceOnMove,
  type MoveMode,
  type MovePayload,
  moveLineId,
  moveLineView,
  modeNeedsSelection,
  moveTargetOptions,
  selectedLineIds,
} from "~/presentation/moveLines";

const props = defineProps<{
  open: boolean;
  tabDisplay: string;
  items: POSCartItem[];
  suggestedSplitRef: string;
  otherTabs: POSTabProjection[];
  /** `tab_manipulation` capability — drives the offered modes + price note. */
  capability: unknown;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  submit: [MovePayload];
}>();

const modes = computed(() => availableMoveModes(props.capability));
const showPriceNote = computed(() => freezesPriceOnMove(props.capability));
const targetOptions = computed(() => moveTargetOptions(props.otherTabs));
const lineViews = computed(() => props.items.map(moveLineView));

const mode = ref<MoveMode>("split");
const selected = ref<Set<string>>(new Set());
const splitRef = ref("");
const targetSessionKey = ref("");

watch(() => props.open, (isOpen) => {
  if (!isOpen) return;
  mode.value = modes.value[0]?.ref ?? "split";
  selected.value = new Set(props.items.map(moveLineId));
  splitRef.value = props.suggestedSplitRef;
  targetSessionKey.value = defaultMoveTarget(props.otherTabs);
});

function toggle(id: string) {
  const next = new Set(selected.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selected.value = next;
}

const selectedIds = computed(() => selectedLineIds(props.items, selected.value));
const needsSelection = computed(() => modeNeedsSelection(mode.value));
const canSubmit = computed(() => canSubmitMove({
  mode: mode.value,
  selectedIds: selectedIds.value,
  splitRef: splitRef.value,
  targetSessionKey: targetSessionKey.value,
  itemCount: props.items.length,
  busy: props.busy,
}));

function submit() {
  const payload = buildMovePayload({
    mode: mode.value,
    items: props.items,
    selectedIds: selectedIds.value,
    splitRef: splitRef.value,
    targetSessionKey: targetSessionKey.value,
  });
  if (payload) emit("submit", payload);
}
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <UiDialogContent class="sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Mover itens · #{{ tabDisplay || "comanda" }}</UiDialogTitle>
        <UiDialogDescription v-if="showPriceNote">
          O preço de cada item é mantido como foi cobrado nesta comanda.
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="grid gap-2" :style="{ gridTemplateColumns: `repeat(${modes.length}, minmax(0, 1fr))` }">
        <UiButton
          v-for="option in modes"
          :key="option.ref"
          variant="outline"
          size="sm"
          :class="mode === option.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
          @click="mode = option.ref"
        >
          {{ option.label }}
        </UiButton>
      </div>

      <p v-if="mode === 'merge'" class="rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">
        Move todos os itens desta comanda para a comanda escolhida e libera esta.
      </p>

      <div v-if="needsSelection" class="grid max-h-56 gap-1 overflow-y-auto">
        <label
          v-for="line in lineViews"
          :key="line.id"
          class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5"
          :class="selected.has(line.id) ? 'border-primary bg-primary/5' : ''"
        >
          <input
            type="checkbox"
            class="size-4 accent-primary"
            :checked="selected.has(line.id)"
            @change="toggle(line.id)"
          />
          <span class="min-w-0 flex-1 truncate text-sm">{{ line.label }}</span>
          <span class="text-xs tabular-nums text-muted-foreground">{{ line.amountDisplay }}</span>
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
          <option v-if="!targetOptions.length" value="" disabled>Nenhuma outra comanda aberta</option>
          <option v-for="option in targetOptions" :key="option.sessionKey" :value="option.sessionKey">
            {{ option.label }}
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
