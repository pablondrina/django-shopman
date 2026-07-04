<script setup lang="ts">
// Nota em estrelas (1..max), acessível (radiogroup) e com preview no hover.
// Substitui o input numérico de avaliação — mais bonito e natural de tocar.
const props = withDefaults(defineProps<{
  modelValue: number
  max?: number
  readonly?: boolean
  size?: 'md' | 'lg'
}>(), { max: 5, readonly: false, size: 'lg' })

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const hovered = ref(0)
const stars = computed(() => Array.from({ length: props.max }, (_, i) => i + 1))
const active = computed(() => hovered.value || props.modelValue)
const starSize = computed(() => (props.size === 'lg' ? 'size-10' : 'size-6'))

function set (value: number) {
  if (!props.readonly) emit('update:modelValue', value)
}
</script>

<template>
  <div
    role="radiogroup"
    :aria-label="`Nota de 1 a ${max}`"
    class="flex items-center gap-1"
    @mouseleave="hovered = 0"
  >
    <button
      v-for="value in stars"
      :key="value"
      type="button"
      role="radio"
      :aria-checked="modelValue === value"
      :aria-label="`${value} de ${max}`"
      :tabindex="readonly ? -1 : 0"
      :disabled="readonly"
      class="rounded-full p-1 transition-transform hover:scale-110 disabled:hover:scale-100"
      @click="set(value)"
      @mouseenter="hovered = value"
    >
      <!-- Não selecionada: só contorno dourado (fill transparente). Selecionada:
           contorno + preenchimento dourado. -->
      <Icon
        name="lucide:star"
        :class="[starSize, 'text-amber-500 transition-colors', value <= active ? 'fill-amber-400' : 'fill-transparent']"
      />
    </button>
  </div>
</template>
