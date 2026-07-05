<script setup lang="ts">
import { appendPinDigit, backspacePin } from "~/utils/operatorLock";

const props = withDefaults(
  defineProps<{ modelValue: string; maxLength?: number; disabled?: boolean }>(),
  { maxLength: 6, disabled: false },
);
const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
}>();

const digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];

function press(d: string) {
  if (props.disabled) return;
  emit("update:modelValue", appendPinDigit(props.modelValue, d, props.maxLength));
}
function back() {
  if (props.disabled) return;
  emit("update:modelValue", backspacePin(props.modelValue));
}
function submit() {
  if (props.disabled) return;
  emit("submit");
}
</script>

<template>
  <div class="flex flex-col items-center gap-5">
    <!-- masked display -->
    <div class="flex items-center gap-3" aria-live="polite" :aria-label="`${modelValue.length} dígitos`">
      <span
        v-for="i in maxLength"
        :key="i"
        class="size-3.5 rounded-full border transition-colors"
        :class="i <= modelValue.length ? 'border-primary bg-primary' : 'border-muted-foreground/40'"
      />
    </div>

    <div class="grid grid-cols-3 gap-3">
      <UiButton
        v-for="d in digits"
        :key="d"
        variant="outline"
        class="h-16 w-20 text-3xl font-semibold tabular-nums"
        :disabled="disabled"
        @click="press(d)"
      >
        {{ d }}
      </UiButton>

      <UiButton
        variant="ghost"
        class="h-16 w-20"
        :disabled="disabled"
        aria-label="Apagar"
        @click="back"
      >
        <Icon name="lucide:delete" class="size-6" />
      </UiButton>

      <UiButton
        variant="outline"
        class="h-16 w-20 text-3xl font-semibold tabular-nums"
        :disabled="disabled"
        @click="press('0')"
      >
        0
      </UiButton>

      <UiButton
        class="h-16 w-20"
        :disabled="disabled || modelValue.length === 0"
        aria-label="Confirmar"
        @click="submit"
      >
        <Icon name="lucide:check" class="size-6" />
      </UiButton>
    </div>
  </div>
</template>
