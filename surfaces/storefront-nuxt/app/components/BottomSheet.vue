<script setup lang="ts">
// Bottom-sheet canônico da loja: um único figurino para todos os painéis que sobem
// da base no mobile (etiqueta de endereço, formulário de endereço, mapa, confirmação
// e recibo do pedido). Padroniza superfície, centragem, largura, header com folga
// do X, rodapé e a affordance de fechar — o corpo continua livre via slot default.
//
// Superfície NEUTRA (card branco / muted cinza); a cor da marca fica nos CTAs que o
// chamador coloca no rodapé. Construído sobre a primitiva Reka (UiSheet) — foco,
// Esc, scroll-lock e backdrop vêm dela.
import type { HTMLAttributes } from 'vue'

// data-* e afins (usados por testes/seletores) vão para o elemento de conteúdo.
defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  /** Largura máxima do painel (centralizado). */
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
  /** Superfície neutra: `card` (branco, padrão) ou `muted` (cinza claro). */
  surface?: 'card' | 'muted'
  /** Classe extra mesclada no conteúdo (ex.: altura fixa do mapa). */
  contentClass?: HTMLAttributes['class']
}>(), {
  maxWidth: 'xl',
  surface: 'card'
})

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const maxWidthClass = computed(() => ({
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl'
})[props.maxWidth])

const surfaceClass = computed(() =>
  props.surface === 'card' ? 'bg-card text-card-foreground' : 'bg-muted'
)
// Gradiente de scroll: precisa desbotar PARA a cor da superfície (branco/cinza),
// senão a borda do fade fica visível.
const fadeFromClass = computed(() => props.surface === 'card' ? 'from-card' : 'from-muted')

// Affordance "tem mais abaixo": um fade no rodapé do corpo rolável, visível só
// enquanto o fim do conteúdo não está à vista. Um sentinela no fim + Intersection
// Observer (sem cálculo de scroll; reage a resize/conteúdo dinâmico de graça).
const scrollEl = ref<HTMLElement>()
const sentinel = ref<HTMLElement>()
const showBottomFade = ref(false)
let io: IntersectionObserver | null = null
function teardownObserver() {
  io?.disconnect()
  io = null
}
function setupObserver() {
  teardownObserver()
  if (!scrollEl.value || !sentinel.value) return
  io = new IntersectionObserver(
    entries => { showBottomFade.value = !entries[0]!.isIntersecting },
    { root: scrollEl.value, threshold: 0.01 }
  )
  io.observe(sentinel.value)
}
watch(() => props.open, async open => {
  if (open) { await nextTick(); setupObserver() } else teardownObserver()
})
onMounted(() => { if (props.open) nextTick(setupObserver) })
onBeforeUnmount(teardownObserver)
</script>

<template>
  <UiSheet :open="open" @update:open="value => emit('update:open', value)">
    <UiSheetContent
      side="bottom"
      variant="floating"
      :class="['mx-auto flex max-h-[85dvh] w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0', maxWidthClass, surfaceClass, contentClass]"
      v-bind="$attrs"
    >
      <!-- X sempre visível e bem posicionado (a primitiva renderia um botão vazio). -->
      <template #close>
        <UiSheetX sr-text="Fechar" />
      </template>

      <!-- Alça de arraste: affirma o idiom de sheet e dá acabamento mobile-native. -->
      <div
        class="mx-auto mt-2 h-1.5 w-9 shrink-0 rounded-full bg-muted-foreground/20"
        aria-hidden="true"
      />

      <UiSheetHeader
        v-if="title || $slots.header"
        class="shrink-0 gap-1 border-b px-4 pt-3 pb-4 pr-12 text-left"
      >
        <slot name="header">
          <UiSheetTitle :title="title" />
          <UiSheetDescription v-if="description" :description="description" />
        </slot>
      </UiSheetHeader>

      <!-- Corpo rolável: flex até o fim (nunca `h-full`/altura %). A altura do
           wrapper vem do flex-grow do pai; uma altura percentual não resolve
           contra base flex e desaba para a altura do conteúdo — o corpo deixaria
           de recortar/rolar e vazaria POR CIMA do rodapé. -->
      <div class="relative flex min-h-0 flex-1 flex-col">
        <div ref="scrollEl" class="min-h-0 flex-1 overflow-y-auto">
          <slot />
          <div ref="sentinel" aria-hidden="true" class="h-px w-full" />
        </div>
        <!-- Fade de "tem mais abaixo" — some quando o fim do conteúdo aparece. -->
        <div
          class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t to-transparent transition-opacity duration-200"
          :class="[fadeFromClass, showBottomFade ? 'opacity-100' : 'opacity-0']"
          aria-hidden="true"
        />
        <!-- Affordance animada "role para ver mais": pill translúcida com chevron,
             flutuar suave (bounce lento), some junto com o fade. Discreta e limpa. -->
        <div
          class="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center transition-opacity duration-300"
          :class="showBottomFade ? 'opacity-100' : 'opacity-0'"
          aria-hidden="true"
        >
          <span class="flex size-7 animate-bounce items-center justify-center rounded-full bg-background/70 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm [animation-duration:1.6s]">
            <Icon name="lucide:chevron-down" class="size-4" />
          </span>
        </div>
      </div>

      <UiSheetFooter
        v-if="$slots.footer"
        class="shrink-0 gap-2 border-t p-4"
      >
        <slot name="footer" />
      </UiSheetFooter>
    </UiSheetContent>
  </UiSheet>
</template>
