<script setup lang="ts">
// FECHAMENTO DO DIA na antesala (WP-ADM-2): a contagem cega de sobras/perdas
// sai do Admin/Unfold para o ritual de fim de dia do PDV, ao lado do fechar
// caixa. Mesma projection e mesmo service da retaguarda (GET/POST
// /api/v1/backstage/closing/), gate `backstage.perform_closing` (Gerente).
// Paridade com a tela Admin: produção pendente (com atrasadas + link p/ o
// Fournil), produção do dia, encomendas dos próximos dias, discrepâncias e a
// contagem cega por SKU. Rótulo visível de sobra aproveitável = "Ontem".
import {
  allQuantitiesFilled,
  buildQuantitiesPayload,
  closingBadge,
  pendingStatusDisplay,
  productionRows,
} from "~/presentation/closing";

useHead({ title: "Fechamento do dia · Shopman POS" });

const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
const productionUrl = computed(() => String(runtimeConfig.public.productionUrl || ""));

const { closing, pending, accessDenied, submitting, submit } = await useDayClosing({ action });

const dayProduction = computed(() => productionRows(closing.value?.production_summary));

// Contagem cega: um input por SKU, começa VAZIO (contar de verdade, não
// aceitar default). O CTA só arma quando toda linha tem um número.
const quantities = reactive<Record<string, string>>({});
const canSubmit = computed(
  () => !!closing.value && !closing.value.already_closed
    && allQuantitiesFilled(closing.value.items, quantities),
);

const confirming = ref(false);
async function confirmSubmit() {
  if (!closing.value || !canSubmit.value) return;
  const ok = await submit(buildQuantitiesPayload(closing.value.items, quantities));
  confirming.value = false;
  if (ok) {
    for (const key of Object.keys(quantities)) quantities[key] = "";
  }
}
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
      <UiButton
        variant="ghost"
        size="icon-sm"
        aria-label="Voltar à sessão de caixa"
        title="Sessão de caixa"
        @click="navigateTo('/session')"
      >
        <Icon name="lucide:arrow-left" class="size-5" />
      </UiButton>
      <h1 class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">Fechamento do dia</h1>
      <span v-if="closing" class="ml-auto truncate text-sm text-muted-foreground">
        {{ closing.today_display }} · contagem cega de sobras e perdas
      </span>
    </header>

    <div class="mx-auto grid w-full max-w-2xl gap-4 p-4 md:py-8">
      <!-- Sem permissão: fechamento é ritual do gerente. -->
      <section v-if="accessDenied" class="grid gap-2 rounded-lg border bg-card p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" />
          <h2 class="text-base font-semibold">Fechamento é do gerente</h2>
        </div>
        <p class="text-sm text-muted-foreground">
          Sua conta não tem permissão para realizar o fechamento do dia. Chame quem cuida do encerramento.
        </p>
        <UiButton variant="outline" size="sm" @click="navigateTo('/session')">Voltar à sessão de caixa</UiButton>
      </section>

      <template v-else-if="closing">
        <UiAlert v-if="closing.already_closed" class="border-success/30 bg-success/10 text-success">
          <Icon name="lucide:circle-check" class="size-4" />
          <UiAlertTitle>Dia fechado</UiAlertTitle>
          <UiAlertDescription>{{ closing.existing_closing_display }}</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="closing.has_old_d1" class="border-destructive/40 bg-destructive/10 text-destructive">
          <Icon name="lucide:triangle-alert" class="size-4" />
          <UiAlertTitle>Sobras antigas na posição de ontem</UiAlertTitle>
          <UiAlertDescription>Há produto de "Ontem" com mais de 1 dia. Confira antes de fechar.</UiAlertDescription>
        </UiAlert>

        <!-- Produção pendente -->
        <section v-if="closing.has_pending_production" class="grid gap-2 rounded-lg border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="text-base font-semibold">Produção pendente</h2>
            <span class="inline-flex items-center rounded-md border border-warning/50 bg-warning/10 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
              {{ closing.pending_production.length }}
            </span>
          </div>
          <p class="text-sm text-muted-foreground">
            Ordens ainda abertas neste fechamento. Conclua ou estorne antes de encerrar o dia. O registro fica no snapshot.
          </p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Ordem</th>
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Status</th>
                  <th class="py-1.5 pr-3 font-medium">Qtd</th>
                  <th class="py-1.5 font-medium">Alvo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.pending_production" :key="row.ref" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3 font-medium">{{ row.ref }}</td>
                  <td class="py-1.5 pr-3">{{ row.output_sku }}</td>
                  <td class="py-1.5 pr-3" :class="row.is_overdue ? 'text-destructive' : ''">{{ pendingStatusDisplay(row) }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.quantity }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.target_date_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <a
            v-if="productionUrl"
            class="text-sm font-medium underline underline-offset-4"
            :href="productionUrl"
            target="_blank" rel="noopener"
          >
            Resolver na produção
          </a>
        </section>

        <!-- Produção do dia -->
        <section class="grid gap-2 rounded-lg border bg-card p-4">
          <h2 class="text-base font-semibold">Produção do dia</h2>
          <p v-if="!dayProduction.length" class="text-sm text-muted-foreground">Sem produção registrada hoje.</p>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Planejado</th>
                  <th class="py-1.5 pr-3 font-medium">Feito</th>
                  <th class="py-1.5 font-medium">Perda</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in dayProduction" :key="row.sku" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3 font-medium">{{ row.sku }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.planned }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.finished }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.loss }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Encomendas dos próximos dias -->
        <section v-if="closing.has_upcoming_preorders" class="grid gap-2 rounded-lg border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="text-base font-semibold">Encomendas para os próximos dias</h2>
            <span class="inline-flex items-center rounded-md border border-border bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {{ closing.upcoming_preorders.length }}
            </span>
          </div>
          <p class="text-sm text-muted-foreground">
            Vendidas hoje, saem do estoque na data combinada. Entram no caixa de hoje e na reconciliação do dia da entrega.
          </p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Data</th>
                  <th class="py-1.5 pr-3 font-medium">Pedidos</th>
                  <th class="py-1.5 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.upcoming_preorders" :key="row.date" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3">{{ row.date_display }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.orders_count }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.total_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Discrepâncias -->
        <section v-if="closing.reconciliation_errors.length" class="grid gap-2 rounded-lg border border-destructive/40 bg-card p-4">
          <h2 class="text-base font-semibold text-destructive">Discrepâncias detectadas</h2>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Vendido</th>
                  <th class="py-1.5 pr-3 font-medium">Disponível</th>
                  <th class="py-1.5 font-medium">Déficit</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.reconciliation_errors" :key="row.sku" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3 font-medium">{{ row.sku }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.sold_qty }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.available_qty }}</td>
                  <td class="py-1.5 tabular-nums text-destructive">{{ row.deficit_qty }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Contagem final (cega) -->
        <section class="grid gap-2 rounded-lg border bg-card p-4">
          <h2 class="text-base font-semibold">Contagem final</h2>
          <p class="text-sm text-muted-foreground">
            Informe apenas o que sobrou fisicamente. O sistema trata destino e perdas automaticamente.
          </p>
          <p v-if="!closing.has_items" class="text-sm text-muted-foreground">Nada em estoque vendável para contar.</p>
          <div v-else class="grid gap-1.5">
            <div
              v-for="item in closing.items"
              :key="item.sku"
              class="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium">{{ item.name }}</p>
                <p class="text-xs text-muted-foreground">{{ item.sku }}</p>
              </div>
              <span
                class="inline-flex shrink-0 items-center rounded-md border px-1.5 py-0.5 text-xs font-medium"
                :class="closingBadge(item.classification).css"
              >
                {{ closingBadge(item.classification).label }}
              </span>
              <UiInput
                v-model="quantities[item.sku]"
                inputmode="numeric"
                placeholder="0"
                class="w-20 text-right tabular-nums"
                :disabled="closing.already_closed || submitting"
                :aria-label="`Sobras de ${item.name}`"
              />
            </div>
          </div>

          <template v-if="closing.has_items && !closing.already_closed">
            <div v-if="!confirming" class="mt-1">
              <UiButton class="w-full" :disabled="!canSubmit || submitting" @click="confirming = true">
                <Icon name="lucide:clipboard-check" class="size-5" />
                Registrar contagem final
              </UiButton>
              <p v-if="!canSubmit" class="mt-1.5 text-xs text-muted-foreground">
                Preencha a contagem de todos os itens para registrar.
              </p>
            </div>
            <div v-else class="mt-1 grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
              <p class="text-sm font-medium">
                Confirmar o fechamento do dia {{ closing.today_display }}? Sobras viram "Ontem" ou perda e a contagem é registrada.
              </p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton variant="outline" :disabled="submitting" @click="confirming = false">Cancelar</UiButton>
                <UiButton variant="destructive" :disabled="submitting" :loading="submitting" @click="confirmSubmit">
                  Confirmar fechamento
                </UiButton>
              </div>
            </div>
          </template>
        </section>
      </template>

      <section v-else-if="pending" class="grid place-items-center rounded-lg border bg-card p-8">
        <Icon name="line-md:loading-loop" class="size-6 text-muted-foreground" />
      </section>
    </div>
  </main>
</template>
