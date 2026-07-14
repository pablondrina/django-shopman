<script setup lang="ts">
// Rail de operador CANÔNICO — a espinha vertical em `bg-rail` (token próprio do chrome,
// de marca: disciplina de ERP) que TODAS as superfícies de operador adotam. É o portador
// nº1 da familiaridade: mesma peça em POS/Gestor/KDS/Fournil/Central. Segura o que é
// COMUM (voltar à Central, operador/travar, tema, e o que o app puser em #status); o
// específico de cada app entra pelos slots (#nav = funções; #status = saúde/conexão).
//
// Três estados que o operador escolhe conforme precisa (persistidos por dispositivo via
// `useRailState`): colapsado (só um puxador) · compacto (só ícone) · estendido (ícone +
// rótulo). A nav de SEÇÃO de cada app (abas do Gestor, visões do Fournil) NÃO vive aqui —
// fica no topo do conteúdo; o rail concentra só o comum e economiza a horizontal.
import { computed } from "vue";

const props = defineProps<{
  /** Ícone forte do app (DS §6), com ou sem `lucide:`. */
  appIcon: string;
  appLabel: string;
  /** URL da Central (launcher). Omitido na própria Central → some o item. */
  centralUrl?: string;
  /** Operador ativo — mostra o item de travar/trocar; emite `lock` ao acionar. */
  operatorName?: string;
}>();

const emit = defineEmits<{ lock: [] }>();

const { state, isCollapsed, isExtended } = useRailState();

const colorMode = useColorMode();
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}
const themeLabel = computed(() => (colorMode.value === "dark" ? "Tema claro" : "Tema escuro"));

const appIconName = computed(() => (props.appIcon.startsWith("lucide:") ? props.appIcon : `lucide:${props.appIcon}`));
</script>

<template>
  <!-- Colapsado → não renderiza nada (some de verdade); quem traz de volta é o
       RailToggle no cabeçalho do app. Compacto / estendido: -->
  <aside
    v-if="!isCollapsed"
    class="flex shrink-0 flex-col bg-rail py-2 text-rail-foreground print:hidden"
    :class="isExtended ? 'w-52 px-2' : 'w-14 items-center px-2'"
    :aria-label="`Barra do ${appLabel}`"
    :data-rail-state="state"
  >
    <!-- Identidade + voltar à Central (padrão Odoo): o ícone forte do app é também o
         atalho pra Central — no hover/foco vira uma seta "voltar". Na própria Central
         (sem centralUrl) é identidade pura, sem atalho. -->
    <component
      :is="centralUrl ? 'a' : 'div'"
      :href="centralUrl"
      :aria-label="centralUrl ? 'Voltar à Central de Apps' : undefined"
      :title="centralUrl ? 'Voltar à Central de Apps' : undefined"
      class="group mb-1 flex items-center gap-2"
      :class="isExtended ? 'w-full' : ''"
    >
      <span
        class="grid size-10 shrink-0 place-items-center rounded-md bg-rail-foreground/15 transition"
        :class="centralUrl ? 'group-hover:bg-rail-foreground/25 group-focus-visible:bg-rail-foreground/25' : ''"
      >
        <Icon
          :name="appIconName"
          class="size-5"
          :class="centralUrl ? 'group-hover:hidden group-focus-visible:hidden' : ''"
        />
        <Icon
          v-if="centralUrl"
          name="lucide:arrow-left"
          class="hidden size-5 group-hover:block group-focus-visible:block"
        />
      </span>
      <span v-if="isExtended" class="truncate text-sm font-semibold">
        <template v-if="centralUrl">
          <span class="group-hover:hidden group-focus-visible:hidden">{{ appLabel }}</span>
          <span class="hidden group-hover:inline group-focus-visible:inline">Central</span>
        </template>
        <template v-else>{{ appLabel }}</template>
      </span>
    </component>

    <!-- Funções específicas do app (RailItem no slot). -->
    <nav class="flex w-full flex-col gap-0.5" :aria-label="`Funções do ${appLabel}`">
      <slot name="nav" />
    </nav>

    <!-- Cluster comum, ancorado embaixo. -->
    <div class="mt-auto flex w-full flex-col gap-0.5">
      <slot name="status" />

      <RailItem
        v-if="operatorName"
        icon="user-round"
        :label="operatorName"
        :aria-label="`${operatorName} — travar / trocar`"
        @activate="emit('lock')"
      />

      <ClientOnly>
        <RailItem
          icon="lucide:moon"
          :label="themeLabel"
          :aria-label="themeLabel"
          @activate="toggleTheme"
        />
        <template #fallback>
          <span class="grid h-10 w-10 place-items-center rounded-md text-rail-foreground/80">
            <Icon name="lucide:moon" class="size-5" />
          </span>
        </template>
      </ClientOnly>
    </div>
  </aside>
</template>
