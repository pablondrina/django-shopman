<script setup lang="ts">
// Operator changes their own PIN on a stepped pad: current → new → confirm.
// Proving the current PIN is the authorization (enforced by the backend). Used
// voluntarily from the lock screen and forced after a manager reset (must-change).
// Pure UI — the parent owns the network call (changePin) and passes busy/error.
import { appendPinDigit } from "~/presentation/operatorLock";

const props = defineProps<{
  operatorName: string;
  forced?: boolean;
  busy?: boolean;
  error?: string;
}>();

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

const label = computed(() => {
  if (step.value === "current")
    return props.forced ? "PIN temporário" : "PIN atual";
  if (step.value === "new") return "Novo PIN";
  return "Repita o novo PIN";
});

function activeValue(): string {
  if (step.value === "current") return currentPin.value;
  if (step.value === "new") return newPin.value;
  return confirmPin.value;
}
function setActive(v: string) {
  if (step.value === "current") currentPin.value = v;
  else if (step.value === "new") newPin.value = v;
  else confirmPin.value = v;
}

const canAdvance = computed(() => activeValue().trim().length >= 4);

function press(d: string) {
  localError.value = "";
  setActive(appendPinDigit(activeValue(), d));
}
function backspace() {
  setActive(activeValue().slice(0, -1));
}

function advance() {
  if (!canAdvance.value || props.busy) return;
  localError.value = "";
  if (step.value === "current") {
    step.value = "new";
    return;
  }
  if (step.value === "new") {
    step.value = "confirm";
    return;
  }
  if (newPin.value.trim() !== confirmPin.value.trim()) {
    localError.value = "Os PINs não conferem. Tente de novo.";
    confirmPin.value = "";
    return;
  }
  emit("submit", {
    currentPin: currentPin.value.trim(),
    newPin: newPin.value.trim(),
  });
}

function back() {
  localError.value = "";
  if (step.value === "confirm") {
    step.value = "new";
    confirmPin.value = "";
    return;
  }
  if (step.value === "new") {
    step.value = "current";
    newPin.value = "";
    return;
  }
  emit("cancel");
}

const shownError = computed(() => localError.value || props.error || "");
</script>

<template>
  <div>
    <div class="mb-4 flex items-center gap-2">
      <Icon name="lucide:key-round" class="size-5 text-muted-foreground" />
      <h2 class="text-lg font-bold">
        {{ forced ? "Defina um novo PIN" : "Trocar meu PIN" }}
      </h2>
    </div>
    <p class="mb-3 text-sm text-muted-foreground">
      <template v-if="forced">
        O gerente resetou seu PIN. Digite o PIN temporário e escolha um novo
        antes de operar.
      </template>
      <template v-else>
        {{ operatorName }} — informe o PIN atual e escolha um novo.
      </template>
    </p>

    <button
      type="button"
      class="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      @click="back"
    >
      <Icon name="lucide:chevron-left" class="size-4" />
      {{ step === "current" ? "Cancelar" : "Voltar" }}
    </button>

    <p class="mb-2 text-sm font-semibold">{{ label }}</p>
    <div
      class="mb-2 flex h-10 items-center justify-center rounded-md border bg-background text-3xl tracking-[0.4em] tabular-nums"
    >
      {{ "•".repeat(activeValue().length) || "—" }}
    </div>
    <p v-if="shownError" class="mb-2 text-sm font-medium text-destructive">
      {{ shownError }}
    </p>

    <div class="grid grid-cols-3 gap-2">
      <button
        v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
        :key="d"
        type="button"
        class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
        @click="press(d)"
      >
        {{ d }}
      </button>
      <button
        type="button"
        class="rounded-lg border bg-background py-3 text-sm transition hover:bg-accent"
        @click="backspace"
      >
        <Icon name="lucide:delete" class="mx-auto size-5" />
      </button>
      <button
        type="button"
        class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
        @click="press('0')"
      >
        0
      </button>
      <button
        type="button"
        :disabled="!canAdvance || busy"
        class="rounded-lg border border-transparent bg-primary py-3 text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        @click="advance"
      >
        <Icon
          :name="step === 'confirm' ? 'lucide:check' : 'lucide:arrow-right'"
          class="mx-auto size-5"
        />
      </button>
    </div>
  </div>
</template>
