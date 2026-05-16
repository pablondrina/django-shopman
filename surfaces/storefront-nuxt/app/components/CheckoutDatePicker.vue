<script setup lang="ts">
import { CalendarDate, getLocalTimeZone, parseDate, today } from '@internationalized/date'

const model = defineModel<string>({ required: true })
const props = defineProps<{
  closedDatesJson?: string
  maxPreorderDays?: number
}>()

const tz = getLocalTimeZone()
const todayDate = computed(() => today(tz))
const maxDays = computed(() => props.maxPreorderDays ?? 14)
const maxDate = computed(() => todayDate.value.add({ days: maxDays.value }))

const closedDateSet = computed(() => {
  try {
    return props.closedDatesJson ? new Set(JSON.parse(props.closedDatesJson) as string[]) : new Set<string>()
  } catch {
    return new Set<string>()
  }
})

function isoFromCalendarDate (cd: CalendarDate): string {
  return `${cd.year}-${String(cd.month).padStart(2, '0')}-${String(cd.day).padStart(2, '0')}`
}

function isClosed (cd: CalendarDate): boolean {
  return closedDateSet.value.has(isoFromCalendarDate(cd))
}

function isUnavailable (cd: any): boolean {
  if (cd.compare(todayDate.value) < 0) return true
  if (cd.compare(maxDate.value) > 0) return true
  return isClosed(cd)
}

const tomorrowDate = computed(() => todayDate.value.add({ days: 1 }))
const todayIso = computed(() => isoFromCalendarDate(todayDate.value))
const tomorrowIso = computed(() => isoFromCalendarDate(tomorrowDate.value))

const todayDisabled = computed(() => isClosed(todayDate.value))
const tomorrowDisabled = computed(() => isClosed(tomorrowDate.value))

const calendarValue = computed({
  get () {
    if (!model.value) return undefined
    try {
      return parseDate(model.value)
    } catch {
      return undefined
    }
  },
  set (value: any) {
    if (!value) {
      model.value = ''
      popoverOpen.value = false
      return
    }
    model.value = isoFromCalendarDate(value)
    popoverOpen.value = false
  }
})

const popoverOpen = ref(false)

const dateLabel = computed(() => {
  if (!model.value) return 'Escolher data'
  if (model.value === todayIso.value) return 'Hoje'
  if (model.value === tomorrowIso.value) return 'Amanhã'
  try {
    const d = new Date(`${model.value}T00:00:00`)
    return d.toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' })
  } catch {
    return model.value
  }
})

const dateHint = computed(() => {
  if (!model.value || model.value === todayIso.value || model.value === tomorrowIso.value) return null
  try {
    const d = new Date(`${model.value}T00:00:00`)
    return d.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
  } catch {
    return null
  }
})

function pickIso (iso: string) {
  if (closedDateSet.value.has(iso)) return
  model.value = iso
}
</script>

<template>
  <div class="grid gap-2">
    <div class="flex flex-wrap gap-2">
      <UButton
        size="sm"
        :color="model === todayIso ? 'primary' : 'neutral'"
        :variant="model === todayIso ? 'solid' : 'outline'"
        :disabled="todayDisabled"
        label="Hoje"
        @click="pickIso(todayIso)"
      />
      <UButton
        size="sm"
        :color="model === tomorrowIso ? 'primary' : 'neutral'"
        :variant="model === tomorrowIso ? 'solid' : 'outline'"
        :disabled="tomorrowDisabled"
        label="Amanhã"
        @click="pickIso(tomorrowIso)"
      />

      <UPopover v-model:open="popoverOpen" :ui="{ content: 'p-0' }">
        <UButton
          size="sm"
          :color="model && model !== todayIso && model !== tomorrowIso ? 'primary' : 'neutral'"
          :variant="model && model !== todayIso && model !== tomorrowIso ? 'solid' : 'outline'"
          icon="i-lucide-calendar"
          :label="model && model !== todayIso && model !== tomorrowIso ? dateLabel : 'Outra data'"
        />
        <template #content>
          <UCalendar
            v-model="calendarValue"
            :is-date-unavailable="isUnavailable"
            :min-value="todayDate"
            :max-value="maxDate"
            color="primary"
          />
        </template>
      </UPopover>
    </div>

    <p v-if="dateHint" class="text-sm text-muted">
      <UIcon name="i-lucide-circle-check" class="size-3.5 text-success inline-block align-text-bottom mr-1" />
      {{ dateHint }}
    </p>
  </div>
</template>
