<script setup lang="ts">
import type { AccountSummary, ReorderConflictProjection } from '~/types/shopman'
import {
  accountGreeting,
  accountNavCards,
  loyaltyView,
  reorderActionFrom
} from '~/presentation/account'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const session = useShopSession()
const { performAction, conflict, pending: reorderPending } = useReorder()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data: summary, pending } = await useFetch<AccountSummary>(apiPath('/api/v1/account/summary/'), {
  credentials: 'include',
  headers: requestHeaders
})

const greeting = computed(() => accountGreeting(summary.value?.customer_first_name || session.customerName.value))
const loyalty = computed(() => loyaltyView(summary.value?.loyalty))
const navCards = computed(() => accountNavCards(summary.value || null))
const lastOrder = computed(() => summary.value?.last_order || null)
const lastOrderReorder = computed(() => (lastOrder.value ? reorderActionFrom(lastOrder.value) : null))
const conflictRef = conflict as Ref<ReorderConflictProjection | null>

async function logout () {
  const csrfHeaders = useShopmanCsrfHeaders()
  await $fetch(apiPath('/api/auth/logout/'), {
    method: 'POST',
    headers: await csrfHeaders(),
    credentials: 'include'
  })
  session.reset()
  await navigateTo('/')
}

function dismissConflict () {
  conflict.value = null
}

useSeoMeta({ title: 'Conta' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-6">
      <div class="shop-container py-2.5">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta' }]" />
      </div>
    </div>
    <div class="shop-container space-y-6">
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <h1 class="truncate text-2xl font-semibold">{{ greeting }}</h1>
          <p class="mt-0.5 text-sm text-muted-foreground">
            <template v-if="pending">Carregando sua conta…</template>
            <template v-else>{{ formatCount(summary?.recent_order_count || 0, 'pedido recente', 'pedidos recentes') }}</template>
          </p>
        </div>
        <UiButton variant="ghost" size="sm" icon="lucide:log-out" @click="logout">Sair</UiButton>
      </header>

      <!-- Vitrine de fidelidade -->
      <section
        v-if="loyalty.available"
        class="overflow-hidden rounded-2xl border bg-card"
        aria-labelledby="loyalty-heading"
      >
        <div class="flex flex-wrap items-end justify-between gap-4 border-b px-5 py-4">
          <div class="min-w-0">
            <p id="loyalty-heading" class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {{ loyalty.tierDisplay || 'Programa de fidelidade' }}
            </p>
            <p class="mt-1 flex items-baseline gap-1.5">
              <span class="text-3xl font-semibold tabular-nums leading-none">{{ loyalty.pointsBalance }}</span>
              <span class="text-sm text-muted-foreground">pontos</span>
            </p>
          </div>
          <Icon name="lucide:sparkles" class="size-7 shrink-0 text-primary" />
        </div>

        <div v-if="loyalty.hasStamps" class="space-y-3 px-5 py-4">
          <div class="flex flex-wrap gap-2" role="img" :aria-label="`${loyalty.stampsCurrent} de ${loyalty.stampsTarget} selos`">
            <span
              v-for="slot in loyalty.slots"
              :key="slot.index"
              class="flex size-9 items-center justify-center rounded-full text-sm font-semibold transition-colors"
              :class="slot.filled
                ? 'bg-primary text-primary-foreground'
                : 'border-2 border-dashed border-muted-foreground/30 text-muted-foreground/50'"
            >
              <Icon v-if="slot.filled" name="lucide:check" class="size-4" />
              <span v-else class="tabular-nums">{{ slot.index }}</span>
            </span>
          </div>
          <p class="text-sm" :class="loyalty.cardComplete ? 'font-medium text-primary' : 'text-muted-foreground'">
            {{ loyalty.stampsLabel }}
          </p>
        </div>
      </section>

      <!-- Último pedido -->
      <section v-if="lastOrder" class="space-y-2">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Último pedido</h2>
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3">
          <div class="min-w-0">
            <p class="font-medium">{{ lastOrder.total_display }} · {{ lastOrder.status_label }}</p>
            <p class="text-sm text-muted-foreground">{{ lastOrder.created_at_display }}</p>
          </div>
          <div class="flex shrink-0 gap-2">
            <UiButton :to="orderTrackingRoute(lastOrder.ref)" variant="outline" size="sm" icon="lucide:radar">Acompanhar</UiButton>
            <UiButton
              v-if="lastOrderReorder"
              size="sm"
              icon="lucide:rotate-ccw"
              :loading="!!reorderPending[lastOrder.ref]"
              @click="performAction(lastOrderReorder)"
            >
              Refazer
            </UiButton>
          </div>
        </div>
      </section>

      <!-- Cartões de navegação -->
      <nav class="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label="Seções da conta">
        <NuxtLink
          v-for="card in navCards"
          :key="card.to"
          :to="card.to"
          class="group flex items-center gap-4 rounded-xl border bg-card px-4 py-4 transition-colors hover:border-primary/40 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
            <Icon :name="card.icon" class="size-5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2 font-medium">
              {{ card.label }}
              <UiBadge v-if="card.count" variant="secondary" size="sm" class="tabular-nums">{{ card.count }}</UiBadge>
            </span>
            <span class="block truncate text-sm text-muted-foreground">{{ card.description }}</span>
          </span>
          <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </NuxtLink>
      </nav>

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
