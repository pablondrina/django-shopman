<script setup lang="ts">
// Order detail — the operator's full view of one order: items, timeline, internal
// notes, fiscal links, and the complete action set. Reads the expanded projection
// via useOrderDetail; actions POST through the django proxy and reconcile.
import {
  lucideIcon,
  splitRef,
  statusTone,
  toneBadge,
} from "~/presentation/board";

const route = useRoute();
const orderRef = computed(() => String(route.params.ref || ""));

const { order, pending, error, busy, confirm, advance, reject, cancel, settleCash, requeueFiscal, saveNotes, addComment } =
  useOrderDetail(orderRef.value);

// timeline comment composer
const comment = ref("");
async function submitComment() {
  if (!comment.value.trim()) return;
  const ok = await addComment(comment.value.trim());
  if (ok) comment.value = "";
}

const code = computed(() => splitRef(orderRef.value));

// notes editor (seeded from the projection; saved explicitly).
const notes = ref("");
watch(order, (o) => { if (o) notes.value = o.internal_notes || ""; }, { immediate: true });
const notesDirty = computed(() => order.value != null && notes.value !== (order.value.internal_notes || ""));

// reject + cancel + settle dialogs (typed input).
const dialog = ref<"" | "reject" | "cancel" | "settle">("");
const reason = ref("");
const amount = ref("");
function openDialog(kind: "reject" | "cancel" | "settle") {
  dialog.value = kind;
  reason.value = "";
  amount.value = "";
}

// Store-configured justification presets (Admin/Unfold). One tap fills the reason
// field; the operator can still edit before sending. The chosen text reaches the
// customer in the cancellation notification.
const presets = computed(() => order.value?.cancellation_presets ?? []);
function applyPreset(text: string) {
  reason.value = text;
}
async function submitDialog() {
  let ok = false;
  if (dialog.value === "reject" && reason.value.trim()) ok = await reject(reason.value.trim());
  else if (dialog.value === "cancel") ok = await cancel(reason.value.trim() || "Cancelado pelo operador");
  else if (dialog.value === "settle") ok = await settleCash(amount.value.trim());
  if (ok) dialog.value = "";
}

const fiscalHref = (link: { href?: string; url?: string }) => link.href || link.url || "#";
</script>

<template>
  <main class="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
    <!-- header -->
    <header class="flex items-center gap-3">
      <NuxtLink to="/" class="grid size-9 shrink-0 place-items-center rounded-md border bg-card text-foreground transition hover:bg-accent" aria-label="Voltar para a fila">
        <Icon name="lucide:arrow-left" class="size-4" />
      </NuxtLink>
      <div class="min-w-0">
        <p class="text-xs text-muted-foreground">{{ code.prefix }}</p>
        <h1 class="truncate text-3xl font-bold leading-tight tabular-nums">{{ code.code }}</h1>
      </div>
      <button type="button" class="ml-auto grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" aria-label="Atualizar" @click="$router.go(0)">
        <Icon name="lucide:refresh-cw" class="size-4" />
      </button>
    </header>

    <p v-if="pending && !order" class="text-sm text-muted-foreground">Carregando…</p>
    <p v-else-if="error || !order" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
      Pedido não encontrado ou falha ao carregar.
    </p>

    <template v-else>
      <!-- summary -->
      <section class="flex flex-col gap-3 rounded-lg border bg-card p-4">
        <div class="flex flex-wrap items-center gap-2">
          <span class="inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium" :class="toneBadge(statusTone(order.status))">
            {{ order.status_label }}
          </span>
          <span class="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            <Icon :name="`lucide:${lucideIcon(order.channel_icon)}`" class="size-4" /> {{ order.channel_ref }}
          </span>
          <span class="ml-auto text-xl font-bold tabular-nums">{{ order.total_display }}</span>
        </div>
        <div class="grid gap-1 text-sm">
          <p class="flex items-center gap-2"><Icon name="lucide:user" class="size-4 text-muted-foreground" /> {{ order.customer_name || "Sem cliente" }}</p>
          <p class="flex items-center gap-2 text-muted-foreground"><Icon name="lucide:package" class="size-4" /> {{ order.fulfillment_label }}</p>
          <p class="flex items-center gap-2 text-muted-foreground"><Icon name="lucide:wallet" class="size-4" /> {{ order.payment_method_label || "—" }} · {{ order.payment_status || "—" }}</p>
        </div>

        <!-- gift -->
        <div v-if="order.is_gift" class="rounded-md bg-muted/60 p-2.5 text-sm">
          <p class="flex items-center gap-1.5 font-medium"><Icon name="lucide:gift" class="size-4" /> Presente para {{ order.gift_recipient_name }}</p>
          <p v-if="order.gift_message" class="mt-1 text-muted-foreground">“{{ order.gift_message }}”</p>
        </div>
      </section>

      <!-- actions -->
      <section class="flex flex-wrap gap-2">
        <button v-if="order.can_settle_delivery_cash !== undefined && order.status !== 'cancelled'" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="advance">
          <Icon name="lucide:arrow-right" class="size-4" /> Avançar
        </button>
        <button type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="confirm">
          <Icon name="lucide:check" class="size-4" /> Confirmar
        </button>
        <button v-if="order.can_settle_delivery_cash" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="openDialog('settle')">
          <Icon name="lucide:banknote" class="size-4" /> Acerto dinheiro
        </button>
        <button v-if="order.fiscal_status === 'failed'" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="requeueFiscal">
          <Icon name="lucide:file-text" class="size-4" /> Reprocessar fiscal
        </button>
        <button type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border border-red-500/40 px-3.5 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-500/10 disabled:opacity-50 dark:text-red-300" @click="openDialog('reject')">
          <Icon name="lucide:x" class="size-4" /> Recusar
        </button>
        <button type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-medium text-muted-foreground transition hover:bg-accent disabled:opacity-50" @click="openDialog('cancel')">
          <Icon name="lucide:ban" class="size-4" /> Cancelar
        </button>
      </section>

      <!-- fiscal -->
      <section v-if="order.fiscal_status_label || order.fiscal_links.length" class="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm">
        <Icon name="lucide:receipt" class="size-4 text-muted-foreground" />
        <span class="text-muted-foreground">{{ order.fiscal_status_label || "Fiscal" }}</span>
        <a v-for="(link, i) in order.fiscal_links" :key="i" :href="fiscalHref(link)" target="_blank" rel="noopener" class="font-medium text-primary underline-offset-2 hover:underline">
          {{ link.label || "Documento" }}
        </a>
      </section>

      <!-- items -->
      <section class="overflow-hidden rounded-lg border bg-card">
        <h2 class="border-b px-4 py-2.5 text-sm font-bold uppercase tracking-wide">Itens</h2>
        <table class="w-full text-sm">
          <tbody>
            <tr v-for="(item, i) in order.items" :key="i" class="border-b last:border-0">
              <td class="px-4 py-2.5 tabular-nums text-muted-foreground">{{ item.qty }}×</td>
              <td class="px-1 py-2.5">{{ item.name }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ item.total_display }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- notes -->
      <section class="flex flex-col gap-2 rounded-lg border bg-card p-4">
        <label class="text-sm font-bold uppercase tracking-wide" for="order-notes">Notas internas</label>
        <textarea
          id="order-notes"
          v-model="notes"
          rows="3"
          placeholder="Anotações do operador (não vão ao cliente)…"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          type="button"
          :disabled="busy || !notesDirty"
          class="self-end rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-40"
          @click="saveNotes(notes)"
        >
          Salvar notas
        </button>
      </section>

      <!-- timeline -->
      <section class="flex flex-col gap-2 rounded-lg border bg-card p-4">
        <h2 class="text-sm font-bold uppercase tracking-wide">Histórico</h2>
        <ol v-if="order.timeline.length" class="flex flex-col gap-2.5">
          <li v-for="(ev, i) in order.timeline" :key="i" class="flex gap-3 text-sm">
            <span class="mt-1 size-2 shrink-0 rounded-full" :class="ev.event_type === 'operator_comment' ? 'bg-primary' : 'bg-muted-foreground/40'" />
            <div class="min-w-0">
              <p class="font-medium">{{ ev.label }}</p>
              <p class="text-xs text-muted-foreground">{{ ev.timestamp_display }}<template v-if="ev.actor"> · {{ ev.actor }}</template><template v-if="ev.detail"> · {{ ev.detail }}</template></p>
            </div>
          </li>
        </ol>

        <!-- comment composer -->
        <div class="flex items-start gap-2 border-t pt-3">
          <textarea
            v-model="comment"
            rows="1"
            placeholder="Comentar no histórico…"
            class="min-h-9 flex-1 resize-y rounded-md border bg-background p-2 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Comentar no histórico"
            @keydown.enter.meta.prevent="submitComment"
          />
          <button
            type="button"
            :disabled="!comment.trim() || busy"
            class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="submitComment"
          >
            <Icon name="lucide:message-square-plus" class="size-4" /> Comentar
          </button>
        </div>
      </section>
    </template>

    <!-- reason/amount dialog -->
    <UiDialog :open="dialog !== ''" @update:open="(v) => { if (!v) dialog = '' }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>
            {{ dialog === "reject" ? "Recusar pedido" : dialog === "cancel" ? "Cancelar pedido" : "Acerto de dinheiro" }}
          </UiDialogTitle>
          <UiDialogDescription>
            {{ dialog === "settle" ? "Valor recebido na entrega. Em branco usa o total." : "Informe o motivo." }}
          </UiDialogDescription>
        </UiDialogHeader>
        <input
          v-if="dialog === 'settle'"
          v-model="amount"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 15,00"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Valor recebido"
        />
        <template v-else>
          <!-- one-tap justification presets (configuráveis no Admin) -->
          <div v-if="presets.length" class="flex flex-wrap gap-1.5">
            <button
              v-for="(preset, i) in presets"
              :key="i"
              type="button"
              :aria-pressed="reason === preset"
              class="rounded-full border px-3 py-1 text-xs font-medium transition hover:bg-accent"
              :class="reason === preset ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
              @click="applyPreset(preset)"
            >
              {{ preset }}
            </button>
          </div>
          <textarea
            v-model="reason"
            rows="3"
            :placeholder="dialog === 'reject' ? 'Motivo da recusa…' : 'Motivo do cancelamento (opcional)…'"
            class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Motivo"
          />
          <p v-if="dialog === 'cancel'" class="text-xs text-muted-foreground">
            O motivo é enviado ao cliente na notificação de cancelamento.
          </p>
        </template>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="dialog = ''">Voltar</button>
          <button
            type="button"
            :disabled="busy || (dialog === 'reject' && !reason.trim())"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="submitDialog"
          >
            Confirmar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
