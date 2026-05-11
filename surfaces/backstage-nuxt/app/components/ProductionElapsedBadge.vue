<script setup lang="ts">
const props = defineProps<{
  elapsedSeconds: number
  timerClass: 'timer-ok' | 'timer-warning' | 'timer-late'
}>()

const { formatted } = useElapsedTimer(() => props.elapsedSeconds)

const color = computed(() => {
  switch (props.timerClass) {
    case 'timer-late': return 'error' as const
    case 'timer-warning': return 'warning' as const
    default: return 'success' as const
  }
})
</script>

<template>
  <UBadge :color="color" variant="solid" size="md" class="tabular-nums">
    {{ formatted }}
  </UBadge>
</template>
