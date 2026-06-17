<script setup lang="ts">
// Coração de favorito (WP-4). Toggle otimista compartilhado entre card/PDP via
// useFavoritesState. Anônimo é convidado a logar (omotenashi: convida, não bloqueia).
const props = defineProps<{
  sku: string
  // Estado inicial vindo da projeção (is_favorite). O overlay tem precedência.
  initial?: boolean
  // Variante sobre foto (card): fundo translúcido + sombra para contraste.
  onPhoto?: boolean
}>()

const { isFavorite, toggle, isAuthenticated } = useFavoritesState()
const submitting = ref(false)

const active = computed(() => isFavorite(props.sku, props.initial ?? false))

async function onClick () {
  if (!isAuthenticated.value) {
    if (import.meta.client) useSonner('Entre para salvar seus favoritos.')
    await navigateTo('/login')
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await toggle(props.sku, active.value)
  } catch {
    // toast já tratado no composable; estado revertido
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiButton
    type="button"
    variant="ghost"
    size="icon"
    :aria-pressed="active"
    :aria-label="active ? `Remover ${sku} dos favoritos` : `Salvar ${sku} nos favoritos`"
    :disabled="submitting"
    class="rounded-full"
    :class="onPhoto ? 'bg-background/80 text-foreground shadow-sm backdrop-blur hover:bg-background' : 'text-muted-foreground hover:text-primary'"
    @click.stop.prevent="onClick"
  >
    <Icon
      name="lucide:heart"
      class="size-5 transition"
      :class="active ? 'fill-primary text-primary' : ''"
    />
  </UiButton>
</template>
