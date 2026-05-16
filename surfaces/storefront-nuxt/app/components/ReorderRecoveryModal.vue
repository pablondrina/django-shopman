<script setup lang="ts">
const {
  skippedItems,
  rateLimitRecovery,
  pending,
  dismissSkippedItems,
  dismissRateLimitRecovery,
  retryRateLimitedReorder
} = useReorder()
const { shop } = useShopSession()

const skippedOpen = computed({
  get: () => skippedItems.value.length > 0,
  set: (open) => {
    if (!open) dismissSkippedItems()
  }
})

const rateLimitOpen = computed({
  get: () => !!rateLimitRecovery.value,
  set: (open) => {
    if (!open) dismissRateLimitRecovery()
  }
})

const supportUrl = computed(() => {
  const message = rateLimitRecovery.value
    ? 'Oi! Pode me ajudar a repetir um pedido?'
    : `Oi! Pode me ajudar com estes itens indisponíveis: ${skippedItems.value.map(item => item.name).join(', ')}?`
  return supportUrlWithMessage(shop.value?.whatsapp_url, message)
})

async function retryReorder () {
  await retryRateLimitedReorder().catch(() => {})
}
</script>

<template>
  <UModal v-model:open="skippedOpen" title="Pedido recriado com ajustes" :ui="{ content: 'max-w-lg' }">
    <template #body>
      <div class="grid gap-4">
        <UAlert
          color="info"
          variant="soft"
          icon="i-lucide-info"
          title="Alguns itens ficaram fora"
          description="O carrinho foi atualizado com o que está disponível agora."
        />

        <div class="rounded-lg border border-default p-4">
          <p class="text-xs font-semibold uppercase text-muted">Itens indisponíveis</p>
          <ul class="mt-3 grid gap-3 text-sm">
            <li
              v-for="item in skippedItems"
              :key="`${item.sku || item.name}-${item.reason}`"
              class="grid gap-1"
            >
              <span class="font-medium text-highlighted">{{ item.name }}</span>
              <span class="text-muted">{{ item.reason }}</span>
            </li>
          </ul>
        </div>

        <div class="grid gap-2 sm:grid-cols-2">
          <UButton to="/cart" label="Ver carrinho" icon="i-lucide-shopping-bag" block @click="dismissSkippedItems" />
          <UButton
            v-if="supportUrl"
            :to="supportUrl"
            target="_blank"
            rel="noopener"
            color="success"
            variant="soft"
            label="Falar com a equipe"
            icon="i-lucide-message-circle"
            block
          />
          <UButton color="neutral" variant="ghost" label="Fechar" block @click="dismissSkippedItems" />
        </div>
      </div>
    </template>
  </UModal>

  <UModal v-model:open="rateLimitOpen" title="Aguarde um instante" :ui="{ content: 'max-w-md' }">
    <template #body>
      <div class="grid gap-4">
        <UAlert
          color="info"
          variant="soft"
          icon="i-lucide-clock"
          title="Muitas tentativas de recompra"
          :description="retryAfterDescription(
            rateLimitRecovery?.detail,
            rateLimitRecovery?.retryAfterSeconds,
            operationalCopy.recovery.reorderRateLimit
          )"
        />

        <div class="grid gap-2 sm:grid-cols-2">
          <UButton
            color="primary"
            variant="solid"
            block
            icon="i-lucide-refresh-cw"
            label="Tentar novamente"
            :loading="pending"
            @click="retryReorder"
          />
          <UButton
            v-if="supportUrl"
            :to="supportUrl"
            target="_blank"
            rel="noopener"
            color="success"
            variant="soft"
            label="Falar com a equipe"
            icon="i-lucide-message-circle"
            block
          />
          <UButton color="neutral" variant="ghost" label="Fechar" block @click="dismissRateLimitRecovery" />
        </div>
      </div>
    </template>
  </UModal>
</template>
