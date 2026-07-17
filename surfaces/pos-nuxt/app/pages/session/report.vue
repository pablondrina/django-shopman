<script setup lang="ts">
// RELATÓRIO da sessão de caixa na antesala (WP-ADM-4, benchmark Odoo POS):
// leitura X (parcial do turno ABERTO do operador), leituras Z (turnos
// FECHADOS do dia) e o histórico agregado de turnos/vendas. Read-only sobre
// GET /api/v1/backstage/pos/cash/report/, gate `backstage.operate_pos`.
// BLIND: o PDV nunca mostra o valor ESPERADO da gaveta nem a variância — a
// conferência (esperado vs contado) é da retaguarda. Impressão térmica fica
// fora (capítulo NFC-e).
useHead({ title: "Relatório de caixa · Shopman POS" });

const { report, pending, accessDenied, refresh } = await useCashReport();
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
      <h1 class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">Relatório de caixa</h1>
      <span v-if="report" class="ml-auto truncate text-sm text-muted-foreground">
        {{ report.date_display }} · leituras X/Z do dia
      </span>
      <UiButton
        variant="ghost"
        size="icon-sm"
        aria-label="Atualizar relatório"
        title="Atualizar"
        :disabled="pending"
        @click="refresh()"
      >
        <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
      </UiButton>
    </header>

    <div class="mx-auto grid w-full max-w-2xl gap-4 p-4 md:py-8">
      <!-- Sem permissão de operação do PDV. -->
      <section v-if="accessDenied" class="grid gap-2 rounded-lg border bg-card p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" />
          <h2 class="text-base font-semibold">Relatório é de quem opera o PDV</h2>
        </div>
        <p class="text-sm text-muted-foreground">
          Sua conta não tem permissão para operar o PDV. Chame quem cuida do caixa.
        </p>
        <UiButton variant="outline" size="sm" @click="navigateTo('/session')">Voltar à sessão de caixa</UiButton>
      </section>

      <template v-else-if="report">
        <!-- Leitura X: parcial do turno aberto do operador. -->
        <PosCashReadingCard v-if="report.x_reading" :reading="report.x_reading" />
        <section v-else class="grid gap-2 rounded-lg border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:receipt-text" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Leitura X</h2>
          </div>
          <p class="text-sm text-muted-foreground">
            Sem turno aberto para esta conta. Abra o caixa na sessão para acompanhar a parcial do turno.
          </p>
        </section>

        <!-- Leituras Z: turnos fechados hoje. -->
        <template v-if="report.has_closed_shifts">
          <PosCashReadingCard
            v-for="reading in report.z_readings"
            :key="reading.shift_id"
            :reading="reading"
          />
        </template>
        <section v-else class="grid gap-2 rounded-lg border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:archive" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Leituras Z</h2>
          </div>
          <p class="text-sm text-muted-foreground">Nenhum turno fechado hoje.</p>
        </section>

        <!-- Histórico do dia: totais agregados dos turnos fechados. -->
        <section v-if="report.has_closed_shifts" class="grid gap-2 rounded-lg border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:history" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Histórico do dia</h2>
          </div>
          <div class="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:grid-cols-4">
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Turnos fechados</span>
              <span class="font-medium tabular-nums">{{ report.day_totals.shifts_count }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Vendas</span>
              <span class="font-medium tabular-nums">{{ report.day_totals.sales_count }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Total vendido</span>
              <span class="font-medium tabular-nums">R$ {{ report.day_totals.sales_total_display }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Total contado</span>
              <span class="font-medium tabular-nums">R$ {{ report.day_totals.counted_total_display }}</span>
            </div>
          </div>
          <div v-if="report.day_totals.sales_by_method.length" class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Método</th>
                  <th class="py-1.5 pr-3 font-medium">Pagamentos</th>
                  <th class="py-1.5 font-medium">Valor</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in report.day_totals.sales_by_method"
                  :key="row.method"
                  class="border-b border-border/60 last:border-0"
                >
                  <td class="py-1.5 pr-3 font-medium">{{ row.method_label }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.orders_count }}</td>
                  <td class="py-1.5 tabular-nums">R$ {{ row.amount_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-xs text-muted-foreground">
            A conferência do contado com o esperado fica na retaguarda.
          </p>
        </section>
      </template>

      <p v-else-if="pending" class="text-sm text-muted-foreground">Carregando relatório…</p>
    </div>
  </main>
</template>
