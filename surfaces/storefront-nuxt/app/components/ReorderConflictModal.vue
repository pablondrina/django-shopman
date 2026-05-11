<script setup lang="ts">
const { conflict, resolveConflict, dismissConflict, pending } = useReorder()

const open = computed({
  get: () => !!conflict.value,
  set: (val) => { if (!val) dismissConflict() }
})
</script>

<template>
  <UModal v-model:open="open" title="Carrinho não está vazio" :ui="{ content: 'max-w-lg' }">
    <template #body>
      <div class="grid gap-4">
        <p class="text-sm text-muted leading-relaxed">
          Você ainda tem itens no carrinho. Como prefere continuar?
        </p>

        <UCard variant="subtle" :ui="{ body: 'p-4' }">
          <p class="text-xs uppercase tracking-wide font-semibold text-muted mb-2">
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
        </UCard>

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
            label="Substituir o carrinho"
            @click="resolveConflict('replace')"
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
