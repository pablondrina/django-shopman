<script setup lang="ts">
import type { DayClosingResponse } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const toast = useToast()
const { data, pending, error, refresh } = await useFetch<DayClosingResponse>(
  () => apiPath('/api/v1/backstage/closing/'),
  { credentials: 'include' }
)

const closing = computed(() => data.value?.closing)
const submitting = ref(false)

const groupedItems = computed(() => {
  const items = closing.value?.items || []
  return {
    d1: items.filter(i => i.classification === 'd1'),
    loss: items.filter(i => i.classification === 'loss'),
    neutral: items.filter(i => i.classification === 'neutral')
  }
})

function csrfHeader (): Record<string, string> {
  const token = useCookie('csrftoken').value || ''
  return token ? { 'X-CSRFToken': token } : {}
}

async function finalize () {
  if (!closing.value) return
  if (!confirm(`Confirma o fechamento do dia ${closing.value.today_display}? Esta ação é irreversível.`)) return
  submitting.value = true
  try {
    const quantities: Record<string, string> = {}
    for (const item of closing.value.items) {
      quantities[item.sku] = String(item.qty_available)
    }
    await $fetch(apiPath('/api/v1/backstage/closing/'), {
      method: 'POST',
      credentials: 'include',
      headers: csrfHeader(),
      body: { quantities }
    })
    toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Dia fechado com sucesso' })
    await refresh()
  } catch (e: any) {
    toast.add({ icon: 'i-lucide-circle-x', color: 'error', title: 'Falha no fechamento', description: e?.data?.detail || '' })
  } finally {
    submitting.value = false
  }
}

useHead({ title: 'Fechamento do dia' })
</script>

<template>
  <UDashboardPanel id="fechamento">
    <template #header>
      <UDashboardNavbar title="Fechamento do dia" icon="i-lucide-archive">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UBadge color="neutral" variant="subtle">
            {{ closing?.today_display }}
          </UBadge>
          <UBadge v-if="closing?.already_closed" color="success" variant="subtle">Fechado</UBadge>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UContainer class="py-4">
        <USkeleton v-if="pending" class="h-40 w-full" />

        <UAlert v-else-if="error" color="error" variant="soft" title="Não foi possível carregar o fechamento" />

        <div v-else-if="closing">
          <UAlert v-if="closing.already_closed" icon="i-lucide-circle-check" color="success" variant="subtle" title="Já fechado" :description="closing.existing_closing_display" class="mb-3" />
          <UAlert v-if="closing.has_old_d1" icon="i-lucide-triangle-alert" color="warning" variant="subtle" title="Atenção: D-1 antigo" description="Há estoque marcado como D-1 com mais de 1 dia. Resolva antes de fechar." class="mb-3" />
          <UAlert v-if="closing.reconciliation_errors.length" icon="i-lucide-circle-x" color="error" variant="subtle" title="Discrepâncias detectadas" :description="`${closing.reconciliation_errors.length} SKU(s) com déficit. Revise estoque vs vendas.`" class="mb-3" />

          <div class="grid lg:grid-cols-3 gap-4">
            <UCard v-for="(items, key) in groupedItems" :key="key">
              <template #header>
                <div class="flex items-center justify-between">
                  <strong>{{ key === 'd1' ? 'D-1 (vai pra "ontem")' : key === 'loss' ? 'Perdas' : 'Neutros' }}</strong>
                  <UBadge :color="key === 'd1' ? 'warning' : key === 'loss' ? 'error' : 'neutral'" variant="subtle">{{ items.length }}</UBadge>
                </div>
              </template>
              <UEmpty v-if="!items.length" icon="i-lucide-circle-dashed" title="Nenhum item" />
              <ul v-else class="grid gap-2">
                <li v-for="item in items" :key="item.sku" class="flex items-center justify-between gap-2">
                  <div class="min-w-0">
                    <p class="font-mono text-sm text-muted">{{ item.sku }}</p>
                    <p class="font-semibold text-highlighted truncate">{{ item.name }}</p>
                  </div>
                  <span class="font-bold tabular-nums shrink-0">{{ item.qty_available }}</span>
                </li>
              </ul>
            </UCard>
          </div>

          <UCard v-if="!closing.already_closed" class="mt-4">
            <template #header><strong>Confirmar fechamento</strong></template>
            <p class="text-sm text-muted">
              Total disponível para classificação: <strong class="text-highlighted tabular-nums">{{ closing.total_available }}</strong> unidade(s).
            </p>
            <template #footer>
              <UButton block size="lg" color="primary" icon="i-lucide-archive" label="Fechar o dia" :loading="submitting" :disabled="closing.has_old_d1 || closing.reconciliation_errors.length > 0" @click="finalize" />
            </template>
          </UCard>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
