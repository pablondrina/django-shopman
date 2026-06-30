<script setup lang="ts">
// Aviso de indisponibilidade no momento do 409 (STOCK-UX-PLAN: acionável, 1 toque).
// Sobe como bottom-sheet global em qualquer superfície (menu/PDP/sacola) — o estoque
// é um retrato e pode mudar entre carregar e tocar; aqui trazemos a saída pronta.
// O substituto é ajuda, não erro: copy acolhedora, em "nós".
const {
  cartIssue,
  isPending,
  addSubstitute,
  acceptAvailableQty,
  retryLastMutation,
  dismissCartIssue
} = useCartState()

const open = computed({
  get: () => !!cartIssue.value,
  // Fechar por gesto (X/overlay/Esc) ou após uma ação = dispensar o aviso.
  set: (value: boolean) => { if (!value) dismissCartIssue() }
})

const itemName = computed(() => cartIssue.value?.name || 'este item')
const availableQty = computed(() => cartIssue.value?.available_qty ?? null)
const hasAvailable = computed(() => availableQty.value != null && availableQty.value > 0)
const substitutes = computed(() => cartIssue.value?.substitutes ?? [])

const title = computed(() => hasAvailable.value ? 'Ajuste a quantidade' : 'Esgotou enquanto você escolhia')
const description = computed(() => hasAvailable.value
  ? `Agora temos ${formatCount(availableQty.value!, 'unidade', 'unidades')} de ${itemName.value}.`
  : `O ${itemName.value} acabou agora — veja boas alternativas.`)

function useAvailable () {
  void acceptAvailableQty()
}
function chooseSubstitute (sub: typeof substitutes.value[number]) {
  void addSubstitute(sub)
}
function tryAgain () {
  void retryLastMutation()
}
</script>

<template>
  <BottomSheet
    v-model:open="open"
    max-width="md"
    :title="title"
    :description="description"
    data-substitute-sheet
  >
    <div class="shop-stack-block px-4 py-4">
      <UiButton
        v-if="hasAvailable"
        size="lg"
        class="w-full"
        :loading="!!cartIssue && isPending(cartIssue.sku)"
        @click="useAvailable"
      >
        Levar {{ formatCount(availableQty!, 'unidade', 'unidades') }}
      </UiButton>

      <div v-if="substitutes.length">
        <p v-if="hasAvailable" class="mb-1 shop-meta">Ou troque por:</p>
        <ul class="divide-y overflow-hidden rounded-lg border">
          <li v-for="sub in substitutes" :key="sub.sku">
            <UiButton
              variant="ghost"
              class="h-auto w-full justify-between gap-3 rounded-none px-3 py-3 hover:bg-muted/60"
              :disabled="!sub.can_order || isPending(sub.sku)"
              :aria-label="`Adicionar ${sub.name} à sacola`"
              @click="chooseSubstitute(sub)"
            >
              <span class="min-w-0 flex-1 truncate text-left shop-item-title">{{ sub.name }}</span>
              <span v-if="sub.price_display" class="shrink-0 shop-price tabular-nums">{{ sub.price_display }}</span>
              <Icon
                :name="isPending(sub.sku) ? 'line-md:loading-loop' : 'lucide:plus'"
                class="size-5 shrink-0 text-primary"
              />
            </UiButton>
          </li>
        </ul>
      </div>

      <UiButton
        v-else-if="!hasAvailable"
        variant="outline"
        size="lg"
        class="w-full"
        :loading="!!cartIssue && isPending(cartIssue.sku)"
        @click="tryAgain"
      >
        Tentar de novo
      </UiButton>

      <UiButton
        variant="ghost"
        size="sm"
        class="-ml-2 self-start text-muted-foreground hover:text-foreground"
        @click="open = false"
      >
        Agora não
      </UiButton>
    </div>
  </BottomSheet>
</template>
