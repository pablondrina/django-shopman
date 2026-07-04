<script setup lang="ts">
// Operator changes their own PIN on the POS pad: current → new → confirm.
// Proving the current PIN is the authorization (enforced by the backend). Used
// voluntarily from the lock screen, or forced after a manager reset (must-change,
// where "current" is the temp PIN). Pure UI — the parent owns the network call.
import { ref, computed } from "vue";

const props = withDefaults(
  defineProps<{ operatorName: string; forced?: boolean; busy?: boolean; error?: string }>(),
  { forced: false, busy: false, error: "" },
);

const emit = defineEmits<{
  submit: [{ currentPin: string; newPin: string }];
  cancel: [];
}>();

type Step = "current" | "new" | "confirm";
const step = ref<Step>("current");
const currentPin = ref("");
const newPin = ref("");
const confirmPin = ref("");
const localError = ref("");

const pad = computed({
  get(): string {
    if (step.value === "current") return currentPin.value;
    if (step.value === "new") return newPin.value;
    return confirmPin.value;
  },
  set(v: string) {
    localError.value = "";
    if (step.value === "current") currentPin.value = v;
    else if (step.value === "new") newPin.value = v;
    else confirmPin.value = v;
  },
});

const label = computed(() => {
  if (step.value === "current") return props.forced ? "PIN temporário" : "PIN atual";
  if (step.value === "new") return "Novo PIN";
  return "Repita o novo PIN";
});

function advance() {
  if (props.busy) return;
  localError.value = "";
  if (step.value === "current") {
    if (currentPin.value.length < 4) return;
    step.value = "new";
    return;
  }
  if (step.value === "new") {
    if (newPin.value.length < 4) return;
    step.value = "confirm";
    return;
  }
  if (confirmPin.value !== newPin.value) {
    localError.value = "Os PINs não conferem. Tente de novo.";
    confirmPin.value = "";
    return;
  }
  emit("submit", { currentPin: currentPin.value, newPin: newPin.value });
}

function back() {
  localError.value = "";
  if (step.value === "confirm") { step.value = "new"; confirmPin.value = ""; return; }
  if (step.value === "new") { step.value = "current"; newPin.value = ""; return; }
  emit("cancel");
}

const shownError = computed(() => localError.value || props.error || "");
</script>

<template>
  <div class="w-full max-w-md px-6 py-8">
    <div class="mb-6 text-center">
      <div class="mx-auto mb-3 grid size-12 place-items-center rounded-md bg-primary text-primary-foreground shadow-sm">
        <Icon name="lucide:key-round" class="size-6" />
      </div>
      <h1 class="mt-1 text-3xl font-semibold">{{ forced ? "Defina um novo PIN" : "Trocar meu PIN" }}</h1>
      <p class="mt-2 text-base text-muted-foreground">
        <template v-if="forced">
          O gerente resetou seu PIN. Digite o temporário e escolha um novo antes de operar.
        </template>
        <template v-else>{{ operatorName }} — informe o PIN atual e escolha um novo.</template>
      </p>
    </div>

    <div class="mb-4 text-center">
      <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">{{ label }}</p>
    </div>

    <p v-if="shownError" class="mb-4 text-center text-base font-medium text-destructive" role="alert">
      {{ shownError }}
    </p>

    <div class="flex flex-col items-center gap-4">
      <PosPinPad v-model="pad" :disabled="busy" @submit="advance" />
      <UiButton variant="ghost" class="mt-1" :disabled="busy" @click="back">
        <Icon name="lucide:chevron-left" class="size-4" />
        {{ step === "current" ? "Cancelar" : "Voltar" }}
      </UiButton>
    </div>
  </div>
</template>
