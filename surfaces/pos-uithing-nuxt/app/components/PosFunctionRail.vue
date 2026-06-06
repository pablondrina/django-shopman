<script setup lang="ts">
// Function rail (Arc 5 · shell spine) — the persistent vertical navigation of
// the POS, Shopify-style. Slim icon-only strip (width tuned to the context-bar
// height) holding the operational functions: go to the Tab Board, open the cash
// drawer, lock the terminal, check terminal health, switch theme, refresh. Each
// icon carries a tooltip (mouse) plus aria-label/title (a11y). It renders status
// the read-side hands it and emits intent; it owns no state.
import type { POSProjection, POSShiftSummaryProjection } from "~/types/pos";

defineProps<{
  pos: POSProjection;
  shift: POSShiftSummaryProjection | null;
  hasOpenCashSession: boolean;
  operatorName: string;
  colorModeValue: string;
  pending: boolean;
  /** which work-area screen is showing, to light up the matching rail item. */
  view: "board" | "sale" | "checkout";
}>();

const emit = defineEmits<{
  board: [];
  cash: [];
  lock: [];
  refresh: [];
  toggleTheme: [];
}>();
</script>

<template>
  <aside
    class="flex w-14 shrink-0 flex-col items-center gap-0.5 self-start bg-primary py-2 text-primary-foreground md:h-full md:self-auto"
    aria-label="Funções do caixa"
  >
    <!-- brand glyph -->
    <UiTooltip>
      <UiTooltipTrigger as-child>
        <span class="mb-1 grid size-10 cursor-default place-items-center rounded-xl bg-primary-foreground/15" aria-label="Ponto de venda">
          <Icon name="lucide:store" class="size-5" />
        </span>
      </UiTooltipTrigger>
      <UiTooltipContent side="right">Ponto de venda</UiTooltipContent>
    </UiTooltip>

    <!-- primary navigation -->
    <UiTooltip>
      <UiTooltipTrigger as-child>
        <button
          type="button"
          class="grid size-10 place-items-center rounded-xl transition hover:bg-primary-foreground/10"
          :class="view === 'board' ? 'bg-primary-foreground/15 text-primary-foreground' : 'text-primary-foreground/80 hover:text-primary-foreground'"
          aria-label="Comandas"
          :aria-current="view === 'board' ? 'page' : undefined"
          @click="emit('board')"
        >
          <Icon name="lucide:layout-grid" class="size-5" />
        </button>
      </UiTooltipTrigger>
      <UiTooltipContent side="right">Comandas</UiTooltipContent>
    </UiTooltip>

    <UiTooltip>
      <UiTooltipTrigger as-child>
        <button
          type="button"
          class="grid size-10 place-items-center rounded-xl text-primary-foreground/80 transition hover:bg-primary-foreground/10 hover:text-primary-foreground"
          aria-label="Caixa"
          @click="emit('cash')"
        >
          <span class="grid size-7 place-items-center rounded-lg" :class="hasOpenCashSession ? '' : 'ring-2 ring-primary-foreground/45'">
            <Icon name="lucide:wallet" class="size-5" />
          </span>
        </button>
      </UiTooltipTrigger>
      <UiTooltipContent side="right">{{ hasOpenCashSession ? "Caixa aberto" : "Abrir caixa" }}</UiTooltipContent>
    </UiTooltip>

    <!-- utility cluster pinned to the bottom -->
    <div class="mt-auto flex w-full flex-col items-center gap-0.5">
      <PosTerminalHealth
        v-if="pos"
        compact
        :terminal-label="pos.terminal_label"
        :health-status="pos.terminal_health_status"
        :components="pos.terminal_components"
        :fiscal-status="pos.fiscal_status"
        :fiscal-label="pos.fiscal_label"
        :fiscal-message="pos.fiscal_message"
      />

      <ClientOnly>
        <UiTooltip>
          <UiTooltipTrigger as-child>
            <button
              type="button"
              class="grid size-10 place-items-center rounded-xl text-primary-foreground/80 transition hover:bg-primary-foreground/10 hover:text-primary-foreground"
              :aria-label="colorModeValue === 'dark' ? 'Tema claro' : 'Tema escuro'"
              @click="emit('toggleTheme')"
            >
              <Icon :name="colorModeValue === 'dark' ? 'lucide:sun' : 'lucide:moon'" class="size-5" />
            </button>
          </UiTooltipTrigger>
          <UiTooltipContent side="right">{{ colorModeValue === "dark" ? "Tema claro" : "Tema escuro" }}</UiTooltipContent>
        </UiTooltip>
        <template #fallback>
          <span class="grid size-10 place-items-center rounded-xl text-primary-foreground/80">
            <Icon name="lucide:sun-moon" class="size-5" />
          </span>
        </template>
      </ClientOnly>

      <UiTooltip>
        <UiTooltipTrigger as-child>
          <button
            type="button"
            class="grid size-10 place-items-center rounded-xl text-primary-foreground/80 transition hover:bg-primary-foreground/10 hover:text-primary-foreground disabled:opacity-50"
            aria-label="Atualizar"
            :disabled="pending"
            @click="emit('refresh')"
          >
            <Icon name="lucide:refresh-cw" class="size-5" :class="pending ? 'animate-spin' : ''" />
          </button>
        </UiTooltipTrigger>
        <UiTooltipContent side="right">Atualizar</UiTooltipContent>
      </UiTooltip>

      <UiTooltip>
        <UiTooltipTrigger as-child>
          <button
            type="button"
            class="grid size-10 place-items-center rounded-xl text-primary-foreground/80 transition hover:bg-primary-foreground/10 hover:text-primary-foreground"
            aria-label="Travar caixa"
            @click="emit('lock')"
          >
            <span class="grid size-7 place-items-center rounded-full bg-primary-foreground/20">
              <Icon name="lucide:lock" class="size-4" />
            </span>
          </button>
        </UiTooltipTrigger>
        <UiTooltipContent side="right">{{ operatorName ? `Travar · ${operatorName}` : "Travar caixa" }}</UiTooltipContent>
      </UiTooltip>
    </div>
  </aside>
</template>
