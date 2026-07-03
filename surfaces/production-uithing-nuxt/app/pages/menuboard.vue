<script setup lang="ts">
// MENUBOARD — demo da visão do CROSS-CHANNEL-CATALOG-HUB no estilo Solari:
// o cardápio real (seções + preços do storefront) num painel de palhetas
// para a TV da loja. Cada PÁGINA é uma seção do cardápio (o título gira em
// palhetas na virada — a tempestade de clacs); itens esgotados dizem
// ESGOTADO em âmbar no lugar do preço. Kiosk puro, mesmo esqueleto do
// FORNADAS. Quando o menuboard virar produto, este demo converge para o
// plano do catalog hub (coleções dedicadas + SSE).
const sound = useFlapClack();

interface MenuItem {
  sku: string;
  name: string;
  price_display: string;
  availability: string;
}
interface MenuSection {
  label: string;
  items: MenuItem[];
}
interface MenuResponse {
  catalog: {
    sections: { label?: string | null; category?: { name?: string } | null; items: MenuItem[] }[];
  };
}

const { data, pending, error } = useFetch<MenuResponse>("/api/v1/storefront/menu/", {
  key: "menuboard",
  server: true,
});

const sections = computed<MenuSection[]>(() =>
  (data.value?.catalog.sections ?? [])
    .map((section) => ({
      label: (section.label || section.category?.name || "Cardápio").toString(),
      items: (section.items ?? []).filter((item) => item.name && item.price_display),
    }))
    .filter((section) => section.items.length > 0),
);

// ── Páginas: uma seção por página (seções grandes quebram em partes) ────────
const ITEMS_PER_PAGE = 9;
interface MenuPage {
  label: string;
  items: MenuItem[];
}
const pages = computed<MenuPage[]>(() => {
  const out: MenuPage[] = [];
  for (const section of sections.value) {
    for (let start = 0; start < section.items.length; start += ITEMS_PER_PAGE) {
      const part = Math.floor(start / ITEMS_PER_PAGE);
      out.push({
        label: part > 0 ? `${section.label} ${part + 1}` : section.label,
        items: section.items.slice(start, start + ITEMS_PER_PAGE),
      });
    }
  }
  return out;
});

const page = ref(0);
let rotateTimer: ReturnType<typeof setInterval> | null = null;
const current = computed(() => pages.value[Math.min(page.value, Math.max(0, pages.value.length - 1))] ?? null);
watch(pages, (list) => {
  if (page.value >= list.length) page.value = 0;
});

// ── Relógio ─────────────────────────────────────────────────────────────────
const clock = ref("--:--");
let clockTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  sound.unlock();
  const tick = () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  };
  tick();
  clockTimer = setInterval(tick, 1000);
  rotateTimer = setInterval(() => {
    if (pages.value.length > 1) page.value = (page.value + 1) % pages.value.length;
  }, 10_000);
});
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (rotateTimer) clearInterval(rotateTimer);
});

// ── Tela cheia ──────────────────────────────────────────────────────────────
const isFullscreen = ref(false);
function toggleFullscreen() {
  sound.unlock();
  if (document.fullscreenElement) void document.exitFullscreen();
  else void document.documentElement.requestFullscreen?.();
}
function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement;
}
onMounted(() => document.addEventListener("fullscreenchange", onFullscreenChange));
onUnmounted(() => document.removeEventListener("fullscreenchange", onFullscreenChange));

const NAME_CHARS = 24;
const PRICE_CHARS = 9; // "R$ 123,90" / "ESGOTADO"
</script>

<template>
  <main class="board flex min-h-screen flex-col">
    <header class="flex flex-col gap-2 px-4 pb-2 pt-4 md:px-8">
      <div class="board-labels flex flex-wrap items-center gap-x-3 gap-y-2">
        <span>Nelson Boulangerie · Cardápio</span>
        <div class="ml-auto flex items-center gap-2.5">
          <button
            type="button"
            class="board-key"
            :aria-label="sound.enabled.value ? 'Silenciar palhetas' : 'Ativar som das palhetas'"
            @click="sound.toggle()"
          >
            <Icon :name="sound.enabled.value ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
          </button>
          <button
            type="button"
            class="board-key"
            :aria-label="isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'"
            @click="toggleFullscreen()"
          >
            <Icon :name="isFullscreen ? 'lucide:minimize' : 'lucide:maximize'" class="size-4" />
          </button>
        </div>
      </div>

      <div class="flex items-baseline justify-between gap-6">
        <h1 class="board-title min-w-0">
          <SplitFlap :value="current?.label ?? 'Cardápio'" :chars="16" class="board-display" />
        </h1>
        <ClientOnly>
          <SplitFlap :value="clock" :chars="5" class="board-display" />
        </ClientOnly>
      </div>
    </header>

    <section class="flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-4 pt-4 md:px-8">
      <p v-if="pending && !pages.length" class="board-labels py-8">Carregando…</p>
      <p v-else-if="error" class="board-labels py-8">Sinal perdido — reconectando…</p>
      <div v-else-if="!pages.length" class="board-labels grid place-items-center gap-2 py-24 text-center">
        <Icon name="lucide:utensils" class="size-9" />
        <p>Cardápio vazio.</p>
      </div>

      <template v-else>
        <TransitionGroup tag="div" name="board-row" class="relative flex min-h-0 flex-1 flex-col content-start gap-1.5 overflow-hidden">
          <article v-for="item in current?.items ?? []" :key="item.sku" class="board-row" :aria-label="`${item.name}: ${item.availability === 'available' ? item.price_display : 'esgotado'}`">
            <SplitFlap :value="item.name" :chars="NAME_CHARS" class="board-flap min-w-0" />
            <SplitFlap
              :value="item.availability === 'available' ? item.price_display : 'ESGOTADO'"
              :chars="PRICE_CHARS"
              align="right"
              class="board-flap"
              :class="item.availability === 'available' ? '' : 'tone-amber'"
            />
          </article>
        </TransitionGroup>

        <div v-if="pages.length > 1" class="flex shrink-0 items-center justify-center gap-2.5 pt-3" role="group" aria-label="Seções do cardápio">
          <button
            v-for="(entry, index) in pages"
            :key="entry.label"
            type="button"
            class="board-pagedot"
            :class="{ 'board-pagedot--active': page === index }"
            :aria-label="entry.label"
            :aria-pressed="page === index"
            @click="sound.unlock(); page = index"
          />
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
/* Mesma pele do FORNADAS (consolidar num tema compartilhado quando o
   menuboard virar produto — hoje é demo da visão). */
.board {
  --board-bg: #0b0d10;
  --board-panel: #121417;
  --board-line: #23262b;
  --board-text: #ece9df;
  --board-dim: #82868d;
  --board-amber: #ffb02e;

  --scale-display: clamp(1.9rem, 4vw, 2.6rem);
  --scale-row: clamp(1.05rem, 2vw, 1.5rem);

  background:
    radial-gradient(120% 90% at 50% 0%, #14171b 0%, var(--board-bg) 55%),
    var(--board-bg);
  color: var(--board-text);
  font-family: Oswald, "Arial Narrow", "Helvetica Neue", sans-serif;
  letter-spacing: 0.02em;
}

.board-title {
  line-height: 1;
}
.board-display {
  font-size: var(--scale-display);
  font-weight: 600;
}
.board-flap {
  font-size: var(--scale-row);
  font-weight: 500;
}

.board-labels {
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--board-dim);
}

.board-key {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.375rem;
  border: 1px solid var(--board-line);
  background: var(--board-panel);
  color: var(--board-dim);
  transition: color 150ms, border-color 150ms;
}
.board-key:hover {
  color: var(--board-text);
  border-color: #3a3e45;
}

.board-pagedot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 9999px;
  background: var(--board-line);
  transition: background 200ms, transform 200ms;
}
.board-pagedot--active {
  background: var(--board-text);
  transform: scale(1.25);
}

.board-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.25rem;
  align-items: center;
  border: 1px solid var(--board-line);
  border-radius: 0.5rem;
  background: linear-gradient(180deg, #14171b 0%, var(--board-panel) 100%);
  padding: 0.7rem 1rem;
}

.tone-amber :deep(.flap-cell) {
  color: var(--board-amber);
}

.board-row-enter-active,
.board-row-leave-active {
  transition: opacity 400ms ease, transform 400ms ease;
}
.board-row-enter-from {
  opacity: 0;
  transform: translateY(-0.5rem);
}
.board-row-leave-to {
  opacity: 0;
  transform: translateY(0.5rem);
}
.board-row-leave-active {
  position: absolute;
  width: 100%;
}

@media (max-width: 700px) {
  .board {
    --scale-display: 1.35rem;
    --scale-row: 0.92rem;
  }
  .board-row {
    gap: 0.75rem;
  }
}
</style>
