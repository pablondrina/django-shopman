<script setup lang="ts">
// Login front-door (Opção C, Camada 1). Shown when there is no device session at
// all — the operator must log in once at the Django admin (on the operator API
// host, a different subdomain), which sets the .<zona> cookie that works across
// every operator app. After login they land on the Admin home, whose sidebar
// links back to the apps. "Já entrei" reloads to pick up the new session.
const config = useRuntimeConfig();

const loginUrl = computed(() => {
  const base = String(config.public.djangoPublicBaseUrl || "").replace(/\/$/, "");
  return `${base}/admin/login/?next=/admin/`;
});

function reload() {
  if (import.meta.client) window.location.reload();
}
</script>

<template>
  <div class="fixed inset-0 z-[100] grid place-items-center bg-background/95 p-4 backdrop-blur-sm">
    <div class="w-full max-w-sm rounded-xl border bg-card p-6 text-center shadow-lg">
      <div class="mx-auto mb-3 grid size-12 place-items-center rounded-full border bg-muted">
        <Icon name="lucide:log-in" class="size-6 text-muted-foreground" />
      </div>
      <h2 class="text-lg font-bold">Entre para operar</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Faça login com uma conta autorizada e volte para esta tela.
      </p>
      <a
        :href="loginUrl"
        class="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md border border-transparent bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
      >
        <Icon name="lucide:log-in" class="size-4" /> Entrar
      </a>
      <button
        type="button"
        class="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
        @click="reload"
      >
        <Icon name="lucide:refresh-cw" class="size-4" /> Já entrei — recarregar
      </button>
    </div>
  </div>
</template>
