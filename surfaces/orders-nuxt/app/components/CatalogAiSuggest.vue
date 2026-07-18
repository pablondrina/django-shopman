<script setup lang="ts">
// Assist de IA de UM campo — o rótulo, o botão "sugerir" e a prévia da sugestão.
// O campo em si entra pelo slot, então o mesmo componente serve input, textarea e
// o que vier depois.
//
// A regra é por campo: cada campo tem seu botão e o operador aceita ou descarta
// aquela sugestão sozinha. Não existe "sugerir tudo" — sugestão em lote vira
// aceitação no atacado, e aí ninguém lê o que foi para a vitrine.
//
// Nada é gravado aqui: "Aceitar" só escreve no rascunho do painel; quem persiste
// é o Salvar. Presentacional — o pai passa `assist` (do useCatalogMatrix) e o
// estado de ocupado.
import type { AssistableField } from "~/types/catalog";

const props = defineProps<{
  field: AssistableField;
  label: string;
  current: string;
  busy: boolean;
  assist: (field: AssistableField, currentValue: string) => Promise<string>;
  hint?: string;
}>();

const emit = defineEmits<{ accept: [text: string] }>();

// Sugestão pendente: fica visível até o operador aceitar ou descartar.
const suggestion = ref("");

async function onSuggest() {
  if (props.busy) return;
  // Erro e "não configurado" já viram toast no composable; aqui "" = nada a mostrar.
  suggestion.value = await props.assist(props.field, props.current);
}

function onAccept() {
  emit("accept", suggestion.value);
  suggestion.value = "";
}

// Trocar de produto com uma sugestão aberta não pode vazar o texto do anterior.
watch(() => props.field, () => (suggestion.value = ""));
</script>

<template>
  <label class="block">
    <span class="mb-1 flex items-center justify-between gap-2">
      <span class="text-xs font-medium text-muted-foreground">{{ label }}</span>
      <button
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-50"
        :aria-label="`Sugerir ${label} com IA`"
        @click.prevent="onSuggest"
      >
        <Icon
          :name="busy ? 'line-md:loading-loop' : 'lucide:sparkles'"
          class="size-3.5"
        />
        {{ busy ? "Sugerindo…" : "Sugerir" }}
      </button>
    </span>

    <slot />

    <span v-if="hint" class="mt-1 block text-xs text-muted-foreground">{{ hint }}</span>

    <!-- prévia da sugestão: comparativa quando o campo já tem texto, para o
         operador ver o que perde antes de aceitar -->
    <span v-if="suggestion" class="mt-2 block rounded-lg border border-primary/30 bg-primary/5 p-3">
      <span class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
        <Icon name="lucide:sparkles" class="size-3.5 text-primary" />
        Sugestão
      </span>

      <span v-if="current.trim()" class="mb-2 block">
        <span class="block text-xs font-medium text-muted-foreground">Texto atual</span>
        <span class="block whitespace-pre-wrap text-sm text-muted-foreground">{{ current }}</span>
      </span>

      <span class="block whitespace-pre-wrap text-sm text-foreground">{{ suggestion }}</span>

      <span class="mt-2 flex items-center gap-2">
        <button
          type="button"
          class="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
          @click.prevent="onAccept"
        >Aceitar</button>
        <button
          type="button"
          class="rounded-md border border-border px-2.5 py-1 text-xs font-medium transition hover:bg-accent"
          @click.prevent="suggestion = ''"
        >Descartar</button>
      </span>
    </span>
  </label>
</template>
