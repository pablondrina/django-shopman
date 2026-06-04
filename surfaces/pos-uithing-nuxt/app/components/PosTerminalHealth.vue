<script setup lang="ts">
import type { POSTerminalComponentProjection } from "~/types/pos";

const props = defineProps<{
  terminalLabel: string;
  healthStatus: string;
  components: POSTerminalComponentProjection[];
  fiscalStatus: string;
  fiscalLabel: string;
  fiscalMessage: string;
}>();

type StatusMeta = {
  label: string;
  dot: string;
  text: string;
  badge: "success" | "warning" | "destructive" | "outline";
};

const STATUS_META: Record<string, StatusMeta> = {
  ready: { label: "OK", dot: "bg-green-500", text: "text-green-700", badge: "success" },
  warning: { label: "Atenção", dot: "bg-amber-500", text: "text-amber-700", badge: "warning" },
  error: { label: "Erro", dot: "bg-red-500", text: "text-red-700", badge: "destructive" },
};

function meta(status: string): StatusMeta {
  return STATUS_META[status] || { label: status || "—", dot: "bg-muted-foreground", text: "text-muted-foreground", badge: "outline" };
}

const overall = computed(() => meta(props.healthStatus));
const rows = computed(() => [
  ...props.components.map((component) => ({
    key: component.key,
    label: component.label,
    status: component.status,
    message: component.message,
  })),
  {
    key: "fiscal",
    label: "Fiscal",
    status: props.fiscalStatus,
    message: props.fiscalMessage || props.fiscalLabel,
  },
]);
</script>

<template>
  <UiPopover>
    <UiPopoverTrigger as-child>
      <UiButton variant="ghost" size="sm" class="gap-2 text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground" :aria-label="`Saúde do terminal: ${overall.label}`">
        <span class="size-2 rounded-full" :class="overall.dot" />
        <span class="font-medium">{{ terminalLabel }}</span>
        <Icon name="lucide:chevron-down" class="size-3.5 opacity-60" />
      </UiButton>
    </UiPopoverTrigger>
    <UiPopoverContent align="end" class="w-72 p-0">
      <div class="border-b p-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-semibold">Saúde do terminal</span>
          <UiBadge :variant="overall.badge">{{ overall.label }}</UiBadge>
        </div>
        <p class="text-xs text-muted-foreground">{{ terminalLabel }}</p>
      </div>
      <ul class="grid gap-0.5 p-2">
        <li
          v-for="row in rows"
          :key="row.key"
          class="grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-md px-2 py-1.5"
        >
          <span class="size-2 rounded-full" :class="meta(row.status).dot" />
          <div class="min-w-0">
            <p class="text-sm font-medium leading-tight">{{ row.label }}</p>
            <p v-if="row.message" class="truncate text-xs text-muted-foreground">{{ row.message }}</p>
          </div>
          <span class="text-xs font-semibold" :class="meta(row.status).text">{{ meta(row.status).label }}</span>
        </li>
      </ul>
    </UiPopoverContent>
  </UiPopover>
</template>
