<script setup lang="ts">
// Central de Apps — o launcher pós-login. Lê a projection do hub (tiles já filtrados
// por permissão) e a apresenta como uma grade de ícones fortes. Sem CRUD: cada tile
// abre a superfície dedicada (ou deep-linka pro Unfold, no caso da Loja). Herda do kit
// o OfflineBanner, o re-gate de 401 (useOperatorSession) e httpErrorMessage.
import { hubGreeting, hubIsEmpty, tileIcon, tileTarget } from "~/presentation/hub";

const apiPath = useHubApiPath();

// Login no próprio hub (sessão de dispositivo cross-subdomínio `.boulangerie`): um submit
// autentica e recarrega já na central. Reusa o endpoint de login do operador.
const loginUser = ref("");
const loginPass = ref("");
const loginPending = ref(false);
const loginError = ref("");
async function submitLogin() {
  if (loginPending.value) return;
  loginError.value = "";
  loginPending.value = true;
  try {
    await $fetch(apiPath("/api/v1/backstage/operator/login/"), {
      method: "POST",
      body: { username: loginUser.value.trim(), password: loginPass.value },
    });
    resetSession();
    if (import.meta.client) window.location.reload();
  } catch (error) {
    loginError.value = httpErrorMessage(error, "Não foi possível entrar. Confira usuário e senha.");
    loginPending.value = false;
  }
}

const { tiles, operatorName, error, refresh } = await useOperatorHub();

// Resiliência de rede (kit): reconciliação ao reconectar/reganhar foco.
const { onReconnect } = useConnectivity();
onReconnect(() => refresh());

// Re-gate de sessão (kit): 401 (sessão expirada) → volta pro login.
const { expired: sessionExpired, reset: resetSession } = useOperatorSession();
const needsLogin = computed(() => Boolean(error.value) || sessionExpired.value);
const isEmpty = computed(() => hubIsEmpty(tiles.value));
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <OfflineBanner />

    <!-- Gate de login (sessão ausente/expirada) -->
    <div v-if="needsLogin" class="grid min-h-dvh place-items-center p-4">
      <form class="grid w-full max-w-sm gap-4 text-center" @submit.prevent="submitLogin">
        <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
          <Icon name="lucide:layout-grid" class="size-7 text-muted-foreground" />
        </div>
        <div class="grid gap-1.5">
          <h1 class="text-lg font-semibold">
            {{ sessionExpired ? "Sua sessão expirou" : "Central de Apps" }}
          </h1>
          <p class="text-sm text-muted-foreground">
            {{ sessionExpired ? "Entre de novo para continuar." : "Acesse com sua conta de operador." }}
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
            class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <input
            v-model="loginPass"
            type="password"
            autocomplete="current-password"
            placeholder="Senha"
            aria-label="Senha"
            :disabled="loginPending"
            class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          >
          <p v-if="loginError" class="text-sm text-destructive" role="alert">{{ loginError }}</p>
        </div>
        <button
          type="submit"
          :disabled="loginPending || !loginUser.trim() || !loginPass"
          class="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        >
          <Icon :name="loginPending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-5" />
          {{ loginPending ? "Entrando…" : "Entrar" }}
        </button>
      </form>
    </div>

    <!-- Launcher -->
    <template v-else>
      <div class="flex min-h-dvh">
        <!-- Rail canônico (kit). A Central é o launcher: sem botão "Central" (é a casa) e
             sem travar-operador. Só identidade + tema — a mesma espinha das outras. -->
        <div class="sticky top-0 flex h-dvh shrink-0">
          <OperatorRail app-icon="layout-grid" app-label="Central" />
        </div>

        <div class="flex min-w-0 flex-1 flex-col">
          <!-- Cabeçalho: controle do rail + a saudação (identidade da Central). -->
          <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-3">
            <RailToggle />
            <div class="min-w-0">
              <h1 class="truncate text-base font-semibold leading-tight">{{ hubGreeting(operatorName) }}</h1>
              <p class="text-xs text-muted-foreground">Central de Apps</p>
            </div>
          </header>

          <section class="mx-auto w-full max-w-4xl p-4">
        <div v-if="isEmpty" class="grid place-items-center gap-3 rounded-md border border-dashed p-10 text-center">
          <Icon name="lucide:inbox" class="size-8 text-muted-foreground" />
          <div class="grid gap-1">
            <p class="text-base font-semibold">Nenhum app liberado</p>
            <p class="text-sm text-muted-foreground">
              Sua conta ainda não tem acesso a nenhuma superfície. Fale com o gerente.
            </p>
          </div>
        </div>

        <ul v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <li v-for="tile in tiles" :key="tile.ref">
            <a
              :href="tile.url"
              :target="tileTarget(tile)"
              class="flex min-h-28 flex-col gap-2 rounded-md border border-border bg-card p-4 transition hover:border-primary/40 hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span class="grid size-11 place-items-center rounded-md bg-primary/10 text-primary">
                <Icon :name="tileIcon(tile.icon)" class="size-6" />
              </span>
              <span class="mt-auto">
                <span class="block text-sm font-semibold leading-tight">{{ tile.label }}</span>
                <span class="block text-xs text-muted-foreground">{{ tile.description }}</span>
              </span>
            </a>
          </li>
          </ul>
          </section>
        </div>
      </div>
    </template>
  </main>
</template>
