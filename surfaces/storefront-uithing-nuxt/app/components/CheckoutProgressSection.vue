<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

type SectionState = 'done' | 'current' | 'upcoming' | 'blocked' | 'error'

const props = withDefaults(defineProps<{
  title: string
  summary?: string
  state: SectionState
  icon?: string
  editable?: boolean
  bodyClass?: HTMLAttributes['class']
}>(), {
  summary: '',
  icon: 'lucide:circle',
  editable: true,
  bodyClass: ''
})

defineEmits<{
  edit: []
}>()

const isExpanded = computed(() => props.state === 'current' || props.state === 'blocked' || props.state === 'error')

const stateIcon = computed(() => {
  if (props.state === 'done') return 'lucide:check'
  if (props.state === 'current') return 'lucide:circle-dot'
  if (props.state === 'blocked') return 'lucide:lock'
  if (props.state === 'error') return 'lucide:triangle-alert'
  return props.icon
})

const stateLabel = computed(() => {
  if (props.state === 'done') return 'Feito'
  if (props.state === 'current') return 'Agora'
  if (props.state === 'blocked') return 'Bloqueado'
  if (props.state === 'error') return 'Revisar'
  return 'Depois'
})

const cardClass = computed(() => {
  if (props.state === 'current') return 'border-primary/60 shadow-sm'
  if (props.state === 'error') return 'border-destructive/60 shadow-sm'
  if (props.state === 'blocked') return 'border-warning/60 shadow-sm'
  if (props.state === 'upcoming') return 'opacity-70'
  return ''
})

const mediaClass = computed(() => {
  if (props.state === 'done') return 'bg-primary text-primary-foreground'
  if (props.state === 'current') return 'bg-primary text-primary-foreground'
  if (props.state === 'error') return 'bg-destructive text-destructive-foreground'
  if (props.state === 'blocked') return 'bg-warning text-warning-foreground'
  return ''
})

const badgeVariant = computed(() => {
  if (props.state === 'error') return 'destructive'
  if (props.state === 'blocked') return 'warning'
  if (props.state === 'done') return 'secondary'
  if (props.state === 'current') return 'default'
  return 'outline'
})
</script>

<template>
  <UiCard
    class="gap-0 overflow-hidden py-0 transition-colors"
    :class="cardClass"
    data-checkout-section
    :data-checkout-section-state="state"
  >
    <div
      class="flex items-start gap-3 p-4 sm:p-5"
      :aria-current="state === 'current' ? 'step' : undefined"
    >
      <UiItemMedia
        variant="icon"
        class="size-8 rounded-full"
        :class="mediaClass"
      >
        <Icon :name="stateIcon" />
      </UiItemMedia>
      <div class="min-w-0 flex-1">
        <div class="flex min-w-0 items-center gap-2">
          <p class="truncate text-sm font-semibold">{{ title }}</p>
          <UiBadge class="hidden sm:inline-flex" :variant="badgeVariant">
            {{ stateLabel }}
          </UiBadge>
        </div>
        <p class="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
          {{ summary || 'Complete esta etapa para continuar' }}
        </p>
      </div>
      <UiButton
        v-if="state === 'done' && editable"
        size="sm"
        variant="ghost"
        icon="lucide:pencil"
        @click="$emit('edit')"
      >
        Editar
      </UiButton>
    </div>

    <template v-if="isExpanded">
      <UiSeparator />
      <div class="p-4 sm:p-5" :class="bodyClass">
        <slot />
      </div>
      <slot name="footer" />
    </template>
  </UiCard>
</template>
