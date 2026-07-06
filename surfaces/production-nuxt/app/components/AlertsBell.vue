<script setup lang="ts">
// Operator alerts bell — count badge + dropdown panel with per-alert ack. Color is
// functional (severity); the bell itself is neutral chrome. Lives in the board header.
// Production alerts deep-link: tapping one lands on its WO (live floor or planning)
// with the search preset to the ref.
import { alertTarget } from "~/presentation/production";
import type { AlertProjection } from "~/types/production";

const { alerts, activeCount, criticalCount, ack } = useAlerts();
const open = ref(false);
const router = useRouter();

function sevChip(sev: AlertProjection["severity"]): string {
  if (sev === "critical") return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
  if (sev === "error") return "border-orange-500/40 bg-orange-500/10 text-orange-700 dark:text-orange-300";
  return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
}

function follow(alert: AlertProjection) {
  const target = alertTarget(alert);
  if (!target) return;
  open.value = false;
  router.push({ path: target.to, query: { q: target.q } });
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="relative grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
      :aria-label="`Alertas (${activeCount})`"
      title="Alertas"
      @click="open = !open"
    >
      <Icon name="lucide:bell" class="size-4" />
      <span
        v-if="activeCount"
        class="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full px-1 text-xs font-bold tabular-nums text-white"
        :class="criticalCount ? 'bg-red-600' : 'bg-amber-500'"
      >{{ activeCount }}</span>
    </button>

    <!-- backdrop to close on outside click -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <div
      v-if="open"
      class="absolute right-0 z-50 mt-2 flex max-h-[70vh] w-80 flex-col overflow-hidden rounded-lg border bg-card shadow-lg"
    >
      <div class="flex items-center justify-between border-b px-4 py-2.5">
        <h2 class="text-sm font-bold">Alertas</h2>
        <button type="button" class="grid size-7 place-items-center rounded text-muted-foreground transition hover:text-foreground" aria-label="Fechar" @click="open = false">
          <Icon name="lucide:x" class="size-4" />
        </button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <div v-if="!alerts.length" class="grid place-items-center gap-1.5 py-8 text-center text-muted-foreground">
          <Icon name="lucide:check-circle-2" class="size-6" />
          <p class="text-sm">Nenhum alerta agora.</p>
        </div>
        <ul v-else class="flex flex-col gap-1.5">
          <li v-for="a in alerts" :key="a.pk" class="flex items-start gap-2 rounded-md border p-2.5" :class="sevChip(a.severity)">
            <component
              :is="alertTarget(a) ? 'button' : 'div'"
              class="min-w-0 flex-1 text-left"
              v-bind="alertTarget(a) ? { type: 'button', 'aria-label': `Abrir ${a.order_ref} na tela` } : {}"
              @click="follow(a)"
            >
              <p class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide">
                {{ a.severity_label }} · {{ a.type_label }}
                <Icon v-if="alertTarget(a)" name="lucide:arrow-up-right" class="size-3" />
              </p>
              <p class="mt-0.5 break-words text-sm text-foreground">{{ a.message }}</p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ a.created_at_display }}<template v-if="a.order_ref"> · {{ a.order_ref }}</template>
              </p>
            </component>
            <button
              type="button"
              class="grid size-7 shrink-0 place-items-center rounded border bg-background text-muted-foreground transition hover:text-foreground"
              aria-label="Reconhecer alerta"
              title="Reconhecer"
              @click="ack(a.pk)"
            >
              <Icon name="lucide:check" class="size-3.5" />
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
