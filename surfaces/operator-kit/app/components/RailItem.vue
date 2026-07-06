<script setup lang="ts">
// Item do rail — a unidade do `OperatorRail`, consistente nos 3 estados: só ícone
// (compacto/colapsado, com tooltip nativo) ou ícone + rótulo (estendido). Vira <a> quando
// recebe `href` (ex.: voltar à Central) ou <button> que emite `activate` (ex.: travar).
// Não conhece o estado do rail — lê `useRailState().showLabels` (verdade compartilhada).
import { computed } from "vue";

const props = defineProps<{
  /** Ícone Lucide, com ou sem o prefixo `lucide:`. */
  icon: string;
  label: string;
  /** Realce de item ativo (nav) — vira `aria-current="page"`. */
  active?: boolean;
  /** Item-link (navega em vez de emitir) — ex.: Central. */
  href?: string;
  /** Rótulo acessível quando difere do visível (ex.: "admin — travar"). */
  ariaLabel?: string;
  /** Ação em andamento — gira o ícone e desabilita (ex.: atualizar). */
  busy?: boolean;
  /** Cue de atenção — anel no ícone mesmo no compacto (ex.: abrir caixa). */
  attention?: boolean;
}>();

const emit = defineEmits<{ activate: [] }>();

const { showLabels } = useRailState();
const iconName = computed(() => (props.icon.startsWith("lucide:") ? props.icon : `lucide:${props.icon}`));
const a11yLabel = computed(() => props.ariaLabel || props.label);

function onClick() {
  if (!props.href && !props.busy) emit("activate");
}
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    :href="href"
    :type="href ? undefined : 'button'"
    :disabled="href ? undefined : busy"
    :aria-label="a11yLabel"
    :aria-current="active ? 'page' : undefined"
    :title="showLabels ? undefined : a11yLabel"
    class="flex h-10 items-center rounded-md transition disabled:opacity-60"
    :class="[
      showLabels ? 'w-full gap-3 px-2.5' : 'w-10 justify-center',
      active
        ? 'bg-primary-foreground/15 text-primary-foreground'
        : 'text-primary-foreground/80 hover:bg-primary-foreground/10 hover:text-primary-foreground',
    ]"
    @click="onClick"
  >
    <!-- Anel de atenção quando `attention` (e não ativo): sobrevive ao estado compacto. -->
    <span
      v-if="attention && !active"
      class="grid size-7 shrink-0 place-items-center rounded-md ring-2 ring-primary-foreground/45"
    >
      <Icon :name="iconName" class="size-5" />
    </span>
    <Icon v-else :name="iconName" class="size-5 shrink-0" :class="busy ? 'animate-spin' : ''" />
    <span v-if="showLabels" class="truncate text-sm">{{ label }}</span>
  </component>
</template>
