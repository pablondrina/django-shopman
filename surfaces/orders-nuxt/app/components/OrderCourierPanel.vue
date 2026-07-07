<script setup lang="ts">
// Courier ride panel — the operator's window into the external delivery
// (Machine): compact step timeline, driver card, tracking link, quoted cost,
// and the ride actions (quote / dispatch / cancel). Status text comes from the
// server projection; steps/tones are derived from the raw letter.
import { courierFailed, courierSteps, courierTone, courierToneBadge } from "~/presentation/courier";
import type { CourierBlock } from "~/types/orders";

const props = defineProps<{ courier: CourierBlock; busy: boolean }>();
const emit = defineEmits<{ quote: []; dispatch: []; cancel: [] }>();

const steps = computed(() => courierSteps(props.courier.status));
const tone = computed(() => courierTone(props.courier.status));
const failed = computed(() => courierFailed(props.courier.status));
const hasRide = computed(() => Boolean(props.courier.status));

// Cancelar corrida é irreversível para a solicitação em curso → confirm de 1 toque.
const confirmingCancel = ref(false);
function requestCancel() {
  if (!confirmingCancel.value) {
    confirmingCancel.value = true;
    return;
  }
  confirmingCancel.value = false;
  emit("cancel");
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
</script>

<template>
  <section class="flex flex-col gap-3 rounded-lg border bg-card p-4">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide">
        <Icon name="lucide:bike" class="size-4" /> Entregador
      </h2>
      <span
        v-if="courier.status_label"
        class="inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium"
        :class="courierToneBadge(tone)"
      >
        {{ courier.status_label }}
      </span>
      <span v-if="courier.attempts_count > 0" class="text-xs text-muted-foreground">
        {{ courier.attempts_count }}ª corrida não concluída
      </span>
      <span v-if="courier.estimate_display" class="ml-auto text-sm tabular-nums text-muted-foreground">
        {{ courier.final_value_display || courier.estimate_display }}
      </span>
    </div>

    <!-- falha terminal do despacho (Machine recusou / dados) -->
    <p
      v-if="courier.error"
      class="rounded-md border border-red-500/30 bg-red-500/5 p-2.5 text-sm text-red-700 dark:text-red-400"
    >
      Falha ao abrir a corrida: {{ courier.error.message }}
    </p>

    <!-- timeline compacta da corrida -->
    <ol v-if="steps.length" class="flex items-center gap-1" aria-label="Etapas da corrida">
      <li v-for="(step, i) in steps" :key="step.key" class="flex flex-1 items-center gap-1">
        <div class="flex min-w-0 flex-1 flex-col items-center gap-1">
          <span
            class="grid size-6 place-items-center rounded-full border text-xs font-semibold"
            :class="step.state === 'done'
              ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
              : step.state === 'current'
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground'"
          >
            <Icon v-if="step.state === 'done'" name="lucide:check" class="size-3.5" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span class="truncate text-[11px]" :class="step.state === 'pending' ? 'text-muted-foreground' : 'font-medium'">
            {{ step.label }}
          </span>
        </div>
        <span v-if="i < steps.length - 1" class="h-px w-4 shrink-0 bg-border md:w-8" aria-hidden="true" />
      </li>
    </ol>
    <p v-else-if="failed" class="text-sm text-muted-foreground">
      A corrida não foi concluída. Re-despache ou combine a entrega por fora.
    </p>

    <!-- entregador -->
    <div v-if="courier.driver?.name" class="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-muted/60 p-2.5 text-sm">
      <p class="flex items-center gap-1.5 font-medium">
        <Icon name="lucide:user" class="size-4" /> {{ courier.driver.name }}
      </p>
      <a
        v-if="courier.driver.phone"
        :href="telHref(courier.driver.phone)"
        class="flex items-center gap-1.5 font-medium text-primary underline-offset-2 hover:underline"
      >
        <Icon name="lucide:phone" class="size-4" /> {{ courier.driver.phone }}
      </a>
      <p v-if="courier.driver.vehicle_model || courier.driver.vehicle_plate" class="flex items-center gap-1.5 text-muted-foreground">
        <Icon name="lucide:bike" class="size-4" />
        {{ [courier.driver.vehicle_model, courier.driver.vehicle_plate].filter(Boolean).join(" · ") }}
      </p>
    </div>

    <!-- rastreio + código de confirmação -->
    <div v-if="courier.tracking_url || courier.confirmation_code" class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <a
        v-if="courier.tracking_url"
        :href="courier.tracking_url"
        target="_blank"
        rel="noopener"
        class="flex items-center gap-1.5 font-medium text-primary underline-offset-2 hover:underline"
      >
        <Icon name="lucide:map-pin" class="size-4" /> Acompanhar corrida
      </a>
      <span v-if="courier.confirmation_code" class="flex items-center gap-1.5 text-muted-foreground">
        <Icon name="lucide:key-round" class="size-4" /> Código: <strong class="tabular-nums">{{ courier.confirmation_code }}</strong>
      </span>
    </div>

    <!-- ações -->
    <div v-if="courier.can_quote || courier.can_dispatch || courier.can_cancel" class="flex flex-wrap gap-2 border-t pt-3">
      <button
        v-if="courier.can_dispatch"
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        @click="emit('dispatch')"
      >
        <Icon name="lucide:send" class="size-4" />
        {{ hasRide || courier.attempts_count > 0 ? "Re-despachar" : "Chamar entregador" }}
      </button>
      <button
        v-if="courier.can_quote"
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50"
        @click="emit('quote')"
      >
        <Icon name="lucide:calculator" class="size-4" /> Cotar entrega
      </button>
      <button
        v-if="courier.can_cancel"
        type="button"
        :disabled="busy"
        class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition disabled:opacity-50"
        :class="confirmingCancel
          ? 'border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-300'
          : 'border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-300'"
        @blur="confirmingCancel = false"
        @click="requestCancel"
      >
        <Icon name="lucide:ban" class="size-4" />
        {{ confirmingCancel ? "Confirmar cancelamento?" : "Cancelar corrida" }}
      </button>
    </div>
  </section>
</template>
