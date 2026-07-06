<script setup lang="ts">
// Login front-door (Opção C, Camada 1) — NO PRÓPRIO app, sem bounce pro Django admin.
// Um formulário: usuário + senha → POST /operator/login/ (reusa a auth do Django,
// grava o cookie .<zona> que vale em todos os apps de operador) → recarrega já dentro.
// Uma tela, um submit. (Antes: pular pro admin, logar, voltar, "Já entrei" — um inferno.)
const username = ref("");
const password = ref("");
const pending = ref(false);
const error = ref("");

async function submit() {
  if (pending.value) return;
  error.value = "";
  pending.value = true;
  try {
    await $fetch("/api/v1/backstage/operator/login/", {
      method: "POST",
      body: { username: username.value.trim(), password: password.value },
    });
    // A sessão é do lado do servidor; recarregar refaz o fetch já autenticado.
    if (import.meta.client) window.location.reload();
  } catch (err) {
    error.value = httpErrorMessage(err, "Não foi possível entrar. Confira usuário e senha.");
    pending.value = false;
  }
}
</script>

<template>
  <div class="fixed inset-0 z-[100] grid place-items-center bg-background/95 p-4 backdrop-blur-sm">
    <form
      class="w-full max-w-sm rounded-xl border bg-card p-6 shadow-lg"
      @submit.prevent="submit"
    >
      <div class="mx-auto mb-3 grid size-12 place-items-center rounded-full border bg-muted">
        <Icon name="lucide:log-in" class="size-6 text-muted-foreground" />
      </div>
      <h2 class="text-center text-lg font-bold">Entre para operar</h2>
      <p class="mt-1 text-center text-sm text-muted-foreground">
        Acesse com sua conta autorizada.
      </p>

      <div class="mt-4 space-y-2.5">
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          autocorrect="off"
          placeholder="Usuário"
          aria-label="Usuário"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        >
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="Senha"
          aria-label="Senha"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        >
      </div>

      <p v-if="error" class="mt-2 text-sm text-destructive" role="alert">{{ error }}</p>

      <button
        type="submit"
        :disabled="pending || !username.trim() || !password"
        class="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md border border-transparent bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon :name="pending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-4" />
        {{ pending ? "Entrando…" : "Entrar" }}
      </button>
    </form>
  </div>
</template>
