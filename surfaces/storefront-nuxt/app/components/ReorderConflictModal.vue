<script setup lang="ts">
const { conflict, resolveConflict, dismissConflict, pending } = useReorder()
const replaceAcknowledged = ref(false)

const open = computed({
  get: () => !!conflict.value,
  set: (val) => { if (!val) dismissConflict() }
})

const copy = computed(() => conflict.value?.copy || null)
const modalTitle = computed(() => copy.value?.title.title || '')
const modalMessage = computed(() => copy.value?.message.message || '')
const currentCartLabel = computed(() => copy.value?.current_cart_label.title || '')
const previousOrderLabel = computed(() => copy.value?.previous_order_label.title || '')
const appendHelp = computed(() => copy.value?.append_help.message || '')
const replaceHelp = computed(() => copy.value?.replace_help.message || '')
const replaceAckLabel = computed(() => copy.value?.replace_ack_label.message || '')
const cancelLabel = computed(() => copy.value?.cancel_label.title || '')
const currentCartItems = computed(() => conflict.value?.cart.items || [])
const hasCurrentCart = computed(() => currentCartItems.value.length > 0)
const appendAction = computed(() => conflict.value?.actions.find(action => action.ref === 'reorder_append' && action.enabled !== false) || null)
const replaceAction = computed(() => conflict.value?.actions.find(action => action.ref === 'reorder_replace' && action.enabled !== false) || null)

watch(open, (value) => {
  if (!value) replaceAcknowledged.value = false
})

async function replaceCart () {
  if (!replaceAcknowledged.value) return
  await resolveConflict('replace')
}
</script>

<template>
  <UModal v-model:open="open" :title="modalTitle" :ui="{ content: 'max-w-lg' }">
    <template #body>
      <div class="grid gap-4">
        <p class="text-sm text-muted leading-relaxed">
          {{ modalMessage }}
        </p>

        <div v-if="hasCurrentCart" class="rounded-lg border border-warning/30 bg-warning/10 p-3">
          <p class="mb-2 text-sm font-medium text-highlighted">
            {{ currentCartLabel }}
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

        <div class="rounded-lg border border-default p-3">
          <p class="mb-2 text-sm font-medium text-highlighted">
            {{ previousOrderLabel }} {{ conflict?.order_ref }}
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

        <div class="grid gap-2">
          <UButton
            color="primary"
            variant="solid"
            size="lg"
            block
            icon="i-lucide-plus-circle"
            :loading="pending"
            :disabled="!appendAction"
            :label="appendAction?.label"
            @click="resolveConflict('append')"
          />
          <p v-if="appendHelp" class="text-xs leading-relaxed text-muted">
            {{ appendHelp }}
          </p>
        </div>

        <div class="grid gap-2">
          <p v-if="replaceHelp" class="text-xs leading-relaxed text-muted">
            {{ replaceHelp }}
          </p>
          <UCheckbox
            v-model="replaceAcknowledged"
            :label="replaceAckLabel"
          />
          <UButton
            color="error"
            variant="outline"
            size="lg"
            block
            icon="i-lucide-rotate-ccw"
            :loading="pending"
            :disabled="!replaceAction || !replaceAcknowledged"
            :label="replaceAction?.label"
            @click="replaceCart"
          />
        </div>

        <UButton
          color="neutral"
          variant="ghost"
          size="sm"
          block
          :label="cancelLabel"
          @click="dismissConflict"
        />
      </div>
    </template>
  </UModal>
</template>
