<script setup lang="ts">
const session = useShopSession()

const shop = computed(() => session.shop.value)
const openingHours = computed(() => session.openingHours.value)
const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || shop.value?.whatsapp_url || '')
const year = new Date().getFullYear()
</script>

<template>
  <footer class="border-t bg-background">
    <div class="shop-container grid gap-6 py-8 sm:grid-cols-2 lg:grid-cols-4">
      <section class="min-w-0 space-y-2">
        <p class="text-base font-semibold">{{ shop?.brand_name || 'Shopman' }}</p>
        <p class="text-sm leading-6 text-muted-foreground">
          {{ shop?.description || shop?.tagline || 'Compra rápida e acompanhada.' }}
        </p>
        <p v-if="shop?.default_city" class="text-sm text-muted-foreground">{{ shop.default_city }}</p>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-sm font-semibold">Horário</p>
        <div v-if="openingHours.length" class="space-y-1">
          <p v-for="entry in openingHours" :key="entry.label" class="flex justify-between gap-3 text-sm">
            <span class="text-muted-foreground">{{ entry.label }}</span>
            <span class="text-right">{{ entry.hours }}</span>
          </p>
        </div>
        <p v-else class="text-sm text-muted-foreground">Consulte os horários de atendimento.</p>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-sm font-semibold">Links</p>
        <NuxtLink to="/menu" class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          Cardápio
        </NuxtLink>
        <NuxtLink to="/cart" class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          Carrinho
        </NuxtLink>
        <NuxtLink to="/account" class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          Conta e pedidos
        </NuxtLink>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-sm font-semibold">Contato</p>
        <NuxtLink
          v-if="shop?.maps_url && shop.full_address"
          :to="shop.maps_url"
          target="_blank"
          rel="noopener"
          class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {{ shop.full_address }}
        </NuxtLink>
        <p v-else-if="shop?.full_address" class="text-sm text-muted-foreground">{{ shop.full_address }}</p>
        <NuxtLink
          v-if="shop?.phone_url && shop.phone_display"
          :to="shop.phone_url"
          class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {{ shop.phone_display }}
        </NuxtLink>
        <NuxtLink
          v-if="shop?.email"
          :to="`mailto:${shop.email}`"
          class="block text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {{ shop.email }}
        </NuxtLink>
        <UiButton
          v-if="whatsappUrl"
          :href="whatsappUrl"
          target="_blank"
          rel="noopener"
          variant="outline"
          size="sm"
          icon="lucide:message-circle"
          class="mt-2"
        >
          Falar no WhatsApp
        </UiButton>
      </section>
    </div>

    <div class="border-t py-3 text-center text-xs text-muted-foreground">
      {{ year }} · {{ shop?.brand_name || 'Shopman' }}
    </div>
  </footer>
</template>
