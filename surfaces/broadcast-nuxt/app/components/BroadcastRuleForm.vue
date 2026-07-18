<script setup lang="ts">
// Formulário de regra — "que evento vira o quê, para quem, onde".
//
// Apresentacional: o pai é dono do fetch e da escrita; aqui mora só o estado do
// formulário. O vocabulário (gatilhos, plataformas, modelos) vem do backend,
// nunca hardcoded — gatilho novo no domínio aparece aqui sem deploy de front.
import type { AudienceRules, BroadcastRule, Choice, PostTemplate } from "~/types/broadcast";

const props = defineProps<{
  rule: BroadcastRule | null; // null = criando
  triggers: Choice[];
  platformOptions: Choice[];
  templates: PostTemplate[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  submit: [payload: Record<string, unknown>];
  cancel: [];
}>();

const name = ref("");
const trigger = ref("");
const templateId = ref<number | null>(null);
const platforms = ref<string[]>([]);
const requiresApproval = ref(true);
const expiresAfterMinutes = ref(0);
const isActive = ref(true);

// Audiência: toggles simples em cima do JSON que o serviço lê.
const favorites = ref(false);
const alerts = ref(false);
const recompraOn = ref(false);
const recompraDays = ref(90);
const vipFirstMinutes = ref(0);

// Estado novo a cada regra aberta — senão o formulário herdaria a anterior.
watch(
  () => props.rule?.pk ?? null,
  () => {
    const rule = props.rule;
    const audience: AudienceRules = rule?.audience_rules ?? {};

    name.value = rule?.name ?? "";
    trigger.value = rule?.trigger ?? props.triggers[0]?.value ?? "";
    templateId.value = rule?.template_id ?? props.templates[0]?.pk ?? null;
    platforms.value = [...(rule?.platforms ?? [])];
    requiresApproval.value = rule?.requires_approval ?? true;
    expiresAfterMinutes.value = rule?.expires_after_minutes ?? 0;
    isActive.value = rule?.is_active ?? true;

    favorites.value = Boolean(audience.favorites);
    alerts.value = Boolean(audience.alerts);
    recompraOn.value = Boolean(audience.recompra_days);
    recompraDays.value = audience.recompra_days || 90;
    vipFirstMinutes.value = audience.vip_first_minutes || 0;
  },
  { immediate: true },
);

const canSubmit = computed(
  () =>
    !props.busy &&
    name.value.trim().length > 0 &&
    trigger.value !== "" &&
    templateId.value !== null &&
    platforms.value.length > 0,
);

function togglePlatform(value: string) {
  const index = platforms.value.indexOf(value);
  if (index >= 0) platforms.value.splice(index, 1);
  else platforms.value.push(value);
}

function submit() {
  if (!canSubmit.value) return;
  emit("submit", {
    name: name.value.trim(),
    trigger: trigger.value,
    template_id: templateId.value,
    platforms: [...platforms.value],
    requires_approval: requiresApproval.value,
    expires_after_minutes: expiresAfterMinutes.value,
    is_active: isActive.value,
    audience_rules: {
      favorites: favorites.value,
      alerts: alerts.value,
      // Chave ausente quando desligado: o serviço lê "0 dias" como "não usa".
      ...(recompraOn.value ? { recompra_days: recompraDays.value } : {}),
      ...(vipFirstMinutes.value > 0 ? { vip_first_minutes: vipFirstMinutes.value } : {}),
    },
  });
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="submit">
    <div>
      <label for="rule-name" class="mb-1 block text-sm font-medium">Nome da regra</label>
      <input
        id="rule-name"
        v-model="name"
        type="text"
        placeholder="Fornada de pães → redes"
        class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
      >
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <div>
        <label for="rule-trigger" class="mb-1 block text-sm font-medium">Quando acontecer</label>
        <select
          id="rule-trigger"
          v-model="trigger"
          class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        >
          <option v-for="choice in triggers" :key="choice.value" :value="choice.value">
            {{ choice.label }}
          </option>
        </select>
      </div>

      <div>
        <label for="rule-template" class="mb-1 block text-sm font-medium">Usar o modelo</label>
        <select
          id="rule-template"
          v-model="templateId"
          class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        >
          <option v-for="template in templates" :key="template.pk" :value="template.pk">
            {{ template.name }}
          </option>
        </select>
        <p v-if="templates.length === 0" class="mt-1 text-xs text-muted-foreground">
          Nenhum modelo cadastrado ainda. Crie um no Admin antes de criar a regra.
        </p>
      </div>
    </div>

    <fieldset>
      <legend class="mb-1 text-sm font-medium">Publicar em</legend>
      <div class="flex flex-wrap gap-1.5">
        <label
          v-for="option in platformOptions"
          :key="option.value"
          class="inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors"
          :class="platforms.includes(option.value)
            ? 'border-primary bg-primary/10 text-foreground'
            : 'border-border text-muted-foreground hover:bg-muted'"
        >
          <input
            type="checkbox"
            class="sr-only"
            :aria-label="option.label"
            :checked="platforms.includes(option.value)"
            @change="togglePlatform(option.value)"
          >
          {{ option.label }}
        </label>
      </div>
    </fieldset>

    <fieldset class="rounded-lg border border-border p-3">
      <legend class="px-1 text-sm font-medium">Avisar quem</legend>
      <div class="space-y-2.5">
        <label class="flex items-center gap-2 text-sm">
          <input v-model="favorites" type="checkbox" class="size-4 rounded border-border">
          Quem favoritou o produto
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="alerts" type="checkbox" class="size-4 rounded border-border">
          Quem pediu "me avise quando sair do forno"
        </label>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label class="flex items-center gap-2">
            <input v-model="recompraOn" type="checkbox" class="size-4 rounded border-border">
            Quem comprou nos últimos
          </label>
          <input
            v-model.number="recompraDays"
            type="number"
            min="1"
            max="365"
            :disabled="!recompraOn"
            aria-label="Dias de recompra"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm disabled:opacity-50"
          >
          <span :class="recompraOn ? '' : 'text-muted-foreground'">dias</span>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label for="rule-vip">VIPs recebem</label>
          <input
            id="rule-vip"
            v-model.number="vipFirstMinutes"
            type="number"
            min="0"
            max="120"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
          >
          <span>minutos antes</span>
          <span class="text-xs text-muted-foreground">(0 = todo mundo junto)</span>
        </div>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        Só quem aceitou receber novidades entra na conta. Assinatura de alerta por produto
        já é um aceite daquele produto.
      </p>
    </fieldset>

    <div class="space-y-2.5">
      <label class="flex items-center gap-2 text-sm">
        <input v-model="requiresApproval" type="checkbox" class="size-4 rounded border-border">
        Revisar antes de publicar
      </label>
      <p v-if="!requiresApproval" class="pl-6 text-xs text-amber-700 dark:text-amber-400">
        Sem revisão, o post sai sozinho assim que o evento acontecer.
      </p>
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <label for="rule-expiry">O post aguarda revisão por</label>
        <input
          id="rule-expiry"
          v-model.number="expiresAfterMinutes"
          type="number"
          min="0"
          max="1440"
          class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
        >
        <span>minutos</span>
        <span class="text-xs text-muted-foreground">(0 = sem prazo)</span>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="isActive" type="checkbox" class="size-4 rounded border-border">
        Regra ativa
      </label>
    </div>

    <div class="flex items-center gap-2 pt-1">
      <button
        type="submit"
        :disabled="!canSubmit"
        class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:check'" class="size-4" />
        {{ rule ? "Salvar" : "Criar regra" }}
      </button>
      <button
        type="button"
        class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
        @click="emit('cancel')"
      >
        Cancelar
      </button>
    </div>
  </form>
</template>
