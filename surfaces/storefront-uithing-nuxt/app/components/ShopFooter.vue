<script setup lang="ts">
const session = useShopSession()

const shop = computed(() => session.shop.value)
const openingHours = computed(() => session.openingHours.value)
const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || shop.value?.whatsapp_url || '')
const fullAddressLines = computed(() => addressLines(shop.value?.full_address))
const year = new Date().getFullYear()
</script>

<template>
  <footer class="shop-footer shop-bottom-safe">
    <div class="shop-container grid gap-6 py-8 sm:grid-cols-2 lg:grid-cols-4">
      <section class="min-w-0 space-y-2">
        <p class="text-base font-semibold">{{ shop?.brand_name || 'Shopman' }}</p>
        <p class="text-sm leading-6 opacity-75">
          {{ shop?.description || shop?.tagline || 'Compra rápida e acompanhada.' }}
        </p>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide">Horário</p>
        <div v-if="openingHours.length" class="space-y-1">
          <p v-for="entry in openingHours" :key="entry.label" class="text-sm">
            <span class="opacity-75">{{ entry.label }}:</span>
            {{ entry.hours }}
          </p>
        </div>
        <p v-else class="text-sm opacity-75">Consulte os horários de atendimento.</p>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide">Links</p>
        <NuxtLink to="/menu" class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100">
          Cardápio
        </NuxtLink>
        <NuxtLink to="/sacola" class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100">
          Carrinho
        </NuxtLink>
        <NuxtLink to="/conta" class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100">
          Conta e pedidos
        </NuxtLink>
      </section>

      <section class="min-w-0 space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide">Contato</p>
        <NuxtLink
          v-if="shop?.maps_url && fullAddressLines.length"
          :to="shop.maps_url"
          target="_blank"
          rel="noopener"
          class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100"
        >
          <span v-for="line in fullAddressLines" :key="line" class="block">{{ line }}</span>
        </NuxtLink>
        <p v-else-if="fullAddressLines.length" class="text-sm opacity-75">
          <span v-for="line in fullAddressLines" :key="line" class="block">{{ line }}</span>
        </p>
        <NuxtLink
          v-if="shop?.phone_url && shop.phone_display"
          :to="shop.phone_url"
          class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100"
        >
          {{ shop.phone_display }}
        </NuxtLink>
        <NuxtLink
          v-if="shop?.email"
          :to="`mailto:${shop.email}`"
          class="block text-sm opacity-75 underline-offset-2 hover:underline hover:opacity-100"
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
          class="mt-2 border-current/40 bg-transparent text-current hover:bg-current/10 hover:text-current"
        >
          Falar no WhatsApp
        </UiButton>
      </section>
    </div>

    <div class="border-t border-current/15 py-3 text-center text-xs opacity-70">
      {{ year }} · {{ shop?.brand_name || 'Shopman' }}
    </div>
  </footer>
</template>
