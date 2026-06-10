<script setup lang="ts">
// Shared customer search (Odoo-style get-or-create entry point): one field
// matches any unique key (name/phone/CPF/email), debounced, returning a list to
// pick from. Picking fills the cart + runs the full lookup; the commit still
// get-or-creates by phone/CPF, so a fresh name+phone just creates on finalize.
// Used by both the comanda header and the payment screen's customer modal.
import type { POSCustomerSearchResult } from "~/types/pos";

const props = defineProps<{
  results: POSCustomerSearchResult[];
  busy: boolean;
}>();

const emit = defineEmits<{
  search: [string];
  select: [POSCustomerSearchResult];
}>();

const query = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;
watch(query, (q) => {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => emit("search", q), 350);
});
function pick(result: POSCustomerSearchResult) {
  emit("select", result);
  query.value = "";
}
// Let the parent reset the field when its modal reopens.
function reset() {
  query.value = "";
}
defineExpose({ reset });
onBeforeUnmount(() => { if (timer) clearTimeout(timer); });
</script>

<template>
  <div class="grid gap-3">
    <div class="relative">
      <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <UiInput
        v-model="query"
        class="h-11 pl-10 text-base"
        placeholder="Buscar por nome, telefone, CPF ou e-mail"
        autofocus
      />
      <Icon v-if="busy" name="lucide:loader-circle" class="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
    </div>

    <div v-if="results.length" class="grid max-h-56 gap-0.5 overflow-auto rounded-md border p-1">
      <button
        v-for="result in results"
        :key="result.ref"
        type="button"
        class="flex items-center justify-between gap-2 rounded-md px-3 py-2 text-left transition hover:bg-accent"
        @click="pick(result)"
      >
        <span class="min-w-0">
          <span class="block truncate text-sm font-medium">{{ result.name || "Sem nome" }}</span>
          <span class="block truncate text-xs tabular-nums text-muted-foreground">{{ [result.phone, result.document, result.email].filter(Boolean).join(" · ") }}</span>
        </span>
        <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
      </button>
    </div>
    <p v-else-if="query.trim().length >= 2 && !busy" class="text-center text-xs text-muted-foreground">
      Nenhum cadastro encontrado — preencha abaixo para criar um novo.
    </p>
  </div>
</template>
