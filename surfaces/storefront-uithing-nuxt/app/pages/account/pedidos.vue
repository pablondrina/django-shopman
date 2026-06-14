<script setup lang="ts">
import type { OrderHistoryItem, ReorderConflictProjection } from '~/types/shopman'
import { ORDER_FILTER_OPTIONS, ordersEmptyCopy, reorderActionFrom } from '~/presentation/account'

definePageMeta({ middleware: 'account' })

type OrderFilter = 'todos' | 'ativos' | 'anteriores'

const apiPath = useShopmanApiPath()
const { performAction, conflict, pending: reorderPending } = useReorder()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const orderFilter = ref<OrderFilter>('todos')

const { data: orders, pending } = await useFetch<OrderHistoryItem[]>(apiPath('/api/v1/account/orders/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: computed(() => ({ filter: orderFilter.value }))
})

const emptyCopy = computed(() => ordersEmptyCopy(orderFilter.value))
const conflictRef = conflict as Ref<ReorderConflictProjection | null>

function dismissConflict () {
  conflict.value = null
}

useSeoMeta({ title: 'Pedidos' })
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/account' }, { label: 'Pedidos' }]" />

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-2xl font-semibold">Pedidos</h1>
          <p class="text-sm text-muted-foreground">
            {{ pending ? 'Carregando…' : formatCount(orders?.length || 0, 'pedido', 'pedidos') }}
          </p>
        </div>
        <UiSelect v-model="orderFilter">
          <UiSelectTrigger class="w-44" />
          <UiSelectContent>
            <UiSelectItem v-for="option in ORDER_FILTER_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </UiSelectItem>
          </UiSelectContent>
        </UiSelect>
      </div>

      <UiSkeleton v-if="pending" class="h-32 rounded-lg" />

      <UiEmpty v-else-if="!(orders || []).length" class="border">
        <UiEmptyMedia variant="icon">
          <Icon name="lucide:receipt" />
        </UiEmptyMedia>
        <UiEmptyHeader>
          <UiEmptyTitle>{{ emptyCopy.title }}</UiEmptyTitle>
          <UiEmptyDescription>{{ emptyCopy.message }}</UiEmptyDescription>
        </UiEmptyHeader>
        <div class="flex justify-center">
          <UiButton to="/menu" icon="lucide:utensils">Ver o cardápio</UiButton>
        </div>
      </UiEmpty>

      <UiItemGroup v-else class="gap-3">
        <UiItem v-for="order in orders || []" :key="order.ref" variant="outline" class="bg-card">
          <UiItemContent>
            <UiItemTitle>{{ order.ref }}</UiItemTitle>
            <UiItemDescription>{{ order.status_label }} · {{ order.created_at_display }}</UiItemDescription>
          </UiItemContent>
          <UiItemActions class="flex gap-2">
            <UiButton :to="orderTrackingRoute(order.ref)" variant="outline" size="sm">Acompanhar</UiButton>
            <UiButton
              v-if="reorderActionFrom(order)"
              size="sm"
              :loading="!!reorderPending[order.ref]"
              @click="performAction(reorderActionFrom(order)!)"
            >
              Refazer
            </UiButton>
          </UiItemActions>
        </UiItem>
      </UiItemGroup>

      <UiAlertDialog :open="!!conflictRef" @update:open="open => { if (!open) dismissConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflictRef?.copy.title.title || 'Carrinho já tem itens' }}</UiAlertDialogTitle>
            <UiAlertDialogDescription>{{ conflictRef?.copy.message.message || conflictRef?.detail }}</UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel>Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction v-if="conflictRef" @click="performAction(conflictRef.actions.find(action => action.ref.includes('replace')) || conflictRef.actions[0])">
              Substituir
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
