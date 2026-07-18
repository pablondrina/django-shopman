<script setup lang="ts">
// Histórico — o que saiu e como foi em CADA plataforma.
//
// Sucesso parcial não vira "publicado": se o Google saiu e o Instagram falhou,
// a linha diz "parcial" e mostra as duas. Esconder a falha aqui seria esconder
// justamente a informação que o gestor precisa para agir.
import { postOutcome, resultLabel, resultTone, shortDateTime, audienceSummary } from "~/presentation/broadcast";

const { posts, loading, error, refresh } = useBroadcastHistory();

const OUTCOME_META = {
  published: { label: "publicado", icon: "lucide:check-circle-2", class: "text-emerald-600" },
  partial: { label: "parcial", icon: "lucide:alert-circle", class: "text-amber-600" },
  failed: { label: "falhou", icon: "lucide:x-circle", class: "text-destructive" },
  pending: { label: "na fila", icon: "lucide:clock", class: "text-muted-foreground" },
} as const;

const TONE_CLASS = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  fail: "bg-destructive/10 text-destructive",
  pending: "bg-muted text-muted-foreground",
} as const;

useHead({ title: "Histórico · Broadcast" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-xl font-bold">Histórico</h1>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted"
        @click="refresh()"
      >
        <Icon name="lucide:refresh-cw" class="size-3.5" />
        Atualizar
      </button>
    </div>

    <div
      v-if="error"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">Não conseguimos carregar o histórico.</p>
      <button type="button" class="mt-1 underline underline-offset-2" @click="refresh()">
        Tentar de novo
      </button>
    </div>

    <div v-else-if="loading && posts.length === 0" class="space-y-3" aria-busy="true">
      <div v-for="n in 3" :key="n" class="h-24 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <div
      v-else-if="posts.length === 0"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon name="lucide:megaphone-off" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-2 font-semibold">Nada publicado ainda</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Os posts aprovados aparecem aqui com o resultado de cada plataforma.
      </p>
    </div>

    <ul v-else class="space-y-3">
      <li
        v-for="post in posts"
        :key="post.pk"
        class="rounded-xl border border-border bg-card p-4"
      >
        <div class="flex items-start gap-3">
          <img
            v-if="post.image_url"
            :src="post.image_url"
            alt=""
            class="size-14 shrink-0 rounded-md border border-border object-cover"
          >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <Icon
                :name="OUTCOME_META[postOutcome(post.platform_results)].icon"
                class="size-4"
                :class="OUTCOME_META[postOutcome(post.platform_results)].class"
              />
              <span
                class="text-sm font-semibold"
                :class="OUTCOME_META[postOutcome(post.platform_results)].class"
              >
                {{ OUTCOME_META[postOutcome(post.platform_results)].label }}
              </span>
              <span class="text-xs text-muted-foreground">
                {{ shortDateTime(post.published_at || post.created_at) }}
              </span>
              <span v-if="post.rule_name" class="text-xs text-muted-foreground">
                · {{ post.rule_name }}
              </span>
            </div>

            <p class="mt-1.5 whitespace-pre-line text-sm">{{ post.body }}</p>

            <p class="mt-1 text-xs text-muted-foreground">
              {{ audienceSummary(post.audience) }}
              <template v-if="post.approved_by"> · aprovado por {{ post.approved_by }}</template>
            </p>

            <!-- Resultado por plataforma -->
            <ul class="mt-2 flex flex-wrap gap-1.5">
              <li
                v-for="result in post.platform_results"
                :key="result.platform"
                class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs"
                :class="TONE_CLASS[resultTone(result.status)]"
              >
                <span class="font-medium">{{ result.label }}</span>
                <span>{{ resultLabel(result.status) }}</span>
                <a
                  v-if="result.url"
                  :href="result.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="underline underline-offset-2"
                >
                  ver
                </a>
              </li>
            </ul>

            <!-- O PORQUÊ, não só o "deu ruim": falha traz o erro, pendência manual
                 traz o motivo (ex.: sem credencial configurada) e o WhatsApp traz
                 quantos saíram de fato. -->
            <p
              v-for="result in post.platform_results.filter((r) => r.detail)"
              :key="`detail-${result.platform}`"
              class="mt-1 text-xs"
              :class="resultTone(result.status) === 'fail' ? 'text-destructive' : 'text-muted-foreground'"
            >
              {{ result.label }}: {{ result.detail }}
            </p>
          </div>
        </div>
      </li>
    </ul>
  </main>
</template>
