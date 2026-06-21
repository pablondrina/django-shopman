<script setup lang="ts">
import type { OrderHistoryItem, ReorderConflictProjection } from '~/types/shopman'
import { ORDER_FILTER_OPTIONS, orderStatusAccentClass, orderStatusDotClass, ordersEmptyCopy, reorderActionFrom } from '~/presentation/account'

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
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Pedidos' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="shop-title">Pedidos</h1>
          <p class="shop-muted">
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

      <ul v-else class="shop-stack-block">
        <li
          v-for="order in orders || []"
          :key="order.ref"
          class="flex flex-col gap-3 rounded-lg border border-l-2 bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          :class="orderStatusAccentClass(order.status_tone)"
        >
          <div class="min-w-0">
            <p class="flex items-center gap-2 font-semibold">
              <span class="size-2 shrink-0 rounded-full" :class="orderStatusDotClass(order.status_tone)" aria-hidden="true" />
              {{ order.status_label }}
              <span v-if="order.total_display" class="text-muted-foreground">· {{ order.total_display }}</span>
            </p>
            <p class="mt-0.5 truncate shop-muted">{{ order.ref }} · {{ order.created_at_display }}</p>
          </div>
          <div class="flex shrink-0 gap-2">
            <UiButton :to="orderTrackingRoute(order.ref)" variant="outline" size="sm" icon="lucide:radar">Acompanhar</UiButton>
            <UiButton
              v-if="reorderActionFrom(order)"
              size="sm"
              icon="lucide:rotate-ccw"
              :loading="!!reorderPending[order.ref]"
              @click="performAction(reorderActionFrom(order)!)"
            >
              Refazer
            </UiButton>
          </div>
        </li>
      </ul>

      <UiAlertDialog :open="!!conflictRef" @update:open="open => { if (!open) dismissConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflictRef?.copy.title.title || 'Sacola já tem itens' }}</UiAlertDialogTitle>
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
