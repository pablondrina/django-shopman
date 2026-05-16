<script setup lang="ts">
import type { ViewMode } from '~/composables/useViewMode'

const model = defineModel<ViewMode>({ required: true })
</script>

<template>
  <UFieldGroup size="sm">
    <UTooltip text="Grade">
      <UButton
        :color="model === 'grid' ? 'primary' : 'neutral'"
        :variant="model === 'grid' ? 'soft' : 'ghost'"
        icon="i-lucide-layout-grid"
        aria-label="Visualizar em grade"
        @click="model = 'grid'"
      />
    </UTooltip>
    <UTooltip text="Lista">
      <UButton
        :color="model === 'list' ? 'primary' : 'neutral'"
        :variant="model === 'list' ? 'soft' : 'ghost'"
        icon="i-lucide-list"
        aria-label="Visualizar em lista"
        @click="model = 'list'"
      />
    </UTooltip>
  </UFieldGroup>
</template>
