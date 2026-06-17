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

const mediaClass = computed(() => {
  if (props.state === 'done') return 'bg-primary text-primary-foreground'
  if (props.state === 'current') return 'bg-primary text-primary-foreground'
  if (props.state === 'error') return 'bg-destructive text-destructive-foreground'
  if (props.state === 'blocked') return 'bg-warning text-warning-foreground'
  return 'border border-border text-muted-foreground'
})

const titleClass = computed(() => props.state === 'upcoming' ? 'text-muted-foreground' : 'text-foreground')
</script>

<template>
  <!-- Editorial: seções separadas por hairline ponta-a-ponta no fundo da
       página (sem card branco/sombra), conteúdo alinhado sob o título. O
       hyper-focus continua: só a etapa atual expande; as outras viram resumo. -->
  <section
    class="-mx-4 border-t px-4 py-4 first:border-t-0 sm:mx-0 sm:px-0"
    data-checkout-section
    :data-checkout-section-state="state"
  >
    <div
      class="flex items-start gap-3"
      :aria-current="state === 'current' ? 'step' : undefined"
    >
      <span
        class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full transition-colors"
        :class="mediaClass"
      >
        <Icon :name="stateIcon" class="size-4" />
        <span class="sr-only">{{ stateLabel }}</span>
      </span>
      <div class="min-w-0 flex-1">
        <p class="shop-item-title font-semibold" :class="titleClass">{{ title }}</p>
        <p class="mt-0.5 line-clamp-3 whitespace-pre-line shop-muted">
          {{ summary || 'Complete esta etapa para continuar' }}
        </p>
      </div>
      <UiButton
        v-if="state === 'done' && editable"
        size="sm"
        variant="ghost"
        icon="lucide:pencil"
        class="-mr-2 min-h-10 shrink-0 text-muted-foreground hover:text-foreground"
        @click="$emit('edit')"
      >
        Editar
      </UiButton>
    </div>

    <template v-if="isExpanded">
      <div class="mt-4 sm:pl-10" :class="bodyClass">
        <slot />
      </div>
      <slot name="footer" />
    </template>
  </section>
</template>
