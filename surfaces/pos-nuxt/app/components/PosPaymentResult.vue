<script setup lang="ts">
// Payment proof (spec §2.4 + PCI SAQ A): renders the gateway's digital payment
// data returned by close_sale — the PIX QR + copia-e-cola, or the card checkout
// link. The screen ONLY DISPLAYS this; it never captures card data. The webhook
// is the authoritative confirmation, so the copy is "aguarde confirmação".
import { toast } from "vue-sonner";
import type { PaymentProofView } from "~/presentation/payment";

// `status` = estado do polling PIX vindo do composable: 'polling' (aguardando),
// 'paid' (confirmado), 'expired' (desistiu — terminal/timeout). Cartão/dinheiro
// não pollam → 'idle'.
const props = defineProps<{ proof: PaymentProofView; status?: "idle" | "polling" | "paid" | "expired" }>();

const TONE_CLASS: Record<PaymentProofView["tone"], string> = {
  info: "border-info/30 bg-info/10 text-info",
  warning: "border-warning/30 bg-warning/10 text-amber-800",
  success: "border-success/30 bg-success/10 text-success",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  neutral: "border bg-muted/40",
};

async function copyCode() {
  if (!props.proof.copyPaste) return;
  try {
    await navigator.clipboard.writeText(props.proof.copyPaste);
    toast.success("Código PIX copiado");
  } catch {
    toast.error("Não foi possível copiar. Selecione e copie manualmente.");
  }
}
</script>

<template>
  <!-- PIX confirmado: o polling detectou o pagamento — troca a tela por "Pago". -->
  <div
    v-if="proof.isPix && status === 'paid'"
    class="grid gap-1 rounded-md border border-success/40 bg-success/10 p-3 text-success dark:text-lime-300"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-center gap-2">
      <Icon name="lucide:circle-check-big" class="size-5" />
      <p class="text-sm font-semibold">Pagamento PIX confirmado · {{ proof.amountDisplay }}</p>
    </div>
  </div>

  <div v-else class="grid gap-3 rounded-md border p-3" :class="TONE_CLASS[proof.tone]">
    <div class="flex items-center gap-2">
      <Icon :name="proof.icon" class="size-5" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold">{{ proof.isPix ? "Pagamento PIX" : "Pagamento por cartão" }} · {{ proof.amountDisplay }}</p>
        <p v-if="proof.message" class="text-xs opacity-90">{{ proof.message }}</p>
        <!-- Aguardando: gira só ENQUANTO polla. Ao desistir, para de mentir. -->
        <p v-if="proof.isPix && proof.hasProof && status === 'polling'" class="mt-0.5 flex items-center gap-1 text-xs opacity-80">
          <Icon name="lucide:loader-circle" class="size-3 animate-spin" /> Aguardando confirmação do PIX…
        </p>
        <!-- Desistiu (expirado/cancelado): acusa honestamente, sem prometer o que não cumpre. -->
        <p v-else-if="proof.isPix && proof.hasProof && status === 'expired'" class="mt-0.5 flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400">
          <Icon name="lucide:clock-alert" class="size-3.5" /> Não confirmamos o PIX automaticamente. Confira no gestor ou gere um novo pagamento.
        </p>
      </div>
    </div>

    <!-- PIX: QR + copia-e-cola -->
    <template v-if="proof.isPix && proof.hasProof">
      <img
        v-if="proof.qrCodeSrc"
        :src="proof.qrCodeSrc"
        alt="QR Code PIX"
        class="mx-auto size-44 rounded-md border bg-white p-2"
      >
      <div v-if="proof.copyPaste" class="grid gap-1.5">
        <p class="break-all rounded-md border bg-background/70 px-2.5 py-2 font-mono text-xs">{{ proof.copyPaste }}</p>
        <UiButton variant="outline" size="sm" class="gap-2" @click="copyCode">
          <Icon name="lucide:copy" class="size-4" />
          Copiar código PIX
        </UiButton>
      </div>
    </template>

    <!-- Card: hosted checkout link (delegated; no capture here) -->
    <a
      v-else-if="proof.isCard && proof.checkoutUrl"
      :href="proof.checkoutUrl"
      target="_blank"
      rel="noopener"
      class="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
    >
      <Icon name="lucide:external-link" class="size-4" />
      Abrir checkout do cartão
    </a>
  </div>
</template>
