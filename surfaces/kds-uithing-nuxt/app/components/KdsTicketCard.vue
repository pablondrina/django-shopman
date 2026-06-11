<script setup lang="ts">
// A prep-station ticket card — desenho ultra-enxuto e glanceable, com rigor de
// layout: UM único inset horizontal alinha tudo numa coluna (código, itens, check,
// finalizar); timer e `i` têm a MESMA altura de controle; o ritmo vertical é um só.
// Face mínima: CODE (final da ref) + minutagem; ITENS como massa focal (qty alinhada,
// toque confere e risca); o `i` abre o detalhe (canal, cliente, data, horário). Cor
// só onde tem significado, num ÚNICO elemento — a barra time-to-SLA na borda inferior.
// Com `next`, o card é pintado ton sur ton no tom de urgência (único pintado da grade
// → é "o próximo"; a ordem é indicada no título da seção, não dentro do card).
import type { KDSTicketProjection } from "~/types/kds";
import { elapsedLabel, slaPercent, splitRef, ticketTone, toneBar, toneNextSurface, toneTimer } from "~/presentation/board";

export type KDSDensity = "compact" | "cozy" | "roomy";

const props = withDefaults(
  defineProps<{ ticket: KDSTicketProjection; density?: KDSDensity; next?: boolean }>(),
  { density: "cozy", next: false },
);
defineEmits<{ open: []; check: [index: number, checked: boolean]; done: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const ref_ = computed(() => splitRef(props.ticket.order_ref));
const fill = computed(() => slaPercent(props.ticket.elapsed_seconds, props.ticket.target_seconds));
const timerChip = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const nextSurface = computed(() => toneNextSurface(tone.value));

// Altura convencionada: TODOS os cards têm a mesma altura (grade limpa). Os itens
// preenchem a área disponível; se sobrar item, o excedente é clipado com um "ver
// todos" — o operador expande só quando precisa. `clipped` é MEDIDO (ResizeObserver),
// então reflete o overflow real (não um chute por contagem).
const itemsRef = ref<HTMLElement | null>(null);
const clipped = ref(false);
function measure() {
  const el = itemsRef.value;
  clipped.value = !!el && el.scrollHeight > el.clientHeight + 1;
}
useResizeObserver(itemsRef, measure);
watch([() => props.ticket.items, () => props.density], () => nextTick(measure), { deep: true });

// Quando clipado, esmaece o fim da lista (máscara — independe do fundo: funciona no
// card neutro e no "próximo" pintado) como dica de que há mais; a ação de ver tudo
// fica no botão "Ver completo".
const FADE = "linear-gradient(to bottom, #000 calc(100% - 26px), transparent)";
const maskStyle = computed(() => (clipped.value ? { maskImage: FADE, WebkitMaskImage: FADE } : {}));

// Escala de densidade num único mapa — padroniza tamanhos, ritmo e altura.
const d = computed(
  () =>
    ({
      compact: { code: "text-2xl", timer: "text-base", ctrlH: "h-8", item: "text-sm", inset: "px-3", padT: "pt-3", padB: "pb-3", gapY: "py-2.5", fin: "h-10", card: "h-[236px]" },
      cozy: { code: "text-3xl", timer: "text-lg", ctrlH: "h-9", item: "text-base", inset: "px-4", padT: "pt-4", padB: "pb-4", gapY: "py-3", fin: "h-11", card: "h-[284px]" },
      roomy: { code: "text-4xl", timer: "text-xl", ctrlH: "h-11", item: "text-lg", inset: "px-5", padT: "pt-5", padB: "pb-5", gapY: "py-4", fin: "h-12", card: "h-[340px]" },
    })[props.density],
);
</script>

<template>
  <article
    class="relative flex flex-col overflow-hidden rounded-md border transition"
    :class="[d.card, next ? `shadow-lg ring-1 ${nextSurface}` : 'bg-card shadow-sm']"
  >
    <!-- topo: CODE (herói) + minutagem na MESMA linha + `i`. A largura mínima do card
         garante que ambos caibam com folga — o código nunca quebra nem trunca. -->
    <div class="flex items-start justify-between gap-2.5" :class="[d.inset, d.padT]">
      <p class="whitespace-nowrap font-extrabold tracking-tight tabular-nums leading-none" :class="d.code">{{ ref_.code }}</p>
      <div class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 font-bold tabular-nums" :class="[timerChip, d.ctrlH, d.timer]">
        <Icon name="lucide:timer" class="size-4 shrink-0 opacity-70" />
        {{ elapsedLabel(ticket.elapsed_seconds) }}
      </div>
    </div>

    <!-- items — massa focal, alinhados ao código (qty em coluna); toque confere e risca.
         A área preenche o espaço; o excedente é clipado e esmaecido (máscara) como dica. -->
    <div class="relative min-h-0 flex-1">
      <ul ref="itemsRef" class="flex h-full flex-col overflow-hidden" :class="[d.inset, d.gapY]" :style="maskStyle">
        <li v-for="(item, idx) in ticket.items" :key="idx">
          <button
            type="button"
            class="-mx-2 flex w-full items-start justify-between gap-3 rounded-md px-2 py-1.5 text-left transition hover:bg-accent/50 active:scale-[0.99]"
            @click="$emit('check', idx, !item.checked)"
          >
            <span class="min-w-0 flex-1">
              <!-- 1ª linha: qty + nome; quando feito, uma risca contínua atravessa
                   tudo de ponta a ponta (o texto só esmaece) — para antes do check. -->
              <span class="relative flex items-center gap-2.5">
                <span class="min-w-[2.5ch] shrink-0 text-right font-bold tabular-nums transition-colors duration-200" :class="[d.item, item.checked ? 'text-muted-foreground' : '']">{{ item.qty }}×</span>
                <span class="min-w-0 flex-1 truncate font-semibold transition-colors duration-200" :class="[d.item, item.checked ? 'text-muted-foreground' : '']">{{ item.name }}</span>
                <span v-if="item.checked" aria-hidden="true" class="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-muted-foreground/50" />
              </span>
              <span v-if="item.notes" class="mt-1 flex" :class="item.checked ? 'opacity-50' : ''">
                <span class="inline-flex min-w-0 max-w-full items-center rounded border bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                  <span class="truncate">{{ item.notes }}</span>
                </span>
              </span>
              <span v-if="item.stock_warning" class="mt-1 flex" :class="item.checked ? 'opacity-50' : ''">
                <span class="inline-flex min-w-0 max-w-full items-center gap-1 rounded border bg-muted px-1.5 py-0.5 text-xs font-semibold text-foreground">
                  <Icon name="lucide:triangle-alert" class="size-3 shrink-0" />
                  <span class="truncate">{{ item.stock_warning }}</span>
                </span>
              </span>
            </span>
            <Icon
              name="lucide:check"
              class="mt-0.5 size-5 shrink-0 transition-colors duration-200"
              :class="item.checked ? 'text-foreground' : 'text-muted-foreground/30'"
            />
          </button>
        </li>
      </ul>
    </div>

    <!-- ações: "Ver completo" (olho — abre o detalhe) + "Finalizar" em destaque
         (neutro INVERTIDO — a ação principal). -->
    <div class="flex gap-2" :class="[d.inset, d.padB]">
      <button
        type="button"
        class="flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md border border-border/60 text-sm font-semibold text-muted-foreground transition hover:bg-accent hover:text-foreground active:scale-[0.99]"
        :class="d.fin"
        @click="$emit('open')"
      >
        <Icon name="lucide:eye" class="size-4 shrink-0" />
        <span class="truncate">Detalhes...</span>
      </button>
      <button
        type="button"
        class="flex min-w-0 flex-1 items-center justify-center gap-2 rounded-md bg-foreground text-sm font-semibold text-background transition hover:bg-foreground/90 active:scale-[0.99]"
        :class="d.fin"
        @click="$emit('done')"
      >
        <Icon name="lucide:check-check" class="size-4 shrink-0" />
        <span class="truncate">Finalizar</span>
      </button>
    </div>

    <!-- time-to-SLA fill bar (bottom edge) — o único elemento de cor de urgência -->
    <div class="h-1.5 w-full bg-white/5" aria-hidden="true">
      <div class="h-full rounded-r-full transition-[width] duration-500" :class="barFill" :style="{ width: `${fill}%` }" />
    </div>
  </article>
</template>
