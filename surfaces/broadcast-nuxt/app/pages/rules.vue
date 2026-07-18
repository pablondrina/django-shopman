<script setup lang="ts">
// Regras — o que a operação dispara sozinha.
//
// O gesto mais comum é ligar/desligar, então ele fica a um toque na própria
// linha. Editar abre um painel lateral: a lista continua visível, e o gestor
// não perde o contexto de quais outras regras já existem.
import { audienceRulesSummary, platformsSummary } from "~/presentation/broadcast";
import type { BroadcastRule } from "~/types/broadcast";

const { rules, templates, triggers, platforms, platformLabels, loading, error, refresh, toggle, patch, create } =
  useBroadcastRules();

const editing = ref<BroadcastRule | null>(null);
const creating = ref(false);
const busy = ref(false);

const panelOpen = computed(() => creating.value || editing.value !== null);

function openNew() {
  editing.value = null;
  creating.value = true;
}

function openEdit(rule: BroadcastRule) {
  creating.value = false;
  editing.value = rule;
}

function close() {
  creating.value = false;
  editing.value = null;
}

async function onSubmit(payload: Record<string, unknown>) {
  busy.value = true;
  const ok = editing.value ? await patch(editing.value.pk, payload) : await create(payload);
  busy.value = false;
  if (ok) close();
}

useHead({ title: "Regras · Broadcast" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-xl font-bold">Regras</h1>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Nova regra
      </button>
    </div>

    <div
      v-if="error"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">Não conseguimos carregar as regras.</p>
      <button type="button" class="mt-1 underline underline-offset-2" @click="refresh()">
        Tentar de novo
      </button>
    </div>

    <div v-else-if="loading && rules.length === 0" class="space-y-3" aria-busy="true">
      <div v-for="n in 3" :key="n" class="h-20 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <div
      v-else-if="rules.length === 0"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon name="lucide:sliders-horizontal" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-2 font-semibold">Nenhuma regra ainda</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Uma regra liga um evento da padaria a um post. Comece pela fornada.
      </p>
      <button
        type="button"
        class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Criar a primeira
      </button>
    </div>

    <ul v-else class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
      <li v-for="rule in rules" :key="rule.pk" class="flex items-start gap-3 px-4 py-3">
        <!-- Liga/desliga: o gesto mais comum, a um toque -->
        <button
          type="button"
          role="switch"
          :aria-checked="rule.is_active"
          :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a regra ${rule.name}`"
          class="mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors"
          :class="rule.is_active ? 'bg-primary' : 'bg-muted-foreground/30'"
          @click="toggle(rule)"
        >
          <span
            class="size-4 rounded-full bg-white shadow transition-transform"
            :class="rule.is_active ? 'translate-x-4' : 'translate-x-0.5'"
          ></span>
        </button>

        <button
          type="button"
          class="min-w-0 flex-1 text-left"
          @click="openEdit(rule)"
        >
          <p class="font-semibold" :class="rule.is_active ? '' : 'text-muted-foreground'">
            {{ rule.name }}
          </p>
          <p class="mt-0.5 text-sm text-muted-foreground">
            {{ rule.trigger_label }} → {{ platformsSummary(rule.platforms, platformLabels) }}
          </p>
          <p class="mt-0.5 text-xs text-muted-foreground">
            {{ audienceRulesSummary(rule.audience_rules) }}
          </p>
        </button>

        <div class="flex shrink-0 items-center gap-2">
          <span
            v-if="!rule.requires_approval"
            class="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Publica sem passar por revisão"
          >
            automática
          </span>
          <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
        </div>
      </li>
    </ul>

    <!-- Painel lateral: edita sem tirar a lista da vista -->
    <UiSheet :open="panelOpen" @update:open="(v) => { if (!v) close() }">
      <UiSheetContent side="right" class="w-full overflow-y-auto sm:max-w-lg">
        <UiSheetHeader>
          <UiSheetTitle>{{ editing ? "Editar regra" : "Nova regra" }}</UiSheetTitle>
          <UiSheetDescription>
            Um evento da padaria vira um post, para as pessoas certas.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="mt-4">
          <BroadcastRuleForm
            :rule="editing"
            :triggers="triggers"
            :platform-options="platforms"
            :templates="templates"
            :busy="busy"
            @submit="onSubmit"
            @cancel="close"
          />
        </div>
      </UiSheetContent>
    </UiSheet>
  </main>
</template>
