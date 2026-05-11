<script setup lang="ts">
const props = defineProps<{
  step: string
  title: string
  description?: string
  active: boolean
  done: boolean
  summary?: string
  icon?: string
  index: number
}>()

const emit = defineEmits<{
  open: [string]
  edit: [string]
}>()
</script>

<template>
  <UCard
    :class="[
      active && 'ring-1 ring-primary',
      !active && !done && 'opacity-60'
    ]"
  >
    <button
      type="button"
      class="w-full flex items-center gap-3 text-left"
      :disabled="!done && active"
      @click="active ? null : (done ? emit('edit', step) : emit('open', step))"
    >
      <span
        class="flex size-10 shrink-0 items-center justify-center rounded-full font-semibold tabular-nums text-sm"
        :class="done
          ? 'bg-success/10 text-success'
          : active
            ? 'bg-primary/10 text-primary'
            : 'bg-elevated text-muted'"
      >
        <UIcon v-if="done" name="i-lucide-check" class="size-4" />
        <UIcon v-else-if="active && icon" :name="icon" class="size-4" />
        <span v-else>{{ index }}</span>
      </span>

      <div class="flex-1 min-w-0">
        <p class="font-semibold text-highlighted leading-tight">{{ title }}</p>
        <p v-if="done && summary" class="text-sm text-muted mt-1 truncate">{{ summary }}</p>
        <p v-else-if="!active && description" class="text-sm text-muted mt-1 truncate">{{ description }}</p>
      </div>

      <UIcon
        v-if="done && !active"
        name="i-lucide-pencil"
        class="size-4 text-muted shrink-0"
      />
    </button>

    <div v-if="active" class="mt-6">
      <slot />
    </div>
  </UCard>
</template>
