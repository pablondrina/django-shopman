<script setup lang="ts">
import type { ProductionKDSResponse } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const toast = useToast()
const { data, pending, error, refresh } = await useFetch<ProductionKDSResponse>(
  () => apiPath('/api/v1/backstage/production/kds/'),
  { credentials: 'include' }
)

const kds = computed(() => data.value?.kds)
const actingId = ref<number | null>(null)

function csrfHeader (): Record<string, string> {
  const token = useCookie('csrftoken').value || ''
  return token ? { 'X-CSRFToken': token } : {}
}

async function advanceStep (woId: number) {
  actingId.value = woId
  try {
    await $fetch(apiPath(`/api/v1/backstage/production/${woId}/advance-step/`), {
      method: 'POST',
      credentials: 'include',
      headers: csrfHeader()
    })
    toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Passo avançado' })
    await refresh()
  } catch (e: any) {
    toast.add({ icon: 'i-lucide-circle-x', color: 'error', title: 'Falha ao avançar passo', description: e?.data?.detail || '' })
  } finally {
    actingId.value = null
  }
}

async function voidWorkOrder (woId: number) {
  if (!confirm('Estornar esta work order? Esta ação não pode ser desfeita.')) return
  actingId.value = woId
  try {
    await $fetch(apiPath(`/api/v1/backstage/production/${woId}/void/`), {
      method: 'POST',
      credentials: 'include',
      headers: csrfHeader(),
      body: { reason: 'Estornado pelo operador' }
    })
    toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Work order estornada' })
    await refresh()
  } catch (e: any) {
    toast.add({ icon: 'i-lucide-circle-x', color: 'error', title: 'Falha ao estornar', description: e?.data?.detail || '' })
  } finally {
    actingId.value = null
  }
}

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  onMounted(() => { pollTimer = setInterval(() => refresh(), 15_000) })
  onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
}

useHead({ title: 'KDS Produção' })
</script>

<template>
  <UDashboardPanel id="producao-kds">
    <template #header>
      <UDashboardNavbar title="KDS · Produção" icon="i-lucide-flame">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UButton to="/producao" icon="i-lucide-arrow-left" color="neutral" variant="ghost" size="sm" label="Board" />
          <UBadge color="success" variant="subtle" class="gap-1.5">
            <span class="size-1.5 rounded-full bg-success animate-pulse" />
            Ao vivo
          </UBadge>
          <UTooltip text="Atualizar">
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              size="sm"
              aria-label="Atualizar"
              :loading="pending"
              @click="refresh()"
            />
          </UTooltip>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UContainer class="py-4">
        <USkeleton v-if="pending" class="h-40 w-full" />

        <UAlert
          v-else-if="error"
          color="error"
          variant="soft"
          title="Não foi possível carregar o KDS de produção"
        />

        <div v-else-if="kds">
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <UBadge color="neutral" variant="subtle" size="lg" class="tabular-nums">Total · {{ kds.total_count }}</UBadge>
            <UBadge :color="kds.late_count > 0 ? 'error' : 'success'" variant="subtle" size="lg" class="tabular-nums">Atrasados · {{ kds.late_count }}</UBadge>
          </div>

          <UEmpty v-if="!kds.cards.length" icon="i-lucide-coffee" title="Sem produção em andamento" description="Inicie uma work order pela tela de produção." />

          <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <UCard
              v-for="card in kds.cards"
              :key="card.pk"
              :class="[card.timer_class === 'timer-late' && 'ring-2 ring-error', card.timer_class === 'timer-warning' && 'ring-1 ring-warning']"
            >
              <template #header>
                <div class="flex items-center justify-between gap-2">
                  <p class="font-mono text-sm text-muted">{{ card.ref }}</p>
                  <ProductionElapsedBadge :elapsed-seconds="card.elapsed_seconds" :timer-class="card.timer_class" />
                </div>
              </template>
              <p class="font-semibold text-highlighted">{{ card.recipe_name }}</p>
              <p class="text-sm text-muted mt-1">SKU: <span class="font-mono">{{ card.output_sku }}</span></p>
              <p class="text-sm text-muted mt-1">{{ card.position_display }}</p>
              <dl class="grid gap-1 text-sm mt-3">
                <div class="flex justify-between">
                  <dt class="text-muted">Quantidade</dt>
                  <dd class="font-semibold tabular-nums">{{ card.quantity_display }}</dd>
                </div>
              </dl>
              <template #footer>
                <div class="flex gap-2">
                  <UButton color="primary" icon="i-lucide-circle-check" :label="card.next_step_label || 'Avançar'" size="md" class="flex-1" :loading="actingId === card.pk" @click="advanceStep(card.pk)" />
                  <UButton color="error" variant="ghost" icon="i-lucide-x" size="md" aria-label="Estornar" :disabled="actingId === card.pk" @click="voidWorkOrder(card.pk)" />
                </div>
              </template>
            </UCard>
          </div>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
