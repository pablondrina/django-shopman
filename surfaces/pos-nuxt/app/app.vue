<script setup lang="ts">
// POS shell — com a antesala de sessão (`/session`) o PDV ganhou rotas, e o
// app.vue afinou para o chrome comum a todas: aviso de conexão, tela de login
// da estação (sessão de dispositivo), overlay de identificação do operador
// (PIN/crachá) e o auto-lock de kiosk. A venda vive em `pages/index.vue`; a
// sessão de caixa em `pages/session/`. Cada página lê a Projection via
// usePosTerminal (useFetch deduplicado — uma busca só por request).
// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco — o tablet do
// balcão que dormiu não fica com dados velhos. O <OfflineBanner> (auto-import do kit)
// dá o aviso calmo enquanto offline.
const { pos, refresh } = await usePosTerminal();
const { onReconnect } = useConnectivity();
onReconnect(() => refresh());

// Re-gate global de sessão (kit): um 401 no meio do turno (sessão de dispositivo
// expirada) sobe a tela de login em vez de o operador bater numa sessão morta.
const { expired: sessionExpired, reset: resetSession } = useOperatorSession();

// Identidade do operador (PIN/crachá) pelo LOCK COMPARTILHADO do kit — o MESMO
// `useOperatorLock` + `<OperatorLock>` dos outros 4 apps de operador.
const OPERATOR_PERM = "backstage.operate_pos";
const { locked, authenticated, mustChange, lock } = useOperatorLock(OPERATOR_PERM);

// Auto-lock por ociosidade é a única particularidade de kiosk do PDV (os outros apps
// não auto-travam). Vale em qualquer rota (venda ou antesala).
usePosAutoLock({ locked, lock, autoLockSeconds: () => pos.value?.auto_lock_seconds ?? 60 });

// A tela de login sobe SÓ quando não há sessão de dispositivo (device_user ausente)
// ou ela expirou no meio do turno. Estação COM sessão mas sem operador ativo → o
// `<OperatorLock>` (picker de PIN/crachá), nunca a tela de login (C1-01).
const needsLogin = computed(() => !authenticated.value || sessionExpired.value);

// Login NO PRÓPRIO caixa (sem bounce pro Django admin): usuário+senha → sessão de
// dispositivo (cookie .<zona>) → recarrega já operando. Uma tela, um submit.
const loginUser = ref("");
const loginPass = ref("");
const loginPending = ref(false);
const loginError = ref("");
async function submitLogin() {
  if (loginPending.value) return;
  loginError.value = "";
  loginPending.value = true;
  try {
    await $fetch("/api/v1/backstage/operator/login/", {
      method: "POST",
      body: { username: loginUser.value.trim(), password: loginPass.value },
    });
    resetSession(); // sessão re-estabelecida antes do reload
    if (import.meta.client) window.location.reload();
  } catch (error) {
    loginError.value = httpErrorMessage(error, "Não foi possível entrar. Confira usuário e senha.");
    loginPending.value = false;
  }
}
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit): fixed no topo, só aparece offline. -->
    <OfflineBanner />

    <!-- Identificação unificada (PIN ou CRACHÁ): o mesmo overlay dos outros 4 apps. -->
    <OperatorLock
      v-if="authenticated && (locked || mustChange)"
      :perm="OPERATOR_PERM"
    />

    <div v-if="needsLogin" class="grid min-h-dvh place-items-center p-4">
      <form class="grid w-full max-w-sm gap-4 text-center" @submit.prevent="submitLogin">
        <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
          <Icon name="lucide:lock-keyhole" class="size-7 text-muted-foreground" />
        </div>
        <div class="grid gap-1.5">
          <h2 class="text-lg font-semibold">{{ sessionExpired ? "Sua sessão expirou" : "Entre para operar o caixa" }}</h2>
          <p class="text-sm text-muted-foreground">
            {{ sessionExpired ? "Entre de novo para continuar de onde parou." : "Acesse com sua conta autorizada a operar o caixa." }}
          </p>
        </div>
        <div class="grid gap-2.5 text-left">
          <input
            v-model="loginUser"
            type="text"
            autocomplete="username"
            autocapitalize="none"
            autocorrect="off"
            placeholder="Usuário"
            aria-label="Usuário"
            :disabled="loginPending"
            class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <input
            v-model="loginPass"
            type="password"
            autocomplete="current-password"
            placeholder="Senha"
            aria-label="Senha"
            :disabled="loginPending"
            class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <p v-if="loginError" class="text-sm text-destructive" role="alert">{{ loginError }}</p>
        </div>
        <UiButton type="submit" size="lg" :disabled="loginPending || !loginUser.trim() || !loginPass">
          <Icon :name="loginPending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-5" />
          {{ loginPending ? "Entrando…" : "Entrar" }}
        </UiButton>
      </form>
    </div>

    <NuxtPage v-else />

    <UiSonner />
  </div>
</template>
