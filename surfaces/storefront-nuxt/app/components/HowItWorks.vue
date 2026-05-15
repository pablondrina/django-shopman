<script setup lang="ts">
import type { HomeSectionsCopyProjection, OpeningHoursEntry } from '~/types/shopman'

const props = defineProps<{
  openingHours: OpeningHoursEntry[]
  copy: HomeSectionsCopyProjection
}>()

const onlineSteps = computed(() => [
  {
    title: props.copy.how_step_choose.title,
    description: props.copy.how_online_choose_message.message
  },
  {
    title: props.copy.how_step_pay.title,
    description: props.copy.how_online_pay_message.message
  },
  {
    title: props.copy.how_step_fulfill.title,
    description: props.copy.how_online_track_message.message
  }
] as const)

const storeFeatures = computed(() => [
  {
    title: props.copy.how_self_service_label.title,
    description: props.copy.how_store_self_service_message.message
  },
  {
    title: props.copy.how_counter_label.title,
    description: props.copy.how_store_counter_message.message
  }
] as const)
</script>

<template>
  <UPageSection
    :title="copy.how_it_works_heading.title"
    :description="copy.how_it_works_intro.message"
    :ui="{ container: 'py-12 sm:py-16', headline: 'text-primary uppercase text-xs font-semibold' }"
  >
    <div class="grid lg:grid-cols-2 gap-6">
      <UPageCard
        :title="copy.how_online_heading.title"
        variant="subtle"
        :ui="{ container: 'p-6 sm:p-8' }"
      >
        <ol class="grid gap-5 mt-6">
          <li
            v-for="(step, idx) in onlineSteps"
            :key="step.title"
            class="flex items-start gap-4"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold tabular-nums">
              {{ idx + 1 }}
            </span>
            <div>
              <p class="font-semibold text-highlighted flex items-center gap-2">
                {{ step.title }}
              </p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </UPageCard>

      <UPageCard
        :title="copy.how_store_heading.title"
        variant="subtle"
        :ui="{ container: 'p-6 sm:p-8' }"
      >
        <div class="grid gap-5 mt-6">
          <div
            v-for="feature in storeFeatures"
            :key="feature.title"
            class="flex items-start gap-4"
          >
            <span class="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
            <div>
              <p class="font-semibold text-highlighted">{{ feature.title }}</p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ feature.description }}</p>
            </div>
          </div>

          <USeparator v-if="openingHours.length" />

          <div v-if="openingHours.length">
            <p class="text-xs uppercase font-semibold text-muted mb-3 flex items-center gap-2">
              {{ copy.how_hours_label.title }}
            </p>
            <dl class="grid gap-1.5 text-sm">
              <div
                v-for="entry in openingHours"
                :key="entry.label"
                class="flex justify-between gap-4 tabular-nums"
              >
                <dt class="text-muted">{{ entry.label }}</dt>
                <dd class="font-medium text-highlighted">{{ entry.hours }}</dd>
              </div>
            </dl>
          </div>
          <p v-else class="text-sm text-muted">
            {{ copy.how_hours_empty.message }}
          </p>
        </div>
      </UPageCard>
    </div>
  </UPageSection>
</template>
