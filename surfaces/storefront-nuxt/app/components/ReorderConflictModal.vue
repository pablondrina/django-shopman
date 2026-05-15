<script setup lang="ts">
const { conflict, resolveConflict, dismissConflict, pending } = useReorder()
const { cart } = useCartState()
const replaceAcknowledged = ref(false)

const open = computed({
  get: () => !!conflict.value,
  set: (val) => { if (!val) dismissConflict() }
})

const currentCartItems = computed(() => cart.value.items || [])
const hasCurrentCart = computed(() => currentCartItems.value.length > 0)

watch(open, (value) => {
  if (!value) replaceAcknowledged.value = false
})

async function replaceCart () {
  if (!replaceAcknowledged.value) return
  await resolveConflict('replace')
}
</script>

<template>
  <UModal v-model:open="open" title="Carrinho não está vazio" :ui="{ content: 'max-w-lg' }">
    <template #body>
      <div class="grid gap-4">
        <p class="text-sm text-muted leading-relaxed">
          Você ainda tem itens no carrinho. Como prefere continuar?
        </p>

        <div v-if="hasCurrentCart" class="rounded-lg border border-warning/30 bg-warning/10 p-4">
          <p class="text-xs uppercase font-semibold text-warning mb-2">
            Carrinho atual
          </p>
          <ul class="grid gap-1.5 text-sm">
            <li
              v-for="item in currentCartItems"
              :key="item.line_id"
              class="flex items-baseline gap-2"
            >
              <span class="text-muted tabular-nums w-8">{{ item.qty }}×</span>
              <span class="flex-1 truncate">{{ item.name }}</span>
              <span class="text-muted whitespace-nowrap">{{ item.total_display }}</span>
            </li>
          </ul>
        </div>

        <div class="rounded-lg border border-default p-4">
          <p class="text-xs uppercase font-semibold text-muted mb-2">
            Itens do pedido {{ conflict?.orderRef }}
          </p>
          <ul class="grid gap-1.5 text-sm">
            <li
              v-for="item in conflict?.items || []"
              :key="item.sku"
              class="flex items-baseline gap-2"
            >
              <span class="text-muted tabular-nums w-8">{{ item.qty }}×</span>
              <span class="flex-1 truncate">{{ item.name }}</span>
            </li>
          </ul>
        </div>

        <UCheckbox
          v-model="replaceAcknowledged"
          label="Entendo que substituir o carrinho remove os itens atuais antes de recriar este pedido."
        />

        <div class="grid sm:grid-cols-2 gap-3 mt-2">
          <UButton
            color="neutral"
            variant="outline"
            size="lg"
            block
            icon="i-lucide-plus-circle"
            :loading="pending"
            label="Adicionar ao carrinho atual"
            @click="resolveConflict('append')"
          />
          <UButton
            color="warning"
            variant="solid"
            size="lg"
            block
            icon="i-lucide-rotate-ccw"
            :loading="pending"
            :disabled="!replaceAcknowledged"
            label="Substituir o carrinho"
            @click="replaceCart"
          />
        </div>

        <UButton
          color="neutral"
          variant="ghost"
          size="sm"
          block
          label="Cancelar"
          @click="dismissConflict"
        />
      </div>
    </template>
  </UModal>
</template>
