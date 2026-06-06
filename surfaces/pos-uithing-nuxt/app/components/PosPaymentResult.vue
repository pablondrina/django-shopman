<script setup lang="ts">
// Payment proof (spec §2.4 + PCI SAQ A): renders the gateway's digital payment
// data returned by close_sale — the PIX QR + copia-e-cola, or the card checkout
// link. The screen ONLY DISPLAYS this; it never captures card data. The webhook
// is the authoritative confirmation, so the copy is "aguarde confirmação".
import { toast } from "vue-sonner";
import type { PaymentProofView } from "~/presentation/payment";

const props = defineProps<{ proof: PaymentProofView }>();

const TONE_CLASS: Record<PaymentProofView["tone"], string> = {
  info: "border-sky-500/30 bg-sky-500/10 text-sky-800",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-800",
  success: "border-green-500/30 bg-green-500/10 text-green-800",
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
  <div class="grid gap-3 rounded-lg border p-3" :class="TONE_CLASS[proof.tone]">
    <div class="flex items-center gap-2">
      <Icon :name="proof.icon" class="size-5" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold">{{ proof.isPix ? "Pagamento PIX" : "Pagamento por cartão" }} · {{ proof.amountDisplay }}</p>
        <p v-if="proof.message" class="text-xs opacity-90">{{ proof.message }}</p>
      </div>
    </div>

    <!-- PIX: QR + copia-e-cola -->
    <template v-if="proof.isPix && proof.hasProof">
      <img
        v-if="proof.qrCodeSrc"
        :src="proof.qrCodeSrc"
        alt="QR Code PIX"
        class="mx-auto size-44 rounded-lg border bg-white p-2"
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
