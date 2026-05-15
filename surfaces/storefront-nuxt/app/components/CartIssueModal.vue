<script setup lang="ts">
const {
  stockIssue,
  rateLimitRecovery,
  lastCartCommand,
  dismissStockIssue,
  dismissRateLimitRecovery,
  retryLastCartCommand,
  acceptStockIssueAvailable
} = useCartState()
const { shop } = useShopSession()

const stockOpen = computed({
  get: () => !!stockIssue.value,
  set: (open) => {
    if (!open) dismissStockIssue()
  }
})

const rateLimitOpen = computed({
  get: () => !!rateLimitRecovery.value,
  set: (open) => {
    if (!open) dismissRateLimitRecovery()
  }
})

const canAcceptAvailable = computed(() =>
  !!lastCartCommand.value &&
  typeof stockIssue.value?.available_qty === 'number' &&
  stockIssue.value.available_qty >= 0
)

const stockSupportUrl = computed(() => supportUrl(
  stockIssue.value?.sku
    ? `Oi! Pode me ajudar com o estoque do item ${stockIssue.value.name} (${stockIssue.value.sku})?`
    : 'Oi! Pode me ajudar com o estoque do meu carrinho?'
))

const rateLimitSupportUrl = computed(() => supportUrl('Oi! Pode me ajudar a finalizar meu carrinho?'))

function supportUrl (message: string) {
  return supportUrlWithMessage(shop.value?.whatsapp_url, message)
}

function substituteName (substitute: any) {
  if (typeof substitute === 'string') return substitute
  return substitute?.name || substitute?.sku || 'Alternativa'
}

function substituteReason (substitute: any) {
  if (typeof substitute === 'string') return ''
  return substitute?.reason || ''
}

async function retryCartCommand () {
  await retryLastCartCommand().catch(() => {})
}

async function acceptAvailableQty () {
  await acceptStockIssueAvailable().catch(() => {})
}
</script>

<template>
  <UModal v-model:open="stockOpen" title="Estoque do carrinho" :ui="{ content: 'max-w-lg' }">
    <template #body>
      <div v-if="stockIssue" class="grid gap-4">
        <UAlert
          color="warning"
          variant="soft"
          icon="i-lucide-package-x"
          :title="stockIssue.title"
          :description="stockIssue.detail"
        />

        <div class="rounded-lg border border-default p-4">
          <p class="text-xs font-semibold uppercase text-muted">Itens afetados</p>
          <ul class="mt-3 grid gap-3">
            <li
              v-for="item in stockIssue.items"
              :key="`${item.sku}-${item.requested_qty}-${item.available_qty}`"
              class="grid gap-1 text-sm"
            >
              <div class="flex items-start justify-between gap-3">
                <span class="font-medium text-highlighted">{{ item.name }}</span>
                <span v-if="item.requested_qty != null" class="shrink-0 tabular-nums text-muted">
                  Pedido: {{ item.requested_qty }}
                </span>
              </div>
              <p class="leading-relaxed text-muted">{{ item.reason }}</p>
              <p v-if="item.available_qty != null" class="text-xs text-muted">
                Disponível para este pedido: {{ item.available_qty }}
              </p>
            </li>
          </ul>
        </div>

        <div v-if="stockIssue.substitutes.length" class="rounded-lg border border-default p-4">
          <p class="text-xs font-semibold uppercase text-muted">Alternativas sugeridas</p>
          <ul class="mt-3 grid gap-2 text-sm">
            <li
              v-for="substitute in stockIssue.substitutes"
              :key="substituteName(substitute)"
              class="flex items-baseline justify-between gap-3"
            >
              <span class="font-medium text-highlighted">{{ substituteName(substitute) }}</span>
              <span v-if="substituteReason(substitute)" class="text-xs text-muted">{{ substituteReason(substitute) }}</span>
            </li>
          </ul>
        </div>

        <div class="grid gap-2 sm:grid-cols-2">
          <UButton
            v-if="canAcceptAvailable"
            color="warning"
            variant="solid"
            block
            icon="i-lucide-check"
            :label="`Usar ${stockIssue.available_qty} disponível(is)`"
            @click="acceptAvailableQty"
          />
          <UButton
            color="neutral"
            variant="outline"
            block
            icon="i-lucide-refresh-cw"
            label="Tentar novamente"
            @click="retryCartCommand"
          />
          <UButton
            v-if="stockSupportUrl"
            color="success"
            variant="soft"
            block
            icon="i-lucide-message-circle"
            label="Falar com a casa"
            :to="stockSupportUrl"
            target="_blank"
            rel="noopener"
          />
          <UButton
            color="neutral"
            variant="ghost"
            block
            label="Fechar"
            @click="dismissStockIssue"
          />
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
          title="Muitas alterações em sequência"
          :description="retryAfterDescription(
            rateLimitRecovery?.detail,
            rateLimitRecovery?.retryAfterSeconds,
            operationalCopy.recovery.cartRateLimit
          )"
        />

        <div class="grid gap-2 sm:grid-cols-2">
          <UButton
            color="primary"
            variant="solid"
            block
            icon="i-lucide-refresh-cw"
            label="Tentar novamente"
            @click="retryCartCommand"
          />
          <UButton
            v-if="rateLimitSupportUrl"
            color="success"
            variant="soft"
            block
            icon="i-lucide-message-circle"
            label="Falar com a casa"
            :to="rateLimitSupportUrl"
            target="_blank"
            rel="noopener"
          />
          <UButton
            color="neutral"
            variant="ghost"
            block
            label="Fechar"
            @click="dismissRateLimitRecovery"
          />
        </div>
      </div>
    </template>
  </UModal>
</template>
