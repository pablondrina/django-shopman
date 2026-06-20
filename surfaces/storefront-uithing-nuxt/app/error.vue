<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()

// app.vue já roda antes da página que lança o erro, então a sessão costuma estar
// populada (marca + WhatsApp). Se a própria API caiu, degrada para neutro/sem CTA.
const session = useShopSession()
useShopTheme(session.shop)

const is404 = computed(() => props.error?.statusCode === 404)
const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || '')

const kicker = computed(() => (is404.value ? 'Erro 404' : 'Ops'))
const title = computed(() =>
  is404.value ? 'Não encontramos esta página' : 'Algo saiu do forno errado'
)
const message = computed(() =>
  is404.value
    ? 'O item pode ter saído do cardápio ou o endereço está incorreto — vamos te levar de volta a um lugar seguro.'
    : 'Tivemos um percalço por aqui. Tente de novo em instantes; se precisar fechar um pedido agora, fale com a gente no WhatsApp.'
)

// Páginas de erro nunca devem ser indexadas (o status 404/5xx já sinaliza, isto é
// reforço). `follow` para o crawler ainda seguir os links de volta.
useSeoMeta({ robots: 'noindex, follow', title: () => title.value })

function goMenu () {
  clearError({ redirect: '/menu' })
}

function goHome () {
  clearError({ redirect: '/' })
}
</script>

<template>
  <div class="flex min-h-svh flex-col items-center justify-center gap-6 px-6 py-16 text-center">
    <div class="shop-stack-block max-w-md">
      <p class="shop-kicker">{{ kicker }}</p>
      <h1 class="shop-display">{{ title }}</h1>
      <p class="shop-muted">{{ message }}</p>
    </div>
    <div class="flex flex-col gap-3 sm:flex-row">
      <template v-if="is404">
        <UiButton icon="lucide:utensils" @click="goMenu">Voltar ao cardápio</UiButton>
        <UiButton variant="outline" icon="lucide:house" @click="goHome">Página inicial</UiButton>
      </template>
      <template v-else>
        <UiButton icon="lucide:house" @click="goHome">Página inicial</UiButton>
        <UiButton
          v-if="whatsappUrl"
          variant="outline"
          :href="whatsappUrl"
          target="_blank"
          rel="noreferrer noopener"
        >
          Falar no WhatsApp
        </UiButton>
      </template>
    </div>

    <UiButton
      v-if="is404 && whatsappUrl"
      variant="link"
      size="sm"
      :href="whatsappUrl"
      target="_blank"
      rel="noreferrer noopener"
      class="text-muted-foreground"
    >
      Prefere falar com a gente? WhatsApp
    </UiButton>
  </div>
</template>
